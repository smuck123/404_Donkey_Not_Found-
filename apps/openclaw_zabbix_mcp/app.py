import os
from statistics import mean

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from zabbix_client import ZabbixClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

ZABBIX_URL = os.getenv("ZABBIX_URL")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN")

if not ZABBIX_URL:
    raise RuntimeError("ZABBIX_URL is not set")
if not ZABBIX_API_TOKEN:
    raise RuntimeError("ZABBIX_API_TOKEN is not set")

app = FastAPI()


def client() -> ZabbixClient:
    return ZabbixClient(ZABBIX_URL, ZABBIX_API_TOKEN)


def _numeric_history_stats(history):
    vals = []
    for h in history:
        try:
            vals.append(float(h.get("value")))
        except Exception:
            pass

    if not vals:
        return {"count": 0, "min": None, "max": None, "avg": None, "latest": None}

    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "avg": round(mean(vals), 2),
        "latest": vals[0]
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/get_zabbix_problems")
def get_zabbix_problems(limit: int = 5):
    try:
        return client().get_zabbix_problems(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search_hosts")
def search_hosts(search_text: str, limit: int = 10):
    try:
        return client().search_hosts(search_text, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_host_status")
def get_host_status(host_name: str):
    try:
        return client().get_host_status(host_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_host_interfaces")
def get_host_interfaces(host_name: str):
    try:
        return client().get_host_interfaces(host_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_recent_events")
def get_recent_events(host_name: str, limit: int = 10):
    try:
        return client().get_recent_events(host_name, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_item_last_value")
def get_item_last_value(host_name: str, item_key: str):
    try:
        return client().get_item_last_value(host_name, item_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/item_search")
def item_search(host_name: str, pattern: str, limit: int = 50):
    try:
        return client().item_search(host_name, pattern, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/item_history")
def item_history(host_name: str, item_key: str, hours: int = 24, limit: int = 200):
    try:
        items = client().get_item_last_value(host_name, item_key)
        if not items:
            return []

        item = items[0]
        itemid = item["itemid"]
        value_type = int(item.get("value_type", 0))

        return client().get_item_history(itemid, value_type, hours, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/host_24h_summary")
def host_24h_summary(host_name: str):
    try:
        c = client()
        host = c.get_host(host_name)
        if not host:
            return {"error": f"Host not found: {host_name}"}

        interfaces = host.get("interfaces", [])
        groups = host.get("groups", [])
        recent_events = c.get_recent_events(host_name, 20)

        cpu_keys = [
            "system.cpu.load[all,avg1]",
            "system.cpu.load[percpu,avg1]",
            "system.cpu.util[,system]",
            "system.cpu.util"
        ]

        cpu_item = None
        for key in cpu_keys:
            data = c.get_item_last_value(host_name, key)
            if data:
                cpu_item = data[0]
                break

        memory_items = c.item_search(host_name, "memory", 20)
        disk_items = c.item_search(host_name, "vfs.fs", 20)
        network_items = c.item_search(host_name, "net.if", 20)

        cpu_stats = None
        if cpu_item:
            cpu_history = c.get_item_history(cpu_item["itemid"], int(cpu_item.get("value_type", 0)), 24, 200)
            cpu_stats = {
                "item": cpu_item,
                "stats_24h": _numeric_history_stats(cpu_history)
            }

        memory_summary = []
        for item in memory_items[:10]:
            hist = c.get_item_history(item["itemid"], int(item.get("value_type", 0)), 24, 100)
            memory_summary.append({
                "itemid": item["itemid"],
                "name": item["name"],
                "key_": item["key_"],
                "lastvalue": item.get("lastvalue"),
                "units": item.get("units"),
                "stats_24h": _numeric_history_stats(hist)
            })

        disk_summary = []
        for item in disk_items[:10]:
            hist = c.get_item_history(item["itemid"], int(item.get("value_type", 0)), 24, 100)
            disk_summary.append({
                "itemid": item["itemid"],
                "name": item["name"],
                "key_": item["key_"],
                "lastvalue": item.get("lastvalue"),
                "units": item.get("units"),
                "stats_24h": _numeric_history_stats(hist)
            })

        network_summary = []
        for item in network_items[:10]:
            hist = c.get_item_history(item["itemid"], int(item.get("value_type", 0)), 24, 100)
            network_summary.append({
                "itemid": item["itemid"],
                "name": item["name"],
                "key_": item["key_"],
                "lastvalue": item.get("lastvalue"),
                "units": item.get("units"),
                "stats_24h": _numeric_history_stats(hist)
            })

        return {
            "host": {
                "hostid": host["hostid"],
                "host": host["host"],
                "name": host["name"],
                "status": host["status"],
                "interfaces": interfaces,
                "groups": groups
            },
            "recent_events": recent_events,
            "cpu": cpu_stats,
            "memory_items": memory_summary,
            "disk_items": disk_summary,
            "network_items": network_summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gpu_summary")
def gpu_summary(host_name: str, hours: int = 24):
    try:
        c = client()
        host = c.get_host(host_name)
        if not host:
            return {"error": f"Host not found: {host_name}"}

        gpu_keys = [
            "gpu.name[0]",
            "gpu.temperature[0]",
            "gpu.utilization[0]",
            "gpu.memory.total[0]",
            "gpu.memory.used[0]",
            "gpu.fan.speed[0]",
            "gpu.power.draw[0]",
            "gpu.power.limit[0]",
        ]

        out = {
            "host": {
                "hostid": host["hostid"],
                "host": host["host"],
                "name": host["name"],
                "status": host["status"],
            },
            "gpu_items": []
        }

        for key in gpu_keys:
            items = c.get_item_last_value(host_name, key)
            if not items:
                continue

            item = items[0]
            value_type = int(item.get("value_type", 0))
            hist = c.get_item_history(item["itemid"], value_type, hours, 200)

            entry = {
                "itemid": item["itemid"],
                "name": item["name"],
                "key_": item["key_"],
                "lastvalue": item.get("lastvalue"),
                "lastclock": item.get("lastclock"),
                "units": item.get("units"),
                "value_type": value_type,
            }

            if value_type in [0, 3]:
                entry["stats_24h"] = _numeric_history_stats(hist)
            else:
                entry["stats_24h"] = {
                    "count": len(hist),
                    "latest": item.get("lastvalue")
                }

            out["gpu_items"].append(entry)

        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_host_groups")
def list_host_groups():
    try:
        return client().list_host_groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/summarize_hosts")
def summarize_hosts(limit: int = 200):
    try:
        return client().summarize_hosts(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat_summary")
def chat_summary():
    try:
        problems = client().get_zabbix_problems(5)
        summary = client().summarize_hosts(200)

        lines = []
        lines.append(f"Total hosts: {summary['total_hosts']}")
        lines.append(f"Enabled: {summary['enabled_hosts']}, Disabled: {summary['disabled_hosts']}")
        lines.append("Recent problems:")

        if not problems:
            lines.append("- No recent problems")
        else:
            for p in problems:
                lines.append(f"- severity={p.get('severity')} problem={p.get('name')}")

        return {"summary": "\n".join(lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
