from fastapi import FastAPI
import requests

app = FastAPI()

BASE = "http://127.0.0.1:8888"

@app.get("/tool/zabbix_summary")
def zabbix_summary():
    r = requests.get(f"{BASE}/chat_summary", timeout=30)
    r.raise_for_status()
    return r.json()

@app.get("/tool/zabbix_problems")
def zabbix_problems(limit: int = 5):
    r = requests.get(f"{BASE}/get_zabbix_problems", params={"limit": limit}, timeout=30)
    r.raise_for_status()
    return r.json()

@app.get("/tool/zabbix_search")
def zabbix_search(search_text: str, limit: int = 5):
    r = requests.get(
        f"{BASE}/search_hosts",
        params={"search_text": search_text, "limit": limit},
        timeout=30
    )
    r.raise_for_status()
    return r.json()

@app.get("/tool/zabbix_host_status")
def zabbix_host_status(host_name: str):
    r = requests.get(
        f"{BASE}/get_host_status",
        params={"host_name": host_name},
        timeout=30
    )
    r.raise_for_status()
    return r.json()

@app.get("/tool/zabbix_item")
def zabbix_item(host_name: str, item_key: str):
    r = requests.get(
        f"{BASE}/get_item_last_value",
        params={"host_name": host_name, "item_key": item_key},
        timeout=30
    )
    r.raise_for_status()
    return r.json()
