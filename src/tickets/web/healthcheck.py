"""
Healthcheck веба для Docker: python -m tickets.web.healthcheck

Запрашивает /health у uvicorn в том же контейнере: код 0 — ответ 200,
1 — ошибка, 503 (нет базы) или таймаут. Путь и порт — только здесь
(порт совпадает с --port в compose.yaml).
"""

import sys
import urllib.request

HEALTH_PATH = "/health"
PORT = 8000

if __name__ == "__main__":
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}{HEALTH_PATH}", timeout=3)
    except Exception as error:
        print(f"unhealthy: {error}", file=sys.stderr)
        sys.exit(1)
