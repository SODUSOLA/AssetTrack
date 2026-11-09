# Backend integration inventory (generated)

Generated from the code on 2026-10-30: 39 endpoints under `/api/v1`. Roles come from each route's
`require_roles(...)` dependency, parameters and bodies from the OpenAPI schema (`/api/v1/openapi.json`,
interactive docs at `/docs`). Regenerate rather than edit by hand.

* **Authentication:** `Authorization: Bearer <access token>` (JWT, 30 minutes). The refresh token is an httpOnly,
  SameSite=Strict cookie scoped to `/api/v1/auth`, so the app must be served from the **same origin** as the API.
* **Pagination:** list endpoints take `page` (from 1) and `page_size` (1 to 100) and return `{items, total, page, page_size}`.
* **Not paginated:** `GET /devices/{id}/timeline`, the five reports, `GET /auth/me`.
* **Sorting:** list endpoints have a fixed order and no sort parameters.
* **Dates and times:** timestamps are UTC ISO-8601; `date_from`, `date_to`, `from`, `to`, `month` are Africa/Lagos calendar days.
* **Downloads:** reports take `?format=xlsx|pdf` and need the bearer header, so they are fetched as blobs.
* **No file uploads, no WebSockets, no server-sent events** exist.

## Authentication

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| POST | `/api/v1/auth/login` | public | Sign in | - | email*, password* | 200 TokenResponse |
| POST | `/api/v1/auth/refresh` | public | Rotate the refresh token | cookie `refresh_token` (sent automatically) | - | 200 TokenResponse |
| POST | `/api/v1/auth/logout` | public | Sign out | cookie `refresh_token` (sent automatically) | - | 204 (no body / file) |
| GET | `/api/v1/auth/me` | any signed-in user | Current user | - | - | 200 UserOut |
| POST | `/api/v1/auth/change-password` | any signed-in user | Change own password | cookie `refresh_token` (sent automatically) | old_password*, new_password* | 204 (no body / file) |

## Users

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| GET | `/api/v1/users` | admin | List users (admin) | role, is_active, page, page_size | - | 200 Page_UserOut_ |
| POST | `/api/v1/users` | admin | Create a user (admin) | - | full_name*, email*, password*, role*, unit_id | 201 UserOut |
| GET | `/api/v1/users/{user_id}` | admin | Get a user (admin) | user_id* | - | 200 UserOut |
| PATCH | `/api/v1/users/{user_id}` | admin | Update role, unit, active flag, name or password (admin) | user_id* | full_name, role, unit_id, is_active, password | 200 UserOut |

## Units

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| GET | `/api/v1/units` | any signed-in user | List units | is_active, page, page_size | - | 200 Page_UnitOut_ |
| POST | `/api/v1/units` | admin | Create a unit (admin) | - | name*, code* | 201 UnitOut |
| PATCH | `/api/v1/units/{unit_id}` | admin | Update a unit (admin) | unit_id* | name, code, is_active | 200 UnitOut |
| GET | `/api/v1/units/{unit_id}/devices` | any signed-in user | Devices currently held by a unit | unit_id*, status, device_type, q, page, page_size | - | 200 Page_DeviceOut_ |

## Devices

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| POST | `/api/v1/devices` | admin, engineer | Register a device (admin, engineer) | - | device_type*, serial_number, make, model, acquired_on | 201 DeviceDetail |
| GET | `/api/v1/devices` | any signed-in user | List and search devices | unit_id, status, device_type, q, page, page_size | - | 200 Page_DeviceOut_ |
| GET | `/api/v1/devices/{device_id}` | any signed-in user | Device details | device_id* | - | 200 DeviceDetail |
| PATCH | `/api/v1/devices/{device_id}` | admin, engineer | Correct device metadata (admin, engineer) | device_id* | device_type, serial_number, make, model, acquired_on | 200 DeviceDetail |
| GET | `/api/v1/devices/{device_id}/timeline` | any signed-in user | Device timeline | device_id*, date_from, date_to | - | 200 Timeline |

## Events and acknowledgements

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| POST | `/api/v1/devices/{device_id}/events` | admin, engineer | Log a device event (admin, engineer) | device_id* | one of 9 event bodies (discriminator `event_type`) | 201 EventOut |
| GET | `/api/v1/events` | any signed-in user | Event log | device_id, unit_id, event_type, actor_id, date_from, date_to, page, page_size | - | 200 Page_EventOut_ |
| GET | `/api/v1/events/{event_id}` | any signed-in user | One event with its acknowledgement | event_id* | - | 200 EventOut |
| POST | `/api/v1/events/{event_id}/acknowledge` | unit_rep | Confirm or dispute an event (unit rep of that unit) | event_id* | status*, comment | 201 EventOut |
| GET | `/api/v1/acknowledgements/pending` | any signed-in user | Events waiting for acknowledgement | unit_id, overdue, page, page_size | - | 200 Page_PendingAcknowledgement_ |

## Complaints

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| POST | `/api/v1/complaints` | admin, engineer, unit_rep | Raise a complaint (unit rep, admin, engineer) | - | unit_id, device_id, category, title*, description*, priority | 201 ComplaintDetail |
| GET | `/api/v1/complaints` | any signed-in user | List complaints | status, unit_id, priority, device_id, assigned_to, date_from, date_to, page, page_size | - | 200 Page_ComplaintOut_ |
| GET | `/api/v1/complaints/{complaint_id}` | any signed-in user | Complaint with its comments and linked device events | complaint_id* | - | 200 ComplaintDetail |
| PATCH | `/api/v1/complaints/{complaint_id}` | admin, engineer | Assign, prioritise or move a complaint (admin, engineer) | complaint_id* | assigned_to, priority, status, comment | 200 ComplaintDetail |
| GET | `/api/v1/complaints/{complaint_id}/comments` | any signed-in user | Comments, oldest first | complaint_id*, page, page_size | - | 200 Page_CommentOut_ |
| POST | `/api/v1/complaints/{complaint_id}/comments` | admin, engineer, unit_rep | Add a comment (unit rep of the unit, admin, engineer) | complaint_id* | body* | 201 CommentOut |
| POST | `/api/v1/complaints/{complaint_id}/confirm` | unit_rep | Unit confirms a resolved complaint (unit rep) | complaint_id* | - | 200 ComplaintDetail |
| POST | `/api/v1/complaints/{complaint_id}/reopen` | admin, engineer, unit_rep | Reopen a resolved complaint (unit rep, admin, engineer) | complaint_id* | reason* | 200 ComplaintDetail |

## Reports

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| GET | `/api/v1/reports/monthly-activity` | any signed-in user | Monthly repair activity | month*, unit_id, format | - | 200 Report |
| GET | `/api/v1/reports/open-tickets` | any signed-in user | Open tickets by unit, priority and age | unit_id, format | - | 200 Report |
| GET | `/api/v1/reports/turnaround` | any signed-in user | Repair turnaround | from, to, unit_id, format | - | 200 Report |
| GET | `/api/v1/reports/repeat-faults` | any signed-in user | Devices repaired again and again | from, to, min, unit_id, format | - | 200 Report |
| GET | `/api/v1/reports/awaiting-unit` | any signed-in user | What is waiting on the units | include_recent, unit_id, format | - | 200 Report |

## Health

| Method | Path | Who | Purpose | Query / path parameters (`*` required) | Body fields (`*` required) | Success response |
|---|---|---|---|---|---|---|
| GET | `/api/v1/health` | public | Liveness and database check | - | - | 200 object |

## Error codes the server can return

Every error has the shape `{"error": {"code", "message", "details"}}`. Validation failures are `422 VALIDATION_ERROR` with `details.errors[]` (`loc`, `msg`, `type`). Unmatched HTTP errors use `HTTP_<status>`; rate limiting is `429 RATE_LIMITED` with a `Retry-After` header.

| Status | Code | Raised in |
|---|---|---|
| 400 | `INVALID_OLD_PASSWORD` | auth.py |
| 400 | `PASSWORD_UNCHANGED` | auth.py |
| 401 | `INVALID_CREDENTIALS` | auth.py |
| 401 | `INVALID_TOKEN` | deps.py, security.py |
| 401 | `NOT_AUTHENTICATED` | deps.py |
| 401 | `REFRESH_TOKEN_EXPIRED` | auth.py |
| 401 | `REFRESH_TOKEN_INVALID` | auth.py |
| 401 | `TOKEN_EXPIRED` | security.py |
| 403 | `FORBIDDEN` | complaints.py, deps.py, events.py |
| 404 | `COMPLAINT_NOT_FOUND` | complaints.py, events.py |
| 404 | `DEVICE_NOT_FOUND` | complaints.py, devices.py, events.py |
| 404 | `EVENT_NOT_FOUND` | events.py |
| 404 | `NOT_FOUND` | scope.py |
| 404 | `UNIT_NOT_FOUND` | common.py, devices.py, units.py |
| 404 | `USER_NOT_FOUND` | users.py |
| 409 | `ACK_NOT_REQUIRED` | events.py |
| 409 | `ALREADY_ACKNOWLEDGED` | events.py |
| 409 | `AWAITS_ACKNOWLEDGEMENT` | complaints.py |
| 409 | `DEVICE_IN_REPAIR` | complaints.py |
| 409 | `EMAIL_TAKEN` | users.py |
| 409 | `INVALID_TRANSITION` | complaints.py, events.py |
| 409 | `LAST_ADMIN` | users.py |
| 409 | `SERIAL_EXISTS` | devices.py |
| 409 | `TICKET_NOT_ACTIVE` | complaints.py |
| 409 | `UNIT_EXISTS` | units.py |
| 422 | `ASSIGNEE_INVALID` | complaints.py |
| 422 | `ASSIGNEE_REQUIRED` | complaints.py |
| 422 | `COMMENT_REQUIRED` | complaints.py |
| 422 | `COMMENT_WITHOUT_CHANGE` | complaints.py |
| 422 | `COMPLAINT_DEVICE_MISMATCH` | events.py |
| 422 | `COMPLAINT_UNIT_MISMATCH` | events.py |
| 422 | `CORRECTS_EVENT_INVALID` | events.py |
| 422 | `COUNTERPARTY_INVALID` | events.py |
| 422 | `DEVICE_DECOMMISSIONED` | complaints.py |
| 422 | `DEVICE_UNIT_MISMATCH` | complaints.py |
| 422 | `INVALID_MIN` | turnaround.py |
| 422 | `INVALID_MONTH` | activity.py |
| 422 | `INVALID_RANGE` | complaints.py, devices.py, events.py, turnaround.py |
| 422 | `RANGE_TOO_LARGE` | turnaround.py |
| 422 | `UNIT_NOT_ALLOWED` | users.py |
| 422 | `UNIT_NOT_FOUND` | complaints.py, events.py, users.py |
| 422 | `UNIT_REQUIRED` | complaints.py, users.py |
| 503 | `DB_UNAVAILABLE` | health.py |
