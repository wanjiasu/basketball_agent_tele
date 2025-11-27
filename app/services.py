import logging
import os
import requests
import psycopg
from .config import chatwoot_base_url, chatwoot_token, telegram_token, telegram_webhook_url
from .db import pg_dsn
from .utils import extract_chatwoot_fields, extract_chatroom_id, normalize_country, to_int

logger = logging.getLogger(__name__)

def send_chatwoot_reply(account_id: int, conversation_id: int, content: str) -> None:
    base_url = chatwoot_base_url()
    token = chatwoot_token()
    if not base_url or not token:
        logger.warning("Chatwoot env missing, skip reply")
        return
    endpoint = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
    payload = {"content": content, "message_type": "outgoing", "private": False, "content_type": "text"}
    headers = {"Content-Type": "application/json", "api_access_token": token}
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Chatwoot reply failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        logger.exception("Chatwoot reply error")

def send_telegram_country_keyboard(chatroom_id_raw) -> None:
    token = telegram_token()
    if not token or chatroom_id_raw is None:
        logger.warning("Telegram token/chat_id missing, skip keyboard")
        return
    chat_id = None
    try:
        if isinstance(chatroom_id_raw, int):
            chat_id = chatroom_id_raw
        else:
            import re
            m = re.search(r"-?\d+", str(chatroom_id_raw))
            chat_id = int(m.group(0)) if m else None
    except Exception:
        chat_id = None
    if chat_id is None:
        logger.warning("Telegram chat_id parse failed, skip keyboard")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "请选择地区",
        "reply_markup": {"inline_keyboard": [[{"text": "🇵🇭 菲律宾", "callback_data": "PH"}, {"text": "🇺🇸 美国", "callback_data": "US"}]]},
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Telegram keyboard failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        logger.exception("Telegram keyboard error")

def send_telegram_message(chatroom_id_raw, text: str) -> None:
    token = telegram_token()
    if not token or chatroom_id_raw is None or not text:
        return
    chat_id = None
    try:
        if isinstance(chatroom_id_raw, int):
            chat_id = chatroom_id_raw
        else:
            import re
            m = re.search(r"-?\d+", str(chatroom_id_raw))
            chat_id = int(m.group(0)) if m else None
    except Exception:
        chat_id = None
    if chat_id is None:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        logger.exception("Telegram sendMessage error")

def set_telegram_webhook() -> None:
    token = telegram_token()
    url = telegram_webhook_url()
    if not token or not url:
        return
    api = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        resp = requests.post(api, json={"url": url}, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Telegram setWebhook failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        logger.exception("Telegram setWebhook error")

def answer_callback_query(token: str, callback_id: str, text: str = None) -> None:
    if not token or not callback_id:
        return
    api = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    try:
        resp = requests.post(api, json=payload, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Telegram answerCallbackQuery failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        logger.exception("Telegram answerCallbackQuery error")

def set_user_country(body: dict, choice_text: str) -> None:
    try:
        country = normalize_country(choice_text)
        if not country:
            return
        external_id = None
        chatroom_id_raw = extract_chatroom_id(body)
        b = body or {}
        data = b.get("data") or b.get("payload") or b
        sender = data.get("sender") or data.get("contact") or {}
        external_id = sender.get("id") or data.get("sender_id") or (data.get("contact") or {}).get("id")
        username = sender.get("name") or data.get("name") or b.get("name")
        with psycopg.connect(pg_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (external_id, username, chatroom_id, country)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (external_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        chatroom_id = COALESCE(EXCLUDED.chatroom_id, users.chatroom_id),
                        country = EXCLUDED.country,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        str(external_id) if external_id is not None else None,
                        username,
                        str(chatroom_id_raw) if chatroom_id_raw is not None else None,
                        country,
                    ),
                )
                conn.commit()
    except Exception:
        logger.exception("DB set country error")

def store_message(body: dict) -> None:
    try:
        content, message_type, conversation_id, account_id = extract_chatwoot_fields(body)
        chatroom_id_raw = extract_chatroom_id(body)
        b = body or {}
        data = b.get("data") or b.get("payload") or b
        sender = data.get("sender") or data.get("contact") or {}
        message = data.get("message") or {}
        contact = data.get("contact") or {}
        external_id = sender.get("id") or data.get("sender_id") or message.get("sender_id")
        msg_id = data.get("id") or message.get("id")
        inbox_id = (data.get("inbox_id") or message.get("inbox_id") or (data.get("conversation") or {}).get("inbox_id"))
        source_id = (
            data.get("source_id")
            or message.get("source_id")
            or (data.get("conversation") or {}).get("source_id")
            or ((data.get("conversation") or {}).get("additional_attributes") or {}).get("source_id")
            or (message.get("additional_attributes") or {}).get("source_id")
        )
        username = sender.get("name") or data.get("name") or b.get("name")
        with psycopg.connect(pg_dsn()) as conn:
            with conn.cursor() as cur:
                user_id = None
                if external_id is not None:
                    cur.execute(
                        """
                        INSERT INTO users (external_id, username, chatroom_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (external_id) DO UPDATE SET
                            username = EXCLUDED.username,
                            chatroom_id = COALESCE(EXCLUDED.chatroom_id, users.chatroom_id),
                            updated_at = NOW()
                        RETURNING id
                        """,
                        (str(external_id), username, str(chatroom_id_raw) if chatroom_id_raw is not None else None),
                    )
                    row = cur.fetchone()
                    user_id = row[0] if row else None
                try:
                    conv_id_int = int(conversation_id) if conversation_id is not None else None
                except Exception:
                    conv_id_int = None
                try:
                    acc_id_int = int(account_id) if account_id is not None else None
                except Exception:
                    acc_id_int = None
                try:
                    msg_id_int = int(msg_id) if msg_id is not None else None
                except Exception:
                    msg_id_int = None
                try:
                    inbox_id_int = int(inbox_id) if inbox_id is not None else None
                except Exception:
                    inbox_id_int = None
                cur.execute(
                    """
                    INSERT INTO chat_messages (chatroom_id, account_id, conversation_id, user_id, content, message_type, message_id, sender_id, contact_id, inbox_id, source_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(chatroom_id_raw) if chatroom_id_raw is not None else (str(conversation_id) if conversation_id is not None else None),
                        acc_id_int,
                        conv_id_int,
                        user_id,
                        content,
                        message_type,
                        msg_id_int,
                        str(external_id) if external_id is not None else None,
                        str(contact.get("id")) if contact.get("id") is not None else None,
                        inbox_id_int,
                        str(source_id) if source_id is not None else None,
                    ),
                )
                conn.commit()
    except Exception:
        logger.exception("DB store error")

def send_lark_help_alert(body: dict) -> None:
    url = os.getenv("LARK_BOT_WEBHOOK_URL", "")
    if not url:
        return
    try:
        b = body or {}
        data = b.get("data") or b.get("payload") or b
        message = data.get("message") or {}
        conversation = data.get("conversation") or {}
        sender = data.get("sender") or data.get("contact") or {}
        content = data.get("content") or message.get("content") or b.get("content") or ""
        username = sender.get("name") or data.get("name") or b.get("name") or ""
        conversation_id = (
            data.get("conversation_id")
            or message.get("conversation_id")
            or conversation.get("id")
            or b.get("conversation_id")
        )
        account_id = (
            data.get("account_id")
            or conversation.get("account_id")
            or message.get("account_id")
            or b.get("account_id")
            or (b.get("account") or {}).get("id")
        )
        chatroom_id = extract_chatroom_id(body)
        text = (
            f"人工接入提醒\n"
            f"用户: {username or '未知'}\n"
            f"会话ID: {conversation_id or ''}\n"
            f"账户ID: {account_id or ''}\n"
            f"聊天ID: {chatroom_id or ''}\n"
            f"请求内容: {str(content)[:300]}"
        )
        payload = {"msg_type": "text", "content": {"text": text}}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code >= 300:
            logger.error(f"Lark alert failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        logger.exception("Lark alert error")
