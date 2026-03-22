import json
import os
import time
from collections import Counter
from typing import Dict, Any, List

from config import OLLAMA_MODEL, OLLAMA_URL
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
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_ACTIONS_FILE = os.path.join(BASE_DIR, "pending_fortigate_actions.json")


def _load_pending() -> dict:
    if not os.path.exists(PENDING_ACTIONS_FILE):
        return {}
    with open(PENDING_ACTIONS_FILE) as f:
        return json.load(f)


def _save_pending(data: dict):
    with open(PENDING_ACTIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)
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


def summarize_fortigate_snapshot() -> str:
    snapshot = fortigate_read_snapshot()

    status = snapshot.get("system_status", {})
    interfaces = snapshot.get("interfaces", {})
    policies = snapshot.get("firewall_policies", {})
    routes = snapshot.get("router_static", {})
    vpn1 = snapshot.get("vpn_phase1", {})
    vpn2 = snapshot.get("vpn_phase2", {})

    def _results(x):
        if isinstance(x, dict):
            if isinstance(x.get("results"), list):
                return x["results"]
            if isinstance(x.get("results"), dict):
                return [x["results"]]
        if isinstance(x, list):
            return x
        return []

    iface_results = _results(interfaces)
    policy_results = _results(policies)
    route_results = _results(routes)
    vpn1_results = _results(vpn1)
    vpn2_results = _results(vpn2)

    hostname = status.get("results", {}).get("hostname", "unknown") if isinstance(status.get("results"), dict) else "unknown"
    version = status.get("version", "unknown")
    model = status.get("results", {}).get("model", "unknown") if isinstance(status.get("results"), dict) else "unknown"

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


def _extract_results(raw: Any) -> List[dict]:
    if isinstance(raw, dict):
        if isinstance(raw.get("results"), list):
            return raw["results"]
        if isinstance(raw.get("results"), dict):
            return [raw["results"]]
        if isinstance(raw.get("data"), list):
            return raw["data"]
        if raw.get("status") == "unsupported":
            return []
    if isinstance(raw, list):
        return raw
    return []


def get_fortigate_traffic_raw() -> dict:
    return get_monitor_sessions()


def get_banned_ips_raw() -> dict:
    return get_banned_ips()


def summarize_fortigate_traffic() -> str:
    raw = get_fortigate_traffic_raw()
    results = _extract_results(raw)

    if not results:
        return f"No FortiGate traffic session data found. Raw response: {json.dumps(raw)[:700]}"

    src_counter = Counter()
    dst_counter = Counter()
    service_counter = Counter()
    proto_counter = Counter()
    action_counter = Counter()

    def _pick(row, *keys, default="unknown"):
        for k in keys:
            if k in row and row[k] not in (None, ""):
                return row[k]
        return default

    for row in results[:2000]:
        src = str(_pick(row, "src", "srcip", "saddr", "src_ip"))
        dst = str(_pick(row, "dst", "dstip", "daddr", "dst_ip"))
        dport = str(_pick(row, "dport", "dstport", "dst_port", default="unknown"))
        proto = str(_pick(row, "proto", "protocol"))
        action = str(_pick(row, "action", "policy_action"))
        service = _pick(row, "service", "service_name", default=None)

        if service in (None, "", "unknown"):
            if dport == "443":
                service = "HTTPS"
            elif dport == "80":
                service = "HTTP"
            elif dport == "22":
                service = "SSH"
            else:
                service = f"port-{dport}"

        src_counter[src] += 1
        dst_counter[dst] += 1
        service_counter[str(service)] += 1
        proto_counter[proto] += 1
        action_counter[action] += 1

    lines = []
    lines.append(f"Traffic status: {len(results)} sessions analyzed")
    lines.append("Top talkers:")
    for ip, count in src_counter.most_common(5):
        lines.append(f"- Source {ip}: {count} sessions")

    lines.append("Top destinations/services:")
    for ip, count in dst_counter.most_common(5):
        lines.append(f"- Destination {ip}: {count} sessions")
    for svc, count in service_counter.most_common(5):
        lines.append(f"- Service {svc}: {count} sessions")

    lines.append("Notable patterns:")
    for proto, count in proto_counter.most_common(3):
        lines.append(f"- Protocol {proto}: {count} sessions")
    for action, count in action_counter.most_common(3):
        lines.append(f"- Action {action}: {count} sessions")

    lines.append("Next checks:")
    lines.append("- Review repeated top destinations and services")
    lines.append("- Confirm dominant talkers are expected endpoints")
    lines.append("- Check policy and session logging if unknown fields remain")

    return "\n".join(lines)


def show_top_talkers() -> str:
    raw = get_fortigate_traffic_raw()
    results = _extract_results(raw)

    if not results:
        return f"No FortiGate traffic session data found. Raw response: {json.dumps(raw)[:700]}"

    src_counter = Counter()
    dst_counter = Counter()

    for row in results[:2000]:
        src = str(row.get("src", row.get("srcip", row.get("saddr", row.get("src_ip", "unknown")))))
        dst = str(row.get("dst", row.get("dstip", row.get("daddr", row.get("dst_ip", "unknown")))))
        src_counter[src] += 1
        dst_counter[dst] += 1

    lines = ["Top source talkers:"]
    for ip, count in src_counter.most_common(10):
        lines.append(f"- {ip}: {count} sessions")

    lines.append("")
    lines.append("Top destination talkers:")
    for ip, count in dst_counter.most_common(10):
        lines.append(f"- {ip}: {count} sessions")

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
        "- show top talkers\n"
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
