#!/usr/bin/env python3
from collections import Counter
from datetime import datetime, timezone
import json
import requests
import urllib3

from config import BOT_TOKEN, FIREWALL_HOST
from zabbix_ai import (
    get_host_24h_summary,
    get_gpu_summary,
    get_item_last_value,
    get_problems,
    summarize_host_24h_with_ai,
    summarize_traffic_with_ai,
    zget,
)
from fortigate_ai import summarize_fortigate_snapshot, summarize_fortigate_traffic
from chat_registry import list_chats, remove_chat

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SERVER_HOST = "zabbix.kivela.work"
TORAKKA_IFACE = '{92B32988-BAC1-4911-9689-64FD64F7FB3F}'


def _fmt_number(value, suffix: str = "") -> str:
    if value in (None, "", "unknown"):
        return "n/a"
    try:
        num = float(value)
    except Exception:
        return str(value)
    if num >= 1000:
        return f"{num:,.2f}{suffix}"
    if num.is_integer():
        return f"{int(num)}{suffix}"
    return f"{num:.2f}{suffix}"


def _metric_stats(host: str, key: str, hours: int = 24) -> dict:
    items = get_item_last_value(host, key)
    if not items:
        return {"key": key, "found": False}

    item = items[0]
    history = zget("/item_history", {"host_name": host, "item_key": key, "hours": hours, "limit": 200})

    vals = []
    for row in history:
        try:
            vals.append(float(row.get("value")))
        except Exception:
            continue

    result = {
        "key": key,
        "found": True,
        "name": item.get("name", key),
        "units": item.get("units", ""),
        "lastvalue": item.get("lastvalue"),
        "lastclock": item.get("lastclock"),
        "count": len(vals),
    }
    if vals:
        result["latest"] = vals[0]
        result["min"] = min(vals)
        result["max"] = max(vals)
        result["avg"] = sum(vals) / len(vals)
    return result


def _format_metric_line(label: str, metric: dict, include_avg: bool = True) -> str:
    if not metric.get("found"):
        return f"- {label}: n/a ({metric['key']} not found)"

    units = metric.get("units", "")
    latest = _fmt_number(metric.get("latest", metric.get("lastvalue")), units)
    parts = [f"- {label}: now={latest}"]
    if metric.get("count", 0) > 0:
        if include_avg:
            parts.append(f"avg24h={_fmt_number(metric.get('avg'), units)}")
        parts.append(f"low24h={_fmt_number(metric.get('min'), units)}")
        parts.append(f"high24h={_fmt_number(metric.get('max'), units)}")
    return " ".join(parts)


def _format_disk_space(host: str) -> list[str]:
    total = _metric_stats(host, r'vfs.fs.size[C:,total]')
    used = _metric_stats(host, r'vfs.fs.size[C:,used]')
    free = _metric_stats(host, r'vfs.fs.size[C:,free]')
    used_pct = _metric_stats(host, r'vfs.fs.size[C:,pused]')
    free_pct = _metric_stats(host, r'vfs.fs.size[C:,pfree]')

    lines = []
    if total.get("found") and used.get("found") and free.get("found"):
        lines.append(
            "- Disk space C:: "
            f"used={_fmt_number(used.get('lastvalue'), used.get('units', ''))} / "
            f"total={_fmt_number(total.get('lastvalue'), total.get('units', ''))} "
            f"free={_fmt_number(free.get('lastvalue'), free.get('units', ''))}"
        )
    if used_pct.get("found") or free_pct.get("found"):
        lines.append(
            "- Disk percentages: "
            f"used={_fmt_number(used_pct.get('lastvalue'), used_pct.get('units', '%'))} "
            f"free={_fmt_number(free_pct.get('lastvalue'), free_pct.get('units', '%'))}"
        )
    return lines or ["- Disk space C:: n/a"]


def _summarize_windows_traffic(host: str) -> str:
    items = get_item_last_value(host, "windows.traffic.out")
    if not items:
        return "- Outbound connection summary: windows.traffic.out item not found"

    raw = items[0].get("lastvalue", "")
    try:
        payload = json.loads(raw)
    except Exception as e:
        return f"- Outbound connection summary: could not parse windows.traffic.out ({e})"

    rows = payload.get("data", []) or []
    if not rows:
        return "- Outbound connection summary: no recent connection rows"

    proc_counter = Counter()
    ip_counter = Counter()
    port_counter = Counter()
    proc_samples = {}
    for row in rows:
        proc = row.get("process", "unknown")
        rip = row.get("r_ip", "unknown")
        rport = row.get("r_port", "unknown")
        proc_counter[proc] += 1
        ip_counter[rip] += 1
        port_counter[str(rport)] += 1
        proc_samples.setdefault(proc, []).append(f"{rip}:{rport}")

    top_processes = ", ".join(f"{proc}({count})" for proc, count in proc_counter.most_common(5))
    top_dests = ", ".join(f"{ip}({count})" for ip, count in ip_counter.most_common(5))
    top_ports = ", ".join(f"{port}({count})" for port, count in port_counter.most_common(5))
    samples = []
    for proc, count in proc_counter.most_common(3):
        examples = ", ".join(proc_samples.get(proc, [])[:3])
        samples.append(f"{proc}: {examples}")

    return (
        f"- Outbound connection summary: {len(rows)} rows. "
        f"Top processes: {top_processes}. "
        f"Top destinations: {top_dests}. "
        f"Top remote ports: {top_ports}. "
        f"Examples: {'; '.join(samples)}"
    )


def _torakka_server_section(host: str) -> str:
    data = get_host_24h_summary(host)
    gpu = get_gpu_summary(host, 24)

    host_info = data.get("host", {}) if isinstance(data, dict) else {}
    os_item = get_item_last_value(host, "system.sw.os")
    alerts = get_problems(50)
    host_alerts = [p for p in alerts if host.lower() in json.dumps(p).lower()]

    lines = [
        f"Server summary: {host}",
        f"- Overall status: {'enabled' if str(host_info.get('status')) == '0' else 'disabled'}",
        f"- OS: {os_item[0].get('lastvalue') if os_item else 'n/a'}",
        f"- Current alerts: {len(host_alerts)}",
        _format_metric_line("CPU utilization", _metric_stats(host, "system.cpu.util")),
        _format_metric_line("Memory utilization", _metric_stats(host, "vm.memory.util")),
        _format_metric_line("Page Faults/sec", _metric_stats(host, r'perf_counter_en["\\Memory\\Page Faults/sec"]')),
        "  Page Faults/sec shows how many memory pages fault per second. Hard faults need disk access and can slow the host noticeably.",
        _format_metric_line("Processes", _metric_stats(host, "proc.num[]")),
        _format_metric_line("Disk reads/sec C:", _metric_stats(host, r'perf_counter_en["\\PhysicalDisk(0 C:)\\Disk Reads/sec",60]')),
    ]
    lines.extend(_format_disk_space(host))
    lines.extend([
        _format_metric_line(f"Traffic in {TORAKKA_IFACE}", _metric_stats(host, f'net.if.in["{TORAKKA_IFACE}"]'), include_avg=False),
        _format_metric_line(f"Traffic out {TORAKKA_IFACE}", _metric_stats(host, f'net.if.out["{TORAKKA_IFACE}"]'), include_avg=False),
        _summarize_windows_traffic(host),
        f"- AI host interpretation: {summarize_host_24h_with_ai(host)}",
        f"- AI traffic interpretation: {summarize_traffic_with_ai(host)}",
    ])

    gpu_items = {item.get("key_"): item for item in gpu.get("gpu_items", [])} if isinstance(gpu, dict) else {}
    if gpu_items:
        lines.append("- Nvidia:")
        for key, label in [
            ("gpu.name[0]", "Name"),
            ("gpu.utilization[0]", "Utilization"),
            ("gpu.temperature[0]", "Temperature"),
            ("gpu.power.draw[0]", "Power draw"),
            ("gpu.memory.used[0]", "Memory used"),
            ("gpu.memory.total[0]", "Memory total"),
            ("gpu.fan.speed[0]", "Fan speed"),
        ]:
            item = gpu_items.get(key)
            if item:
                lines.append(f"  - {label}: {item.get('lastvalue')} {item.get('units', '')}".rstrip())
        lines.append("  - Services overall status: infer from active alerts/events until a dedicated service item is added.")
    else:
        lines.append("- Nvidia: no GPU metrics found")

    return "\n".join(lines)


def _zabbix_server_section(host: str) -> str:
    lines = [
        f"Server summary: {host}",
        _format_metric_line("CPU count", _metric_stats(host, "system.cpu.num"), include_avg=False),
        _format_metric_line("Memory total", _metric_stats(host, "vm.memory.size[total]"), include_avg=False),
        _format_metric_line("Logged in users", _metric_stats(host, "system.users.num"), include_avg=False),
    ]

    log_summary = get_item_last_value(host, "log.summary.text")
    if log_summary:
        lines.append(f"- Log summary: {log_summary[0].get('lastvalue', '')[:700]}")
    else:
        lines.append("- Log summary: n/a")

    nginx_keys = [
        "nginx.connections.active",
        "nginx.connections.dropped.rate",
        "nginx.connections.handled.rate",
        "nginx.connections.reading",
        "nginx.connections.writing",
        "nginx.connections.waiting",
        "nginx.requests.total.rate",
        "vhost.urls[zabbix.kivela.work]",
    ]
    lines.append("- Nginx:")
    for key in nginx_keys:
        item = get_item_last_value(host, key)
        if item:
            value = item[0].get("lastvalue")
            lines.append(f"  - {key}: {value}")
    lines.append(_format_metric_line("New log lines today", _metric_stats(host, "log.summary.total_new_lines"), include_avg=False))
    for key in [
        "audit anomaly",
        "connections active",
        "selenium state",
        "system.cpu.util[,nice]",
        "system.cpu.util[,iowait]",
        "system.cpu.util[,idle]",
        "vfs.fs.size[/,free]",
        "zabbix[preprocessing_throughput]",
        "zabbix[preprocessing_queue]",
        "zabbix[process,agent poller,avg,busy]",
    ]:
        item = get_item_last_value(host, key)
        if item:
            lines.append(f"- {key}: {item[0].get('lastvalue')}")

    return "\n".join(lines)


def _firewall_network_section() -> str:
    host = FIREWALL_HOST
    lines = [
        f"Network summary: {host}",
        _format_metric_line("Internet traffic in", _metric_stats(host, "net.if.in[ifHCOutOctets.4]"), include_avg=False),
        _format_metric_line("Internet traffic out", _metric_stats(host, "net.if.out[ifHCOutOctets.4]"), include_avg=False),
        _format_metric_line("Active sessions", _metric_stats(host, "net.ipv4.sessions[fgSysSesCount.0]"), include_avg=False),
        _format_metric_line("Active VPN tunnels", _metric_stats(host, "vpn.tunnel.active[fgVpnTunnelUpCount.0]"), include_avg=False),
        _format_metric_line("CPU usage", _metric_stats(host, "system.cpu.util[fgSysCpuUsage.0]")),
        _format_metric_line("Memory usage", _metric_stats(host, "vm.memory.util[memoryUsedPercentage.0]")),
        _format_metric_line("Critical IPS detections", _metric_stats(host, "ips.detected.crit[fgIpsCritSevDetections.0]"), include_avg=False),
        f"- FortiGate config summary: {summarize_fortigate_snapshot()}",
        f"- FortiGate traffic summary: {summarize_fortigate_traffic()}",
    ]
    return "\n".join(lines)


def build_daily_report(host: str = "TORAKKA") -> str:
    try:
        problems = get_problems(10)
        if problems:
            problems_text = "\n".join(
                [f"- sev={p.get('severity')} {p.get('name')}" for p in problems[:10]]
            )
        else:
            problems_text = "- No current problems"
    except Exception as e:
        problems_text = f"Could not get current problems: {e}"

    try:
        server_summary = "\n\n".join([
            _torakka_server_section(host),
            _zabbix_server_section(SERVER_HOST),
        ])
    except Exception as e:
        server_summary = f"Could not build server summary: {e}"

    try:
        network_summary = _firewall_network_section()
    except Exception as e:
        network_summary = f"Could not build network summary: {e}"

    return (
        f"Daily infrastructure report ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})\n\n"
        "Current problems:\n"
        f"{problems_text}\n\n"
        "Servers summary:\n"
        f"{server_summary}\n\n"
        "Network summary:\n"
        f"{network_summary}"
    )


def send_telegram_message(chat_id: int, text: str) -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunk_size = 3500
    parts = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    for part in parts:
        payload = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": True,
        }
        r = requests.post(url, data=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Telegram send failed for chat_id={chat_id}: {r.status_code} {r.text}")


def send_daily_report_to_all(host: str = "TORAKKA") -> None:
    message = build_daily_report(host)
    chats = list_chats()

    if not chats:
        raise RuntimeError("No registered Telegram chats found. Send a message to the bot first.")

    failed = []
    for chat in chats:
        chat_id = chat["chat_id"]
        try:
            send_telegram_message(chat_id, message)
        except Exception as e:
            failed.append(f"{chat_id}: {e}")
            err = str(e).lower()
            if "forbidden" in err or "chat not found" in err:
                remove_chat(chat_id)

    if failed:
        raise RuntimeError("Some sends failed:\n" + "\n".join(failed))


def main() -> None:
    send_daily_report_to_all("TORAKKA")


if __name__ == "__main__":
    main()
