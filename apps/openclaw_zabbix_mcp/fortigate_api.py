import requests
from typing import Any, Dict, Optional

from config import (
    FORTIGATE_HOST,
    FORTIGATE_TOKEN,
    FORTIGATE_VERIFY_SSL,
    FORTIGATE_VDOM,
    FORTIGATE_TRAFFIC_PATH,
)

class FortiGateAPIError(Exception):
    pass

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {FORTIGATE_TOKEN}",
        "Content-Type": "application/json",
    }

def _request(method: str, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Any:
    if not FORTIGATE_HOST or not FORTIGATE_TOKEN:
        raise FortiGateAPIError("FORTIGATE_HOST or FORTIGATE_TOKEN is not configured")

    url = f"{FORTIGATE_HOST}{path}"
    params = dict(params or {})
    params.setdefault("vdom", FORTIGATE_VDOM)

    try:
        r = requests.request(
            method=method,
            url=url,
            headers=_headers(),
            params=params,
            json=json_body,
            timeout=10,
            verify=FORTIGATE_VERIFY_SSL,
        )
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        body = e.response.text[:500] if e.response is not None else str(e)
        raise FortiGateAPIError(f"HTTP error for {url}: {body}")
    except requests.exceptions.RequestException as e:
        raise FortiGateAPIError(f"Request failed for {url}: {e}")

    content_type = (r.headers.get("Content-Type") or "").lower()
    text = r.text.strip()

    if not text:
        return {"raw": "", "note": "empty response"}

    if "application/json" in content_type or text.startswith("{") or text.startswith("["):
        try:
            return r.json()
        except Exception as e:
            raise FortiGateAPIError(f"Invalid JSON from {url}: {text[:300]} ({e})")

    return {"raw": text, "content_type": content_type}

# ---------- Read-only helpers ----------

def get_system_status():
    return _request("GET", "/api/v2/monitor/system/status")

def get_system_interface():
    return _request("GET", "/api/v2/cmdb/system/interface")

def get_firewall_policies():
    return _request("GET", "/api/v2/cmdb/firewall/policy")

def get_firewall_addresses():
    return _request("GET", "/api/v2/cmdb/firewall/address")

def get_router_static():
    return _request("GET", "/api/v2/cmdb/router/static")

def get_vpn_ipsec_phase1():
    return _request("GET", "/api/v2/cmdb/vpn.ipsec/phase1-interface")

def get_vpn_ipsec_phase2():
    return _request("GET", "/api/v2/cmdb/vpn.ipsec/phase2-interface")

def get_monitor_sessions(start: int = 0, count: int = 200, ip_version: str = "ipv4"):
    params = {
        "start": start,
        "count": count,
        "ip_version": ip_version,
    }
    return _request("GET", FORTIGATE_TRAFFIC_PATH, params=params)

def get_banned_ips():
    # Not all FortiGate builds expose a banned IP monitor endpoint.
    # Return a controlled message instead of hard-failing.
    return {
        "status": "unsupported",
        "message": "Blocked/banned IP monitor endpoint is not available on this FortiGate build."
    }

# ---------- Guarded write helpers ----------

def create_address_object(name: str, subnet: str, comment: str = ""):
    body = {
        "name": name,
        "subnet": subnet,
        "comment": comment,
    }
    return _request("POST", "/api/v2/cmdb/firewall/address", json_body=body)

def get_address_group(group_name: str):
    return _request("GET", f"/api/v2/cmdb/firewall/addrgrp/{group_name}")

def update_address_group(group_name: str, members: list):
    body = {"member": members}
    return _request("PUT", f"/api/v2/cmdb/firewall/addrgrp/{group_name}", json_body=body)

def add_ip_to_existing_group(group_name: str, member_name: str):
    group = get_address_group(group_name)
    results = group.get("results", {}) if isinstance(group, dict) else {}
    members = results.get("member", []) or []
    if not any(m.get("name") == member_name for m in members):
        members.append({"name": member_name})
    return update_address_group(group_name, members)

def create_phase1_interface(name: str, interface: str, remote_gw: str, psksecret: str, proposal: str = "aes256-sha256"):
    body = {
        "name": name,
        "interface": interface,
        "remote-gw": remote_gw,
        "psksecret": psksecret,
        "proposal": proposal,
    }
    return _request("POST", "/api/v2/cmdb/vpn.ipsec/phase1-interface", json_body=body)

def create_phase2_interface(name: str, phase1name: str, src_subnet: str, dst_subnet: str, proposal: str = "aes256-sha256"):
    body = {
        "name": name,
        "phase1name": phase1name,
        "src-subnet": src_subnet,
        "dst-subnet": dst_subnet,
        "proposal": proposal,
    }
    return _request("POST", "/api/v2/cmdb/vpn.ipsec/phase2-interface", json_body=body)
