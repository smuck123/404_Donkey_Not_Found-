#!/usr/bin/env python3
import requests

from config import BOT_TOKEN, TELEGRAM_REPORT_CHAT_ID
from fortigate_ai import build_fortigate_report


def send_telegram_message(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not TELEGRAM_REPORT_CHAT_ID:
        raise RuntimeError("TELEGRAM_REPORT_CHAT_ID is not set")

    report = build_fortigate_report()
    send_telegram_message(TELEGRAM_REPORT_CHAT_ID, report)


if __name__ == "__main__":
    main()
