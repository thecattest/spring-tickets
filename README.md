# Tickets

Билеты на концерт: VK-бот для билетёров (брони, оплаты) и веб — публичная схема зала и страница оплат для админа. Python 3.12, PostgreSQL, Redis, Docker Compose.

Разработка, команды и устройство проекта — в [CLAUDE.md](CLAUDE.md), план работ — в [ROADMAP.md](ROADMAP.md). Полный README — ROADMAP, раздел «README».

## Бэкапы

- **Регулярные:** сервис `cron`, каждый день в 04:00 по Москве (`jobs/crontab`). Дамп уходит владельцам (`OWNER_VK_IDS`) в VK; отключить — `BACKUP_SEND_TO_VK=false`.
- **Перед миграциями:** сервис `db-backup` при `docker compose up`, только если есть ненакатанные миграции.
- Файлы — `./backups/tickets-<regular|pre-migrate>-<UTC-время>.dump` (формат `pg_dump -Fc`), хранятся последние 14 каждого вида (`BACKUP_KEEP`).
- Сделать бэкап вручную (без отправки в VK):

  ```bash
  docker compose run --rm -e BACKUP_SEND_TO_VK=false cron python -m jobs.backup
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
   docker compose run --rm -e BACKUP_SEND_TO_VK=false cron python -m jobs.backup
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
