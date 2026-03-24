import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ZABBIX_API_URL = os.getenv("ZABBIX_API_URL", "https://zabbix.kivela.work").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()


TRAFFIC_ITEM_KEY = os.getenv("TRAFFIC_ITEM_KEY", "windows.traffic.out").strip()
FIREWALL_HOST = os.getenv("FIREWALL_HOST", "fw1.kivela.work").strip()
FORTIGATE_HOST = os.getenv("FORTIGATE_HOST", "").rstrip("/")
FORTIGATE_TOKEN = os.getenv("FORTIGATE_TOKEN", "").strip()
FORTIGATE_VERIFY_SSL = os.getenv("FORTIGATE_VERIFY_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
FORTIGATE_VDOM = os.getenv("FORTIGATE_VDOM", "root").strip()
FORTIGATE_TRAFFIC_PATH = os.getenv("FORTIGATE_TRAFFIC_PATH", "/api/v2/monitor/firewall/session/select").strip()
FORTIGATE_BANNED_IP_PATH = os.getenv("FORTIGATE_BANNED_IP_PATH", "/api/v2/monitor/firewall/banned/select").strip()

# ADD THIS
TELEGRAM_REPORT_CHAT_ID = os.getenv("TELEGRAM_REPORT_CHAT_ID", "").strip()

HOST_ALIASES = {
    "firewall": FIREWALL_HOST,
    "fw": FIREWALL_HOST,
    "fw1": FIREWALL_HOST,
    "traffic": FIREWALL_HOST,
}

def validate_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required config values: {', '.join(missing)}")
