# syntax=docker/dockerfile:1

# Both stages use the same Python image so the virtualenv built in the first works in the second.
# To pin exactly, append @sha256:<digest> (docker buildx imagetools inspect python:3.14-slim).
ARG PYTHON_IMAGE=python:3.14-slim

# ---- Build stage: resolve and install the locked runtime dependencies ---------------------------
FROM ${PYTHON_IMAGE} AS build

# Pin uv itself; bump deliberately.
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Only the dependency manifests, so this layer is cached until they change.
# --frozen installs exactly what uv.lock says (and fails if it is out of date); --no-dev leaves
# out pylint, pytest and the other development tools.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    # google-api-python-client bundles the description of every Google API (93 MB); only YouTube is used.
    && find .venv -path '*/googleapiclient/discovery_cache/documents/*.json' ! -name 'youtube.v3.json' -delete

# ---- Runtime stage -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE}

# 99:100 is nobody:users, the account Unraid's shares use, so files the bot writes to the mapped
# data folder are already readable and writable from Windows. (Debian's "users" group is gid 100.)
ARG APP_UID=99
ARG APP_GID=100

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

WORKDIR /app

COPY --from=build /app/.venv /app/.venv

# Chromium for the tournament bracket images, plus the OS libraries it needs. Only the headless shell
# is installed: that is what launch(headless=True) runs, and the full browser would add ~600 MB. It
# lives outside any home folder so the non-root user can run it. The apt lists are removed in the
# same layer.
RUN playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

# The data folder is a mount point; the app code stays read-only to the bot user.
RUN useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin iubot \
    && mkdir -p /app/data \
    && chown ${APP_UID}:${APP_GID} /app/data

COPY iu ./iu

ENV DATA_DIR=/app/data \
    TOKEN_DIR=/app/data/token.json \
    HALLYU_ID=904751089633615972 \
    DB_PATH_BIASES=/app/data/biases.db \
    DB_PATH_BOT=/app/data/bot.db \
    DB_PATH_HALL_OF_FAME=/app/data/hall_of_fame.db \
    DB_PATH_HMAS=/app/data/hmas.db \
    DB_PATH_LISTEN_GAME=/app/data/listen_game.db \
    DB_PATH_LISTS=/app/data/lists.db \
    DB_PATH_MERCH=/app/data/merch.db \
    DB_PATH_RELEASES=/app/data/releases.db \
    DB_PATH_ROLES=/app/data/roles.db \
    DB_PATH_TOP_SONGS=/app/data/top_songs.db \
    DB_PATH_TOURNAMENTS=/app/data/tournaments.db

USER ${APP_UID}:${APP_GID}

CMD ["python", "iu/main.py"]
