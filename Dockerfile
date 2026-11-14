FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_LINK_MODE=copy \
    PATH="/code/.venv/bin:$PATH"

# Клиент PostgreSQL (pg_dump для бэкапов) той же мажорной версии, что сервер:
# pg_dump не работает с сервером новее себя, а в Debian только 17 —
# поэтому из официального репозитория PostgreSQL (PGDG).
#
# supercronic — cron для контейнеров (сервис cron, jobs/crontab): работает без
# root и демона, пишет вывод задач в stdout. Бинарник с GitHub, проверка SHA-256
# для архитектуры сборки (TARGETARCH подставляет BuildKit: amd64 / arm64).
#
# Слой выше uv sync: меняется редко и не пересобирается при смене зависимостей.
ARG PG_MAJOR=18
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256_amd64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256_arm64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} \
    && case "$TARGETARCH" in \
        amd64) sha="$SUPERCRONIC_SHA256_amd64" ;; \
        arm64) sha="$SUPERCRONIC_SHA256_arm64" ;; \
        *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
    && echo "${sha}  /usr/local/bin/supercronic" | sha256sum -c - \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# /backups — для jobs.backup; без смонтированного каталога тоже доступен app
RUN useradd --create-home app && install -d -o app -g app /backups

# Код принадлежит app: docker compose watch (compose.dev.yaml) синхронизирует
# файлы от имени пользователя контейнера. .venv выше остаётся за root —
# зависимости приложение изменить не может.
COPY --chown=app:app . .

USER app

EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
