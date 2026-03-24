#!/usr/bin/env python3
from collections import Counter
from datetime import datetime, timezone
import json
import requests
import urllib3

from config import BOT_TOKEN, FIREWALL_HOST
from zabbix_ai import (
    get_estate_summary,
    get_gpu_summary,
    get_host_24h_summary,
    get_item_last_value,
    get_problems,
    search_hosts,
    zget,
)
from fortigate_ai import summarize_fortigate_snapshot, summarize_fortigate_traffic
from chat_registry import list_chats, remove_chat

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SERVER_HOST = "zabbix.kivela.work"
TORAKKA_IFACE = '{92B32988-BAC1-4911-9689-64FD64F7FB3F}'
SEVERITY_LABELS = {
    "0": "not classified",
    "1": "information",
    "2": "warning",
    "3": "average",
    "4": "high",
    "5": "disaster",
}
SEVERITY_ICONS = {
    "0": "ℹ️",
    "1": "🟡",
    "2": "🟠",
    "3": "🔴",
    "4": "🚨",
    "5": "💥",
}


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


def _title(text: str) -> str:
    return f"==== {text} ===="


def _subtitle(text: str) -> str:
    return f"-- {text} --"


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
    parts = [f"- {label}: now {latest}"]
    if metric.get("count", 0) > 0:
        if include_avg:
            parts.append(f"avg24h {_fmt_number(metric.get('avg'), units)}")
        parts.append(f"low24h {_fmt_number(metric.get('min'), units)}")
        parts.append(f"high24h {_fmt_number(metric.get('max'), units)}")
    return " | ".join(parts)


def _format_disk_space(host: str) -> list[str]:
    total = _metric_stats(host, r'vfs.fs.size[C:,total]')
    used = _metric_stats(host, r'vfs.fs.size[C:,used]')
    free = _metric_stats(host, r'vfs.fs.size[C:,free]')
    used_pct = _metric_stats(host, r'vfs.fs.size[C:,pused]')

    lines = []
    if total.get("found") and used.get("found") and free.get("found"):
        lines.append(
            "- Disk C:: "
            f"used {_fmt_number(used.get('lastvalue'), used.get('units', ''))} / "
            f"total {_fmt_number(total.get('lastvalue'), total.get('units', ''))} | "
            f"free {_fmt_number(free.get('lastvalue'), free.get('units', ''))}"
        )
    if used_pct.get("found"):
        lines.append(f"- Disk C: used {_fmt_number(used_pct.get('lastvalue'), used_pct.get('units', '%'))}")
    return lines or ["- Disk C:: n/a"]


def _summarize_windows_traffic(host: str) -> str:
    items = get_item_last_value(host, "windows.traffic.out")
    if not items:
        return "- Outbound connections: windows.traffic.out item not found"

    raw = items[0].get("lastvalue", "")
    try:
        payload = json.loads(raw)
    except Exception as e:
        return f"- Outbound connections: could not parse windows.traffic.out ({e})"

    rows = payload.get("data", []) or []
    if not rows:
        return "- Outbound connections: no recent connection rows"

    proc_counter = Counter()
    ip_counter = Counter()
    port_counter = Counter()
    for row in rows:
        proc_counter[row.get("process", "unknown")] += 1
        ip_counter[row.get("r_ip", "unknown")] += 1
        port_counter[str(row.get("r_port", "unknown"))] += 1

    top_processes = ", ".join(f"{proc}({count})" for proc, count in proc_counter.most_common(3))
    top_dests = ", ".join(f"{ip}({count})" for ip, count in ip_counter.most_common(3))
    top_ports = ", ".join(f"{port}({count})" for port, count in port_counter.most_common(3))
    return (
        f"- Outbound connections: {len(rows)} rows | "
        f"top processes {top_processes} | "
        f"top destinations {top_dests} | "
        f"top ports {top_ports}"
    )


def _format_problem_summary(problems: list[dict]) -> str:
    if not problems:
        return "✅ No current problems detected."

    active_problems = [p for p in problems if str(p.get("severity")) != "0"]
    if not active_problems:
        return "✅ No actionable alerts."

    problem_counts = Counter(str(p.get("severity")) for p in active_problems)
    summary_bits = []
    for severity in sorted(problem_counts.keys(), key=lambda value: int(value), reverse=True):
        summary_bits.append(
            f"{SEVERITY_ICONS.get(severity, '•')} {SEVERITY_LABELS.get(severity, severity)}={problem_counts[severity]}"
        )

    lines = [" | ".join(summary_bits), "Top active alerts:"]
    for problem in active_problems[:8]:
        sev = str(problem.get("severity"))
        lines.append(f"- {SEVERITY_ICONS.get(sev, '•')} sev={sev} {problem.get('name')}")

    remaining = len(active_problems) - min(len(active_problems), 8)
    if remaining > 0:
        lines.append(f"- …and {remaining} more active alerts")
    return "\n".join(lines)


def _build_search_section(host: str) -> str:
    try:
        matches = search_hosts(host, 5)
    except Exception as e:
        return f"- Host lookup unavailable: {e}"

    if not matches:
        return f"- No host matches returned for search term: {host}"

    lines = []
    for match in matches[:5]:
        status = "enabled" if str(match.get("status")) == "0" else "disabled"
        lines.append(f"- {match.get('host')} ({match.get('name')}) [{status}]")
    return "\n".join(lines)


def _estate_overview_section() -> str:
    summary = get_estate_summary(200)
    problem_list = get_problems(50)
    active_problem_count = sum(1 for p in problem_list if str(p.get("severity")) != "0")
    return "\n".join([
        "- Zabbix host estate:",
        f"  - Total hosts: {summary.get('total_hosts', 'n/a')}",
        f"  - Enabled: {summary.get('enabled_hosts', 'n/a')}",
        f"  - Disabled: {summary.get('disabled_hosts', 'n/a')}",
        f"  - Active problems sampled: {active_problem_count}",
    ])


def _torakka_server_section(host: str) -> str:
    data = get_host_24h_summary(host)
    gpu = get_gpu_summary(host, 24)

    host_info = data.get("host", {}) if isinstance(data, dict) else {}
    os_item = get_item_last_value(host, "system.sw.os")
    alerts = get_problems(50)
    host_alerts = [p for p in alerts if host.lower() in json.dumps(p).lower() and str(p.get("severity")) != "0"]

    lines = [
        _subtitle(f"Primary host: {host}"),
        f"- Status: {'enabled' if str(host_info.get('status')) == '0' else 'disabled'}",
        f"- OS: {os_item[0].get('lastvalue') if os_item else 'n/a'}",
        f"- Active alerts on host: {len(host_alerts)}",
        _format_metric_line("CPU utilization", _metric_stats(host, "system.cpu.util")),
        _format_metric_line("Memory utilization", _metric_stats(host, "vm.memory.util")),
        _format_metric_line("Page Faults/sec", _metric_stats(host, r'perf_counter_en["\\Memory\\Page Faults/sec"]')),
        _format_metric_line("Processes", _metric_stats(host, "proc.num[]")),
        _format_metric_line("Disk reads/sec C:", _metric_stats(host, r'perf_counter_en["\\PhysicalDisk(0 C:)\\Disk Reads/sec",60]')),
    ]
    lines.extend(_format_disk_space(host))
    lines.extend([
        _format_metric_line(f"Traffic in {TORAKKA_IFACE}", _metric_stats(host, f'net.if.in["{TORAKKA_IFACE}"]'), include_avg=False),
        _format_metric_line(f"Traffic out {TORAKKA_IFACE}", _metric_stats(host, f'net.if.out["{TORAKKA_IFACE}"]'), include_avg=False),
        _summarize_windows_traffic(host),
    ])

    gpu_items = {item.get("key_"): item for item in gpu.get("gpu_items", [])} if isinstance(gpu, dict) else {}
    if gpu_items:
        lines.append("- GPU summary:")
        for key, label in [
            ("gpu.name[0]", "Name"),
            ("gpu.utilization[0]", "Utilization"),
            ("gpu.temperature[0]", "Temperature"),
            ("gpu.power.draw[0]", "Power draw"),
        ]:
            item = gpu_items.get(key)
            if item:
                lines.append(f"  - {label}: {item.get('lastvalue')} {item.get('units', '')}".rstrip())
    else:
        lines.append("- GPU summary: no metrics found")

    return "\n".join(lines)


def _zabbix_server_section(host: str) -> str:
    lines = [
        _subtitle(f"Zabbix server: {host}"),
        _format_metric_line("CPU count", _metric_stats(host, "system.cpu.num"), include_avg=False),
        _format_metric_line("Memory total", _metric_stats(host, "vm.memory.size[total]"), include_avg=False),
        _format_metric_line("Logged in users", _metric_stats(host, "system.users.num"), include_avg=False),
    ]

    log_summary = get_item_last_value(host, "log.summary.text")
    lines.append(f"- Log summary: {log_summary[0].get('lastvalue', '')[:220] if log_summary else 'n/a'}")

    for key in [
        "nginx.connections.active",
        "nginx.requests.total.rate",
        "vhost.urls[zabbix.kivela.work]",
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
        _subtitle(f"Firewall & network: {host}"),
        _format_metric_line("Internet traffic in", _metric_stats(host, "net.if.in[ifHCOutOctets.4]"), include_avg=False),
        _format_metric_line("Internet traffic out", _metric_stats(host, "net.if.out[ifHCOutOctets.4]"), include_avg=False),
        _format_metric_line("Active sessions", _metric_stats(host, "net.ipv4.sessions[fgSysSesCount.0]"), include_avg=False),
        _format_metric_line("Active VPN tunnels", _metric_stats(host, "vpn.tunnel.active[fgVpnTunnelUpCount.0]"), include_avg=False),
        _format_metric_line("CPU usage", _metric_stats(host, "system.cpu.util[fgSysCpuUsage.0]")),
        _format_metric_line("Memory usage", _metric_stats(host, "vm.memory.util[memoryUsedPercentage.0]")),
        f"- FortiGate config summary: {summarize_fortigate_snapshot()}",
        f"- FortiGate traffic summary: {summarize_fortigate_traffic()}",
    ]
    return "\n".join(lines)


def build_daily_report(host: str = "TORAKKA") -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    sections = []
    try:
        sections.append((_title("Estate overview"), _estate_overview_section()))
    except Exception as e:
        sections.append((_title("Estate overview"), f"⚠️ Could not build estate overview: {e}"))

    try:
        problems = get_problems(10)
        sections.append((_title("Current problems"), _format_problem_summary(problems)))
    except Exception as e:
        sections.append((_title("Current problems"), f"⚠️ Could not get current problems: {e}"))

    try:
        sections.append((_title("Host search"), _build_search_section(host)))
    except Exception as e:
        sections.append((_title("Host search"), f"⚠️ Host search failed: {e}"))

    try:
        sections.append((_title("Server details"), "\n\n".join([
            _torakka_server_section(host),
            _zabbix_server_section(SERVER_HOST),
        ])))
    except Exception as e:
        sections.append((_title("Server details"), f"⚠️ Could not build server summary: {e}"))

    try:
        sections.append((_title("Network & firewall"), _firewall_network_section()))
    except Exception as e:
        sections.append((_title("Network & firewall"), f"⚠️ Could not build network summary: {e}"))

    body = "\n\n".join(f"{title}\n{content}" for title, content in sections)
    return (
        f"🏁 Daily infrastructure report\n"
        f"Generated: {timestamp}\n"
        f"Primary host: {host}\n"
        f"Data sources: problem.get, host.get/search, item.get, history.get, FortiGate summaries\n\n"
        f"{body}"
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
