import logging
from fastapi import FastAPI
import asyncio
 
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = FastAPI()
logger = logging.getLogger(__name__)


from app.db import init_db
from app.push import run_daily_push_scheduler
from app.routes import router as api_router
from app.services import set_telegram_webhook

app.include_router(api_router)

@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(run_daily_push_scheduler())
    try:
        set_telegram_webhook()
    except Exception:
        logger.exception("Set Telegram webhook failed")
