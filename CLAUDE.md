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
cp .env.example .env  # fill in DATABASE_URL, VK_BOT_TOKEN, VK_GROUP_ID, OWNER_VK_IDS, REDIS_PASSWORD, PAYMENTS_PASSWORD, COOKIE_SECRET
uv run alembic upgrade head  # create / update the schema

# Run bot (requires Redis + VK token)
uv run python -m bot

# Run web UI
./web/run.sh
# or: uv run uvicorn web.app:app --host 0.0.0.0 --port 8080

# Run tests (throwaway Postgres container via testcontainers — needs Docker running)
uv run pytest
# test_redis_fsm uses local Redis db 15 and is skipped when Redis is not running

# Debtors reminders (cron)
uv run python scripts/send_debtors_reminders.py

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
- **Web** (`web/app.py`) — FastAPI app with Jinja2 templates. Public hall map at `/`, password-protected payments dashboard at `/payments`, concert day booking list at `/concert-day`.
- **Models** (`models/`) — SQLAlchemy ORM. `SeatAssignment` is the critical table: a partial unique index on `(row_number, seat_number) WHERE released_at IS NULL` prevents double-booking at the DB level.
- **Database** (`database.py`) — Engine, `SessionLocal` factory, `upgrade_db()` / `alembic_config()` for running migrations from code. PostgreSQL only; `DATABASE_URL` is required.
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

## Configuration

Environment variables loaded from `.env` (see `.env.example`). Key vars: `VK_BOT_TOKEN`, `VK_GROUP_ID`, `OWNER_VK_IDS`, `REDIS_*`, `DATABASE_URL`, `SEAT_PRICE`, `PAYMENTS_PASSWORD`, `COOKIE_SECRET`, `COOKIE_SECURE`, `DISPLAY_TZ`, `LOG_LEVEL`, `SQL_ECHO`.

- `web/app.py` refuses to start without `PAYMENTS_PASSWORD` and `COOKIE_SECRET`. `COOKIE_SECURE=false` is needed for local HTTP (default `true`, Secure cookie behind HTTPS).
- Timestamps are stored as `timestamptz` (UTC); the web shows them in `DISPLAY_TZ` (default `Europe/Moscow`) via the `local_dt` Jinja filter.
- Logging: call `logging_config.setup_logging()` once at process start (bot, web, scripts already do); no other `basicConfig`. stdout only, level from `LOG_LEVEL`.

Config centralized in `bot/config.py` for the bot; `database.py` reads `DATABASE_URL` and `SQL_ECHO` directly from env.

`database.py` loads the project-root `.env` itself (`override=False`), so every entry point — bot, web, scripts, `alembic` — sees the same `DATABASE_URL`. Variables already set in the environment win (Docker `--env-file`/`environment:`, `conftest.py` in tests). No fallback: without `DATABASE_URL` it raises. Log `database.DATABASE_URL_SAFE` (password hidden), never `DATABASE_URL`.

### Local run with Docker Compose

`compose.yaml` runs `postgres` (18, volume `tickets_pgdata`), one-off `migrate` (`alembic upgrade head`, `restart: "no"`; `web` starts only after it exits 0) and `web` (built from `Dockerfile`, uv-based). `web` reads `.env` but `DATABASE_URL` is overridden to the service name `postgres`. Ports are bound to `127.0.0.1` (web 8000, Postgres 5432 — for `uv run` and DB tools on the host).

```bash
docker compose up -d --build                         # start / rebuild (migrate runs first)
docker compose run --rm migrate                      # run migrations again by hand
# or copy the old SQLite data instead (creates the schema itself, target must be empty):
docker compose run --rm -v ./data:/code/data web python scripts/migrate_sqlite_to_postgres.py data/tickets.db
docker compose logs -f web
```

Running on the host instead (`uv run ...`) uses `DATABASE_URL` from `.env` = `localhost:5432`, i.e. the same Compose Postgres through its published port. The bot, Redis, cron, `db-backup` and secrets are not in Compose yet (ROADMAP stages 3–4). On host-only runs (`uv run`) apply migrations yourself.

`scripts/migrate_sqlite_to_postgres.py` is one-off and is deleted after the server cutover. `scripts/backup_db.py` runs `pg_dump` (needs a `pg_dump` of the server's major version or newer).

## Migrations

Config lives in `[tool.alembic]` in `pyproject.toml` (no `alembic.ini`); `migrations/env.py` takes the URL and engine from `database.py` and metadata from `models`.

```bash
uv run alembic revision --autogenerate -m "add foo"   # then READ and edit the generated file
uv run alembic upgrade head
uv run alembic check          # models and migrations in sync
uv run alembic upgrade head --sql   # print SQL without a DB connection
```

- Autogenerate misses `CheckConstraint`s (add them by hand), renames (it emits drop + add — rewrite as `alter_column`) and data changes.
- Expand/contract, forward only: each migration must work with the previous code version (new columns nullable or with `server_default`; drops and `NOT NULL` a release later). Full rules: ROADMAP → «Миграции и совместимость».
- A database created before Alembic (`create_all()`, the SQLite transfer script) is marked with `alembic stamp head` after checking the schema matches; `scripts/migrate_sqlite_to_postgres.py` runs `upgrade_db()` itself.

## Testing

- Root `conftest.py` starts a throwaway `postgres:18-alpine` container (testcontainers) in `pytest_configure` and sets `DATABASE_URL` to it before any test imports `database.py` (engine is created at import time, so it must happen first; `load_dotenv` in `database.py` does not override it). The schema is created once per session by `alembic upgrade head`; before every test all tables are truncated (`RESTART IDENTITY`). `bot/tests/test_migrations.py` checks models vs migrations (`alembic check`) and downgrade/upgrade. It asserts the engine points at the test container — tests never touch a real database. Docker must be running.
- Don't override `DATABASE_URL` inside test fixtures: the engine already exists by then, the override has no effect.
