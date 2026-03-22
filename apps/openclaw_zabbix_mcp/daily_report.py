#!/usr/bin/env python3
import requests
import urllib3

from config import BOT_TOKEN, FIREWALL_HOST
from zabbix_ai import get_cpu_load_text, summarize_host_24h_with_ai, get_problems
from fortigate_ai import summarize_fortigate_snapshot, summarize_fortigate_traffic
from chat_registry import list_chats, remove_chat

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_daily_report(host: str = "TORAKKA") -> str:
    try:
        problems = get_problems(10)
        if problems:
            problems_text = "\n".join(
                [f"- sev={p.get('severity')} {p.get('name')}" for p in problems[:10]]
            )
        else:
            problems_text = "- No current problems"
    except Exception as e:
        problems_text = f"Could not get current problems: {e}"

    try:
        cpu_text = get_cpu_load_text(host)
    except Exception as e:
        cpu_text = f"Could not get CPU load for {host}: {e}"

    try:
        host_summary = summarize_host_24h_with_ai(host)
    except Exception as e:
        host_summary = f"Could not summarize {host}: {e}"

    try:
        fw_summary = summarize_fortigate_snapshot()
    except Exception as e:
        fw_summary = f"Could not summarize firewall {FIREWALL_HOST}: {e}"

    try:
        fw_traffic = summarize_fortigate_traffic()
    except Exception as e:
        fw_traffic = f"Could not summarize firewall traffic: {e}"

    return (
        "Daily infrastructure report\n\n"
        "Current problems:\n"
        f"{problems_text}\n\n"
        f"Host: {host}\n\n"
        f"CPU status:\n{cpu_text}\n\n"
        f"24h host summary:\n{host_summary}\n\n"
        f"Firewall summary ({FIREWALL_HOST}):\n{fw_summary}\n\n"
        f"Firewall traffic summary:\n{fw_traffic}"
    )


def send_telegram_message(chat_id: int, text: str) -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunk_size = 3500
    parts = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    for part in parts:
        payload = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": True,
        }
        r = requests.post(url, data=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Telegram send failed for chat_id={chat_id}: {r.status_code} {r.text}")


def send_daily_report_to_all(host: str = "TORAKKA") -> None:
    message = build_daily_report(host)
    chats = list_chats()

    if not chats:
        raise RuntimeError("No registered Telegram chats found. Send a message to the bot first.")

    failed = []
    for chat in chats:
        chat_id = chat["chat_id"]
        try:
            send_telegram_message(chat_id, message)
        except Exception as e:
            failed.append(f"{chat_id}: {e}")
            err = str(e).lower()
            if "forbidden" in err or "chat not found" in err:
                remove_chat(chat_id)

    if failed:
        raise RuntimeError("Some sends failed:\n" + "\n".join(failed))


def main() -> None:
    send_daily_report_to_all("TORAKKA")


if __name__ == "__main__":
    main()
