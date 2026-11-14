"""
Приложение веба: uvicorn tickets.web.main:app

Роуты — tickets/web/routers/, зависимости (сессия на запрос, вход, IP) —
deps.py, шаблоны и фильтры — filters.py. Данные — из сервисов.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from tickets.config import web_settings
from tickets.logging import setup_logging
from tickets.notify import notify_owner
from tickets.web.deps import LOGIN_PATH, LoginRequired
from tickets.web.healthcheck import HEALTH_PATH
from tickets.web.routers import concert_day, health, payments, public

setup_logging()
logger = logging.getLogger(__name__)

# Секреты обязательны и не пустые: без них веб не стартует (а не пускает
# по пустому паролю или подписывает cookie пустым ключом)
web_settings()

app = FastAPI()
for module in (public, health, concert_day, payments):
    app.include_router(module.router)


@app.exception_handler(LoginRequired)
async def login_required(request: Request, error: LoginRequired):
    return RedirectResponse(LOGIN_PATH, status_code=303)


@app.exception_handler(Exception)
async def on_error(request: Request, error: Exception):
    """Необработанная ошибка → 500, в лог и владельцу (одинаковые — не чаще раза в 10 мин)."""
    logger.error("Unhandled error: %s %s", request.method, request.url.path, exc_info=error)
    summary = f"{request.method} {request.url.path}: {type(error).__name__}: {error}"
    await notify_owner(
        f"⚠️ Ошибка 500 в вебе: {summary}",
        dedup_key=f"web:{request.url.path}:{type(error).__name__}",
    )
    return PlainTextResponse("Internal Server Error", status_code=500)


class _SkipHealthAccessLog(logging.Filter):
    """Не писать в access-лог uvicorn успешные /health — healthcheck дёргает его каждые 10 с."""

    def filter(self, record: logging.LogRecord) -> bool:
        # args uvicorn.access: (client, method, path, http_version, status)
        args = record.args
        return not (
            isinstance(args, tuple) and len(args) == 5 and args[2] == HEALTH_PATH and args[4] == 200
        )


logging.getLogger("uvicorn.access").addFilter(_SkipHealthAccessLog())
