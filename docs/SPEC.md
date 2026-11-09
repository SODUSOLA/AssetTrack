# LASRRA Engineering Audit System: Build Specification

> Version 1.1 | Stack: FastAPI + PostgreSQL + HTML/CSS/JS (React later)
> Purpose: a transparent, tamper-evident record of device complaints, assignments, repairs and returns, visible to both the Engineering department and the units it serves.

> **Changes since 1.0 (v1.1): no pricing.** At the admin's direction the system records **no
> monetary values anywhere**: no purchase prices, repair costs, invoice references, currency or
> spend reports. It is an audit system for complaints, device handovers and repairs, plus
> reports on that activity. Removed: the `costs` table and `cost_kind` enum (migration `0003`),
> FR4, the cost end points and `costs.html`, the monthly-spend report, and open items 14.3 and 14.5.
> Section 9 is now "Reports and Exports" (contents to be confirmed at the Milestone 7 plan).
> `backend/tests/test_no_pricing.py` fails if money ever reappears in the schema or API.

> **No vendors (v1.2).** Repairs are done in-house, so the system has no vendor concept: removed are
> the `vendors` table, `device_events.vendor_id` and its rule, the `sent_to_vendor` event type, the
> `with_vendor` device status, the `/vendors` endpoints, and every vendor column and section of the
> reports (migration `0006`, which refuses to run if any record still refers to a vendor). Where this
> document still shows the v1.0 schema, `backend/alembic/versions/` and `docs/ERD.md` are the source of truth.

> **Frontend (v1.1, Milestone 8).** The UI is a React app (not plain HTML/CSS), served by the API at
> `/app/`; see `docs/FRONTEND.md`. Repairs are done in-house, so there is no "send to
> vendor" step; the head of engineering (admin) and the other report viewers can print a report from the
> Reports page. Official colours: dark green, light green and yellow.

---

## 0. Working Agreement for the Coding Agent

1. **Propose before build.** For each module, first post a short plan (files, endpoints, edge cases). Wait for approval, then implement.
2. **One module at a time**, in the order in section 11. Each module ships with tests and docs before the next starts.
3. **Never edit or delete audit data.** Events, acknowledgements and comments are append-only. Corrections are new rows.
4. **Server decides time.** Clients never send `occurred_at`; the server stamps it (UTC).
5. **Business rules live in the service layer**, not in routers and not in the frontend.
6. Keep the API strictly JSON under `/api/v1` so the HTML frontend can be replaced by React without backend changes.
7. Small commits, clear messages, no secrets in the repo.

---

## 1. Requirements

### 1.1 Problem
The Engineering department (a) receives complaints from units about faulty systems, (b) buys new devices and assigns them to units, (c) repairs and returns devices, and (d) reports monthly on repair activity per unit and per device. Today there is no shared, verifiable record. This system makes every handover and every repair traceable and confirmable by both sides.

### 1.2 Roles
| Role | Who | Can do |
|---|---|---|
| `admin` | Head of Engineering / system owner | Everything, including managing users and units |
| `engineer` | Engineering staff | Register devices, log events, handle complaints |
| `unit_rep` | Representative of one unit | Raise complaints, view own unit's devices/tickets, acknowledge handovers |
| `auditor` | Management / oversight | Read-only access to everything, reports and exports |

### 1.3 Confirmed Decisions
1. Users are staff (engineers), unit reps, and head/auditor. Accounts are created by an admin only (no public signup).
2. Every device gets a system-generated **asset tag** (e.g. `LAS-ENG-000123`) as its primary human ID. Serial number is optional but unique when present.
3. The audit trail is **append-only**. Every entry records who and when. Corrections are new entries.
4. No monetary values are recorded anywhere in the system (v1.1). Monthly reports aggregate repair activity per unit and per device.
5. A unit rep acknowledges handovers by logging in and clicking Confirm or Dispute (OTP at handover is a possible later upgrade).
6. Repairs are done in-house (v1.2): the system has no vendor concept and no outsourced-repair step.
7. Reports: monthly repair activity per unit and per device, open tickets, average turnaround, repeat-fault devices; export to Excel and PDF.
8. Stack: FastAPI, PostgreSQL, plain HTML/CSS/JS first, React later.

### 1.4 Functional Requirements
- **FR1** Unit rep raises a complaint (optionally linked to a device); engineering sees it and updates it; both can comment.
- **FR2** Engineering registers new devices and assigns them to a unit; unit acknowledges receipt.
- **FR3** Engineering logs the repair lifecycle of a device (received, diagnosed, in repair, repaired, returned); unit acknowledges at hand-in and at return.
- **FR4** *(removed in v1.1: no pricing is recorded.)*
- **FR5** Full per-device timeline and per-unit view, filterable by date.
- **FR6** Monthly reports and exports.
- **FR7** Pending-acknowledgement list; items overdue past a threshold are flagged (never auto-confirmed).

### 1.5 Non-Functional Requirements
- **Integrity:** DB-level triggers block UPDATE/DELETE on audit tables.
- **Security:** argon2 password hashing, JWT auth, role checks on every endpoint, unit-scoped data for `unit_rep`, login rate limiting, HTTPS in production.
- **Traceability:** every write records `actor_id` and a server timestamp.
- **Time:** store UTC; display in Africa/Lagos.
- **Performance:** single-office scale; pagination on all list endpoints.
- **Backups:** nightly `pg_dump`, tested restore.

### 1.6 Out of Scope for v1
OTP at handover, file uploads for receipts or attachments, email/SMS notifications, inter-unit device transfers, hash-chained tamper evidence (listed as a v1.1 hardening idea).

---

## 2. Mapping of Your Original Device Fields

| Original field | Where it lives now |
|---|---|
| Date received | `device_events.occurred_at` where `event_type = 'received_for_repair'` |
| S/N of device | `devices.serial_number` (plus `devices.asset_tag`) |
| Device type | `devices.device_type` |
| Status | `devices.status` (current) and `device_events.to_status` (history) |
| Diagnosis | `device_events.diagnosis` on the `diagnosed` event |
| Received by | `device_events.actor_id` on `received_for_repair` |
| Returned by | `device_events.actor_id` on `returned_to_unit` |
| Collected by | `device_events.counterparty_name/user_id` on `returned_to_unit` |
| Unit/dept | `devices.unit_id` (current) and `device_events.unit_id` (at time of event) |
| Date returned | `device_events.occurred_at` where `event_type = 'returned_to_unit'` |

One device can now have many repair cycles without losing history.

---

## 3. Tech Stack and Conventions

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI, Pydantic v2 |
| DB | PostgreSQL 16 |
| ORM / migrations | SQLAlchemy 2.0, Alembic |
| Auth | JWT (PyJWT), argon2-cffi, refresh token in httpOnly cookie |
| Rate limiting | slowapi |
| Reports | openpyxl (Excel), WeasyPrint or ReportLab (PDF) |
| Frontend v1 | Static HTML/CSS/vanilla JS served by FastAPI `StaticFiles`, using `fetch` against `/api/v1` |
| Tests | pytest, httpx, a dedicated test database |
| Packaging | Docker, docker-compose |

**Conventions**
- IDs: UUID primary keys, except `device_events.id` (bigint identity, gives natural ordering).
- Timestamps: `TIMESTAMPTZ`, UTC.
- Pagination: `?page=1&page_size=20` returning `{ items, total, page, page_size }`.
- Errors: `{ "error": { "code": "STRING_CODE", "message": "Human readable", "details": {} } }`.
- Versioning: all routes under `/api/v1`.

### Project Structure

*(v1.2 layout. The original v1.0 layout had everything at the top level and plain HTML pages.)*

```
lasrra-audit/
├── backend/                 # the API
│   ├── app/                 # main.py; core/ db/ models/ schemas/ services/ routers/ reports/;
│   │                        # static/ holds the built web app (not committed)
│   ├── alembic/             # hand-written migrations (versions/)
│   ├── tests/
│   ├── scripts/             # create_admin, seed_demo, dump_openapi
│   ├── pyproject.toml, poetry.lock, Dockerfile, .env.example
├── frontend/                # the React web app, its tests and its browser tests (e2e/)
├── docs/                    # SPEC.md, CHANGELOG.md, ERD and the guides
├── scripts/e2e.sh           # browser tests against the real API
├── docker/                  # database start-up script
├── docker-compose.yml
└── README.md
```

### Environment Variables (`backend/.env.example`)
```
DATABASE_URL=postgresql+psycopg://audit:audit@db:5432/audit
SECRET_KEY=change-me
ACCESS_TOKEN_MINUTES=30
REFRESH_TOKEN_DAYS=7
ACK_OVERDUE_DAYS=3
CORS_ORIGINS=http://localhost:8000
ENV=development
```

---

## 4. Database Schema

### 4.1 Entity Overview
```
units 1──* users
units 1──* devices
units 1──* complaints
devices 1──* device_events
complaints 1──* device_events
complaints 1──* complaint_comments
device_events 1──0..1 acknowledgements
```

### 4.2 DDL (initial migration reference)

```sql
-- ===== ENUMS =====
CREATE TYPE user_role AS ENUM ('admin', 'engineer', 'unit_rep', 'auditor');

CREATE TYPE device_status AS ENUM (
  'in_stock', 'assigned', 'received_for_repair', 'diagnosed',
  'in_repair', 'awaiting_parts', 'repaired', 'decommissioned'
);

CREATE TYPE event_type AS ENUM (
  'device_registered', 'assigned_to_unit', 'received_for_repair', 'diagnosed',
  'repair_started', 'parts_requested', 'repair_completed',
  'returned_to_unit', 'decommissioned', 'note_added'
);

CREATE TYPE complaint_status AS ENUM ('open', 'in_progress', 'resolved', 'closed', 'reopened');
CREATE TYPE complaint_category AS ENUM ('hardware', 'software', 'network', 'other');
CREATE TYPE priority_level AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE ack_status AS ENUM ('confirmed', 'disputed');

-- ===== SEQUENCES (human-friendly numbers) =====
CREATE SEQUENCE asset_tag_seq START 1;
CREATE SEQUENCE ticket_no_seq START 1;

-- ===== CORE TABLES =====
CREATE TABLE units (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name TEXT NOT NULL,
  email CITEXT NOT NULL UNIQUE,            -- requires: CREATE EXTENSION citext;
  password_hash TEXT NOT NULL,
  role user_role NOT NULL,
  unit_id UUID REFERENCES units(id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT unit_rep_requires_unit CHECK (role <> 'unit_rep' OR unit_id IS NOT NULL)
);

CREATE TABLE devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_tag TEXT NOT NULL UNIQUE
    DEFAULT ('LAS-ENG-' || lpad(nextval('asset_tag_seq')::text, 6, '0')),
  serial_number TEXT UNIQUE,               -- NULL allowed; unique when present
  device_type TEXT NOT NULL,               -- laptop, desktop, printer, monitor, UPS...
  make TEXT,
  model TEXT,
  unit_id UUID REFERENCES units(id),       -- NULL = in central stock
  status device_status NOT NULL DEFAULT 'in_stock',
  acquired_on DATE,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_devices_unit ON devices(unit_id);
CREATE INDEX idx_devices_status ON devices(status);

CREATE TABLE complaints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_no TEXT NOT NULL UNIQUE
    DEFAULT ('TKT-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('ticket_no_seq')::text, 5, '0')),
  unit_id UUID NOT NULL REFERENCES units(id),
  raised_by UUID NOT NULL REFERENCES users(id),
  device_id UUID REFERENCES devices(id),   -- optional (e.g. network issue)
  category complaint_category NOT NULL DEFAULT 'hardware',
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  priority priority_level NOT NULL DEFAULT 'medium',
  status complaint_status NOT NULL DEFAULT 'open',
  assigned_to UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ
);
CREATE INDEX idx_complaints_unit_status ON complaints(unit_id, status);

CREATE TABLE complaint_comments (          -- append-only
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  complaint_id UUID NOT NULL REFERENCES complaints(id),
  author_id UUID NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===== AUDIT CORE =====
CREATE TABLE device_events (               -- append-only
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  device_id UUID NOT NULL REFERENCES devices(id),
  complaint_id UUID REFERENCES complaints(id),
  unit_id UUID REFERENCES units(id),       -- unit the device belonged to at the time
  event_type event_type NOT NULL,
  from_status device_status,
  to_status device_status NOT NULL,
  actor_id UUID NOT NULL REFERENCES users(id),   -- engineering staff who did it
  counterparty_name TEXT,                  -- unit person who handed in / collected
  counterparty_user_id UUID REFERENCES users(id),
  diagnosis TEXT,
  notes TEXT,
  corrects_event_id BIGINT REFERENCES device_events(id),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT diagnosed_needs_diagnosis CHECK (event_type <> 'diagnosed' OR diagnosis IS NOT NULL),
  CONSTRAINT return_needs_collector CHECK (event_type <> 'returned_to_unit' OR counterparty_name IS NOT NULL),
  CONSTRAINT intake_needs_depositor CHECK (event_type <> 'received_for_repair' OR counterparty_name IS NOT NULL)
);
CREATE INDEX idx_events_device_time ON device_events(device_id, occurred_at);
CREATE INDEX idx_events_complaint ON device_events(complaint_id);
CREATE INDEX idx_events_unit_time ON device_events(unit_id, occurred_at);

CREATE TABLE acknowledgements (            -- append-only, one per event
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id BIGINT NOT NULL UNIQUE REFERENCES device_events(id),
  acknowledged_by UUID NOT NULL REFERENCES users(id),
  status ack_status NOT NULL,
  comment TEXT,
  acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT dispute_needs_comment CHECK (status <> 'disputed' OR comment IS NOT NULL)
);

-- ===== IMMUTABILITY GUARDS =====
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% on % is not allowed (append-only table)', TG_OP, TG_TABLE_NAME;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER device_events_immutable BEFORE UPDATE OR DELETE ON device_events
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER acknowledgements_immutable BEFORE UPDATE OR DELETE ON acknowledgements
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER complaint_comments_immutable BEFORE UPDATE OR DELETE ON complaint_comments
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
```

**v1.1 additions (migrations `0001` and `0003`):** the guard exceptions use SQLSTATE `23001` (`restrict_violation`), and `BEFORE TRUNCATE` statement triggers on the three append-only tables block `TRUNCATE` (row triggers do not fire on it). The `costs` DDL that appeared here in v1.0 has been removed.

**Hardening:** in production the app's DB role should have `INSERT, SELECT` only on `device_events`, `acknowledgements` and `complaint_comments`, with no `UPDATE` or `DELETE` granted. Use a separate migration role for Alembic.

**Note on mutable tables:** `devices` (current status/unit) and `complaints` (status) are *current-state snapshots*. They are only changed by the service layer, in the same transaction as the event that justifies the change. The event log is the source of truth.

---

## 5. Module: Auth and Roles

### 5.1 Permission Matrix
| Action | admin | engineer | unit_rep | auditor |
|---|---|---|---|---|
| Manage users and units | ✅ | ❌ | ❌ | ❌ |
| Register / assign devices | ✅ | ✅ | ❌ | ❌ |
| View devices | all | all | own unit | all |
| Raise complaint | ✅ | ✅ (on behalf) | ✅ own unit | ❌ |
| Update complaint status, assign | ✅ | ✅ | ❌ | ❌ |
| Comment on complaint | ✅ | ✅ | ✅ own unit | ❌ |
| Log device events | ✅ | ✅ | ❌ | ❌ |
| Acknowledge events | ❌ | ❌ | ✅ own unit | ❌ |
| Reports and exports | ✅ | ✅ | own unit summary | ✅ |

### 5.2 Rules
- Passwords hashed with argon2id. Minimum 10 characters.
- Access token (JWT, 30 min) returned in JSON; refresh token in an httpOnly, Secure, SameSite=Strict cookie (7 days) with rotation.
- JWT claims: `sub` (user id), `role`, `unit_id`, `exp`.
- `unit_rep` queries are **always** filtered by their `unit_id` in the service layer (never trust a client-supplied unit filter).
- Login is rate limited (e.g. 5 attempts/minute/IP); inactive users cannot log in.
- `backend/scripts/create_admin.py` seeds the first admin.
- Dependency helpers: `get_current_user`, `require_roles(*roles)`.

### 5.3 Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | email + password → access token, sets refresh cookie |
| POST | `/auth/refresh` | rotates refresh token |
| POST | `/auth/logout` | clears cookie |
| GET | `/auth/me` | current user |
| POST | `/auth/change-password` | requires old password |
| GET/POST | `/users` | admin; list / create |
| GET/PATCH | `/users/{id}` | admin; update role, unit, active flag |
| GET/POST | `/units` | list (all authenticated) / create (admin) |
| PATCH | `/units/{id}` | admin |

### 5.4 Acceptance
- A `unit_rep` can never read another unit's data (test with two units).
- An `auditor` receives 403 on every write endpoint.

---

## 6. Module: Devices

### 6.1 Rules
- Registering a device creates the `devices` row **and** a `device_registered` event (`to_status = in_stock`) in one transaction.
- `status` and `unit_id` on `devices` change only through the events module (section 8). There is no direct `PATCH status`.
- Metadata (make, model, serial correction) may be patched by engineer/admin, and every patch writes a `note_added` event describing the change.
- Decommissioned devices remain visible and queryable, never deleted.

### 6.2 Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/devices` | register (device_type required; serial, make, model, acquired_on optional) |
| GET | `/devices` | filters: `unit_id, status, device_type, q` (asset tag / serial search) |
| GET | `/devices/{id}` | details + current unit + open complaint count |
| PATCH | `/devices/{id}` | metadata only |
| GET | `/devices/{id}/timeline` | ordered events with acknowledgements |
| GET | `/units/{id}/devices` | convenience, scoped |

### 6.3 Clarifications (v1.1)
- Request bodies reject unknown fields (422): `status`, `unit_id`, `asset_tag`, `created_by` and `occurred_at` can never be supplied by a client.
- `device_type` is trimmed, whitespace-collapsed and lower-cased; blank `serial_number`, `make` and `model` are stored as NULL.
- Serial numbers are unique regardless of letter case (migration `0004`). A duplicate returns `409 SERIAL_EXISTS`.
- A metadata patch that changes nothing writes no event. Each real change writes one `note_added` event.
- "Open complaint count" counts tickets in `open`, `in_progress` or `reopened`.
- A unit rep asking for a device outside their unit (or in central stock) gets the same 404 as for a device that does not exist.
- Timeline: events ordered by `occurred_at` then id; `date_from` / `date_to` are inclusive calendar days in Africa/Lagos; each event carries `ack_state` (`not_required`, `pending`, `confirmed`, `disputed`), `pending_days` and `overdue`. The timeline is one document per device and is not paginated.

### 6.4 Acceptance
- Duplicate serial → 409.
- Timeline returns events in chronological order, including who acted, the counterparty, diagnosis, and acknowledgement state.

---

## 7. Module: Complaints / Tickets

### 7.1 Status Flow
```
open → in_progress → resolved → closed
             ↑            │
             └─ reopened ←┘  (when the unit disputes the return or says it is still faulty)
```

### 7.2 Rules
- Raised by a `unit_rep` for their own unit; `unit_id` is taken from the user, not the request body.
- `device_id`, if given, must belong to the same unit.
- Engineer picks it up via `assigned_to` → status `in_progress`.
- Automatic transitions (service layer):
  - `received_for_repair` event linked to the ticket → `in_progress`
  - `returned_to_unit` event → `resolved` (sets `resolved_at`)
  - unit acknowledgement `confirmed` on the return → `closed` (sets `closed_at`)
  - unit acknowledgement `disputed` on the return → `reopened`
- Comments are append-only and visible to both the unit and engineering.

### 7.3 Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/complaints` | create |
| GET | `/complaints` | filters: `status, unit_id, priority, device_id, assigned_to, date_from, date_to` |
| GET | `/complaints/{id}` | with comments and linked events |
| PATCH | `/complaints/{id}` | engineer/admin: assign, priority, manual status where allowed |
| POST | `/complaints/{id}/comments` | both parties |
| GET | `/complaints/{id}/comments` | |

### 7.4 Clarifications (v1.1)
- **Unit and device.** A unit rep's unit always comes from their account; a different `unit_id` in the body is rejected (403). Admin or engineer raising on behalf must pass `unit_id`. A linked device must be currently held by that unit and not decommissioned.
- **Manual moves (PATCH, admin or engineer):** `open`/`reopened` → `in_progress`; `in_progress` → `resolved` (resolution note required); `open`/`in_progress` → `closed` (reason required, for duplicate or mistaken tickets; `resolved_at` stays empty). Naming an assignee on an `open` or `reopened` ticket starts work. The assignee must be an active engineer or admin and can be changed but not cleared. A device taken in for the ticket and not yet returned blocks resolving or closing it (`DEVICE_IN_REPAIR`).
- **Engineering never closes a `resolved` ticket.** The unit does: by acknowledging the returned device (Milestone 6), or, for tickets with no repair cycle, with `POST /complaints/{id}/confirm` (→ `closed`) or `POST /complaints/{id}/reopen` with a required reason (→ `reopened`; also open to admin and engineer). Both return `409 AWAITS_ACKNOWLEDGEMENT` while a returned device is still unacknowledged. Resolved tickets left unconfirmed are reported, never auto-closed.
- **Explainability.** Every assignment, priority change and status change, manual or caused by a device event, writes a system comment (`is_system: true`, migration `0005`) from the acting user. Reopening clears `resolved_at` and `closed_at`; the comments keep the history.
- **Comments** are allowed in any status, from admin, engineer or a unit rep of that unit, and are all visible to both sides. There are no private notes.
- A unit rep asking for another unit's ticket gets the same 404 as for a ticket that does not exist.

### 7.5 Acceptance
- Every state change of a ticket is explainable by an event or comment.
- A unit rep cannot see another unit's tickets.

---

## 8. Module: Events and Acknowledgement (Audit Core)

### 8.1 Device State Machine
| Event type | Allowed from | To status | Required fields |
|---|---|---|---|
| `device_registered` | none | `in_stock` | system |
| `assigned_to_unit` | `in_stock` | `assigned` | `unit_id`, `counterparty_name` (who received) |
| `received_for_repair` | `assigned` | `received_for_repair` | `complaint_id`, `counterparty_name` (who handed it in) |
| `diagnosed` | `received_for_repair` | `diagnosed` | `diagnosis` |
| `repair_started` | `diagnosed`, `awaiting_parts` | `in_repair` | none |
| `parts_requested` | `in_repair` | `awaiting_parts` | `notes` |
| `repair_completed` | `in_repair` | `repaired` | `notes` |
| `returned_to_unit` | `repaired` | `assigned` | `counterparty_name` (who collected) |
| `decommissioned` | any except `decommissioned` | `decommissioned` | `notes` (reason) |
| `note_added` | any | unchanged | `notes` (optional `corrects_event_id`) |

Any invalid transition → 409 `INVALID_TRANSITION` with the allowed next events.

### 8.2 Event Creation Algorithm (single DB transaction)
1. Lock the device row (`SELECT ... FOR UPDATE`).
2. Validate the transition and required fields.
3. Insert into `device_events` (`actor_id` = current user, server time, `unit_id` snapshot).
4. Update `devices.status` (and `unit_id` on assignment).
5. Apply linked-complaint side effects (section 7.2).
6. Commit. Any failure rolls back everything.

### 8.3 Acknowledgement Rules
- Events that **require acknowledgement:** `assigned_to_unit`, `received_for_repair`, `returned_to_unit`.
- Only a `unit_rep` of the event's unit may acknowledge, once per event (unique constraint).
- Outcome is `confirmed` or `disputed` (a dispute requires a comment).
- A dispute does not change history. Engineering responds with a `note_added` event (optionally referencing `corrects_event_id`) and/or a comment on the ticket. A disputed return sets the ticket to `reopened`.
- **Pending acknowledgement** = an acknowledgement-required event with no acknowledgement row. Events pending longer than `ACK_OVERDUE_DAYS` are flagged `overdue: true`. They are never auto-confirmed.

### 8.4 Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/devices/{id}/events` | engineer/admin; body: `event_type` + fields from the table above |
| GET | `/events` | filters: `device_id, unit_id, event_type, actor_id, date_from, date_to` |
| GET | `/events/{id}` | with acknowledgement |
| POST | `/events/{id}/acknowledge` | unit_rep; body: `{ status, comment? }` |
| GET | `/acknowledgements/pending` | unit_rep: own unit; engineer/auditor: all, with `overdue` flag |

### 8.5 Clarifications (v1.1)
- **Request bodies.** Each `event_type` takes exactly its own fields (see `docs/EVENTS.md`); unknown fields are rejected with 422, `device_registered` cannot be posted, and `occurred_at` is always stamped by the database. The stamp is `clock_timestamp()` taken after the device lock is held, so events of one device are in time order exactly as they happened (`now()` would give the start of the transaction, which can precede an earlier event that merely got the lock first).
- **Locking.** The *device* row is locked for every event and acknowledgement. Audit rows are never locked or updated, so the production role can hold `INSERT, SELECT` only on them (SPEC 4.2); a test runs the whole lifecycle under such a role.
- **Tickets.** `received_for_repair` needs a ticket of the device's unit, about this device or about none yet (it is then linked to the device). Intake assigns the engineer who logged it when the ticket has no assignee. Every step from `diagnosed` to `returned_to_unit` is linked to that ticket automatically, so the ticket shows the whole repair. `note_added` may name a ticket of the device's unit and may correct (`corrects_event_id`) an earlier event of the same device.
- **References.** `counterparty_user_id` (optional) must be an active rep of the unit; the unit of an `assigned_to_unit` event is the unit receiving the device; units and tickets must exist (422/404).
- **Acknowledgements.** Another unit's event returns **403** (as in 8.6; event ids are sequential, so hiding their existence would add little), staff cannot acknowledge, and an event type that is not acknowledged returns `409 ACK_NOT_REQUIRED`. Acknowledging a `returned_to_unit` closes (confirmed) or reopens (disputed) its ticket; other acknowledgements change nothing. A dispute never alters history; engineering answers with a `note_added` event.
- **Decommissioning mid-repair is allowed.** A decommissioned device no longer blocks its ticket (`DEVICE_IN_REPAIR`), so engineering can then resolve or close the ticket by hand with a note.
- **Reading.** `GET /events` is newest first; a unit rep sees events of devices in their own unit. `GET /acknowledgements/pending` lists unanswered events oldest first with `pending_days` and `overdue`; a unit rep sees only their unit's.

### 8.6 Acceptance
- Direct SQL `UPDATE` or `DELETE` on `device_events` raises an exception (test it).
- Skipping states (e.g. `assigned` → `repair_completed`) is rejected.
- Two concurrent events on the same device cannot both succeed from the same starting state.
- Acknowledging twice → 409; acknowledging another unit's event → 403.

---

## 9. Module: Reports and Exports

*(v1.1: the cost rules, void flow and monthly-spend report of v1.0 were removed. The system records no money, so every report describes repair activity.)*

### 9.1 Endpoints
All are `GET`, take `?format=json|xlsx|pdf` (JSON by default, Excel and PDF as downloads) and, for staff, an optional `unit_id`.

| Path | Parameters | What it reports |
|---|---|---|
| `/reports/monthly-activity` | `month=YYYY-MM` | Per unit and per device: devices assigned, received for repair, repaired, returned, decommissioned, in the workshop at month end, average days to return, tickets opened and closed, disputes raised |
| `/reports/open-tickets` | | Open, in-progress and reopened tickets by unit, priority, age and status; the tickets themselves; resolved tickets waiting for the unit |
| `/reports/turnaround` | `from`, `to` | Days from intake to return for repairs returned in the period: average, median, shortest, longest; by unit; the repairs themselves |
| `/reports/repeat-faults` | `from`, `to`, `min` (default 3) | Devices received for repair at least `min` times in the period |
| `/reports/awaiting-unit` | `include_recent` | Acknowledgements pending past `ACK_OVERDUE_DAYS`, disputes engineering has not answered, resolved tickets the unit has not confirmed |

### 9.2 Rules
- Reports are computed from `device_events`, `acknowledgements` and `complaints` only.
- Dates and months are Africa/Lagos calendar days (a month starts at Lagos midnight). `from`/`to` are inclusive and default to the last 90 days; periods over five years are refused.
- A **repair cycle** is a `received_for_repair` event paired with the next `returned_to_unit` of the same device. Cycles ending in decommissioning, or not yet returned, are not turnaround figures. Figures are computed from exact times and rounded to one decimal at the end; the overall average is over all repairs, not the average of the unit averages.
- "In the workshop at month end" is reconstructed from the event log as it stood at that moment.
- An **unanswered dispute** is a disputed return whose ticket is still `reopened`, or any other disputed event with no `note_added` event correcting it.
- Admin, engineer and auditor see every unit and may filter by `unit_id`; a unit rep gets the same reports for their own unit only, and a `unit_id` they send is ignored.
- JSON, Excel and PDF are rendered from one object and carry the same numbers; every export has a "Generated by <name> on <date and time>" footer. Text from users is stored as text in Excel (never as a formula) and escaped in PDF.
- Reports are documents, not paginated lists.

### 9.3 Acceptance
- Report figures equal the events in a test fixture, including month and day boundaries in Lagos time.
- A `unit_rep` sees only their own unit's figures, in every format.
- Excel and PDF exports contain the same numbers as the JSON response.

---

## 10. Frontend v1 (Plain HTML/CSS/JS)

Served from `/app` by FastAPI `StaticFiles`; talks only to `/api/v1`.

| Page | Roles | Purpose |
|---|---|---|
| `login.html` | all | sign in |
| `dashboard.html` | all | role-aware summary (open tickets, pending acks, devices in repair) |
| `devices.html` / `device.html` | all (scoped) | list, search, **timeline view** |
| `complaints.html` / `complaint.html` | all (scoped) | list, create, comments |
| `acknowledgements.html` | unit_rep, engineer, auditor | pending confirmations |
| `reports.html` | engineer, admin, auditor | monthly activity, exports |
| `admin.html` | admin | users, units |

Guidelines:
- One shared `api.js` wrapper that attaches the bearer token, handles 401 → refresh → retry, and parses the error format.
- Keep the access token in memory (not localStorage). Refresh token is the httpOnly cookie.
- Escape all user-supplied text when rendering (avoid `innerHTML` with raw data).
- Keep markup semantic and CSS variable-driven so the later React migration can reuse the design tokens.
- The timeline is the hero feature: a vertical list showing each event with actor, counterparty, diagnosis, and a visible "Acknowledged by X on DATE" or "Pending since N days" badge.

---

## 11. Build Order and Milestones

| # | Milestone | Deliverables | Done when |
|---|---|---|---|
| 1 | Project scaffold | Repo, Docker, compose, config, Alembic, health endpoint, CI lint+test | `docker compose up` serves `/health` |
| 2 | Schema | Migration for section 4 incl. triggers | Trigger tests pass |
| 3 | Auth and roles | Section 5 | Matrix tests pass |
| 4 | Devices | Section 6 | Register/list/search/timeline work |
| 5 | Complaints | Section 7 | Ticket lifecycle tests pass |
| 6 | Events and ack | Section 8 | State machine, concurrency, ack tests pass |
| 7 | Reports and exports | Section 9 | Report numbers verified against fixtures, exports open correctly |
| 8 | Frontend v1 | Section 10 pages | End-to-end happy path in browser |
| 9 | Docs, hardening, deploy | Section 12 | Deployed behind HTTPS with backups |

Per-milestone workflow: **plan → approval → implement → tests → docs update → demo**.

---

## 12. Testing, Documentation and Deployment

### 12.1 Testing
- **Unit tests:** state machine transitions, permission checks.
- **Integration tests (httpx + test DB):** every endpoint, happy and failure paths.
- **Must-have tests:**
  1. Append-only triggers reject UPDATE/DELETE on events, acknowledgements, comments.
  2. *(removed in v1.1: no costs.)*
  3. Unit scoping: unit_rep A cannot read unit B's devices, tickets or events.
  4. Invalid transition returns 409 with allowed events.
  5. Concurrent event creation on one device (row lock) yields exactly one success.
  6. Full lifecycle: complaint → received → diagnosed → repair started → repaired → returned → acknowledged → ticket closed, with the timeline asserted.
  7. Dispute path reopens the ticket.
  8. Monthly activity report counts equal the events in the fixture.
  9. The schema and API contain no pricing fields (`backend/tests/test_no_pricing.py`).
- Target ≥ 80% coverage on `services/`.

### 12.2 Documentation
- **API:** FastAPI auto OpenAPI at `/docs` (every route has summary, description, examples).
- **README:** setup, env vars, running tests, creating the first admin.
- **docs/ERD:** diagram of section 4.1.
- **docs/RUNBOOK.md:** deploy, rollback, backup/restore, adding a user, handling a disputed acknowledgement.
- **docs/CHANGELOG.md** per milestone.

### 12.3 Deployment
- `Dockerfile` (multi-stage, non-root user) and `docker-compose.yml` with `api`, `db` (Postgres volume) and `proxy` (Caddy or Nginx with automatic HTTPS).
- Run `alembic upgrade head` on release.
- Production env: `ENV=production`, strong `SECRET_KEY`, Secure cookies, restricted CORS.
- **Backups:** nightly `pg_dump` to off-server storage; monthly restore drill.
- **Logging:** structured JSON logs; never log passwords, tokens or full request bodies.
- **CI (GitHub Actions):** lint (ruff), type check (optional mypy), tests with a Postgres service container.

---

## 13. Future Enhancements (post v1)

- React frontend (API unchanged).
- OTP/QR-code handover confirmation.
- Attachment uploads such as photos or signed handover forms (object storage).
- Hash-chained events per device for cryptographic tamper evidence.
- Email/SMS/WhatsApp notifications for new tickets and pending acknowledgements.
- Inter-unit device transfers and warranty/expiry tracking.
- Repair-vs-replace flags from repeat-fault data.

---

## 14. Open Items to Confirm During Build
1. Unit list (seed data).
2. Device types to preload (laptop, desktop, printer, monitor, UPS, router, etc.).
3. *(removed in v1.1: no pricing.)*
4. Acknowledgement overdue threshold (default 3 days).
5. *(removed in v1.1: no pricing.)*
