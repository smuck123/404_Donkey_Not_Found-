#!/usr/bin/env python3
import json
import requests
from datetime import datetime
from pathlib import Path

# CONFIG
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID_FILE = Path("/opt/404_donkey_not_found/apps/openclaw_zabbix_mcp/telegram_chats.json")
PENDING_FILE = Path("/opt/404_donkey_not_found/apps/openclaw_zabbix_mcp/pending_fortigate_actions.json")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def load_chat_ids():
    if CHAT_ID_FILE.exists():
        try:
            return json.loads(CHAT_ID_FILE.read_text())
        except Exception:
            return {}
    return {}


def load_pending_actions():
    if PENDING_FILE.exists():
        try:
            return json.loads(PENDING_FILE.read_text())
        except Exception:
            return []
    return []


def save_pending_actions(actions):
    PENDING_FILE.write_text(json.dumps(actions, indent=2))


def send_telegram(chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(TELEGRAM_API, json=payload, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")


def format_report(action):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""
🔥 *Fortigate Alert*

Time: `{ts}`
Host: `{action.get("host", "unknown")}`
IP: `{action.get("ip", "unknown")}`
Reason: `{action.get("reason", "unknown")}`
Severity: `{action.get("severity", "unknown")}`

Action: `{action.get("action", "block")}`
"""


def process_actions():
    actions = load_pending_actions()
    if not actions:
        print("[*] No pending Fortigate actions")
        return

    chats = load_chat_ids()
    if not chats:
        print("[!] No Telegram chats configured")
        return

    print(f"[*] Processing {len(actions)} Fortigate actions")

    for action in actions:
        msg = format_report(action)

        for chat_id in chats.values():
            send_telegram(chat_id, msg)

    # clear after sending
    save_pending_actions([])
    print("[+] Reports sent and queue cleared")


if __name__ == "__main__":
    process_actions()
