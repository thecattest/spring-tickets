#!/usr/bin/env bash
cd "$(dirname "$0")/.."
exec .venv/bin/uvicorn web.app:app --host 0.0.0.0 --port "${PORT:-8080}"
