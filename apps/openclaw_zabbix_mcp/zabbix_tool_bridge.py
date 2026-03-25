from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

BASE = "http://127.0.0.1:8888"


def _get(path: str, params: dict | None = None):
    try:
        r = requests.get(f"{BASE}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Bridge request failed: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "base": BASE}


@app.get("/tool/zabbix_summary")
def zabbix_summary():
    return _get("/chat_summary")


@app.get("/tool/zabbix_problems")
def zabbix_problems(limit: int = 5):
    return _get("/get_zabbix_problems", {"limit": limit})


@app.get("/tool/zabbix_search")
def zabbix_search(search_text: str, limit: int = 5):
    return _get("/search_hosts", {"search_text": search_text, "limit": limit})


@app.get("/tool/zabbix_host_status")
def zabbix_host_status(host_name: str):
    return _get("/get_host_status", {"host_name": host_name})


@app.get("/tool/zabbix_item")
def zabbix_item(host_name: str, item_key: str):
    return _get("/get_item_last_value", {"host_name": host_name, "item_key": item_key})
