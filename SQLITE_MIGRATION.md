# Адаптация моделей для SQLite3 (MVP)

Модели были адаптированы для работы с SQLite3 вместо PostgreSQL.

## Изменения

### 1. Типы данных
- `BigInteger` → `Integer` (SQLite не различает размеры целых чисел)
- `JSONB` → `JSON` (SQLite не поддерживает JSONB)
- Убраны `server_default` для timestamp (SQLite работает с default на уровне Python)

### 2. ENUM типы
- Убран `type_annotation_map` из `Base` (не нужен CREATE TYPE для SQLite)
- SQLAlchemy автоматически создаст CHECK constraints для ENUM полей

### 3. Индексы
- `postgresql_where` заменен на `sqlite_where` для partial indexes
- SQLite поддерживает partial indexes с версии 3.8.0+ (присутствует во всех современных версиях Python)

### 4. database.py
- Connection string изменен на `sqlite:///tickets.db`
- Добавлен `connect_args={"check_same_thread": False}` для SQLite
- Добавлен event listener для включения `PRAGMA foreign_keys=ON` (обязательно для CASCADE deletes)

### 5. requirements.txt
- Убран `psycopg2-binary` (не нужен для SQLite)
- SQLite3 встроен в Python, дополнительные зависимости не требуются

## Что работает одинаково

- Все partial indexes (уникальность активных мест)
- Foreign keys и CASCADE deletes (после включения pragma)
- Транзакции и сессии
- Все ORM операции (queries, joins, relationships)

## Миграция на PostgreSQL (в будущем)

Когда понадобится миграция:

1. Установить `psycopg2-binary`:
   ```bash
   pip install psycopg2-binary
   ```

2. Изменить DATABASE_URL:
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@host:port/dbname"
   ```

3. Опционально вернуть `BigInteger` в моделях (если важны большие ID)

4. Заменить `sqlite_where` на `postgresql_where` в индексах (или использовать dialect-agnostic подход)

Все остальное должно работать без изменений.
