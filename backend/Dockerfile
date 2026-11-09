# syntax=docker/dockerfile:1
# Build from the repository root (it needs both backend/ and frontend/):
#   docker build -f backend/Dockerfile .      (docker compose does exactly this)
FROM python:3.12-slim AS builder

ENV POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Same path in both stages so the venv's scripts keep working after COPY.
RUN python -m venv /opt/venv && pip install "poetry==${POETRY_VERSION}"
WORKDIR /build
COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry install --only main --no-root

# The web app. vite.config.ts writes the build to ../backend/app/static, i.e.
# /build/backend/app/static here.
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
# postinstall only does the iCloud .nosync step, which has no meaning in the image.
RUN npm ci --ignore-scripts
COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# A Unicode font so PDF reports can print names such as "Ọlá Adéṣọlá".
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home /app app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app backend/alembic.ini ./
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/app ./app
COPY --from=frontend --chown=app:app /build/backend/app/static ./app/static
COPY --chown=app:app backend/scripts ./scripts

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
