"""
Бэкап базы: pg_dump в BACKUP_DIR с ротацией.

    python -m jobs.backup                       # регулярный (cron): дамп + отправка владельцу
    python -m jobs.backup --reason pre-migrate  # перед миграциями (сервис db-backup)

Регулярный бэкап уходит владельцам в VK, если BACKUP_SEND_TO_VK не false.
Предмиграционный делается, только если есть ненакатанные миграции, и не
отправляется. Хранятся последние BACKUP_KEEP (по умолчанию 14) дампов
каждого вида; файлы tickets-<reason>-<UTC-время>.dump.

Восстановление: pg_restore --clean --if-exists -d <url> <файл> (см. README).
Дамп содержит персональные данные — только владельцу.
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL, make_url

from database import DATABASE_URL, PROJECT_ROOT, alembic_config, engine
from jobs.runner import run_job
from notify import notify_owner
from timeutils import utcnow

logger = logging.getLogger("jobs.backup")

REASONS = ("regular", "pre-migrate")
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", PROJECT_ROOT / "backups"))
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "14"))
BACKUP_SEND_TO_VK = os.getenv("BACKUP_SEND_TO_VK", "true").lower() != "false"


def has_pending_migrations() -> bool:
    """Отстаёт ли ревизия базы от head (то есть migrate что-то накатит)."""
    heads = set(ScriptDirectory.from_config(alembic_config()).get_heads())
    with engine.connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    return current != heads


def rotate(directory: Path, reason: str, keep: int) -> list[Path]:
    """Удалить старые дампы вида reason, оставив keep последних. Возвращает удалённые."""
    # Имя содержит время в формате ГГГГММДД-ЧЧММСС — сортировка по имени = по времени
    dumps = sorted(directory.glob(f"tickets-{reason}-*.dump"))
    removed = dumps[:-keep] if keep > 0 else dumps
    for path in removed:
        path.unlink()
    return removed


async def pg_dump(target: Path) -> None:
    url = make_url(DATABASE_URL)
    # pg_dump понимает libpq-URL без драйвера SQLAlchemy (+psycopg). Пароль —
    # через PGPASSWORD, а не в URL: аргументы процесса видны в ps
    # (URL.set(password=None) пароль не убирает — None там значит «не менять»)
    libpq_url = URL.create(
        "postgresql", url.username, None, url.host, url.port, url.database, url.query
    ).render_as_string()
    env = {**os.environ, "PGPASSWORD": url.password or ""}

    # Сначала во временный файл: оборванный дамп не попадёт в ротацию
    partial = target.with_suffix(".partial")
    process = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--format=custom",
        f"--file={partial}",
        f"--dbname={libpq_url}",
        env=env,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump exited {process.returncode}: {stderr.decode().strip()}")
    partial.rename(target)


async def backup(reason: str) -> None:
    if reason == "pre-migrate" and not has_pending_migrations():
        logger.info("No pending migrations, pre-migrate backup skipped")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"tickets-{reason}-{utcnow():%Y%m%d-%H%M%S}Z.dump"
    await pg_dump(target)
    logger.info("Backup created: %s (%d KB)", target, target.stat().st_size // 1024)

    for path in rotate(BACKUP_DIR, reason, BACKUP_KEEP):
        logger.info("Old backup removed: %s", path.name)

    if reason == "regular" and BACKUP_SEND_TO_VK:
        await notify_owner(f"Бэкап БД: {target.name}", file=target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Бэкап базы (pg_dump) с ротацией")
    parser.add_argument("--reason", choices=REASONS, default="regular")
    args = parser.parse_args()
    run_job(f"backup ({args.reason})", backup(args.reason))


if __name__ == "__main__":
    main()
