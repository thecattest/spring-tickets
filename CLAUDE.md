# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Plan of the ongoing cleanup and refactor: `ROADMAP.md` (check items off as they are done).

Concert ticket management system for VK (VKontakte). Ticketers create seat reservations, record payments, and manage bookings via a VK bot. A web UI shows a public hall map and admin payments dashboard.

**Stack**: Python 3.12 (uv), SQLAlchemy 2.0+, Alembic, vkbottle (VK bot), FastAPI (web), Redis (bot FSM state), PostgreSQL 18 (psycopg 3).

## Commands

```bash
# Setup (uv installs Python 3.12 from .python-version and creates .venv)
uv sync
uv run pre-commit install   # ruff check/format + requirements.txt sync before each commit
cp .env.example .env  # non-secret settings; secrets go to ./secrets/ (see Configuration)
# fill in VK_GROUP_ID, OWNER_VK_IDS
mkdir -m 700 secrets   # one file per secret, value only; postgres_password=tickets for the local volume
python -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/cookie_secret   # same for redis_password
# vk_bot_token, payments_password — by hand
uv run alembic upgrade head  # create / update the schema

# Run bot (requires Redis + VK token)
uv run python -m bot

# Run web UI
./web/run.sh
# or: uv run uvicorn web.app:app --host 0.0.0.0 --port 8080

# Run tests (throwaway Postgres container via testcontainers — needs Docker running)
uv run pytest
# test_redis_fsm uses local Redis db 15 and is skipped when Redis is not running

# Background jobs (normally run by cron; pg_dump is only in the image, so run backup in Compose)
docker compose run --rm web python -m jobs.backup [--reason pre-migrate]
docker compose run --rm web python -m jobs.debtors

# Lint / format
uv run ruff check --fix . && uv run ruff format .

# Deploy (run locally — SSHes into server, pulls, installs deps, migrates DB, restarts services)
bash deploy/deploy.sh
```

## Deployment

Server SSH alias: `tickets`. Project dir on server: `~/spring-tickets`.

- `deploy/deploy.sh` — main deploy script, run locally. Does: `ssh tickets` → `git pull` → `pip install` → `alembic upgrade head` → `systemctl --user restart tickets-bot tickets-web`
- `deploy/install.sh` — one-time server setup: installs systemd user services, nginx config, bash aliases, enables linger
- `deploy/aliases.sh` — adds `start`/`stop`/`restart`/`status`/`tw-log`/`tb-log` aliases to server `.bashrc`
- `deploy/setup-ssl.sh` — SSL certificate setup
- `deploy/setup-cron.sh` — cron jobs setup
- Services run as systemd **user** units (`systemctl --user`), no sudo needed

## Architecture

Two interfaces share the same database and models:

- **Bot** (`bot/`) — VK bot using vkbottle with FSM (finite state machine) handlers. Redis stores FSM state. Handlers in `bot/handlers/` orchestrate conversations; business logic lives in `bot/utils/db.py`.
- **Web** (`web/app.py`) — FastAPI app with Jinja2 templates. Public hall map at `/`, password-protected payments dashboard at `/payments`, concert day booking list at `/concert-day`. `/health` (app + `SELECT 1`, 503 if the DB is down) is the Compose healthcheck; successful `/health` calls are filtered out of the uvicorn access log.
- **Models** (`models/`) — SQLAlchemy ORM. `SeatAssignment` is the critical table: a partial unique index on `(row_number, seat_number) WHERE released_at IS NULL` prevents double-booking at the DB level.
- **Database** (`database.py`) — Engine, `SessionLocal` factory, `upgrade_db()` / `alembic_config()` for running migrations from code. PostgreSQL only; connection settings come from `config.db_settings()`.
- **Migrations** (`migrations/`) — Alembic; the schema is never created by the app (`create_all()` is not used).

### Key data flow

```
VK message → bot handler → bot/utils/db.py → SQLAlchemy models → PostgreSQL
                                                    ↓
Web UI (read-only) ← FastAPI ← SQLAlchemy queries ←─┘
```

All state changes are recorded in the `AuditLog` table.

## Key Domain Concepts

- **SeatAssignment**: source of truth for seat occupancy. Statuses: `booked`, `paid`, `reserved`. Soft-deleted via `released_at` timestamp.
- **Reservation**: groups seats for one buyer. One active reservation per VK user — enforced by the partial unique index `reservations_one_active_per_buyer`. Tracks `last_activity_at` for 7-day debtor detection.
- **Payment/PaymentSeat**: supports partial payments (pay for N of M seats). Deterministic seat selection (row ASC, seat ASC).
- **Owners vs admins**: `ADMIN` is a business role in the DB. Project owners are `OWNER_VK_IDS` in config, not a role: only owners run `/addadmin`, `/addseller`, `/removeuser`, `/users` and receive technical messages (backups). `bot.config.is_owner()`.
- **layout.json**: defines hall geometry (24 rows, variable seats, aisles). Used by both bot (validation) and web (rendering).

## Dependencies

- `pyproject.toml` + `uv.lock` are the source of truth. Add a dependency: `uv add <pkg>` (dev tools: `uv add --dev <pkg>`); update one: `uv lock --upgrade-package <pkg>`.
- `requirements.txt` is **generated** from `uv.lock` (no dev deps) only for the old pip-based server deploy (`deploy/deploy.sh`); the Dockerfile uses `uv sync --frozen --no-dev`. Never edit it by hand — the pre-commit hook regenerates it. It goes away with the old deploy (ROADMAP stage 5).

## Code Conventions

- ruff (lint + format, config in `pyproject.toml`) is enforced by pre-commit. `.git-blame-ignore-revs` lists the bulk-format commit.

- Enums in `models/base.py`: `UserRole`, `ReservationState`, `SeatStatus`, `ActorType`. Stored as VARCHAR + CHECK with the enum **values** (`'paid'`), not native Postgres ENUM (configured once in `Base.type_annotation_map`).
- Times: always aware UTC — `timeutils.utcnow()`, `timeutils.from_unix()` for VK dates; never `datetime.utcnow()`. Every `Mapped[datetime]` column is `timestamptz`.
- Partial indexes use `postgresql_where`. Constraint names follow `NAMING_CONVENTION` in `models/base.py`; name every `CheckConstraint`.
- Datetime fields use `*_at` suffix (`created_at`, `released_at`, `last_activity_at`)
- FK fields use `{entity}_{entity_id}` pattern (`buyer_vk_user_id`, `sold_by_user_id`)
- Session pattern: `with SessionLocal() as session:` — commit explicitly, auto-rollback on exception
- Seat input format: `"1-3,5,8-10"` — parsed by `bot/utils/seat_parser.py`
- Comments and user-facing messages are in Russian

## Background jobs

`jobs/` package (moves to `tickets/jobs/` in ROADMAP stage 7): `python -m jobs.backup`, `python -m jobs.debtors`. Each job wraps its async main in `jobs.runner.run_job()`: logging, exit 1 + `notify_owner()` on failure. `notify.notify_owner(text, file=None)` messages `OWNER_VK_IDS` in VK from any process and never raises. Schedule: `jobs/crontab` (supercronic; check with `supercronic -test`). Backup env: `BACKUP_DIR` (`/backups` in Compose), `BACKUP_KEEP` (14 per reason), `BACKUP_SEND_TO_VK` (default true). When testing jobs by hand with the real `.env`, pass `-e OWNER_VK_IDS=` so failures don't message the owner. Send VK messages with `random_id=random.getrandbits(31)`, never 0 (0 disables VK deduplication of retried requests).

## Bot entry point

`python -m bot` → `bot/__main__.py` → `bot.main.main()` → `asyncio.run(run_bot())`. Plain asyncio (vkbottle ≥ 4.9: `run_polling()` is a regular coroutine, `LoopWrapper` / `run_forever()` are deprecated — don't use them). Init and cleanup are `await` + `try/finally` in `run_bot()` (Redis, VK HTTP session). SIGTERM cancels the main task, SIGINT is handled by `asyncio.run`; both → graceful shutdown, exit 0. Startup and polling errors are not caught (traceback, exit 1).

Monitoring: `HeartbeatPolling` touches `/tmp/bot-heartbeat` after every Long Poll response (VK answers at least every 25 s even when idle); the bot's Compose healthcheck fails when it is older than 2 minutes. Unhandled errors in handlers and polling go to `bot.error_handler` → `bot.main.on_error` → log + `notify_owner(dedup_key=...)`; the web has the same for HTTP 500 (`@app.exception_handler(Exception)`, so `web` also gets the `vk_bot_token` secret). `dedup_key` is error type + place, not the message text; the same key is sent at most once per 10 minutes per process.

## Configuration

All settings live in `config.py` (pydantic-settings; moves to `tickets/config.py` in ROADMAP stage 7) — no `os.getenv` / `load_dotenv` anywhere else. Settings are split into sections, each validated on first use, so a process only needs what it uses (`migrate` runs without VK settings): `db_settings()` (`POSTGRES_HOST/PORT/DB/USER` with defaults, `POSTGRES_PASSWORD`, `SQL_ECHO`), `redis_settings()` (`REDIS_*`), `vk_settings()` (`VK_BOT_TOKEN`, `VK_GROUP_ID`, `OWNER_VK_IDS` comma-separated, `is_owner()`), `web_settings()` (`PAYMENTS_PASSWORD`, `COOKIE_SECRET`, `COOKIE_SECURE`), `backup_settings()`, `app_settings()` (`LOG_LEVEL`, `DISPLAY_TZ`, `SEAT_PRICE`, `DEBTORS_REMINDER_MIN_DAYS`). Each getter is cached per process.

- Sources, first found wins: environment (Compose `environment:`, `conftest.py`) → project-root `.env` → secret files (`/run/secrets/<field>`, `./secrets/<field>`) → code default. Env var name = field name upper-cased, secret file name = field name.
- Secrets are files in `./secrets/` (gitignored, one per secret: `postgres_password`, `redis_password`, `vk_bot_token`, `payments_password`, `cookie_secret`), never in `.env`. Compose mounts each service only the secrets it needs (`secrets:` in `compose.yaml` is the list); `uv run` on the host reads `./secrets/` directly. Postgres takes `POSTGRES_PASSWORD_FILE` (applied only when the volume is first created), Redis gets its config via stdin so the password is not in process args.
- Secrets are `SecretStr` and must be non-empty (`Secret` type): a missing or empty one raises `ValidationError` naming the field, so the process refuses to start. Use `.get_secret_value()` only where the raw value is needed; log `database.DATABASE_URL_SAFE`, never `DATABASE_URL`.
- Defaults in code only for non-secret values that are the same everywhere.
- `COOKIE_SECURE=false` is needed for local HTTP (default `true`, Secure cookie behind HTTPS).
- Timestamps are stored as `timestamptz` (UTC); the web shows them in `DISPLAY_TZ` (default `Europe/Moscow`) via the `local_dt` Jinja filter.
- Logging: call `logging_config.setup_logging()` once at process start (bot, web, jobs already do); no other `basicConfig`. stdout only, level from `LOG_LEVEL`.
- `bot/config.py` keeps only domain constants (`LAYOUT_FILE`), not settings.

### Local run with Docker Compose

`compose.yaml` runs `postgres` (18, volume `tickets_pgdata`), one-off `db-backup` (`jobs.backup --reason pre-migrate`: dumps into `./backups` only when migrations are pending; if it fails, migrate and app services don't start), one-off `migrate` (`alembic upgrade head`, `restart: "no"`; `web` starts only after it exits 0) `redis` (8, password from the `redis_password` secret, AOF, volume `tickets_redisdata`, not published to the host), `web` and `bot` (both from the one `Dockerfile` image, uv-based, with `pg_dump` 18 from PGDG for backups; `bot` has `init: true` so SIGTERM reaches it), `cron` (supercronic running `jobs/crontab`, Moscow time: backup daily 04:00, debtors every 3 days 20:00; supercronic is PID 1 itself, no `init`). `./backups` is mounted only into `db-backup` and `cron` (dumps contain personal data). App services read `.env`, but `POSTGRES_HOST` and `REDIS_HOST` are set to the service names. Every service logs via the `local` driver, max 5 × 10 MB (`x-logging` anchor) — read logs with `docker compose logs`, not files. Ports are bound to `127.0.0.1`: web 8000 always, Postgres 5432 only in dev.

`compose.dev.yaml` holds only dev differences and is enabled by `COMPOSE_FILE=compose.yaml:compose.dev.yaml` in the local `.env` (unset on the server): `web` with `uvicorn --reload`, `develop.watch` (sync code into `/code`, `sync+restart` for `bot`, rebuild on `pyproject.toml`/`uv.lock`; `.dockerignore` rules apply, so `.venv`/`.env`/`data` are never synced), Postgres port, `bot` and `cron` behind the `bot` / `cron` profiles — the local `.env` holds the real VK token, so the bot starts only with `--profile bot` (use a test community token, ROADMAP stage 3). The image copies code with `--chown=app:app` because watch needs the container user to write to `/code`.

```bash
docker compose watch                                 # dev: start + sync code on save (Ctrl+C stops watching, containers stay)
docker compose up -d --build                         # start / rebuild (migrate runs first)
docker compose --profile bot up -d bot               # bot too (test community token only)
docker compose run --rm migrate                      # run migrations again by hand
# or copy the old SQLite data instead (creates the schema itself, target must be empty):
docker compose run --rm -v ./data:/code/data web python scripts/migrate_sqlite_to_postgres.py data/tickets.db
docker compose logs -f web
```

Running on the host instead (`uv run ...`) connects to `localhost:5432` (the default `POSTGRES_HOST`), i.e. the same Compose Postgres through its dev-published port. Secrets are not in Compose yet (ROADMAP stage 5). On host-only runs (`uv run`) apply migrations yourself.

`scripts/migrate_sqlite_to_postgres.py` is one-off and is deleted after the server cutover. `jobs.backup` runs `pg_dump` (needs a `pg_dump` of the server's major version or newer — the image has 18 from PGDG).

## Migrations

Config lives in `[tool.alembic]` in `pyproject.toml` (no `alembic.ini`); `migrations/env.py` takes the URL and engine from `database.py` and metadata from `models`.

```bash
uv run alembic revision --autogenerate -m "add foo"   # then READ and edit the generated file
uv run alembic upgrade head
uv run alembic check          # models and migrations in sync
uv run alembic upgrade head --sql   # print SQL without a DB connection
```

- Autogenerate misses `CheckConstraint`s and enum value changes (write `op.drop_constraint` + `op.create_check_constraint` with `op.f(...)` by hand; `test_migrations_produce_model_schema` fails until you do), renames (it emits drop + add — rewrite as `alter_column`) and data changes.
- Migrations never import models or enums: use `op`, `sa.table()`/`sa.column()` and literals, so an old migration still runs on a fresh DB after models change.
- Expand/contract, forward only: each migration must work with the previous code version (new columns nullable or with `server_default`; drops and `NOT NULL` a release later). Full rules: ROADMAP → «Миграции и совместимость».
- A database created before Alembic (`create_all()`, the SQLite transfer script) is marked with `alembic stamp head` after checking the schema matches; `scripts/migrate_sqlite_to_postgres.py` runs `upgrade_db()` itself.

## Testing

- Root `conftest.py` starts a throwaway `postgres:18-alpine` container (testcontainers) in `pytest_configure` and sets `POSTGRES_*` to it before any test imports `database.py` (engine is created at import time, so it must happen first; environment beats `.env` in pydantic-settings). The schema is created once per session by `alembic upgrade head`; before every test all tables are truncated (`RESTART IDENTITY`). `bot/tests/test_migrations.py` checks models vs migrations: `alembic check`, plus a full schema comparison against a `create_all()` reference database (constraints via `pg_get_constraintdef`, indexes, columns, comments) that catches what autogenerate misses; and downgrade/upgrade. It asserts the engine points at the test container — tests never touch a real database. Docker must be running.
- Don't override `POSTGRES_*` inside test fixtures: the engine already exists by then, the override has no effect. To change a setting in a test, monkeypatch the getter (`monkeypatch.setattr(module, "vk_settings", ...)`).
