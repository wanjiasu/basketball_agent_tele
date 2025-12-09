import logging
import json
import psycopg
import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
from datetime import datetime, timezone
from .config import telegram_token
from .db import pg_dsn
from .utils import is_help_command, is_ai_pick_command, is_ai_history_command, is_ai_yesterday_command, is_start_command, normalize_country, extract_chatroom_id, to_int
from .services import send_telegram_country_keyboard, answer_callback_query, set_user_country, send_telegram_message, forward_telegram_to_agent
from .ai import ai_pick_reply, ai_history_reply, ai_yesterday_reply

logger = logging.getLogger(__name__)

WELCOME_TEXT = """Welcome to the support bot.
We provide AI match recommendations and fundamentals analysis.
Coverage highlights: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, UCL, World Cup.
Please choose your country so we can show times in your local timezone.
"""

router = APIRouter()

@router.get("/start")
async def start():
    return {"message": WELCOME_TEXT}

# Chatwoot integration removed; only Telegram webhook is supported.

@router.get("/health")
async def health():
    db_ok = False
    try:
        with psycopg.connect(pg_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                db_ok = True
    except Exception:
        db_ok = False
    return {
        "telegram_token_configured": bool(telegram_token()),
        "db_connected": db_ok,
    }

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    token = telegram_token()
    msg = body.get("message") or {}
    cb = body.get("callback_query") or {}
    if msg:
        text = msg.get("text") or ""
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if is_start_command(text):
            background_tasks.add_task(send_telegram_country_keyboard, chat.get("id"))
        choice = normalize_country(text)
        if choice:
            background_tasks.add_task(set_user_country, body, text)
        if is_ai_pick_command(text) and chat_id is not None:
            try:
                hint = {"data": {"message": {"additional_attributes": {"chat_id": chat_id}}}}
                reply = ai_pick_reply(hint)
                if isinstance(reply, list):
                    for seg in reply:
                        background_tasks.add_task(send_telegram_message, chat_id, seg)
                else:
                    background_tasks.add_task(send_telegram_message, chat_id, reply)
            except Exception:
                logger.exception("Telegram AI pick reply error")
        if is_ai_history_command(text) and chat_id is not None:
            try:
                hint = {"data": {"message": {"additional_attributes": {"chat_id": chat_id}}}}
                reply = ai_history_reply(hint)
                background_tasks.add_task(send_telegram_message, chat_id, reply)
            except Exception:
                logger.exception("Telegram AI history reply error")
        if is_ai_yesterday_command(text) and chat_id is not None:
            try:
                hint = {"data": {"message": {"additional_attributes": {"chat_id": chat_id}}}}
                reply = ai_yesterday_reply(hint)
                background_tasks.add_task(send_telegram_message, chat_id, reply)
            except Exception:
                logger.exception("Telegram AI yesterday reply error")
        t = str(text or "").strip()
        if chat_id is not None and t and not (
            is_start_command(text)
            or is_help_command(text)
            or is_ai_pick_command(text)
            or is_ai_history_command(text)
            or is_ai_yesterday_command(text)
            or normalize_country(text)
        ):
            background_tasks.add_task(forward_telegram_to_agent, body)
    if cb:
        data = cb.get("data") or ""
        choice = normalize_country(data)
        if choice:
            background_tasks.add_task(set_user_country, body, data)
            from .services import answer_callback_query
            background_tasks.add_task(answer_callback_query, token, cb.get("id"), "Selection recorded")
    return {"status": "ok"}
