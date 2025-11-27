import os
import json

def chatwoot_base_url() -> str:
    url = os.getenv("CHATWOOT_BASE_URL", "")
    return url.rstrip("/")

def chatwoot_token() -> str:
    return os.getenv("CHATWOOT_API_ACCESS_TOKEN", "")

def telegram_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def telegram_webhook_url() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_URL", "")

def lark_webhook_url() -> str:
    return os.getenv("LARK_BOT_WEBHOOK_URL", "")

def read_offset(country: str) -> int:
    try:
        base = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base, "时差.json")
        with open(path, "r", encoding="utf-8") as f:
            m = json.load(f)
        v = m.get(country)
        return int(v) if v is not None else 0
    except Exception:
        return 0
