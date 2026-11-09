# LASRRA Engineering Audit System

> A transparent, tamper-evident record of device complaints, assignments, repairs and returns, visible to both the Engineering department and the units it serves.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB?logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

Full specification: [`docs/SPEC.md`](docs/SPEC.md) · What changed and when: [`docs/CHANGELOG.md`](docs/CHANGELOG.md)

---

## Table of Contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [How it works](#how-it-works)
- [Roles](#roles)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Quick start (Docker)](#quick-start-docker)
- [First admin and signing in](#first-admin-and-signing-in)
- [Local development](#local-development)
- [Testing](#testing)
- [Environment variables](#environment-variables)
- [Migrations](#migrations)
- [Security](#security)
- [Documentation](#documentation)
- [Conventions](#conventions)
- [About this project](#about-this-project)

---

## Why this exists

The Engineering department receives complaints from units about faulty systems, assigns new devices to units, repairs devices and returns them. Without a shared record, it is hard to prove who handed in what, what was found, and when it came back.

This system gives Engineering and the units **one record both sides can verify**. Every receipt, diagnosis, repair and return is logged permanently, and the unit confirms or disputes each handover.

> Repairs are done in-house and no money is recorded (SPEC v1.1 and v1.2): there is no vendor or pricing concept anywhere.

## Features

- **Complaints:** units raise tickets and follow their progress; both sides can comment
- **Device register:** every device has a system-generated asset tag, with optional serial number, searchable and with a full timeline
- **Append-only audit trail:** receipts, diagnoses, repairs and returns are permanent events; corrections are new entries, never edits
- **Two-party confirmation:** units confirm or dispute each handover; overdue confirmations are flagged, never auto-approved
- **Role-based access:** admin, engineer, unit representative and auditor, with units only seeing their own data
- **Reports:** five reports with Excel and PDF export
- **Database-enforced integrity:** audit tables reject UPDATE, DELETE and TRUNCATE in PostgreSQL itself, not just in the app
- **Accessible web app:** automated accessibility checks plus a manual checklist

## How it works

```mermaid
flowchart LR
    A[Unit raises complaint] --> B[Engineering receives device]
    B --> C[Diagnosis and repair]
    C --> D[Device returned to unit]
    D --> E{Unit confirms?}
    E -- Confirm --> F[Ticket closed]
    E -- Dispute --> G[Ticket reopened]
    G --> B
```

Every step is recorded as an event with the person who did it, the person who handed over or collected, and a server-stamped time. The exact device state machine is in [`docs/EVENTS.md`](docs/EVENTS.md).

## Roles

| Role | Who | Can do |
|---|---|---|
| `admin` | Head of Engineering | Everything, including managing people and units |
| `engineer` | Engineering staff | Register devices, log events, handle complaints |
| `unit_rep` | A unit's representative | Raise complaints, view their own unit's records, confirm or dispute handovers |
| `auditor` | Management / oversight | Read-only access and reports |

The full permission matrix is in [`docs/AUTH.md`](docs/AUTH.md).

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI, SQLAlchemy 2.0, Alembic, Poetry |
| Database | PostgreSQL 16 |
| Web app | React, TypeScript, Vite (served by the API at `/app/`) |
| Testing | pytest (API), Vitest (screens), browser end-to-end tests |
| Packaging | Docker, docker-compose |

## Repository layout

```
backend/    the API: app/, alembic/ (migrations), tests/, scripts/, pyproject.toml, Dockerfile
frontend/   the web app (React) and its browser tests (e2e/)
docs/       the specification (SPEC.md), CHANGELOG.md and every guide
scripts/    e2e.sh: the browser tests against the real API
docker/     database start-up script used by docker-compose.yml
```

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env   # then edit SECRET_KEY before any non-local use
docker compose up --build
```

| What | Where |
|---|---|
| Web app | http://localhost:8000/app/ (see [`docs/FRONTEND.md`](docs/FRONTEND.md)) |
| API health | http://localhost:8000/health (also `/api/v1/health`) |
| Interactive API docs | http://localhost:8000/docs |

Postgres is published on `127.0.0.1:5432` (user/password/db: `audit`). A second database, `audit_test`, is created on first start for the test suite.

> The init script `docker/db/init.sql` only runs on an empty data volume. To reset the database: `docker compose down -v`.

## First admin and signing in

There is no public sign-up. Create the first admin (the Head of Engineering) on the server:

```bash
docker compose run --rm api python -m scripts.create_admin \
    --email head@your-domain.example --name "Head of Engineering"
```

It asks for a password (or reads `ADMIN_PASSWORD`; never pass it on the command line). Then:

1. Open http://localhost:8000/app/ and sign in.
2. Add departments under **Units**.
3. Add everyone else under **People**. Each new person is shown a starting password once, to pass on; they change it after signing in.

Roles, tokens and the permission matrix are in [`docs/AUTH.md`](docs/AUTH.md). The API can also be tried directly at http://localhost:8000/docs (`POST /api/v1/auth/login`, then the **Authorize** button).

## Local development

Requires Python 3.12, Poetry, Node 22 and Docker (for Postgres).

**API** (from `backend/`):

```bash
docker compose up -d db       # Postgres only (run from the repository root)
cd backend
poetry install --no-root
poetry run ruff check . && poetry run ruff format --check .
poetry run pytest             # uses TEST_DATABASE_URL, default localhost:5432/audit_test
```

To run the API on the host instead of in Docker (from `backend/`), point `DATABASE_URL` at localhost:

```bash
DATABASE_URL=postgresql+psycopg://audit:audit@localhost:5432/audit \
  poetry run uvicorn app.main:app --reload
```

**Web app** (from `frontend/`; details and scripts in [`docs/FRONTEND.md`](docs/FRONTEND.md)):

```bash
cd frontend
npm ci
npm run dev                   # http://localhost:5173/app/, /api proxied to the API on :8000
npm test                      # screens, against a mocked network
npm run build                 # builds into backend/app/static, served by the API at /app/
```

**Sample data** (development only; refuses `ENV=production`):

```bash
cd backend && poetry run python -m scripts.seed_demo
```

## Testing

| Suite | Command | Notes |
|---|---|---|
| API | `poetry run pytest` (in `backend/`) | Each test runs in a rolled-back transaction |
| Screens | `npm test` (in `frontend/`) | Against a mocked network |
| Whole system | `scripts/e2e.sh` | Every journey and every page in a real browser against the real API; needs the db container, a built app and Chrome |

> The test session **drops and recreates the `public` schema** of the test database, then runs `alembic upgrade head`. Never point `TEST_DATABASE_URL` at a database you care about.

Accessibility: what is checked automatically and what needs a person is in [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md).

## Environment variables

See `backend/.env.example`. With `ENV=production` the app refuses to start while `SECRET_KEY` is still the default.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://audit:audit@db:5432/audit` | SQLAlchemy URL |
| `SECRET_KEY` | `change-me` | JWT signing key |
| `ACCESS_TOKEN_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh cookie lifetime |
| `ACK_OVERDUE_DAYS` | `3` | Days before a pending acknowledgement is flagged overdue |
| `CORS_ORIGINS` | `http://localhost:8000` | Comma-separated allowed origins (the web app is served from the API's own address, so it needs none) |
| `ENV` | `development` | `development`, `test` or `production` |

## Migrations

Alembic reads `DATABASE_URL` from the app settings. Migrations are applied **by hand, after a backup** ([`docs/RUNBOOK.md`](docs/RUNBOOK.md)), and never by the web process.

```bash
docker compose run --rm api alembic upgrade head   # apply
docker compose run --rm api alembic current        # show revision
```

- Migration `0006` (no vendors) refuses to run if any record still refers to a vendor.
- Migrations are hand-written SQL (`backend/alembic/versions/`), because triggers, sequence defaults and `CITEXT` are not expressible through autogenerate.
- `backend/tests/test_migrations.py` fails if the ORM models in `backend/app/models/` drift from the migrated schema.
- Entity diagram: [`docs/ERD.md`](docs/ERD.md).

## Security

- **No public sign-up.** Accounts are created by an admin only.
- **Append-only audit tables.** `device_events`, `acknowledgements` and `complaint_comments` reject UPDATE, DELETE and TRUNCATE in the database itself (see [`docs/ERD.md`](docs/ERD.md)).
- **Unit scoping.** A unit representative can only see their own unit's data, enforced in the service layer.
- **Startup guard.** In production the app refuses to start with the default `SECRET_KEY`.
- **Secrets stay out of git.** Keep `backend/.env` untracked, and never pass passwords on the command line.
- Before going live, follow the go-live checklist in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Documentation

| Guide | Covers |
|---|---|
| [`docs/AUTH.md`](docs/AUTH.md) | Sessions, roles, permission matrix, unit scoping |
| [`docs/DEVICES.md`](docs/DEVICES.md) | Registering, searching and the device timeline |
| [`docs/COMPLAINTS.md`](docs/COMPLAINTS.md) | Tickets, status flow, comments, confirm/reopen |
| [`docs/EVENTS.md`](docs/EVENTS.md) | The device state machine, acknowledgements, pending list |
| [`docs/REPORTS.md`](docs/REPORTS.md) | The five reports and their Excel/PDF exports |
| [`docs/ERD.md`](docs/ERD.md) | The database |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | The web app, its design decisions, security and tests |
| [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md) | What is checked automatically and what needs a person |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Running it for real: go-live checklist, backups, updating |

## Conventions

- All routes are under `/api/v1`; errors are `{ "error": { "code", "message", "details" } }`.
- Business rules live in `backend/app/services`, never in routers or the frontend.
- Audit tables are append-only; corrections are new rows.

## About this project

> Built during my SIWES (Tier 1) industrial training at the **Lagos State Residents Registration Agency (LASRRA)**, for the Engineering unit of the **Information Management & Data Processing Department**. It replaces informal tracking of device complaints, repairs and returns with a single record that Engineering and every other unit can verify.