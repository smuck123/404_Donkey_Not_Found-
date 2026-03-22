import time
import requests


class ZabbixAPIError(Exception):
    pass


class ZabbixClient:
    def __init__(self, url: str, api_token: str, timeout: int = 30):
        self.url = url
        self.api_token = api_token
        self.timeout = timeout
        self._id = 0

    def _rpc(self, method: str, params: dict):
        self._id += 1

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._id
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

        r = requests.post(
            self.url,
            json=payload,
            headers=headers,
            timeout=self.timeout
        )
        r.raise_for_status()

        try:
            data = r.json()
        except Exception as e:
            raise ZabbixAPIError(f"Invalid JSON from Zabbix API: {r.text[:500]} ({e})")

        if "error" in data:
            raise ZabbixAPIError(f"{method} failed: {data['error']}")

        return data.get("result", [])

    def get_host(self, host_name: str):
        hosts = self._rpc("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "filter": {"host": [host_name]},
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type", "main", "useip", "available"],
            "selectGroups": ["groupid", "name"]
        })
        return hosts[0] if hosts else None

    def get_zabbix_problems(self, limit: int = 5):
        return self._rpc("problem.get", {
            "output": ["eventid", "name", "severity", "clock", "objectid"],
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            "limit": limit
        })

    def search_hosts(self, search_text: str, limit: int = 10):
        return self._rpc("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "search": {"host": search_text},
            "limit": limit
        })

    def get_host_status(self, host_name: str):
        return self._rpc("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "filter": {"host": [host_name]},
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type", "main", "useip", "available"],
            "selectGroups": ["groupid", "name"]
        })

    def get_host_interfaces(self, host_name: str):
        hosts = self._rpc("host.get", {
            "output": ["hostid", "host", "name"],
            "filter": {"host": [host_name]},
            "selectInterfaces": ["interfaceid", "ip", "dns", "port", "type", "main", "useip", "available"]
        })
        if not hosts:
            return []
        return hosts[0].get("interfaces", [])

    def get_recent_events(self, host_name: str, limit: int = 10):
        host = self.get_host(host_name)
        if not host:
            return []

        return self._rpc("event.get", {
            "output": ["eventid", "name", "severity", "clock", "value"],
            "hostids": [host["hostid"]],
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "limit": limit
        })

    def get_item_last_value(self, host_name: str, item_key: str):
        host = self.get_host(host_name)
        if not host:
            return []

        return self._rpc("item.get", {
            "output": ["itemid", "name", "key_", "lastvalue", "lastclock", "value_type", "units", "state", "status"],
            "hostids": [host["hostid"]],
            "filter": {"key_": [item_key]},
            "sortfield": "name"
        })

    def item_search(self, host_name: str, pattern: str, limit: int = 50):
        host = self.get_host(host_name)
        if not host:
            return []

        items = self._rpc("item.get", {
            "output": ["itemid", "name", "key_", "lastvalue", "lastclock", "value_type", "units", "state", "status"],
            "hostids": [host["hostid"]],
            "search": {
                "name": pattern,
                "key_": pattern
            },
            "searchByAny": True,
            "sortfield": "name",
            "limit": limit
        })
        return items

    def get_item_history(self, itemid: str, value_type: int, hours: int = 24, limit: int = 200):
        time_till = int(time.time())
        time_from = time_till - (hours * 3600)

        return self._rpc("history.get", {
            "output": "extend",
            "history": value_type,
            "itemids": [itemid],
            "sortfield": "clock",
            "sortorder": "DESC",
            "time_from": time_from,
            "time_till": time_till,
            "limit": limit
        })

    def list_host_groups(self):
        return self._rpc("hostgroup.get", {
            "output": ["groupid", "name"],
            "sortfield": "name"
        })

    def summarize_hosts(self, limit: int = 200):
        hosts = self._rpc("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "limit": limit
        })

        total = len(hosts)
        enabled = sum(1 for h in hosts if str(h.get("status")) == "0")
        disabled = sum(1 for h in hosts if str(h.get("status")) != "0")

        return {
            "total_hosts": total,
            "enabled_hosts": enabled,
            "disabled_hosts": disabled
        }
