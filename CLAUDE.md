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
uv run pre-commit install   # ruff check/format before each commit
cp .env.example .env  # non-secret settings; secrets go to ./secrets/ (see Configuration)
# fill in VK_GROUP_ID, OWNER_VK_IDS
mkdir -m 700 secrets   # one file per secret, value only; postgres_password=tickets for the local volume
python -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/cookie_secret   # same for redis_password
# vk_bot_token, payments_password — by hand
uv run alembic upgrade head  # create / update the schema

# Run bot (requires Redis + VK token)
uv run python -m tickets.bot

# Run web UI
uv run uvicorn tickets.web.app:app --reload --port 8000   # or in Compose: docker compose watch

# Run tests (throwaway Postgres and Redis containers via testcontainers — needs Docker running)
uv run pytest

# Background jobs (normally run by cron; pg_dump is only in the image, so run backup in Compose)
docker compose run --rm web python -m tickets.jobs.backup [--reason pre-migrate]
docker compose run --rm web python -m tickets.jobs.debtors

# Lint / format
uv run ruff check --fix . && uv run ruff format .

# Deploy (run locally — SSHes into server, git pull, docker compose up --build --wait)
bash deploy/deploy.sh
```

## Deployment

Server SSH alias: `tickets`. Project dir on server: `~/spring-tickets`. Everything runs in Docker Compose (`compose.yaml` only, no dev file); nginx and certbot are on the host. Server setup, HTTPS and the one-time cutover from the old systemd deploy: README, «Сервер».

- `deploy/deploy.sh` — main deploy script, run locally. Does: `ssh tickets` → `git pull --ff-only` → `docker compose up -d --build --wait --remove-orphans` (db-backup → migrate → services, fails if anything is not healthy) → `docker compose ps` → `docker image prune -f`.
- `deploy/tickets-nginx.conf` — nginx site: proxy to `127.0.0.1:8000`, rate limit on `/payments/login`. The server copy was modified by certbot, so changes are applied there by hand.
- `deploy/setup-ssl.sh` — Let's Encrypt certificate via `certbot --nginx` + renewal check. Keep it.
- On the server: secrets in `~/spring-tickets/secrets/`, non-secret settings in `.env`, both readable by uid 1000 (`app` in the image); dumps in `./backups`.

## Architecture

Code is one installable package `tickets` in `src/tickets/` (src layout; `uv sync` installs it editable, so imports are `from tickets…` everywhere — absolute, no `sys.path` tricks). Outside it: `migrations/` (Alembic), `tests/`, `scripts/` (one-off), `deploy/`, `layout.json`.

```
src/tickets/
  config.py    settings (pydantic-settings)      logging.py  setup_logging()
  time.py      aware UTC helpers                  db.py       engine, SessionLocal, migrations from code
  hall.py      hall geometry from layout.json     notify.py   notify_owner()
  models/      ORM models and enums               jobs/       backup, debtors, runner, crontab
  services/    business logic (users, reservations, seats, payments, reports, audit)
  bot/         VK bot (handlers/, fsm/, utils/)   web/        FastAPI app, templates
```

Two interfaces share the same database and models:

- **Bot** (`tickets/bot/`) — VK bot using vkbottle with FSM (finite state machine) handlers. Redis stores FSM state. Handlers in `tickets/bot/handlers/` orchestrate conversations; they still call the transitional facade `tickets/bot/utils/db.py`.
- **Web** (`tickets/web/app.py`) — FastAPI app with Jinja2 templates. Public hall map at `/`, password-protected payments dashboard at `/payments`, concert day booking list at `/concert-day`. `/health` (app + `SELECT 1`, 503 if the DB is down) is the Compose healthcheck; successful `/health` calls are filtered out of the uvicorn access log.
- **Models** (`tickets/models/`) — SQLAlchemy ORM. `SeatAssignment` is the critical table: a partial unique index on `(row_number, seat_number) WHERE released_at IS NULL` prevents double-booking at the DB level.
- **Database** (`tickets/db.py`) — `async_engine` / `AsyncSessionLocal` / `unit_of_work()` for the app; sync `engine` / `SessionLocal` only for Alembic, scripts, test checks and (until ROADMAP stage 7 step 6) the web; `upgrade_db()` / `alembic_config()` for running migrations from code. PostgreSQL only; connection settings come from `config.db_settings()`.
- **Migrations** (`migrations/`) — Alembic; the schema is never created by the app (`create_all()` is not used).

### Key data flow

```
VK message → bot handler → tickets/bot/utils/db.py (facade, one unit_of_work per call) → tickets.services → SQLAlchemy models → PostgreSQL
                                                    ↓
Web UI (read-only) ← FastAPI ← SQLAlchemy queries ←─┘
```

All state changes are recorded in the `AuditLog` table.

## Services and transactions

- `tickets.services.*`: `async` functions, `AsyncSession` first (SQLAlchemy asyncio on the same psycopg 3 driver, `sqlalchemy[asyncio]`); pure helpers without queries (`audit.log`, `seats.release`) stay sync; they **never** call `commit()`/`rollback()` (guard: `tests/test_guards.py`), use `session.flush()` for new ids. They know nothing about VK. Errors are `tickets.services.errors` (`ServiceError` and subclasses: `SeatOccupiedError`, `InsufficientSeatsError`, `ReservationNotActiveError`, `NotAllowedError`, `NotFoundError`).
- The boundary owns the transaction: `async with tickets.db.unit_of_work() as session:` — COMMIT on success, ROLLBACK on exception. Jobs already do it; bot handlers `await` `tickets/bot/utils/db.py`, a temporary async facade where each function is one unit of work and old exception names are kept (`DatabaseError` = `ServiceError`); handlers move to calling services directly in ROADMAP stage 7 step 5. No network calls inside a transaction; side effects (VK messages) after it.
- Everything that changes a reservation first calls `reservations.lock_active()` (`SELECT … FOR UPDATE` + must be ACTIVE): concurrent changes of one reservation are serialized, a cancelled one can't be changed. Seats are taken by `seats.occupy()`: check, then insert in a SAVEPOINT; a race on the unique index becomes `SeatOccupiedError` with re-read conflicts. Audit (`services.audit.log`, `AuditAction`) is written in the same transaction as the change.

## Key Domain Concepts

- **SeatAssignment**: source of truth for seat occupancy. Statuses: `booked`, `paid`, `reserved`. Soft-deleted via `released_at` timestamp.
- **Reservation**: groups seats for one buyer. One active reservation per VK user — enforced by the partial unique index `reservations_one_active_per_buyer`. Tracks `last_activity_at` for 7-day debtor detection.
- **Payment/PaymentSeat**: supports partial payments (pay for N of M seats). Deterministic seat selection (row ASC, seat ASC).
- **Owners vs admins**: `ADMIN` is a business role in the DB. Project owners are `OWNER_VK_IDS` in config, not a role: only owners run `/addadmin`, `/addseller`, `/removeuser`, `/users` and receive technical messages (backups). `bot.config.is_owner()`.
- **layout.json** (repo root, read by `tickets.hall`): defines hall geometry (24 rows, variable seats, aisles). Used by both bot (validation) and web (rendering).

## Dependencies

- `pyproject.toml` + `uv.lock` are the source of truth. Add a dependency: `uv add <pkg>` (dev tools: `uv add --dev <pkg>`); update one: `uv lock --upgrade-package <pkg>`.

## Code Conventions

- ruff (lint + format, config in `pyproject.toml`) is enforced by pre-commit. `.git-blame-ignore-revs` lists the bulk-format commit.

- Enums in `tickets/models/base.py`: `UserRole`, `ReservationState`, `SeatStatus`, `ActorType`. Stored as VARCHAR + CHECK with the enum **values** (`'paid'`), not native Postgres ENUM (configured once in `Base.type_annotation_map`).
- Times: always aware UTC — `tickets.time.utcnow()`, `tickets.time.from_unix()` for VK dates (accepts int or the `datetime` vkbottle-types already parse); never `datetime.utcnow()`. Every `Mapped[datetime]` column is `timestamptz`.
- Partial indexes use `postgresql_where`. Constraint names follow `NAMING_CONVENTION` in `tickets/models/base.py`; name every `CheckConstraint`.
- Datetime fields use `*_at` suffix (`created_at`, `released_at`, `last_activity_at`)
- FK fields use `{entity}_{entity_id}` pattern (`buyer_vk_user_id`, `sold_by_user_id`)
- Session pattern: `with SessionLocal() as session:` — commit explicitly, auto-rollback on exception
- Seat input format: `"1-3,5,8-10"` — parsed by `tickets/bot/utils/seat_parser.py`
- Comments and user-facing messages are in Russian

## Background jobs

`tickets.jobs`: `python -m tickets.jobs.backup`, `python -m tickets.jobs.debtors`. Each job wraps its async main in `tickets.jobs.runner.run_job()`: logging, exit 1 + `notify_owner()` on failure. `tickets.notify.notify_owner(text, file=None)` messages `OWNER_VK_IDS` in VK from any process and never raises. Schedule: `src/tickets/jobs/crontab` (supercronic; check with `supercronic -test`). Backup env: `BACKUP_DIR` (`/backups` in Compose), `BACKUP_KEEP` (14 per reason), `BACKUP_SEND_TO_VK` (default true). When testing jobs by hand with the real `.env`, pass `-e OWNER_VK_IDS=` so failures don't message the owner. Send VK messages with `random_id=random.getrandbits(31)`, never 0 (0 disables VK deduplication of retried requests).

## Bot entry point

`python -m tickets.bot` → `src/tickets/bot/__main__.py` → `tickets.bot.main.main()` → `asyncio.run(run_bot())`. Plain asyncio (vkbottle ≥ 4.9: `run_polling()` is a regular coroutine, `LoopWrapper` / `run_forever()` are deprecated — don't use them). Init and cleanup are `await` + `try/finally` in `run_bot()` (Redis, VK HTTP session). SIGTERM cancels the main task, SIGINT is handled by `asyncio.run`; both → graceful shutdown, exit 0. Startup and polling errors are not caught (traceback, exit 1).

Monitoring: `HeartbeatPolling` touches the heartbeat file after every Long Poll response (VK answers at least every 25 s even when idle). Path and max age live only in `tickets/bot/heartbeat.py`; the bot's Compose healthcheck is `python -m tickets.bot.heartbeat` (the web's is `python -m tickets.web.healthcheck`). Unhandled errors in handlers and polling go to `bot.error_handler` → `tickets.bot.main.on_error` → log + `notify_owner(dedup_key=...)`; the web has the same for HTTP 500 (`@app.exception_handler(Exception)`, so `web` also gets the `vk_bot_token` secret). `dedup_key` is error type + place, not the message text; the same key is sent at most once per 10 minutes per process.

## Configuration

All settings live in `tickets/config.py` (pydantic-settings) — no `os.getenv` / `load_dotenv` anywhere else. Settings are split into sections, each validated on first use, so a process only needs what it uses (`migrate` runs without VK settings): `db_settings()` (`POSTGRES_HOST/PORT/DB/USER` with defaults, `POSTGRES_PASSWORD`, `SQL_ECHO`), `redis_settings()` (`REDIS_*`), `vk_settings()` (`VK_BOT_TOKEN`, `VK_GROUP_ID`, `OWNER_VK_IDS` comma-separated, `is_owner()`), `web_settings()` (`PAYMENTS_PASSWORD`, `COOKIE_SECRET`, `COOKIE_SECURE`), `backup_settings()`, `app_settings()` (`LOG_LEVEL`, `DISPLAY_TZ`, `SEAT_PRICE`, `DEBTORS_REMINDER_MIN_DAYS`). Each getter is cached per process.

- Sources, first found wins: environment (Compose `environment:`, `conftest.py`) → project-root `.env` → secret files (`/run/secrets/<field>`, `./secrets/<field>`) → code default. Env var name = field name upper-cased, secret file name = field name.
- Secrets are files in `./secrets/` (gitignored, one per secret: `postgres_password`, `redis_password`, `vk_bot_token`, `payments_password`, `cookie_secret`), never in `.env`. Compose mounts each service only the secrets it needs (`secrets:` in `compose.yaml` is the list); `uv run` on the host reads `./secrets/` directly. Postgres takes `POSTGRES_PASSWORD_FILE` (applied only when the volume is first created), Redis gets its config via stdin so the password is not in process args.
- Secrets are `SecretStr` and must be non-empty (`Secret` type): a missing or empty one raises `ValidationError` naming the field, so the process refuses to start. Use `.get_secret_value()` only where the raw value is needed; log `tickets.db.DATABASE_URL_SAFE`, never `DATABASE_URL`.
- Defaults in code only for non-secret values that are the same everywhere.
- `COOKIE_SECURE=false` is needed for local HTTP (default `true`, Secure cookie behind HTTPS).
- Timestamps are stored as `timestamptz` (UTC); the web shows them in `DISPLAY_TZ` (default `Europe/Moscow`) via the `local_dt` Jinja filter.
- Logging: call `tickets.logging.setup_logging()` once at process start (bot, web, jobs already do); no other `basicConfig`. stdout only, level from `LOG_LEVEL`.
- Domain constants are not settings: hall geometry is `tickets.hall` (`LAYOUT_FILE`), texts are in `tickets/bot/texts.py`.

### Local run with Docker Compose

`compose.yaml` runs `postgres` (18, volume `tickets_pgdata`), one-off `db-backup` (`tickets.jobs.backup --reason pre-migrate`: dumps into `./backups` only when migrations are pending; if it fails, migrate and app services don't start), one-off `migrate` (`alembic upgrade head`, `restart: "no"`; `web` starts only after it exits 0) `redis` (8, password from the `redis_password` secret, AOF, volume `tickets_redisdata`, not published to the host), `web` and `bot` (both from the one `Dockerfile` image, uv-based, with `pg_dump` 18 from PGDG for backups; `bot` has `init: true` so SIGTERM reaches it), `cron` (supercronic running `tickets/jobs/crontab`, Moscow time: backup daily 04:00, debtors every 3 days 20:00; supercronic is PID 1 itself, no `init`). `./backups` is mounted only into `db-backup` and `cron` (dumps contain personal data). App services read `.env`, but `POSTGRES_HOST` and `REDIS_HOST` are set to the service names. Database name and user come from the `x-postgres-env` anchor shared by the `postgres` service and the apps — change them there, not in `config.py` defaults (those are for host runs only). `tests/test_config_guards.py` fails if compose and code drift: secrets list vs secret fields in `config.py`, secret file names, Postgres user/db for server and apps, healthcheck modules. Every service logs via the `local` driver, max 5 × 10 MB (`x-logging` anchor) — read logs with `docker compose logs`, not files. Ports are bound to `127.0.0.1`: web 8000 always, Postgres 5432 only in dev.

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

`scripts/migrate_sqlite_to_postgres.py` is one-off and is deleted after the server cutover. `tickets.jobs.backup` runs `pg_dump` (needs a `pg_dump` of the server's major version or newer — the image has 18 from PGDG).

## Migrations

Config lives in `[tool.alembic]` in `pyproject.toml` (no `alembic.ini`); `migrations/env.py` takes the URL and engine from `tickets.db` and metadata from `tickets.models`.

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

- Root `conftest.py` starts a throwaway `postgres:18-alpine` container (testcontainers) in `pytest_configure` and sets `POSTGRES_*` to it before any test imports `tickets.db` (engine is created at import time, so it must happen first; environment beats `.env` in pydantic-settings). The schema is created once per session by `alembic upgrade head`; before every test all tables are truncated (`RESTART IDENTITY`). `tests/test_migrations.py` checks models vs migrations: `alembic check`, plus a full schema comparison against a `create_all()` reference database (constraints via `pg_get_constraintdef`, indexes, columns, comments) that catches what autogenerate misses; and downgrade/upgrade. It asserts the engine points at the test container — tests never touch a real database. Docker must be running.
- Tests never read the local `.env` or `./secrets/`: `conftest.py` turns off both sources for every settings section and sets test values in the environment (`TEST_OWNER_VK_ID` is the owner).
- One event loop for the whole pytest session (`asyncio_default_*_loop_scope = "session"`): the `async_engine` pool is bound to its loop. Async fixtures need `@pytest_asyncio.fixture`.
- Redis for FSM is a second testcontainer; the `redis_storage` fixture gives an empty `RedisStorage`.
- **Bot scenario tests** (`tests/test_scenarios.py`, harness in `tests/scenario.py`): the real `Bot` + `Router` + handlers, real Postgres and Redis; only vkbottle's HTTP client is replaced (`FakeVK`: answers `messages.send` and `users.get`, any other VK method fails the test). `await bot.send(peer, text, fwd_from=..., fwd_attachments=[photo(...)])` feeds a `message_new` event and returns what the bot sent; check replies, `await bot.state(peer)` and the DB. The bot is built with `ErrorHandler(raise_exceptions=True)` so a crashing handler fails the test, and real network access (`aiohttp.ClientSession`) is blocked; receipt re-upload is faked (`bot.vk.reuploaded`). These tests pin current behaviour before the ROADMAP stage 7 rewrite; texts are matched by key fragments.
- Don't override `POSTGRES_*` inside test fixtures: the engine already exists by then, the override has no effect. To change a setting in a test, monkeypatch the getter (`monkeypatch.setattr(module, "vk_settings", ...)`).
