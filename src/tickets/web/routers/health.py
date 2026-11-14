"""/health — для healthcheck Docker: приложение отвечает и база доступна."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from tickets.db import async_engine
from tickets.web.healthcheck import HEALTH_PATH

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(HEALTH_PATH)
async def health():
    # Без unit_of_work: проверка соединения, не бизнес-операция. Детали — только в лог
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check failed: database unavailable")
        return JSONResponse({"status": "error"}, status_code=503)
    return {"status": "ok"}
