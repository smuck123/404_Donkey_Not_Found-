import json
import os
import time
from collections import Counter, defaultdict
from typing import Dict, Any, List

import requests

from config import OLLAMA_MODEL, OLLAMA_URL, FIREWALL_HOST
from fortigate_api import (
    get_system_status,
    get_system_interface,
    get_firewall_policies,
    get_firewall_addresses,
    get_router_static,
    get_vpn_ipsec_phase1,
    get_vpn_ipsec_phase2,
    get_monitor_sessions,
    get_banned_ips,
    create_address_object,
    add_ip_to_existing_group,
    create_phase1_interface,
    create_phase2_interface,
)
from zabbix_ai import summarize_host_24h_with_ai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_ACTIONS_FILE = os.path.join(BASE_DIR, "pending_fortigate_actions.json")


def _load_pending() -> dict:
    if not os.path.exists(PENDING_ACTIONS_FILE):
        return {}
    with open(PENDING_ACTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_pending(data: dict):
    with open(PENDING_ACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _new_action_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}"


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


def _extract_results(raw: Any) -> List[dict]:
    if isinstance(raw, dict):
        if isinstance(raw.get("results"), list):
            return raw["results"]

        if isinstance(raw.get("results"), dict):
            results_obj = raw["results"]

            if isinstance(results_obj.get("details"), list):
                return results_obj["details"]

            if isinstance(results_obj.get("results"), list):
                return results_obj["results"]

            return [results_obj]

        if isinstance(raw.get("data"), list):
            return raw["data"]

        if raw.get("status") == "unsupported":
            return []

    if isinstance(raw, list):
        return raw

    return []


def _pick(row, *keys, default="unknown"):
    for k in keys:
        if k in row and row[k] not in (None, "", [], {}):
            return row[k]
    return default


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _bytes_to_mbps(total_bytes: int, duration_seconds: int) -> float:
    if duration_seconds <= 0:
        return 0.0
    return round((total_bytes * 8) / duration_seconds / 1_000_000, 3)


def _safe_avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _is_private_ip(ip: str) -> bool:
    if not ip or ip == "unknown":
        return False

    if ip.startswith("10.") or ip.startswith("192.168."):
        return True

    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                return 16 <= second <= 31
            except Exception:
                return False

    return False


def _session_service_name(row: dict) -> str:
    apps = row.get("apps", [])
    if isinstance(apps, list) and apps:
        app0 = apps[0]
        if isinstance(app0, dict):
            name = app0.get("name")
            if name:
                return str(name)

    proto = str(_pick(row, "proto", "protocol", default="unknown")).lower()
    dport = str(_pick(row, "dport", "dstport", "dst_port", default="unknown"))

    if proto != "unknown" and dport != "unknown":
        return f"{proto}/{dport}"

    if dport != "unknown":
        return f"port-{dport}"

    return "unknown"


def _session_summary_rows(results: List[dict]) -> List[dict]:
    rows = []

    for row in results[:5000]:
        src = str(_pick(row, "saddr", "src", "srcip", "src_ip"))
        dst = str(_pick(row, "daddr", "dst", "dstip", "dst_ip"))
        proto = str(_pick(row, "proto", "protocol"))
        dport = str(_pick(row, "dport", "dstport", "dst_port"))
        sport = str(_pick(row, "sport", "srcport", "src_port"))
        action = str(_pick(row, "action", "policy_action", "policytype", default="unknown"))
        country = str(_pick(row, "country", default="unknown"))
        policyid = str(_pick(row, "policyid", "policy_id", "policy", default="unknown"))
        srcintf = str(_pick(row, "srcintf", default="unknown"))
        dstintf = str(_pick(row, "dstintf", default="unknown"))

        sentbyte = _to_int(row.get("sentbyte", 0))
        rcvdbyte = _to_int(row.get("rcvdbyte", 0))
        tx_packets = _to_int(row.get("tx_packets", 0))
        rx_packets = _to_int(row.get("rx_packets", 0))
        tx_shaper_drops = _to_int(row.get("tx_shaper_drops", 0))
        rx_shaper_drops = _to_int(row.get("rx_shaper_drops", 0))
        duration = _to_int(row.get("duration", 0))
        expiry = _to_int(row.get("expiry", 0))
        total_bytes = sentbyte + rcvdbyte
        total_packets = tx_packets + rx_packets
        mbps = _bytes_to_mbps(total_bytes, duration) if duration > 0 else 0.0

        rows.append({
            "src": src,
            "dst": dst,
            "sport": sport,
            "dport": dport,
            "proto": proto,
            "action": action,
            "country": country,
            "policyid": policyid,
            "srcintf": srcintf,
            "dstintf": dstintf,
            "service": _session_service_name(row),
            "sentbyte": sentbyte,
            "rcvdbyte": rcvdbyte,
            "total_bytes": total_bytes,
            "tx_packets": tx_packets,
            "rx_packets": rx_packets,
            "total_packets": total_packets,
            "tx_shaper_drops": tx_shaper_drops,
            "rx_shaper_drops": rx_shaper_drops,
            "total_shaper_drops": tx_shaper_drops + rx_shaper_drops,
            "duration": duration,
            "expiry": expiry,
            "mbps": mbps,
            "raw": row,
        })

    return rows


def fortigate_read_snapshot() -> Dict[str, Any]:
    return {
        "system_status": get_system_status(),
        "interfaces": get_system_interface(),
        "firewall_policies": get_firewall_policies(),
        "firewall_addresses": get_firewall_addresses(),
        "router_static": get_router_static(),
        "vpn_phase1": get_vpn_ipsec_phase1(),
        "vpn_phase2": get_vpn_ipsec_phase2(),
    }


def get_fortigate_traffic_raw() -> dict:
    return get_monitor_sessions()


def get_banned_ips_raw() -> dict:
    return get_banned_ips()


def summarize_fortigate_snapshot() -> str:
    snapshot = fortigate_read_snapshot()

    status = snapshot.get("system_status", {})
    interfaces = snapshot.get("interfaces", {})
    policies = snapshot.get("firewall_policies", {})
    routes = snapshot.get("router_static", {})
    vpn1 = snapshot.get("vpn_phase1", {})
    vpn2 = snapshot.get("vpn_phase2", {})

    iface_results = _extract_results(interfaces)
    policy_results = _extract_results(policies)
    route_results = _extract_results(routes)
    vpn1_results = _extract_results(vpn1)
    vpn2_results = _extract_results(vpn2)

    status_results = status.get("results", {}) if isinstance(status, dict) else {}
    hostname = status_results.get("hostname", "unknown")
    version = status.get("version", "unknown") if isinstance(status, dict) else "unknown"
    model = status_results.get("model", "unknown")

    up_ifaces = 0
    down_ifaces = 0
    for iface in iface_results:
        st = str(iface.get("status", "")).lower()
        if st in ["up", "1"]:
            up_ifaces += 1
        else:
            down_ifaces += 1

    lines = []
    lines.append(f"Firewall status: {hostname} ({model}) on {version}")
    lines.append("Interfaces:")
    lines.append(f"- Total interfaces seen: {len(iface_results)}")
    lines.append(f"- Up: {up_ifaces}, Down/other: {down_ifaces}")

    lines.append("Policies/routes:")
    lines.append(f"- Firewall policies: {len(policy_results)}")
    lines.append(f"- Static routes: {len(route_results)}")

    lines.append("VPN:")
    lines.append(f"- IPsec phase1 entries: {len(vpn1_results)}")
    lines.append(f"- IPsec phase2 entries: {len(vpn2_results)}")

    lines.append("Next checks:")
    if down_ifaces > 0:
        lines.append("- Review down interfaces and confirm whether they are expected")
    if len(vpn1_results) != len(vpn2_results):
        lines.append("- Verify phase1/phase2 tunnel consistency")
    if len(policy_results) == 0:
        lines.append("- Confirm firewall policy retrieval is working")
    if down_ifaces == 0 and len(policy_results) > 0:
        lines.append("- No obvious configuration summary issue detected")

    return "\n".join(lines)


def explain_fortigate_api_capabilities() -> str:
    prompt = (
        "Summarize the main FortiGate REST API capability groups for an operator: "
        "configuration, monitoring, logs, VPN, addresses, policies, routes, interfaces, traffic sessions. "
        "Keep it short and practical."
    )
    system_prompt = "You are a concise network automation assistant."
    return ollama_chat(system_prompt, prompt)


def build_block_ip_plan(ip_address: str) -> str:
    action_id = _new_action_id("block-ip")
    pending = _load_pending()
    pending[action_id] = {
        "type": "block_ip",
        "ip_address": ip_address,
        "group_name": "blocked-by-bot",
        "address_name": f"blocked-{ip_address.replace('.', '-')}",
    }
    _save_pending(pending)

    return (
        f"Planned block for IP {ip_address}\n"
        f"- Address object: {pending[action_id]['address_name']}\n"
        f"- Target group: {pending[action_id]['group_name']}\n"
        f"- Approval required\n\n"
        f"To execute: approve block ip {action_id}"
    )


def build_site_to_site_vpn_plan(peer_ip: str, local_subnet: str, remote_subnet: str) -> str:
    action_id = _new_action_id("vpn")
    pending = _load_pending()
    pending[action_id] = {
        "type": "site_to_site_vpn",
        "peer_ip": peer_ip,
        "local_subnet": local_subnet,
        "remote_subnet": remote_subnet,
        "phase1_name": f"vpn-{peer_ip.replace('.', '-')}",
        "phase2_name": f"vpn-p2-{peer_ip.replace('.', '-')}",
        "interface": "wan1",
        "psksecret": "CHANGE_ME_PSK",
    }
    _save_pending(pending)

    return (
        f"Planned site-to-site VPN\n"
        f"- Peer IP: {peer_ip}\n"
        f"- Local subnet: {local_subnet}\n"
        f"- Remote subnet: {remote_subnet}\n"
        f"- Phase1: {pending[action_id]['phase1_name']}\n"
        f"- Phase2: {pending[action_id]['phase2_name']}\n"
        f"- PSK still required before execution\n\n"
        f"To execute: approve site to site vpn {action_id}"
    )


def approve_block_ip(action_id: str) -> str:
    pending = _load_pending()
    action = pending.get(action_id)
    if not action or action.get("type") != "block_ip":
        return f"Pending block IP action not found: {action_id}"

    subnet = f"{action['ip_address']}/32"
    create_address_object(action["address_name"], subnet, "Created by Telegram bot")
    add_ip_to_existing_group(action["group_name"], action["address_name"])

    del pending[action_id]
    _save_pending(pending)
    return f"Approved and executed block IP action: {action_id}"


def approve_site_to_site_vpn(action_id: str) -> str:
    pending = _load_pending()
    action = pending.get(action_id)
    if not action or action.get("type") != "site_to_site_vpn":
        return f"Pending VPN action not found: {action_id}"

    if action.get("psksecret") == "CHANGE_ME_PSK":
        return f"Pending VPN action {action_id} still needs a real PSK secret before execution."

    create_phase1_interface(
        name=action["phase1_name"],
        interface=action["interface"],
        remote_gw=action["peer_ip"],
        psksecret=action["psksecret"],
    )
    create_phase2_interface(
        name=action["phase2_name"],
        phase1name=action["phase1_name"],
        src_subnet=action["local_subnet"],
        dst_subnet=action["remote_subnet"],
    )

    del pending[action_id]
    _save_pending(pending)
    return f"Approved and executed site-to-site VPN action: {action_id}"


def show_top_drops() -> str:
    results = _extract_results(get_fortigate_traffic_raw())
    if not results:
        return "No FortiGate traffic session data found."

    rows = _session_summary_rows(results)
    dropped = [r for r in rows if r["total_shaper_drops"] > 0]

    if not dropped:
        return "Top drops: no non-zero shaper drops seen in current live sessions."

    dropped.sort(key=lambda x: (x["total_shaper_drops"], x["total_packets"], x["total_bytes"]), reverse=True)

    lines = ["Top shaper drops:"]
    for r in dropped[:20]:
        lines.append(
            f"- {r['src']} -> {r['dst']} {r['proto']}/{r['dport']} "
            f"drops={r['total_shaper_drops']} tx_drops={r['tx_shaper_drops']} rx_drops={r['rx_shaper_drops']} "
            f"policy={r['policyid']} bytes={r['total_bytes']} avg_mbps={r['mbps']}"
        )

    return "\n".join(lines)


def show_suspicious_sources() -> str:
    results = _extract_results(get_fortigate_traffic_raw())
    if not results:
        return "No FortiGate traffic session data found."

    rows = _session_summary_rows(results)

    stats = defaultdict(lambda: {
        "sessions": 0,
        "bytes": 0,
        "packets": 0,
        "drops": 0,
        "countries": Counter(),
        "ports": Counter(),
        "policies": Counter(),
        "destinations": Counter(),
        "mbps_values": [],
    })

    for r in rows:
        src = r["src"]
        if _is_private_ip(src):
            continue

        st = stats[src]
        st["sessions"] += 1
        st["bytes"] += r["total_bytes"]
        st["packets"] += r["total_packets"]
        st["drops"] += r["total_shaper_drops"]
        st["countries"][r["country"]] += 1
        st["ports"][str(r["dport"])] += 1
        st["policies"][r["policyid"]] += 1
        st["destinations"][r["dst"]] += 1
        if r["mbps"] > 0:
            st["mbps_values"].append(r["mbps"])

    if not stats:
        return "Suspicious external sources: no external source IPs seen in current live sessions."

    scored = []
    for ip, st in stats.items():
        score = 0
        score += st["sessions"] * 2
        score += min(st["packets"] // 50, 25)
        score += min(st["bytes"] // 500000, 20)
        score += st["drops"] * 5

        avg_mbps = _safe_avg(st["mbps_values"])
        if avg_mbps >= 1:
            score += int(avg_mbps * 3)

        scored.append({
            "ip": ip,
            "score": score,
            "sessions": st["sessions"],
            "bytes": st["bytes"],
            "packets": st["packets"],
            "drops": st["drops"],
            "avg_mbps": avg_mbps,
            "top_country": st["countries"].most_common(1)[0][0] if st["countries"] else "unknown",
            "top_port": st["ports"].most_common(1)[0][0] if st["ports"] else "unknown",
            "top_policy": st["policies"].most_common(1)[0][0] if st["policies"] else "unknown",
            "top_dst": st["destinations"].most_common(1)[0][0] if st["destinations"] else "unknown",
        })

    scored.sort(key=lambda x: (x["score"], x["sessions"], x["bytes"], x["packets"]), reverse=True)

    lines = ["Suspicious external source review:"]
    for row in scored[:15]:
        lines.append(
            f"- {row['ip']} score={row['score']} sessions={row['sessions']} "
            f"bytes={row['bytes']} packets={row['packets']} avg_mbps={row['avg_mbps']} "
            f"drops={row['drops']} country={row['top_country']} port={row['top_port']} "
            f"policy={row['top_policy']} top_dst={row['top_dst']}"
        )

    return "\n".join(lines)


def build_block_review_hints() -> str:
    results = _extract_results(get_fortigate_traffic_raw())
    if not results:
        return "Block review hints: no traffic session data found."

    rows = _session_summary_rows(results)

    stats = defaultdict(lambda: {
        "sessions": 0,
        "bytes": 0,
        "packets": 0,
        "drops": 0,
        "mbps_values": [],
        "ports": Counter(),
        "destinations": Counter(),
        "countries": Counter(),
        "policies": Counter(),
    })

    for r in rows:
        src = r["src"]
        if _is_private_ip(src):
            continue

        st = stats[src]
        st["sessions"] += 1
        st["bytes"] += r["total_bytes"]
        st["packets"] += r["total_packets"]
        st["drops"] += r["total_shaper_drops"]
        if r["mbps"] > 0:
            st["mbps_values"].append(r["mbps"])
        st["ports"][str(r["dport"])] += 1
        st["destinations"][r["dst"]] += 1
        st["countries"][r["country"]] += 1
        st["policies"][r["policyid"]] += 1

    hints = []
    for ip, st in stats.items():
        avg_mbps = _safe_avg(st["mbps_values"])
        score = 0
        score += st["sessions"] * 2
        score += min(st["packets"] // 50, 25)
        score += min(st["bytes"] // 500000, 20)
        score += st["drops"] * 5
        if avg_mbps >= 1:
            score += int(avg_mbps * 3)

        if score < 40:
            continue

        hints.append({
            "ip": ip,
            "score": score,
            "sessions": st["sessions"],
            "bytes": st["bytes"],
            "packets": st["packets"],
            "drops": st["drops"],
            "avg_mbps": avg_mbps,
            "top_port": st["ports"].most_common(1)[0][0] if st["ports"] else "unknown",
            "top_dst": st["destinations"].most_common(1)[0][0] if st["destinations"] else "unknown",
            "top_country": st["countries"].most_common(1)[0][0] if st["countries"] else "unknown",
            "top_policy": st["policies"].most_common(1)[0][0] if st["policies"] else "unknown",
        })

    if not hints:
        return "Block review hints: no external IP currently crosses the review threshold."

    hints.sort(key=lambda x: (x["score"], x["sessions"], x["bytes"]), reverse=True)

    lines = ["Block review hints:"]
    for h in hints[:10]:
        lines.append(
            f"- Review {h['ip']} score={h['score']} sessions={h['sessions']} "
            f"bytes={h['bytes']} packets={h['packets']} avg_mbps={h['avg_mbps']} drops={h['drops']} "
            f"port={h['top_port']} top_dst={h['top_dst']} country={h['top_country']} policy={h['top_policy']}"
        )

    lines.append("These are review hints only, not automatic block decisions.")
    return "\n".join(lines)


def summarize_fortigate_traffic() -> str:
    raw = get_fortigate_traffic_raw()
    results = _extract_results(raw)

    if not results:
        return f"No FortiGate traffic session data found. Raw response: {json.dumps(raw)[:700]}"

    rows = _session_summary_rows(results)

    src_counter = Counter()
    dst_counter = Counter()
    service_counter = Counter()
    proto_counter = Counter()
    action_counter = Counter()
    country_counter = Counter()
    policy_counter = Counter()
    srcintf_counter = Counter()
    dstintf_counter = Counter()

    src_bytes = defaultdict(int)
    dst_bytes = defaultdict(int)
    mbps_samples = []

    total_sent = 0
    total_recv = 0
    total_tx_packets = 0
    total_rx_packets = 0
    total_shaper_drops = 0

    for r in rows:
        src_counter[r["src"]] += 1
        dst_counter[r["dst"]] += 1
        service_counter[r["service"]] += 1
        proto_counter[r["proto"]] += 1
        action_counter[r["action"]] += 1
        country_counter[r["country"]] += 1
        policy_counter[r["policyid"]] += 1
        srcintf_counter[r["srcintf"]] += 1
        dstintf_counter[r["dstintf"]] += 1

        src_bytes[r["src"]] += r["total_bytes"]
        dst_bytes[r["dst"]] += r["total_bytes"]

        total_sent += r["sentbyte"]
        total_recv += r["rcvdbyte"]
        total_tx_packets += r["tx_packets"]
        total_rx_packets += r["rx_packets"]
        total_shaper_drops += r["total_shaper_drops"]

        if r["mbps"] > 0:
            mbps_samples.append(r["mbps"])

    avg_session_mbps = _safe_avg(mbps_samples)
    peak_session_mbps = round(max(mbps_samples), 3) if mbps_samples else 0.0
    aggregate_est_mbps = round(sum(mbps_samples), 3) if mbps_samples else 0.0

    lines = []
    lines.append(f"Traffic status: {len(rows)} sessions analyzed")
    lines.append(
        f"Volume: sent={total_sent}B received={total_recv}B "
        f"tx_packets={total_tx_packets} rx_packets={total_rx_packets} shaper_drops={total_shaper_drops}"
    )
    lines.append(
        f"Speed estimate: avg_session={avg_session_mbps} Mb/s peak_session={peak_session_mbps} Mb/s aggregate_est={aggregate_est_mbps} Mb/s"
    )

    lines.append("Top source talkers:")
    for ip, count in src_counter.most_common(5):
        lines.append(f"- {ip}: {count} sessions, {src_bytes[ip]}B")

    lines.append("Top destinations:")
    for ip, count in dst_counter.most_common(5):
        lines.append(f"- {ip}: {count} sessions, {dst_bytes[ip]}B")

    lines.append("Top services:")
    for svc, count in service_counter.most_common(5):
        lines.append(f"- {svc}: {count} sessions")

    lines.append("Top protocols:")
    for proto, count in proto_counter.most_common(5):
        lines.append(f"- {proto}: {count} sessions")

    lines.append("Top countries:")
    for country, count in country_counter.most_common(5):
        lines.append(f"- {country}: {count} sessions")

    lines.append("Top policy IDs:")
    for pid, count in policy_counter.most_common(5):
        lines.append(f"- policy {pid}: {count} sessions")

    lines.append("Interfaces:")
    for iface, count in srcintf_counter.most_common(3):
        lines.append(f"- src {iface}: {count} sessions")
    for iface, count in dstintf_counter.most_common(3):
        lines.append(f"- dst {iface}: {count} sessions")

    top_drops = sorted(rows, key=lambda x: x["total_shaper_drops"], reverse=True)
    non_zero_drops = [r for r in top_drops if r["total_shaper_drops"] > 0][:5]
    if non_zero_drops:
        lines.append("Top shaper drops:")
        for r in non_zero_drops:
            lines.append(
                f"- {r['src']} -> {r['dst']} {r['proto']}/{r['dport']} drops={r['total_shaper_drops']} policy={r['policyid']}"
            )
    else:
        lines.append("Top shaper drops:")
        lines.append("- No non-zero shaper drops in current live sessions")

    lines.append("Next checks:")
    lines.append("- Review dominant source clients on internal interfaces")
    lines.append("- Check whether top destinations and countries are expected")
    lines.append("- Review policy concentration if one policy dominates most traffic")
    lines.append("- Treat block hints as review suggestions, not automatic block decisions")

    return "\n".join(lines)


def show_top_talkers() -> str:
    raw = get_fortigate_traffic_raw()
    results = _extract_results(raw)

    if not results:
        return f"No FortiGate traffic session data found. Raw response: {json.dumps(raw)[:700]}"

    rows = _session_summary_rows(results)

    src_counter = Counter()
    dst_counter = Counter()
    src_bytes = defaultdict(int)
    dst_bytes = defaultdict(int)
    src_mbps = defaultdict(list)
    dst_mbps = defaultdict(list)

    for r in rows:
        src_counter[r["src"]] += 1
        dst_counter[r["dst"]] += 1
        src_bytes[r["src"]] += r["total_bytes"]
        dst_bytes[r["dst"]] += r["total_bytes"]
        if r["mbps"] > 0:
            src_mbps[r["src"]].append(r["mbps"])
            dst_mbps[r["dst"]].append(r["mbps"])

    lines = ["Top source talkers:"]
    for ip, count in src_counter.most_common(10):
        lines.append(
            f"- {ip}: {count} sessions, {src_bytes[ip]}B, avg_mbps={_safe_avg(src_mbps[ip])}"
        )

    lines.append("")
    lines.append("Top destination talkers:")
    for ip, count in dst_counter.most_common(10):
        lines.append(
            f"- {ip}: {count} sessions, {dst_bytes[ip]}B, avg_mbps={_safe_avg(dst_mbps[ip])}"
        )

    return "\n".join(lines)


def show_blocked_ips() -> str:
    raw = get_banned_ips_raw()
    if isinstance(raw, dict) and raw.get("status") == "unsupported":
        return raw["message"]

    results = _extract_results(raw)
    if not results:
        return f"No blocked/banned IPs found. Raw response: {json.dumps(raw)[:700]}"

    lines = ["Blocked/Banned IPs:"]
    for row in results[:30]:
        ip = row.get("ip", row.get("address", row.get("src", "unknown")))
        expire = row.get("expire", row.get("expires", row.get("ttl", "")))
        lines.append(f"- {ip} {expire}".strip())

    return "\n".join(lines)


def show_fortigate_interfaces() -> str:
    raw = get_system_interface()
    results = _extract_results(raw)

    if not results:
        return f"No FortiGate interfaces found. Raw response: {json.dumps(raw)[:700]}"

    lines = ["FortiGate interfaces:"]
    for row in results[:30]:
        name = row.get("name", "unknown")
        alias = row.get("alias", "")
        ip = row.get("ip", row.get("ipv4-address", ""))
        status = row.get("status", row.get("link", "unknown"))
        role = row.get("role", "")
        bits = [f"- {name}"]
        if alias:
            bits.append(f"alias={alias}")
        if role:
            bits.append(f"role={role}")
        if ip:
            bits.append(f"ip={ip}")
        bits.append(f"status={status}")
        lines.append(" ".join(bits))

    return "\n".join(lines)


def show_fortigate_vpn() -> str:
    p1 = _extract_results(get_vpn_ipsec_phase1())
    p2 = _extract_results(get_vpn_ipsec_phase2())

    lines = ["FortiGate VPN summary:"]
    lines.append(f"- Phase1 entries: {len(p1)}")
    lines.append(f"- Phase2 entries: {len(p2)}")

    if p1:
        lines.append("Phase1:")
        for row in p1[:20]:
            name = row.get("name", "unknown")
            interface = row.get("interface", "")
            remote = row.get("remote-gw", row.get("remote_gw", ""))
            lines.append(f"- {name} interface={interface} remote={remote}".strip())

    if p2:
        lines.append("Phase2:")
        for row in p2[:20]:
            name = row.get("name", "unknown")
            phase1 = row.get("phase1name", "")
            src = row.get("src-subnet", row.get("src_subnet", ""))
            dst = row.get("dst-subnet", row.get("dst_subnet", ""))
            lines.append(f"- {name} phase1={phase1} src={src} dst={dst}".strip())

    return "\n".join(lines)


def show_fortigate_routes() -> str:
    results = _extract_results(get_router_static())
    if not results:
        return "No static routes found."

    lines = ["FortiGate static routes:"]
    for row in results[:30]:
        dst = row.get("dst", row.get("dstaddr", "unknown"))
        gateway = row.get("gateway", row.get("device", "unknown"))
        device = row.get("device", "")
        distance = row.get("distance", "")
        lines.append(f"- dst={dst} gateway={gateway} device={device} distance={distance}".strip())

    return "\n".join(lines)


def find_fortigate_policy(search_text: str) -> str:
    results = _extract_results(get_firewall_policies())
    if not results:
        return "No firewall policies found."

    q = search_text.lower().strip()
    matches = []

    for row in results:
        blob = json.dumps(row, ensure_ascii=False).lower()
        if q in blob:
            matches.append(row)

    if not matches:
        return f"No FortiGate policies matched: {search_text}"

    lines = [f"Matching FortiGate policies for: {search_text}"]
    for row in matches[:20]:
        pid = row.get("policyid", row.get("id", "unknown"))
        name = row.get("name", "")
        action = row.get("action", "")
        srcintf = row.get("srcintf", "")
        dstintf = row.get("dstintf", "")
        schedule = row.get("schedule", "")
        service = row.get("service", "")
        lines.append(
            f"- policyid={pid} name={name} action={action} srcintf={srcintf} dstintf={dstintf} schedule={schedule} service={service}"
        )

    return "\n".join(lines)


def find_fortigate_address(search_text: str) -> str:
    results = _extract_results(get_firewall_addresses())
    if not results:
        return "No firewall addresses found."

    q = search_text.lower().strip()
    matches = []

    for row in results:
        blob = json.dumps(row, ensure_ascii=False).lower()
        if q in blob:
            matches.append(row)

    if not matches:
        return f"No FortiGate addresses matched: {search_text}"

    lines = [f"Matching FortiGate addresses for: {search_text}"]
    for row in matches[:30]:
        name = row.get("name", "unknown")
        subnet = row.get("subnet", row.get("fqdn", row.get("type", "")))
        comment = row.get("comment", "")
        lines.append(f"- {name} subnet={subnet} comment={comment}".strip())

    return "\n".join(lines)


def show_fortigate_sessions_for_ip(ip_address: str) -> str:
    results = _extract_results(get_fortigate_traffic_raw())
    if not results:
        return "No FortiGate traffic session data found."

    rows = _session_summary_rows(results)

    matches = []
    for r in rows:
        if ip_address == r["src"] or ip_address == r["dst"]:
            matches.append(r)

    if not matches:
        return f"No sessions found for IP {ip_address}"

    lines = [f"FortiGate sessions for IP {ip_address}: count={len(matches)}"]
    for r in matches[:30]:
        lines.append(
            f"- {r['src']} -> {r['dst']} port={r['dport']} proto={r['proto']} "
            f"policy={r['policyid']} country={r['country']} bytes={r['total_bytes']} "
            f"packets={r['total_packets']} avg_mbps={r['mbps']} drops={r['total_shaper_drops']}"
        )

    return "\n".join(lines)


def show_fortigate_sessions_for_port(port: str) -> str:
    results = _extract_results(get_fortigate_traffic_raw())
    if not results:
        return "No FortiGate traffic session data found."

    rows = _session_summary_rows(results)
    port = str(port).strip()

    matches = [r for r in rows if str(r["dport"]) == port]

    if not matches:
        return f"No sessions found for port {port}"

    counter = Counter()
    country_counter = Counter()
    total_bytes = 0
    total_packets = 0
    mbps_values = []

    for r in matches:
        counter[r["dst"]] += 1
        country_counter[r["country"]] += 1
        total_bytes += r["total_bytes"]
        total_packets += r["total_packets"]
        if r["mbps"] > 0:
            mbps_values.append(r["mbps"])

    lines = [f"FortiGate sessions for port {port}: count={len(matches)}"]
    lines.append(
        f"Volume: bytes={total_bytes} packets={total_packets} avg_mbps={_safe_avg(mbps_values)} peak_mbps={round(max(mbps_values), 3) if mbps_values else 0.0}"
    )
    lines.append("Top destinations:")
    for dst, count in counter.most_common(15):
        lines.append(f"- {dst}: {count} sessions")

    lines.append("Top countries:")
    for country, count in country_counter.most_common(10):
        lines.append(f"- {country}: {count} sessions")

    return "\n".join(lines)


def investigate_firewall() -> str:
    zabbix_part = summarize_host_24h_with_ai(FIREWALL_HOST)
    forti_part = summarize_fortigate_snapshot()
    traffic_part = summarize_fortigate_traffic()
    drops_part = show_top_drops()
    review_part = build_block_review_hints()

    return (
        "Firewall investigation\n"
        "======================\n"
        f"{zabbix_part}\n\n"
        "----------------------\n"
        f"{forti_part}\n\n"
        "----------------------\n"
        f"{traffic_part}\n\n"
        "----------------------\n"
        f"{drops_part}\n\n"
        "----------------------\n"
        f"{review_part}"
    )


def build_fortigate_report() -> str:
    return (
        "FortiGate 8h report\n"
        "===================\n"
        f"{summarize_fortigate_snapshot()}\n\n"
        "-------------------\n"
        f"{summarize_fortigate_traffic()}\n\n"
        "-------------------\n"
        f"{show_top_drops()}\n\n"
        "-------------------\n"
        f"{build_block_review_hints()}"
    )


def bot_capabilities_text() -> str:
    return (
        "I can do:\n"
        "- problems\n"
        "- summary\n"
        "- search host NAME\n"
        "- search hosts NAME\n"
        "- find host NAME\n"
        "- get host status for NAME\n"
        "- get cpu load for NAME\n"
        "- summarize host NAME\n"
        "- summarize gpu\n"
        "- summarize gpu for NAME\n"
        "- check gpu\n"
        "- check gpu for NAME\n"
        "- summarize traffic\n"
        "- summarize traffic for NAME\n"
        "- summarize fortigate\n"
        "- summarize fortigate traffic\n"
        "- investigate firewall\n"
        "- show fortigate interfaces\n"
        "- show fortigate vpn\n"
        "- show fortigate routes\n"
        "- find fortigate policy TEXT\n"
        "- find fortigate address TEXT\n"
        "- show fortigate sessions for IP\n"
        "- show fortigate sessions port PORT\n"
        "- show top talkers\n"
        "- show top drops\n"
        "- show suspicious fortigate sources\n"
        "- show fortigate block hints\n"
        "- show blocked ips\n"
        "- what fortigate api can call\n"
        "- plan block ip X.X.X.X\n"
        "- approve block ip ACTION_ID\n"
        "- plan site to site vpn <peer_ip> <local_subnet> <remote_subnet>\n"
        "- approve site to site vpn ACTION_ID\n"
        "- summarize daily report\n"
        "- daily_report\n"
        "- my chat id\n"
        "- list registered chats\n"
        "- tell story\n"
        "- story about TOPIC\n"
        "- joke\n"
        "- explain TEXT"
    )
