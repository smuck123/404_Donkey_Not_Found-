#!/usr/bin/env python3
import json
import os
from typing import Dict, List

REGISTRY_PATH = "/opt/openclaw_zabbix_mcp/telegram_chats.json"


def _load_registry() -> Dict[str, dict]:
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_registry(data: Dict[str, dict]) -> None:
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, REGISTRY_PATH)


def register_chat(chat_id: int, chat_type: str = "", title: str = "", username: str = "", first_name: str = "", last_name: str = "") -> None:
    data = _load_registry()
    key = str(chat_id)
    data[key] = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
    }
    _save_registry(data)


def remove_chat(chat_id: int) -> None:
    data = _load_registry()
    key = str(chat_id)
    if key in data:
        del data[key]
        _save_registry(data)


def list_chats() -> List[dict]:
    data = _load_registry()
    return list(data.values())
