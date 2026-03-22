from fastapi import FastAPI
import requests

app = FastAPI()

AI_URL = "http://127.0.0.1:8010/chat/messages/retrieval"

@app.post("/ask_ai")
def ask_ai(data: dict):
    payload = {
        "model": "qwen3:8b",
        "messages": data.get("messages", []),
        "use_retrieval": True,
        "selected_template": "cpu_rightsize_template_all",
        "selected_repo": "Zabbix-Widget-CPU-Rightsize-Advisor"
    }

    r = requests.post(AI_URL, json=payload, timeout=60)
    return r.json()
