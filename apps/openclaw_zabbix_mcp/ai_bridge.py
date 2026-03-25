from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

AI_URL = "http://127.0.0.1:8010/chat/messages/retrieval"


@app.get("/health")
def health():
    return {"status": "ok", "ai_url": AI_URL}


@app.post("/ask_ai")
def ask_ai(data: dict):
    payload = {
        "model": "qwen3:8b",
        "messages": data.get("messages", []),
        "use_retrieval": True,
        "selected_template": "cpu_rightsize_template_all",
        "selected_repo": "Zabbix-Widget-CPU-Rightsize-Advisor",
    }

    try:
        r = requests.post(AI_URL, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"AI bridge request failed: {e}")
