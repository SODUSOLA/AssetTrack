# Changelog

## Folder structure: backend/, frontend/, docs/

- Everything Python moved into `backend/` (`app/`, `alembic/`, `tests/`, `scripts/`, `pyproject.toml`,
  `poetry.lock`, `Dockerfile`, `.env.example`); `SPEC.md` and this file moved into `docs/`. The web app
  builds into `backend/app/static`. `docker-compose.yml`, `docker/`, `scripts/e2e.sh`, `.github/` and
  the README stay at the top. No code changed.
- Build the image from the repository root: `docker compose build` (or `docker build -f
  backend/Dockerfile .`). Backend commands now run from `backend/`; the local `.env` lives in
  `backend/.env`. Older entries below refer to the earlier paths.

## SPEC v1.2: no vendors (repairs are in-house)

- **Removed from the system:** the `vendors` table, `device_events.vendor_id` and its rule, the
  `sent_to_vendor` event type, the `with_vendor` device status, the `GET`/`POST /vendors` endpoints,
  the `vendor` field of timeline and event responses, and every vendor column and section of the
  reports (monthly activity, turnaround, repeat faults) and so of their Excel and PDF files.
  Every in-house report figure is unchanged (the report tests that compute them by hand all pass).
  The state machine is now diagnosed -> repair started -> repair completed -> returned.
- **Migration `0006_remove_vendors`.** It refuses to run, and changes nothing, if any event or device
  still refers to a vendor (the record is append-only). Otherwise no row is edited, deleted or
  truncated: the guards stay in place (tested: edit, delete and truncate are still refused after the
  upgrade), the event checks are re-added unchanged, and new devices still start in stock. The
  downgrade recreates the empty structure only. Run it by hand after a backup (`docs/RUNBOOK.md`).
- **Frontend:** the code that hid vendors (hidden event set, report filters, labels) is deleted; the
  API snapshot and types are regenerated; browser tests still assert that no page mentions vendors.
- **Docs:** `SPEC.md` (v1.2 note and every vendor passage), `EVENTS`, `DEVICES`, `ERD`, `AUTH`,
  `REPORTS`, the API inventory and `FRONTEND`.
- **Tests:** backend 808 (the vendor tests are gone, new ones prove the endpoints are 404, the
  reports never mention vendors and the migration is safe), frontend 223.
- **API change:** the `vendor` field and the vendor event are gone; only our own frontend used them.

## Milestone 8d: Administration, browser tests and hardening

- **People and Units** screens for the head of engineering (create, edit, deactivate, reset password
  with a generated one-time password). No API change.
- **Playwright end-to-end suite** (`scripts/e2e.sh`, CI job `e2e`): the full repair journey, access
  scoping, auth, reports and downloads, admin, security, keyboard, and every page at six screen
  sizes in light and dark with axe in a real browser.
- **Fixes the browser tests found:** the content-security policy blocked the scroll-lock style of
  dialogs and menus (now a per-page nonce; `app/core/spa.py`, `tests/test_spa.py`); dialogs did not
  return focus to the button that opened them; the skip link had no target; two controls' names did
  not contain their visible text; tables flashed in table layout on phones.
- `scripts/seed_demo.py` accepts `DEMO_PASSWORD` (so tests can sign in). Bundle-size budget
  (`npm run budget`). `docs/RUNBOOK.md`, `docs/ACCESSIBILITY.md`.
- Tests: 225 frontend, 855 backend, and the browser suite (over 170 runs across six screen sizes).
- Open: a screen-reader and keyboard pass by a person, HTTPS and proxy decisions (see the runbook),
  backup automation, and the backend vendor clean-up (needs explicit authorisation).

## Milestone 8c: Reports in the frontend

- `/reports`: the five reports, with their settings in the address, drawn from the one generic
  report shape; Print for every role that can open reports (including the head of engineering),
  and Excel and PDF downloads through the signed-in client. Reports joins the sidebar; the
  dashboard's "In the workshop" links to the monthly report. No backend change.
- Print: sidebar and controls hidden, always light, real tables with repeating headers, a
  "Printed from" line; the printed app frame no longer reserves the sidebar's column.
- Vendor sections, columns and figures are hidden on screen (the exports still include them).
- `DataTable` gained a totals row; its card layout is screen-only.
- Tests: 199 frontend (what each report asks the API checked against `openapi.json`, cell
  formatting, vendor hiding, file names, print theme, every setting reaching the request, Print and
  both downloads, refusals in plain words, axe). Checked in a browser, including a print emulation.

## Milestone 8b: Complaints in the frontend

- Complaints list, complaint page, raise-a-complaint dialog (also from a device's page), and the
  actions assign/take, change priority, resolve, close duplicate, confirm, reopen and comment.
  Complaints joins the sidebar; dashboard figures link to their lists; a device shows its open
  complaints. No backend change.
- Action rules follow `docs/COMPLAINTS.md`; the server's 409 reasons are shown in plain words.
- Only the head of engineering can pick any assignee (only they may list users); an engineer takes
  a complaint for themselves.
- `DataTable` decides between table and cards from its own measured width (`cardsBelow`), and
  scrolls inside its own box instead of widening the page.
- Tests: 168 frontend (rules for every role and status, API contract for the request bodies, list
  filters and rep scoping, raise as rep and as staff, each action with its validation and refusals,
  comment thread, axe). Checked in a browser against the demo data.

## Milestone 8: React frontend

- A React 19 + TypeScript app in `frontend/`, built with Vite and served by the API at `/app/`
  (same origin, so the httpOnly refresh cookie works). See `docs/FRONTEND.md`.
- Pages: sign-in, dashboard (by role), devices with search and filters, device record with its
  timeline, log-event, register and edit device, acknowledgements (confirm or dispute as a unit rep;
  read-only for staff), account and password.
- Typed API client generated from `frontend/openapi.json`; the access token is held in memory,
  refresh is single-flight within a tab and serialised across tabs.
- No vendor step in the UI (repairs are in-house) and no money anywhere. Official colours (dark
  green, light green, yellow) with light and dark themes.
- Backend changes (authorised): `GET /devices/{id}` returns `allowed_events`; `app/core/spa.py`
  serves the built app with a strict CSP and security headers; `scripts/seed_demo.py` and
  `scripts/dump_openapi.py`; Dockerfile gained a Node build stage; CI builds, tests and lints the app
  and checks the OpenAPI snapshot is current.
- Tests: 124 frontend tests (session races, client refresh and retry, Lagos time, permissions,
  contrast in both themes, form-versus-OpenAPI contract, axe on pages, page flows with a mocked
  network). Backend: 852 passing.
- Not yet: complaints, reports (with Print for the head of engineering), users and units screens,
  Playwright end-to-end tests, a keyboard and screen-reader pass.

## Milestone 7: Reports and exports

- Five reports under `/api/v1/reports`, each as JSON, Excel (`?format=xlsx`) or PDF
  (`?format=pdf`): `monthly-activity`, `open-tickets`, `turnaround`, `repeat-faults`,
  `awaiting-unit`. See `docs/REPORTS.md`. SPEC section 9 is final.
- One generic report object (summary figures plus titled sections of typed rows) rendered three
  ways, so JSON, Excel and PDF cannot disagree.
- Lagos calendar months and days; repair cycles paired from the event log; the overall average is
  over all repairs; "in the workshop at month end" reconstructed from history.
- Unit reps get the same reports for their own unit only, in every format.
- Excel stores user text as text (no formula injection); PDF escapes markup and uses a Unicode font
  for names with accents (DejaVu in the Docker image, Arial on macOS).
- Decisions A-C: ReportLab for PDF; monthly report lists every device with activity; all five
  reports for unit reps, scoped.
- Tests: figures checked against a hand-computed world (month and day boundaries, in-house versus
  vendor, disputes, overdue items), Excel and PDF read back and compared with the JSON, scoping in
  every format, hostile text, empty periods, query counts. No schema change.
- New dependencies: `openpyxl`, `reportlab`; `pypdf` for tests. The Docker image installs
  `fonts-dejavu-core`.

## Milestone 6: Events and acknowledgements

- Endpoints: 
  - `POST /devices/{id}/events`
  - `GET /events` 
  - `GET /events/{id}`
  - `POST/events/{id}/acknowledge`
  - `GET /acknowledgements/pending`
- The device state machine of SPEC 8.1 as data (`services/event_rules.py`), checked against the
  spec table for every status and event type. A discriminated request body per event type;
  unknown fields are rejected and the server stamps the time.
- One transaction per event: device row locked, transition and references validated, event
  appended, device and ticket updated; any failure rolls everything back.
- Events and acknowledgements are stamped with `clock_timestamp()` after the lock, so timeline order
  equals the order things happened. Only the device row is locked, never an audit row.
- Acknowledgements (confirm/dispute, once per event, unit rep of the event's unit); a confirmed
  return closes its ticket, a disputed one reopens it. Pending list with `pending_days` and
  `overdue`; nothing is auto-confirmed.
- Decisions D1-D3: intake links a device-less ticket and assigns the engineer; decommissioning
  mid-repair frees the ticket for manual resolution.
- Every step of a repair cycle is linked to its ticket, so the ticket page shows the whole repair.
- Tests: all status x event pairs over HTTP, malformed bodies, references, full lifecycle (SPEC
  12.1 tests 6 and 7), acknowledgement rules, pending list, real-thread concurrency (SPEC 12.1 test
  5; verified to fail without the lock), and the full lifecycle under a database role with only
  `INSERT, SELECT` on the audit tables.
- No schema change. `services/events.py` was split: `event_log.py` appends rows, `events.py`
  records, acknowledges and queries.

~ See `docs/EVENTS.md` for detailed documentation

## Milestone 5: Complaints

- Endpoints: 
  - `POST/GET /complaints`
  - `GET/PATCH /complaints/{id}`
  - `GET/POST/complaints/{id}/comments`
  - `POST /complaints/{id}/confirm`
  - `/reopen`
- Ticket state machine in `services/complaints.py`; engineering can never close a resolved ticket.
- Migration `0005`: `complaint_comments.is_system`. Every assignment, priority change
  and status change, manual or caused by a device event, writes a system comment.
- `on_intake`, `on_return`, `on_return_acknowledged`: the device-event effects of SPEC 7.2, ready
  for Milestone 6 to call inside its transaction and tested with factory-made events.
- Raising on behalf of a unit; linked devices validated against the unit; a device in the workshop
  blocks resolving; `AWAITS_ACKNOWLEDGEMENT` guards tickets whose returned device is unacknowledged.
- Unit-rep scoping on every complaint route, with identical 404s for other units and missing ids.
- `device` detail's open complaint count now reflects real tickets.

~ See `docs/COMPLAINTS.md` fpr detailed documentation
## Milestone 4: Devices

- Endpoints: 
  - `POST /devices`
  - `GET /devices`
  - `GET /devices/{id}`
  - `PATCH /devices/{id}`
  - `GET /devices/{id}/timeline`
  - `GET /units/{id}/devices`
- Registration writes the device and its `device_registered` event atomically; metadata patches
  write `note_added` events; status and unit are not patchable and unknown fields are rejected.
- Timeline with actor, counterparty, vendor, ticket, diagnosis, acknowledgement state
  (`pending_days`, `overdue`), Lagos-day date filters, and a constant number of queries.
- Migration `0004`: serial numbers unique ignoring case (decision A).
- `device_type` normalised to lower case; blank optional text stored as NULL.
- Unit-rep scoping on every device route, with identical 404s for other units, central stock and
  unknown ids. `can_access_unit` added to `app/services/scope.py`.
- Foundations for later milestones: `services/events.py` (`append_event`, `ACK_REQUIRED`),
  `atomic()` unit-of-work helper, `core/timeutil.py` (Africa/Lagos), model relationships with
  `lazy="raise_on_sql"` so accidental N+1 queries fail loudly. New dependency: `tzdata`.

~ See `docs/DEVICES.md` for detailed documentation

## v1.1: pricing removed

At the admin's direction the system records no monetary values anywhere.

- Migration `0003_remove_pricing`: drops `costs`, `cost_kind` and the cost guard functions and
  triggers. No endpoint ever wrote cost rows, so no data was lost. `downgrade()` restores them.
- Removed the `Cost` model, `CostKind` enum, cost test helper and cost tests.
- `SPEC.md` is now v1.1: FR4, the cost endpoints and page, the monthly-spend report, the cost
  tests and open items 14.3 and 14.5 are gone; section 9 is "Reports and Exports" (contents to be
  confirmed at the Milestone 7 plan). Vendors are kept (repairs can be outsourced).
- New `tests/test_no_pricing.py` fails if any table, column, type, function, index, trigger or
  API field named like cost, price, invoice, amount, currency, spend, payment or billing appears.
- ERD, README and docs updated.

## Milestone 3: Auth and roles

- Endpoints under `/api/v1`: 
  - `auth/login|refresh|logout|me|change-password`
  - `users` (list, create, get, patch)
  - `units` (list, create, patch)
  - `vendors` (list, create)
- argon2id passwords; 30-minute JWT access tokens; opaque 7-day refresh tokens in an httpOnly,
  SameSite=Strict cookie with rotation and reuse detection; login limited to 5/minute/IP.
- Migration `0002_refresh_tokens` (decision A): server-side hashed refresh tokens.
- Role, unit and active flag are read from the database on every request (decision C).
- Admin sets initial passwords and can reset them with `PATCH /users/{id}` (decision B).
- `require_roles`, `get_current_user`, shared pagination (`Page`, `Pagination`) and unit-scoping
  helpers (`app/services/scope.py`) for later modules.
- `scripts/create_admin.py` (password via prompt or `ADMIN_PASSWORD`, never an argument).
- Production now also requires `SECRET_KEY` of at least 32 characters.
- Tests: permission matrix, route-walking checks (every non-public route needs a token; auditor gets
  403 on every write), token and session lifecycle, user/unit/vendor rules, scoping helpers,
  `create_admin`.
- Judgment calls: auditors can read vendors; any signed-in role can list unit names.
- Dependencies added: `pyjwt`, `argon2-cffi`, `slowapi`, `email-validator`.

~ See `docs/AUTH.md` for detailed documentation

## Milestone 2: Schema

- Migration `0001_initial_schema`: enums, sequences, all tables and indexes from SPEC section 4.2,
  plus the immutability guards (hand-written SQL).
- Additions beyond the spec DDL, approved in the plan:
  - guard exceptions carry SQLSTATE `23001` (`restrict_violation`);
  - `BEFORE TRUNCATE` guards on `device_events`, `acknowledgements`, `complaint_comments` and
    `costs` (row triggers do not fire on `TRUNCATE`; the `costs` guard was added for consistency).
- SQLAlchemy 2.0 models in `app/models/` mirroring the schema.
- Tests: migration round trip, model/schema drift check, append-only and cost-void guards,
  CHECK/UNIQUE/default behaviour. Test DB is reset per session; each test is rolled back.
- `docs/ERD.md` (Mermaid diagram and guard table).
- Alembic no longer disables existing loggers; `path_separator` set to silence a deprecation.

## Milestone 1: Project scaffold

- Poetry project (Python 3.12), ruff and pytest configuration.
- FastAPI app factory with `/health` and `/api/v1/health` (checks PostgreSQL, 503 on failure).
- Standard JSON error format for app, HTTP, validation and unhandled errors.
- Settings from environment (`app/core/config.py`); production refuses the default `SECRET_KEY`.
- SQLAlchemy 2.0 base and session; Alembic wired to settings (no migrations yet).
- Multi-stage, non-root Dockerfile; `docker-compose.yml` with `api` and `db` (Postgres 16),
  plus an `audit_test` database with `citext` and `pgcrypto` for the test suite.
- GitHub Actions CI: ruff, format check, pytest with a Postgres service container.
