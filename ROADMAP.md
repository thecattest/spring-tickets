# Roadmap

План приведения проекта в порядок: от очевидных проблем к инфраструктуре
(Postgres → Alembic → Docker Compose) и затем к архитектурному рефактору.
Отмечайте пункты `[x]` по мере выполнения. Подробности решений — в разделе
«Справка» ниже; ссылки вида (→ Архитектура) ведут туда.

Контекст: проект сейчас не используется в проде — требований к простою нет,
данные из текущей SQLite переносятся только ради проверки переноса.
`compose.yaml` владелец пишет сам; Claude консультирует и ревьюит.

---

## Этап 0. Гигиена

- [x] **uv вместо pip.** Зависимости в `pyproject.toml` (`[project.dependencies]`), pytest и линтеры — в `[dependency-groups] dev`, точные версии всего дерева в `uv.lock` (коммитится). Локально `uv sync`, в образе `uv sync --frozen --no-dev`, обновление — `uv lock --upgrade-package <имя>`. `requirements.txt` пока генерируется из `uv.lock` (хук pre-commit) для текущего pip-деплоя — удалить вместе с переходом образа и деплоя на uv (этапы 3, 5).
- [x] **Python 3.12 везде:** `.python-version`, `requires-python = ">=3.12,<3.13"`, `.venv` пересоздать через `uv sync`, Dockerfile, версия в CLAUDE.md.
- [x] **Владелец — настройка `OWNER_VK_IDS`** вместо захардкоженного `498417215` (`scripts/backup_db.py`). Используется для технических уведомлений и прав владельца.
- [x] **Управление пользователями только владельцу:** `/addadmin`, `/addseller`, `/removeuser`, `/users` проверяют `OWNER_VK_IDS`, а не роль `ADMIN`. Логические админы сохраняют бизнес-права. Первого админа владелец создаёт через бота → удалить `scripts/create_admin.py`.
- [x] **Безопасность `/payments`:** `COOKIE_SECRET` обязателен (не выводится из пароля), `secrets.compare_digest` вместо `==`, cookie `secure=True` (отключаемо настройкой для локального HTTP), `limit_req` на `/payments/login` в nginx на хосте (в `deploy/tickets-nginx.conf`; на сервере применить вручную — там файл дополнен certbot). Учёток в вебе не будет — один админский режим.
- [x] **Единое логирование:** одна `setup_logging()` для бота, веба и задач; только stdout; уровень `LOG_LEVEL` (по умолчанию `INFO`); текстовый формат `время уровень модуль: сообщение`; убрать остальные `basicConfig`, `print` в боте → `logger`.
- [x] **Показ времени в Europe/Moscow** на странице оплат (сейчас UTC выдаётся за московское). Полный переход на aware-даты — на этапе 1 (→ Даты).
- [x] **Уборка:** удалить `tickets.db~`, `migrations/001_add_payment_amount_fields.sql`, `test_db.py` (нужное — в тесты), `REFACTORING_PLAN.md`, `SQLITE_MIGRATION.md`, `README_MODELS.md` (полезное про сессии — в README/CLAUDE.md), `DB_SCHEMA.md`, `.planning/`. `TZ.md` → `docs/`.
- [x] **Починить 2 падающих теста:** `test_redis_fsm` (нужен Redis), `test_negative_seat`.
- [x] **ruff + pre-commit:** ruff как линтер и форматтер (умеренный набор правил), одно автоформатирование всего кода до рефакторинга; pre-commit с локальными хуками `uv run ruff` (версия из `uv.lock`); настройки в `pyproject.toml`; `.vscode/settings.json` для Cursor (ruff-форматтер, format on save, fixAll/organizeImports, `ruff.importStrategy = fromEnvironment`).

## Этап 1. Postgres

- [x] **Драйвер `psycopg` (sync).** Async — на этапе 7.
- [x] **Частичные индексы `seat_assignments` — добавить `postgresql_where`.** Без этого уникальный индекс «одно активное назначение на место» станет обычным UNIQUE, и освобождённое место нельзя будет забронировать снова. (`app_users_vk_user_id_uniq` условие на Postgres не нужно — UNIQUE и так допускает много NULL.)
- [x] **Одна активная бронь на покупателя:** частичный уникальный индекс `reservations (buyer_vk_user_id) WHERE state = 'active'`. Сейчас гонка может создать две активные брони, после чего `get_active_reservation` для клиента падает навсегда.
- [x] **Удалить `seat_assignments_row_seat_idx`** — дубликат `seat_assignments_one_active_per_seat`.
- [x] **Удалить модель и таблицу `ReconcileCheckpoint`** до создания схемы в Postgres (не используется; убрать и из CLAUDE.md).
- [x] **Enum-колонки → `VARCHAR` + CHECK:** `Enum(..., native_enum=False, create_constraint=True, length=32, values_callable=lambda e: [m.value for m in e])`. Хранить **значения** (`paid`), а не имена (`PAID`, как сейчас). CHECK на геометрию зала (`row 1–24`, `seat 1–28`) оставляем как страховку — при смене зала править вместе с `layout.json`.
- [x] **Даты:** `DateTime(timezone=True)` → `timestamptz`; в коде везде aware UTC (→ Даты).
- [x] **Убрать SQLite-специфику:** `PRAGMA foreign_keys`, `check_same_thread`, `_run_migrations()`.
- [x] **Скрипт переноса SQLite → Postgres** (одноразовый, на SQLAlchemy): схема из моделей (`create_all()`), копирование в порядке зависимостей (пользователи → брони → места → оплаты → аудит), наивные даты как UTC, enum-имена → значения, пропуск `reconcile_checkpoints`, сверка количества строк по таблицам, сдвиг sequence. После переезда удалить.
- [x] **Тесты на Postgres** через testcontainers (полная реорганизация тестов — этап 8).

## Этап 2. Alembic

- [x] Базовая миграция по схеме Postgres (схема совпадает с `create_all()` по `pg_dump --schema-only`); на существующей базе — `alembic stamp head`. Конфиг в `[tool.alembic]` в `pyproject.toml`, тесты накатывают схему миграциями и проверяют `alembic check`.
- [x] Убрать `init_db()` / `create_all()` из рантайма.
- [x] Правила миграций — expand/contract, только вперёд (→ Миграции и совместимость); краткая выжимка в CLAUDE.md.

## Этап 3. Docker / Compose

- [x] **Образ:** Python 3.12, `uv sync --frozen --no-dev` (вместо `pip install -r requirements.txt`), пользователь не root, пакет `tzdata`.
- [ ] **Клиент `pg_dump` в образе** из официального apt-репозитория PostgreSQL той же мажорной версии, что сервер (для бэкапов, этап 4).
- [ ] **Сервисы:** `web`, `bot`, `postgres`, `redis`, `db-backup` (разовый), `migrate` (разовый), `cron`. Сейчас есть `postgres`, `redis`, `migrate`, `web`, `bot`.
- [ ] **Порядок старта:** `db-backup` → `migrate` (`alembic upgrade head`, `restart: "no"`) → `web`, `bot`, `cron` через `condition: service_completed_successfully`.
- [ ] **Healthcheck** у каждого сервиса, `depends_on` с условиями, `restart: unless-stopped` для постоянных сервисов.
- [x] **Порты только на `127.0.0.1`** (nginx на хосте проксирует).
- [x] **Ротация логов Docker:** драйвер `local`, `max-size: 10m`, `max-file: 5` для всех сервисов (якорь `x-logging`).
- [ ] **Redis:** пароль, `appendonly yes`, named volume. TTL для FSM не используем.
- [x] **`/health` в вебе** (приложение + `SELECT 1`) и healthcheck по нему (перенесено с этапа 5).
- [x] **Dev-режим:** `compose.dev.yaml` только с отличиями (`--reload`/`fastapi dev`, порты, `develop.watch`), подключается через `COMPOSE_FILE=compose.yaml:compose.dev.yaml` в локальном `.env`; `docker compose watch` — `sync` кода, `rebuild` при изменении `pyproject.toml` / `uv.lock`. `compose.override.yaml` не используем. Бот в dev — за профилем `bot` (в локальном `.env` боевой токен); порт Postgres публикуется только в dev.
- [ ] **Тестовое VK-сообщество** для локальной разработки (свой токен).

## Этап 4. Фоновые задачи

- [x] **Сервис `cron`:** `supercronic` + `jobs/crontab` в образе (`deploy/` не попадает в образ), `CRON_TZ=Europe/Moscow`.
- [x] **Задачи как модули** — пока пакет `jobs/` в корне (`python -m jobs.…`), на этапе 7 переезжает в `tickets/jobs/`; с общим конфигом и логированием; без `sys.path.insert` и `load_dotenv`; ошибка → лог + ненулевой код выхода + уведомление владельцу.
- [x] **Напоминания о должниках:** `0 20 */3 * *` (раз в 3 дня в 20:00; сейчас в `setup-cron.sh` ошибочно ежедневно).
- [x] **Бэкапы** (→ Бэкапы): задача `jobs.backup` — по cron раз в день в 04:00 и сервисом `db-backup` перед миграциями (только если есть ненакатанные миграции); ротация 14 регулярных + 14 предмиграционных; отправка в VK отключается `BACKUP_SEND_TO_VK=false`.
- [x] **`cron` в dev** — за профилем `cron` (в локальном `.env` боевой токен).
- [x] Процедура восстановления описана в README и один раз проверена руками (2026-11-14, в отдельную базу `restore_check`).

## Этап 5. Переезд сервера и уборка легаси

- [x] **Новый `deploy/deploy.sh`:** `ssh` → `git pull --ff-only` → `docker compose up -d --build --wait` → `docker compose ps` → `docker image prune -f`. Написан и проверен локально (`--wait` падает на unhealthy), на сервере ещё не запускался; первичная настройка и переезд — README, «Сервер». Отката пока нет — чиним вперёд. Перед первым запуском: `mkdir backups` от пользователя с uid 1000 (= `app` в образе) — иначе Docker создаст каталог от root и `db-backup` не сможет писать.
- [x] **Удалить:** `tickets-*.service`, `install.sh`, `aliases.sh`, `bootstrap.sh`, `setup-cron.sh`, `setup-backup-cron.sh`, `web/run.sh`, `deploy/README.md` (→ README), сгенерированный `requirements.txt` и хук `uv-export` в `.pre-commit-config.yaml`. Системный `redis-server` на сервере больше не нужен. **Остаются:** `deploy/deploy.sh`, `deploy/setup-ssl.sh` (certbot) и `deploy/tickets-nginx.conf` — nginx и сертификат на хосте.
- [x] **Секреты** — Compose `secrets:` (→ Секреты и доступы) вместе с конфигом на `pydantic-settings` (перенесён сюда с этапа 7). Несекретные настройки окружения (`VK_GROUP_ID`, `OWNER_VK_IDS`) — в необязательном `.env`, а не в `compose.yaml`: они разные у сервера и локально.
- [x] **Мониторинг:** heartbeat цикла Long Poll для бота (файл + healthcheck); `notify_owner()` при ошибках бота и 500 в вебе, одинаковые — не чаще раза в 10 минут (в памяти процесса; через Redis — этап 7). Внешнюю проверку доступности пока не делаем.
- [x] **Бот остаётся на Long Poll**; источник событий заменяемый (Callback — в бэклоге).

## Этап 6. Логические баги — требования к новым сервисам

Схемные исправления сделаны на этапе 1. Остальное выполняется на этапе 7 при переписывании `bot/utils/db.py`, чтобы не трогать код дважды:

- [ ] **Атомарность:** сейчас `add_seats_to_reservation` делает 3 коммита, ещё 7 функций — по 2. Решается правилом «сервисы не коммитят» (→ Архитектура).
- [ ] **Гонка при оплате:** `record_payment` выбирает BOOKED-места без блокировки → `SELECT … FOR UPDATE`.
- [ ] **Конфликт мест при гонке** → `SeatOccupiedError`, а не общий `DatabaseError`.
- [ ] **Нельзя добавлять места в неактивную бронь**; FSM проверяет актуальность брони на каждом шаге.
- [ ] **Аудит:** добавить отметку «проверено» в вебе и управление пользователями; актор `web_admin` + IP клиента (`X-Real-IP`); входы в `/payments` не аудируем; `action_type` — enum-константы; запись в той же транзакции.
- [ ] **Страница оплат:** только кнопка «Проверено» для всех неотмеченных; чекбоксы и `/payments/{id}/verify` удалить; `/payments/checkpoint` → `/payments/verify-all`; одна запись аудита со списком id.
- [ ] **Проверить:** какие действия обновляют `last_activity_at`; поведение бота при недоступном Redis; `cancel_handler`.
- [ ] **Странности, найденные тестами сценариев** (сейчас зафиксированы как есть): после удаления места бот шлёт три сообщения, включая «Места забронированы… Спасибо за бронь!»; на шагах «Удалить» (ряд) и «Резерв → Добавить/Удалить» показывается главная клавиатура вместо кнопок шага; `/cancel` посреди брони удаляет состояние, а из меню брони ставит `idle`; на подтверждение отмены брони «Да» не работает — только «Подтвердить».

## Этап 7. Архитектура

Делается вместе с этапом 6, по шагам — каждый своей веткой и вливанием в master: (1) тесты сценариев бота с подменённым VK (пункт этапа 8, подтянут сюда — страховка переписывания); (2) пакет `tickets/`; (3) сервисы + unit of work + исправления этапа 6; (4) async SQLAlchemy; (5) бот; (6) веб; (7) mypy и «проверить» из этапа 6.


- [ ] **Пакет `tickets/`** с подпакетами и правилом зависимостей «только вниз» (→ Архитектура); `package = true` в `[tool.uv]` (перенесено с этапа 0 — до появления папки `tickets/` включить нельзя).
- [ ] **Сервисы** из `bot/utils/db.py`: `users`, `reservations`, `seats`, `payments`, `reports`, `audit`.
- [ ] **Транзакции:** сервисы не коммитят; unit of work на границе; побочные эффекты после коммита; тест-страж.
- [ ] **Async SQLAlchemy на psycopg 3 (async-режим)** — тот же драйвер, что у Alembic и скриптов, вместо asyncpg; вместе с переходом на сервисы: `AsyncSession`, явные `selectinload`, async-роуты, `pytest-asyncio`.
- [ ] **Бот:** тонкие `handlers/`, сценарии в `flows/`, VK-специфика в `vk.py`, права — декораторы в `auth.py`. Отправка сообщений — через `vk.py` с уникальным `random_id` (сейчас `message.answer()` шлёт `random_id=0`, и VK не отбрасывает дубли при ретраях).
- [ ] **FSM:** pydantic-контекст, `BotState` вместо строк, проверка актуальности брони, без TTL, совместимость форматов (→ Миграции и совместимость).
- [ ] **Веб:** `main` / `deps` / `routers` / `filters`, тонкие роуты, `require_admin` как dependency, Jinja, Chart.js с фиксированной версией (сейчас плавающая `@4` с CDN).
- [ ] **`notify_owner()`** и обработчики ошибок бота/веба/задач.
- [ ] **mypy:** строго для `services/` и `models/`, мягко для остального; хук в pre-commit.

## Этап 8. Качество и CI

- [ ] **Тесты** (→ Тесты): `tests/unit`, `tests/integration`, `tests/test_guards.py`; testcontainers; схема через Alembic; откат транзакции на тест.
- [ ] **CI, шаг 1** — на каждый push/PR: `ruff check`, `ruff format --check`, `mypy`, `pytest`, `alembic check`.
- [ ] **CI, шаг 2** — только когда шаг 1 стабилен: push в `master` → образ `linux/amd64` в GHCR (тег по коммиту) → деплой по SSH (`docker compose pull && up -d`). Сервер перестаёт собирать образ; откат кода — прошлый тег.
- [ ] **`README.md`** в корне (→ README); CLAUDE.md ссылается на него и не дублирует.

## Бэклог (не приоритет)

- [ ] **Watchdog** — задача в `cron` раз в несколько минут: `web /health`, heartbeat бота, Postgres/Redis, место на volume; при **смене** статуса — `notify_owner()` (прошлый статус в Redis), без `docker.sock`. Не заметит падение всего сервера или самого `cron`; при необходимости — Uptime Kuma.
- [ ] **Callback API для бота** вместо Long Poll (→ Callback API).

---

# Справка

## Архитектура

### Структура
```
tickets/
  config.py     pydantic-settings
  logging.py    setup_logging()
  time.py       utcnow(), перевод в DISPLAY_TZ
  db.py         engine, фабрика сессий, unit_of_work()
  hall.py       геометрия зала из layout.json (сейчас bot/utils/layout.py)
  notify.py     notify_owner(): сообщения и файлы владельцу в VK
  models/       ORM-модели и enum'ы
  services/     users, reservations, seats, payments, reports, audit
  bot/          handlers/, flows/, vk.py, fsm/, auth.py, keyboards.py, texts.py
  web/          main.py, deps.py, routers/, filters.py, templates/, static/
  jobs/         debtors, backup
migrations/     Alembic
tests/          unit/, integration/, test_guards.py
```
Запуск: `python -m tickets.bot`, `python -m tickets.jobs.debtors`, `uvicorn tickets.web.main:app`.

### Правила зависимостей
```
bot, web, jobs         ← интерфейсы: ввод → сервисы → ответ
      ↓
services               ← бизнес-правила
      ↓
models, db, hall       ← данные
      ↓
config, logging, time  ← ни от чего не зависят
```
- Веб и задачи не импортируют ничего из `bot/`.
- Между сервисами без циклов: `payments`, `reports` → `reservations` → `seats`, `users` → `audit`. Цикл — сигнал опустить общую часть ниже. Общего `utils.py` для бизнес-логики нет.

### Сервисы
- Модули с функциями, `session` — первый аргумент. Без слоя репозиториев: SQLAlchemy напрямую; разросшиеся запросы — в модуль `queries` этого сервиса.
- Переиспользование: внутри сервиса — приватные функции модуля; между сервисами — вызов публичной функции в той же сессии. Общая функция живёт в сервисе своей сущности («освободить места» — `seats`).
- Сервисы ничего не знают о VK: получают обычные значения, а не объект сообщения vkbottle.
- Распределение: `users` (VK- и App-пользователи, роли); `reservations`; `seats` (включая резервы); `payments` (включая данные страницы оплат); `reports` (должники, напоминания, данные страниц «зал» и «день концерта»); `audit` (`audit.log(session, actor, action, entity, payload)`).

### Транзакции
- Сервисы **никогда** не вызывают `commit()` / `rollback()`; для получения `id` — `session.flush()`.
- Транзакцию открывает и завершает граница: веб — FastAPI-dependency на запрос; бот — явный `async with unit_of_work() as session:` в хендлере (не middleware на весь хендлер); задачи — обёртка запуска. Успех → COMMIT, исключение → ROLLBACK.
- Побочные эффекты (сообщения VK, `notify_owner`, файлы) — только после коммита.
- Внутри транзакции нет сетевых вызовов: сначала данные из VK, потом короткая транзакция, потом ответ.
- Тест-страж: падает при `.commit(` / `.rollback(` в `tickets/services/`.

### Конфиг
- `pydantic-settings`. Умолчания в коде — только несекретное и одинаковое везде (`LOG_LEVEL=INFO`, `DISPLAY_TZ=Europe/Moscow`, …). Секреты и всё, что зависит от окружения, — без умолчаний: приложение не стартует, если их нет.
- Приоритет: env > `.env` > `secrets_dir` (`/run/secrets`) > умолчание. Типы валидируются (`OWNER_VK_IDS: list[int]`), секреты — `SecretStr`.
- БД: поля `postgres_host` (умолчание `localhost`), `postgres_port`, `postgres_db`, `postgres_user`, `postgres_password` (секрет); `database_url` собирается в коде. В Compose `POSTGRES_HOST=postgres`.
- Константы предметной области (геометрия зала, тексты) — не конфиг.

### notify
- `notify_owner(text)` и отправка файла — владельцам из `OWNER_VK_IDS` через VK API с токеном сообщества, из любого процесса.
- Вызывают только интерфейсные слои: обёртка задач (падение, файл бэкапа), глобальный обработчик ошибок бота, обработчик 500 в вебе, позже watchdog.
- Ограничение частоты одинаковых ошибок через Redis. Сам `notify_owner` никогда не бросает исключений.

### Бот
- `handlers/` — тонкие: ввод → сценарий → ответ. `flows/` — сценарии диалога (пересылка, оплата, переключение клиента): шаги FSM + вызовы сервисов в unit of work. `vk.py` — разбор пересылки/ответа/ссылки, имя через VK API, время сообщения. `auth.py` — `@requires(Role.SELLER)`, `@owner_only`.
- `forwarded_message_handler` (341 строка) распадается на разбор входа и небольшие функции сценария. Хендлеры не вызывают и не импортируют друг друга.
- Источник событий заменяемый: сейчас Long Poll, Callback — в бэклоге.

### FSM
- Контекст — pydantic-модели в Redis (JSON) вместо плоского словаря из ~23 ключей: `Client` (`reservation_id`, `buyer_id` — id в БД, `buyer_vk_id` — id в VK, `buyer_name`), `PendingSwitch` вместо 8 полей `pending_*`, `SavedState` вместо `original_state` + `original_context`.
- Состояния — `BotState` везде, без `str(...)` и `split(":")`.
- Каждый шаг с бронью проверяет через сервис, что бронь существует и активна; иначе — сброс и сообщение продавцу. TTL не используем.

### Веб
```
web/
  main.py      приложение, обработчик 500 → лог + notify_owner
  deps.py      сессия (unit of work на запрос), require_admin, client_ip
  routers/     public.py (/, favicon), concert_day.py, payments.py, health.py
  filters.py   время в DISPLAY_TZ, деньги, диапазоны мест
  templates/   static/
```
Роуты тонкие, данные — из сервисов `reports` и `payments`; остаёмся на Jinja (SSR).

## Даты

Сейчас: наивное UTC (`datetime.utcnow()`, `utcfromtimestamp`), страница оплат показывает UTC как московское, бэкап именуется локальным временем сервера.

1. В коде везде aware UTC: `utcnow()` → `datetime.now(UTC)`, для VK — `datetime.fromtimestamp(ts, UTC)`.
2. В моделях `DateTime(timezone=True)` → `timestamptz`. Вместе с Postgres — SQLite пояса не хранит.
3. Бизнес-логика (должники, «N дней») — только в UTC.
4. Пересчёт в `DISPLAY_TZ` (Europe/Moscow) только при показе: Jinja-фильтр, форматирование в боте.
5. Сервису `cron` — `TZ=Europe/Moscow` для расписания; в образе — пакет `tzdata`.
6. При переносе наивные значения считаем UTC.

## Миграции и совместимость

- **Expand/contract:** каждая миграция совместима с предыдущей версией кода. Новая колонка — nullable или с `server_default`. Переименование — новая колонка, запись в обе, перенос данных, переключение чтения; старая удаляется через релиз. Удаление колонки — только после релиза, где код её не использует. `NOT NULL` — после заполнения данных.
- **Contract-миграции** (удаление, `NOT NULL`, сужение CHECK) явно помечаются и выходят на релиз позже кода, который перестал от них зависеть.
- **Только вперёд:** откат = откат образа, база остаётся. Downgrade-миграции пишем, но в проде не используем. При проблеме по возможности чиним вперёд.
- **Страховка:** `db-backup` (`pg_dump`) перед каждым `migrate`.
- **Enum в VARCHAR:** новое значение — сначала код умеет его читать и CHECK расширен, в следующем релизе код начинает его писать. Удаление — наоборот: перестать писать → перенести данные → сузить CHECK.
- **FSM-контекст (без миграций), schema-on-read:** новые поля только с умолчаниями; `extra="ignore"` — старый код игнорирует новые поля; переименования через `AliasChoices` в два шага; поле версии `v` + апгрейдеры для несовместимых изменений. Ошибка чтения или неизвестное состояние → лог, сброс в IDLE, «начните заново» — никогда не падение.
- **Краевые случаи:** старый код работает с новой схемой во время деплоя (поэтому expand/contract нужен и без откатов); Postgres выполняет миграцию в транзакции, кроме `CREATE INDEX CONCURRENTLY`; миграции данных — отдельно от схемы и идемпотентны; конфликт голов Alembic ловит CI.

## Бэкапы

- Одна задача `jobs.backup` (на этапе 7 — `tickets.jobs.backup`), два повода: по `cron` раз в день (частота — строка в crontab) с отправкой владельцу в VK (отключается настройкой) и сервисом `db-backup` перед `migrate` (`--reason pre-migrate`, без отправки).
- `pg_dump -Fc`, восстановление через `pg_restore`. Хранение — bind mount `./backups`; ротация в задаче: последние N регулярных и N предмиграционных.
- Не делаем: шифрование, S3, WAL / point-in-time recovery. Дамп содержит персональные данные — уходит только владельцу.

## Секреты и доступы

- **Секреты приложения:** Compose `secrets:` — файлы в `secrets/` (в `.gitignore`) на сервере и локально, монтируются в `/run/secrets/<имя>`, pydantic-settings читает через `secrets_dir`. Postgres — `POSTGRES_PASSWORD_FILE`, Redis — пароль из файла в `command:`. Файлы читаемы пользователем `app`. Список ожидаемых секретов — в репозитории. Несекретное — `environment:` в `compose.yaml`. На сервер кладутся вручную один раз; CI их не получает.
- **Доступы:**
  - мой компьютер → сервер: `Host tickets` в `~/.ssh/config`;
  - сервер → GitHub: deploy key только на чтение (уже настроен);
  - GitHub Actions → сервер (с CI шаг 2): отдельная пара ключей; приватный ключ и `known_hosts` — в GitHub Secrets; публичный — в `authorized_keys` с `command="…"` (только деплой-скрипт), `no-pty`, `no-port-forwarding`;
  - сервер → GHCR: токен с `read:packages`, `docker login ghcr.io`.

## Тесты

- `tests/unit/` (без БД и сети), `tests/integration/` (сервисы на Postgres, FSM на Redis, веб-роуты через `httpx.AsyncClient`), `tests/test_guards.py`. `bot/tests/` и корневой `conftest.py` переезжают сюда.
- Postgres и Redis — testcontainers; на SQLite сервисы не тестируем. Схема — `alembic upgrade head`; изоляция — транзакция на тест с откатом.
- Приоритет: сервисы (двойное бронирование, частичная оплата, отмена с оплаченными местами, одна активная бронь, должники) → конкурентность оплат → сценарии бота с подменённым VK → веб-роуты.
- `pytest-asyncio` (auto), `pytest-cov` без жёсткого порога.

## README

Один `README.md` в корне: что за проект; запуск для разработки (Docker, `secrets/`, тестовое VK-сообщество, `docker compose watch`; без Docker — `uv sync`); секреты и настройки; тесты и линтеры (`uv run pytest`, `pre-commit install`); деплой и первичная настройка сервера; структура `tickets/` и правила.

## Callback API (бэклог)

- vkbottle 4.6 поддерживает: `BotCallback` + `bot.setup_webhook()` (регистрирует callback-сервер, возвращает код подтверждения и secret), `bot.process_event(event)` — те же роутер и хендлеры.
- Сделать самим: эндпоинт (`confirmation`, проверка `secret`, быстрый `ok` и обработка в фоне — иначе VK повторит событие), дедупликация по `event_id` в Redis, включить нужные типы событий (`setup_webhook` включает только `message_new`).
- Отдельное тестовое сообщество обязательно: иначе локальный поллинг и прод-callback обработают одно сообщение дважды.
- Бот — свой сервис с FastAPI (`/vk/callback`, `/health`), nginx проксирует `/vk/callback`. Healthcheck: `/health` + проверка статуса через `groups.getCallbackServers`.
