import json
from collections import Counter
from typing import Any, Dict, List, Optional

import requests

from config import (
    ZABBIX_API_URL,
    OLLAMA_URL,
    OLLAMA_MODEL,
    TRAFFIC_ITEM_KEY,
    HOST_ALIASES,
)


class ZabbixBridgeError(Exception):
    pass


def normalize_host(text: str) -> str:
    key = text.strip().lower()
    return HOST_ALIASES.get(key, text.strip())


def _safe_json_response(r: requests.Response, url: str) -> Any:
    text = r.text.strip()

    if not text:
        raise ZabbixBridgeError(f"Empty response from {url}")

    content_type = (r.headers.get("Content-Type") or "").lower()
    if "application/json" in content_type or text.startswith("{") or text.startswith("["):
        try:
            return r.json()
        except Exception as e:
            raise ZabbixBridgeError(f"Invalid JSON from {url}: {text[:300]} ({e})")

    raise ZabbixBridgeError(f"Non-JSON response from {url}: {text[:300]}")


def zget(path: str, params: Optional[dict] = None) -> Any:
    url = f"{ZABBIX_API_URL}{path}"
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return _safe_json_response(r, r.url)
    except requests.exceptions.HTTPError as e:
        body = e.response.text[:500] if e.response is not None else str(e)
        raise ZabbixBridgeError(f"HTTP error from Zabbix bridge: {body}")
    except requests.exceptions.RequestException as e:
        raise ZabbixBridgeError(f"Request to Zabbix bridge failed: {e}")


def chat_with_ai(user_text: str) -> str:
    system_prompt = (
        "You are a concise helpful 404donkey assistant inside a Telegram bot. "
        "You are slightly bored but still useful, and you make occasional dry jokes. "
        "For casual requests like stories, jokes, explanations, and general chat, "
        "reply clearly and briefly unless the user asks for more."
    )
    return ollama_chat(system_prompt, user_text)


def ollama_chat(system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("message", {}).get("content", "").strip()


def get_problems(limit: int = 5):
    return zget("/get_zabbix_problems", {"limit": limit})


def get_summary():
    return zget("/chat_summary")


def get_estate_summary(limit: int = 200):
    return zget("/summarize_hosts", {"limit": limit})


def search_hosts(search_text: str, limit: int = 5):
    return zget("/search_hosts", {"search_text": search_text, "limit": limit})


def get_host_status(host_name: str):
    return zget("/get_host_status", {"host_name": host_name})


def get_item_last_value(host_name: str, item_key: str):
    return zget("/get_item_last_value", {"host_name": host_name, "item_key": item_key})


def get_host_interfaces(host_name: str):
    return zget("/get_host_interfaces", {"host_name": host_name})


def get_recent_events(host_name: str, limit: int = 20):
    return zget("/get_recent_events", {"host_name": host_name, "limit": limit})


def get_host_24h_summary(host_name: str):
    return zget("/host_24h_summary", {"host_name": host_name})


def get_gpu_summary(host_name: str, hours: int = 24):
    return zget("/gpu_summary", {"host_name": host_name, "hours": hours})


def filter_problems_for_host(problems: List[dict], host_name: str) -> List[dict]:
    host_l = host_name.lower()
    out = []
    for p in problems:
        blob = json.dumps(p).lower()
        if host_l in blob:
            out.append(p)
    return out


def build_host_context(host_name: str) -> Dict[str, Any]:
    host_status = get_host_status(host_name)
    interfaces = get_host_interfaces(host_name)
    recent_events = get_recent_events(host_name, 20)
    all_problems = get_problems(50)
    host_problems = filter_problems_for_host(all_problems, host_name)

    return {
        "host_name": host_name,
        "host_status": host_status,
        "interfaces": interfaces,
        "recent_events": recent_events,
        "host_problems": host_problems,
    }


def summarize_host_with_ai(host_name: str) -> str:
    context = build_host_context(host_name)

    system_prompt = (
        "You are a concise infrastructure operations assistant. "
        "Summarize host health, active problems, likely issue pattern, and next checks. "
        "Be specific, operational, and short. "
        "Do not invent facts. "
        "If there are no host-specific problems, say so clearly."
    )

    user_prompt = (
        f"Summarize problems for host: {host_name}\n\n"
        f"Zabbix context:\n{json.dumps(context, indent=2)}\n\n"
        "Return:\n"
        "1) one-line status\n"
        "2) key problems\n"
        "3) likely cause or pattern\n"
        "4) next checks"
    )

    return ollama_chat(system_prompt, user_prompt)


def get_cpu_load_text(host_name: str) -> str:
    host_name = normalize_host(host_name)

    hosts = get_host_status(host_name)
    if not hosts:
        suggestions = search_hosts(host_name, 5)
        if suggestions:
            names = ", ".join(h.get("host", "?") for h in suggestions[:5])
            return f"Host not found: {host_name}. Similar hosts: {names}"
        return f"Host not found: {host_name}"

    candidate_keys = [
        "system.cpu.load[all,avg1]",
        "system.cpu.load[percpu,avg1]",
        "system.cpu.util[,system]",
        "system.cpu.util",
    ]

    for key in candidate_keys:
        try:
            data = get_item_last_value(host_name, key)
            if data:
                item = data[0]
                return (
                    f"{host_name} CPU item: {item.get('name', key)}\n"
                    f"Key: {item.get('key_', key)}\n"
                    f"Last value: {item.get('lastvalue', 'unknown')}\n"
                    f"Last clock: {item.get('lastclock', 'unknown')}"
                )
        except Exception:
            continue

    return f"No CPU item found for {host_name}. Tried keys: {', '.join(candidate_keys)}"


def get_traffic_item(host_name: str):
    data = get_item_last_value(host_name, TRAFFIC_ITEM_KEY)
    if not data:
        return None
    return data[0]


def parse_traffic_json(raw_value: str) -> dict:
    return json.loads(raw_value)


def build_traffic_summary_struct(traffic_obj: dict) -> Dict[str, Any]:
    entries = traffic_obj.get("data", []) or []
    count = traffic_obj.get("count", len(entries))
    timestamp = traffic_obj.get("time", "unknown")

    process_counter = Counter()
    remote_ip_counter = Counter()
    remote_port_counter = Counter()

    internal_connections = 0
    external_connections = 0
    ssh_connections = 0
    https_connections = 0

    for e in entries:
        process = e.get("process", "unknown")
        rip = str(e.get("r_ip", "unknown"))
        rport = e.get("r_port", "unknown")

        process_counter[process] += 1
        remote_ip_counter[rip] += 1
        remote_port_counter[str(rport)] += 1

        if rip.startswith("192.168.") or rip.startswith("10.") or rip.startswith("172.16."):
            internal_connections += 1
        else:
            external_connections += 1

        if str(rport) == "22":
            ssh_connections += 1
        if str(rport) == "443":
            https_connections += 1

    return {
        "time": timestamp,
        "count": count,
        "top_processes": process_counter.most_common(10),
        "top_remote_ips": remote_ip_counter.most_common(10),
        "top_remote_ports": remote_port_counter.most_common(10),
        "internal_connections": internal_connections,
        "external_connections": external_connections,
        "ssh_connections": ssh_connections,
        "https_connections": https_connections,
        "sample_entries": entries[:15],
    }


def summarize_traffic_with_ai(host_name: str) -> str:
    item = get_traffic_item(host_name)
    if not item:
        return f"No traffic item found for {host_name} using key {TRAFFIC_ITEM_KEY}"

    raw_value = item.get("lastvalue", "")
    traffic_obj = parse_traffic_json(raw_value)
    summary_struct = build_traffic_summary_struct(traffic_obj)

    system_prompt = (
        "You are a concise network traffic analyst. "
        "Summarize host outbound traffic in an operational way. "
        "Highlight dominant processes, repeated remote IPs, notable ports, internal vs external patterns, "
        "and anything potentially unusual. "
        "Do not overstate risk. Be short and practical."
    )

    user_prompt = (
        f"Host: {host_name}\n"
        f"Traffic item key: {TRAFFIC_ITEM_KEY}\n\n"
        f"Parsed traffic summary:\n{json.dumps(summary_struct, indent=2)}\n\n"
        "Return:\n"
        "1) one-line traffic status\n"
        "2) dominant processes\n"
        "3) notable remote destinations/ports\n"
        "4) anything unusual or worth checking"
    )

    return ollama_chat(system_prompt, user_prompt)


def summarize_host_24h_with_ai(host_name: str) -> str:
    host_name = normalize_host(host_name)
    data = get_host_24h_summary(host_name)

    if isinstance(data, dict) and data.get("error"):
        return data["error"]

    host = data.get("host", {})
    recent_events = data.get("recent_events", [])
    cpu = data.get("cpu", {})
    memory_items = data.get("memory_items", [])
    disk_items = data.get("disk_items", [])
    network_items = data.get("network_items", [])

    lines = []
    host_status = "enabled" if str(host.get("status")) == "0" else "disabled"
    lines.append(f"Host status: {host.get('host', host_name)} is {host_status}")

    lines.append("CPU:")
    cpu_stats = (cpu or {}).get("stats_24h", {})
    cpu_item = (cpu or {}).get("item", {})
    if cpu_stats and cpu_stats.get("count", 0) > 0:
        lines.append(
            f"- {cpu_item.get('name', 'CPU')}: latest={cpu_stats.get('latest')} "
            f"avg={cpu_stats.get('avg')} min={cpu_stats.get('min')} max={cpu_stats.get('max')}"
        )
    else:
        lines.append("- No CPU history available")

    lines.append("Memory:")
    if memory_items:
        shown = 0
        for item in memory_items[:5]:
            stats = item.get("stats_24h", {})
            if stats.get("count", 0) > 0:
                lines.append(
                    f"- {item.get('name')}: latest={item.get('lastvalue')} {item.get('units', '')} "
                    f"avg={stats.get('avg')} min={stats.get('min')} max={stats.get('max')}"
                )
                shown += 1
        if shown == 0:
            lines.append("- No numeric memory history available")
    else:
        lines.append("- No memory items found")

    lines.append("Disk:")
    if disk_items:
        shown = 0
        for item in disk_items[:5]:
            stats = item.get("stats_24h", {})
            if stats.get("count", 0) > 0:
                lines.append(
                    f"- {item.get('name')}: latest={item.get('lastvalue')} {item.get('units', '')} "
                    f"avg={stats.get('avg')} min={stats.get('min')} max={stats.get('max')}"
                )
                shown += 1
        if shown == 0:
            lines.append("- No numeric disk history available")
    else:
        lines.append("- No disk items found")

    lines.append("Network:")
    if network_items:
        shown = 0
        for item in network_items[:5]:
            stats = item.get("stats_24h", {})
            if stats.get("count", 0) > 0:
                lines.append(
                    f"- {item.get('name')}: latest={item.get('lastvalue')} {item.get('units', '')} "
                    f"avg={stats.get('avg')} max={stats.get('max')}"
                )
                shown += 1
        if shown == 0:
            lines.append("- No numeric network history available")
    else:
        lines.append("- No network items found")

    lines.append("Events/problems:")
    if recent_events:
        for event in recent_events[:5]:
            lines.append(f"- sev={event.get('severity')} {event.get('name')}")
    else:
        lines.append("- No recent events")

    lines.append("Next checks:")
    if recent_events:
        lines.append("- Review recent events for repeated alerts")
    if cpu_stats and cpu_stats.get("max") is not None:
        try:
            if float(cpu_stats["max"]) > 80:
                lines.append("- Check CPU peaks and running processes")
        except Exception:
            pass
    if not recent_events and not network_items and not disk_items:
        lines.append("- Verify host template/items coverage")

    return "\n".join(lines)


def summarize_gpu_with_ai(host_name: str) -> str:
    host_name = normalize_host(host_name)
    data = get_gpu_summary(host_name, 24)

    if isinstance(data, dict) and data.get("error"):
        return data["error"]

    host = data.get("host", {})
    gpu_items = data.get("gpu_items", [])

    if not gpu_items:
        return f"No GPU items found for host {host_name}"

    item_map = {item.get("key_"): item for item in gpu_items}

    def val(key: str, default: str = "unknown"):
        item = item_map.get(key)
        if not item:
            return default
        return str(item.get("lastvalue", default))

    def stat(key: str, field: str, default: str = "unknown"):
        item = item_map.get(key)
        if not item:
            return default
        stats = item.get("stats_24h", {})
        v = stats.get(field)
        return str(v) if v is not None else default

    gpu_name = val("gpu.name[0]")
    temp_now = val("gpu.temperature[0]")
    temp_avg = stat("gpu.temperature[0]", "avg")
    temp_max = stat("gpu.temperature[0]", "max")

    util_now = val("gpu.utilization[0]")
    util_avg = stat("gpu.utilization[0]", "avg")
    util_max = stat("gpu.utilization[0]", "max")

    mem_total = val("gpu.memory.total[0]")
    mem_used = val("gpu.memory.used[0]")
    mem_used_avg = stat("gpu.memory.used[0]", "avg")
    mem_used_max = stat("gpu.memory.used[0]", "max")

    fan_now = val("gpu.fan.speed[0]")
    power_draw = val("gpu.power.draw[0]")
    power_limit = val("gpu.power.limit[0]")

    lines = []
    host_status = "enabled" if str(host.get("status")) == "0" else "disabled"
    lines.append(f"GPU status: {host.get('host', host_name)} is {host_status}")
    lines.append("GPU:")
    lines.append(f"- Name: {gpu_name}")
    lines.append(f"- Utilization: latest={util_now} avg24h={util_avg} max24h={util_max}")
    lines.append(f"- Temperature: latest={temp_now} avg24h={temp_avg} max24h={temp_max}")
    lines.append(f"- Memory used: latest={mem_used} / total={mem_total} avg24h={mem_used_avg} max24h={mem_used_max}")
    lines.append(f"- Fan speed: latest={fan_now}")
    lines.append(f"- Power: draw={power_draw} limit={power_limit}")

    lines.append("Next checks:")
    try:
        if float(util_max) > 90:
            lines.append("- GPU utilization peaked high in last 24h")
    except Exception:
        pass
    try:
        if float(temp_max) > 80:
            lines.append("- GPU temperature peaked high in last 24h")
    except Exception:
        pass
    try:
        if float(mem_total) > 0 and float(mem_used) / float(mem_total) > 0.9:
            lines.append("- GPU memory usage is currently high")
    except Exception:
        pass
    if len(lines) == 8:
        lines.append("- No obvious GPU issue detected")

    return "\n".join(lines)
