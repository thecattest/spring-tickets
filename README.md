# Tickets

Билеты на концерт: VK-бот для билетёров (брони, оплаты) и веб — публичная схема зала и страница оплат для админа. Python 3.12, PostgreSQL, Redis, Docker Compose.

Разработка, команды и устройство проекта — в [CLAUDE.md](CLAUDE.md), план работ — в [ROADMAP.md](ROADMAP.md). Полный README — ROADMAP, раздел «README».

## Сервер

Всё работает в Docker Compose (`compose.yaml`): `postgres`, `redis`, `web`, `bot`, `cron`, разовые `db-backup` и `migrate`. На хосте — только Docker и nginx (HTTPS, прокси на `127.0.0.1:8000`). Каталог проекта — `~/spring-tickets`, SSH-хост на своей машине — `tickets` в `~/.ssh/config`.

### Обновление

С локальной машины:

```bash
bash deploy/deploy.sh
```

`git pull` → сборка → `db-backup` (если есть миграции) → `migrate` → перезапуск изменившихся сервисов → ожидание healthy. Не поднялось — скрипт падает с ошибкой, работающие контейнеры старой версии остаются.

### Первичная настройка (один раз)

1. **Docker Engine и плагин Compose** — по [официальной инструкции для Ubuntu](https://docs.docker.com/engine/install/ubuntu/) (apt-репозиторий Docker). Пользователя — в группу `docker`, перелогиниться:

   ```bash
   sudo usermod -aG docker "$USER"
   docker compose version
   ```

2. **Код** — клонировать с deploy key (только чтение):

   ```bash
   git clone git@github.com:thecattest/spring-tickets.git ~/spring-tickets
   cd ~/spring-tickets
   ```

3. **Каталоги.** Процессы в контейнерах работают от пользователя `app` с uid 1000 — ему нужно читать секреты и писать бэкапы. Если `id -u` на сервере не 1000, после шага 4 выполнить `sudo chown -R 1000:1000 secrets backups`.

   ```bash
   mkdir -m 700 secrets
   mkdir backups
   ```

4. **Секреты** — по файлу на секрет, только значение (список — `secrets:` в `compose.yaml`):

   ```bash
   for name in postgres_password redis_password cookie_secret; do
     python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "secrets/$name"
   done
   nano secrets/vk_bot_token        # токен сообщества VK (Управление → Работа с API)
   nano secrets/payments_password   # пароль страницы /payments
   chmod 600 secrets/*
   ```

   `postgres_password` применяется только при создании пустого volume базы. Сменить потом — `ALTER USER tickets PASSWORD '…'` в базе и новый файл.

5. **`.env`** — несекретные настройки этого сервера (`COMPOSE_FILE` не задавать — на сервере только `compose.yaml`):

   ```bash
   cat > .env <<'EOF'
   VK_GROUP_ID=<id сообщества>
   OWNER_VK_IDS=<ваш VK ID>
   EOF
   chmod 600 .env
   ```

6. **nginx** — на хосте, не в Compose. Сайт из `deploy/tickets-nginx.conf`: HTTP на 80, прокси на `127.0.0.1:8000` (`web`), не больше 5 попыток входа в минуту на `/payments/login`.

   ```bash
   sudo apt install -y nginx
   sudo cp deploy/tickets-nginx.conf /etc/nginx/sites-available/tickets
   sudo ln -sf /etc/nginx/sites-available/tickets /etc/nginx/sites-enabled/tickets
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx
   ```

7. **HTTPS (Let's Encrypt, certbot)** — после того как A-запись домена указывает на сервер и сайт открывается по HTTP (Let's Encrypt проверяет домен запросом на порт 80):

   ```bash
   bash deploy/setup-ssl.sh
   ```

   Скрипт ставит `certbot` и `python3-certbot-nginx`, проверяет, что домен резолвится (утилита `host`), выпускает сертификат через `certbot --nginx` и проверяет автопродление (`certbot renew --dry-run`). Домен задан в начале скрипта (`DOMAIN`, в punycode).

   - `certbot --nginx` **сам дописывает** серверную копию конфига `/etc/nginx/sites-available/tickets`: `listen 443 ssl`, пути к сертификату, редирект с HTTP на HTTPS. Поэтому после этого шага файл из репозитория поверх серверного **не копировать** — изменения из `deploy/tickets-nginx.conf` переносить в серверный файл руками и проверять `sudo nginx -t && sudo systemctl reload nginx`.
   - Продление — автоматически: пакет certbot ставит systemd-таймер (`systemctl list-timers | grep certbot`), сертификаты на 90 дней продлеваются заранее, nginx перезагружается сам. Проверить вручную — `sudo certbot renew --dry-run`, посмотреть сертификаты — `sudo certbot certificates`.
   - `COOKIE_SECURE` по умолчанию `true`: cookie страницы оплат передаётся только по HTTPS, так что вход в `/payments` работает только после этого шага.

8. **Первый запуск** — с локальной машины `bash deploy/deploy.sh`. Пустая база получит схему от `migrate`.

### Переезд со старого деплоя (один раз)

Старый деплой — systemd user-сервисы, venv, SQLite `data/tickets.db`, crontab, системный `redis-server`.

1. Остановить старое. Бот — обязательно: два бота с одним токеном делят события сообщества.

   ```bash
   systemctl --user disable --now tickets-bot tickets-web
   rm ~/.config/systemd/user/tickets-*.service && systemctl --user daemon-reload
   crontab -e   # удалить строки tickets: debtor reminders / db backup
   ```

   Из `~/.bashrc` удалить блок алиасов `systemctl --user` от старого `deploy/aliases.sh` — между строками `# tickets-aliases` и `# end tickets-aliases`.

2. Скопировать `data/tickets.db` в надёжное место (это исходные данные для переноса).
3. `git pull` и шаги 1, 3–5 первичной настройки. nginx и сертификат на сервере уже есть — не переустанавливать, а в серверном `/etc/nginx/sites-available/tickets` (его правил certbot) руками: `proxy_pass` на `http://127.0.0.1:8000` вместо 8080 и блок `limit_req` для `/payments/login` из `deploy/tickets-nginx.conf`; затем `sudo nginx -t && sudo systemctl reload nginx`.
4. Перенести данные из SQLite в пустой Postgres (скрипт сам создаёт схему и сверяет количество строк):

   ```bash
   docker compose up -d postgres
   docker compose run --rm -v ./data:/code/data web python scripts/migrate_sqlite_to_postgres.py data/tickets.db
   ```

5. С локальной машины `bash deploy/deploy.sh`, проверить сайт, `/payments` и ответ бота.
6. Убрать остатки: системный Redis (`sudo apt remove redis-server`), `~/spring-tickets/.venv`, `~/spring-tickets/logs`, старые бэкапы `~/tickets-backup` — когда новые бэкапы приходят.

### Повседневные команды

```bash
docker compose ps                       # состояние и healthcheck сервисов
docker compose logs -f --tail 100 bot   # логи (web, bot, cron, postgres, …)
docker compose restart bot
docker compose exec redis redis-cli     # пароль подставится сам (REDISCLI_AUTH)
docker compose exec postgres psql -U tickets
```

## Бэкапы

- **Регулярные:** сервис `cron`, каждый день в 04:00 по Москве (`src/tickets/jobs/crontab`). Дамп уходит владельцам (`OWNER_VK_IDS`) в VK; отключить — `BACKUP_SEND_TO_VK=false`.
- **Перед миграциями:** сервис `db-backup` при `docker compose up`, только если есть ненакатанные миграции.
- Файлы — `./backups/tickets-<regular|pre-migrate>-<UTC-время>.dump` (формат `pg_dump -Fc`), хранятся последние 14 каждого вида (`BACKUP_KEEP`).
- Сделать бэкап вручную (без отправки в VK):

  ```bash
  docker compose run --rm -e BACKUP_SEND_TO_VK=false cron python -m tickets.jobs.backup
  ```

Дамп содержит персональные данные покупателей — не передавать никому, кроме владельца.

## Восстановление из бэкапа

`pg_restore` запускается внутри контейнера `postgres` (нужная версия, вход без пароля по локальному сокету), файл передаётся с хоста через stdin.

1. Остановить всё, что пишет в базу:

   ```bash
   docker compose stop web bot cron
   ```

2. На всякий случай сохранить текущее состояние:

   ```bash
   docker compose run --rm -e BACKUP_SEND_TO_VK=false cron python -m tickets.jobs.backup
   ```

3. Восстановить. `--clean --if-exists` удаляет существующие объекты перед созданием, `--single-transaction` — либо всё, либо ничего:

   ```bash
   docker compose exec -T postgres pg_restore -U tickets -d tickets \
     --clean --if-exists --no-owner --single-transaction < backups/<файл>.dump
   ```

4. Запустить обратно. Дамп содержит ревизию Alembic: если он старше текущего кода, `migrate` докатит схему до актуальной (перед этим `db-backup` сделает ещё один дамп):

   ```bash
   docker compose up -d
   ```

Проверить дамп, не трогая рабочую базу, — восстановить в отдельную:

```bash
docker compose exec -T postgres createdb -U tickets restore_check
docker compose exec -T postgres pg_restore -U tickets -d restore_check --no-owner --single-transaction < backups/<файл>.dump
docker compose exec -T postgres psql -U tickets -d restore_check -c "select count(*) from reservations"
docker compose exec -T postgres dropdb -U tickets restore_check
```

Процедура проверена 2026-11-14: восстановление в отдельную базу и повторное с `--clean` поверх заполненной, данные совпали по всем таблицам.
