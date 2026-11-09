# Complaints (tickets)

Implements SPEC section 7 (v1.1). All routes are under `/api/v1`.

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/complaints` | unit rep, admin, engineer | unit rep: own unit; staff: on behalf, `unit_id` required |
| GET | `/complaints` | all roles (unit rep: own unit) | filters below |
| GET | `/complaints/{id}` | all roles (scoped) | ticket, comments, linked device events |
| PATCH | `/complaints/{id}` | admin, engineer | assign, priority, manual status |
| GET | `/complaints/{id}/comments` | all roles (scoped) | paginated, oldest first |
| POST | `/complaints/{id}/comments` | unit rep (own unit), admin, engineer | |
| POST | `/complaints/{id}/confirm` | unit rep (own unit) | `resolved` → `closed` |
| POST | `/complaints/{id}/reopen` | unit rep (own unit), admin, engineer | `resolved` → `reopened`, reason required |

Filters on the list: `status`, `unit_id`, `priority`, `device_id`, `assigned_to`, `date_from`,
`date_to` (inclusive Africa/Lagos days on the creation date). Newest first.

## Status flow

```
            assign                 note required            unit confirms
 open ───────────────▶ in_progress ─────────────▶ resolved ───────────────▶ closed
  │                       ▲   │                      │
  │ reason required       │   │ reason required      │ unit disputes / reopens
  └────▶ closed ◀─────────┼───┘                      ▼
                          └─────────────────────── reopened
                              (assign: back to work)
```

| Moved by | Transition |
|---|---|
| Engineering, `PATCH` | `open`/`reopened` → `in_progress` (naming an assignee does this automatically) |
| Engineering, `PATCH` | `in_progress` → `resolved` (resolution note required) |
| Engineering, `PATCH` | `open`/`in_progress` → `closed` (reason required: duplicate or mistaken ticket; `resolved_at` stays empty) |
| Device event (Milestone 6) | intake → `in_progress`; return → `resolved`; confirmed return → `closed`; disputed return → `reopened` |
| The unit | `resolved` → `closed` (`confirm`) or `reopened` (`reopen`, or disputing the returned device) |

Engineering can **never** close a `resolved` ticket: only the unit can, so a repair is never
signed off by the party that did it. A ticket left `resolved` is reported (Milestone 7), not
auto-closed.

Anything else returns `409 INVALID_TRANSITION` with `{"current": ..., "allowed": [...]}`. Resolved
or closed tickets reject engineering changes with `409 TICKET_NOT_ACTIVE`.

### Tickets with a repair cycle

* While a device taken in for the ticket has not been returned, engineering cannot resolve or
  close it (`409 DEVICE_IN_REPAIR`).
* Once a `returned_to_unit` event exists without an acknowledgement, `confirm` and `reopen`
  answer `409 AWAITS_ACKNOWLEDGEMENT`: the unit must acknowledge the device instead, which then
  closes or reopens the ticket.

## Every change is explained

Each assignment, priority change and status change writes a **system comment**
(`"is_system": true`) authored by the user who acted, for example:

```
Priority: medium -> high. Assigned to Ada Obi. Status: open -> in_progress.
Status: in_progress -> resolved. Device returned to the unit (device event #41).
Status: resolved -> reopened. Reason: Fault is back
```

Comments are append-only (database trigger). Clients cannot create system comments. Reopening
clears `resolved_at` and `closed_at` because they describe the *current* state; the system
comments keep the full history.

## How device events drive tickets

`backend/app/services/complaints.py` exposes `on_intake`, `on_return` and `on_return_acknowledged`. The
events module (`docs/EVENTS.md`) calls them inside its own transaction; they lock the ticket and do
not commit. Intake also **links a ticket raised without a device** to the device taken in and
**assigns the engineer** who logged it when nobody was assigned; both are recorded in the system
comment. A device that is decommissioned mid-repair no longer blocks resolving or closing its
ticket by hand.

## Visibility

Admin, engineer and auditor see every ticket. A unit rep sees only their own unit's. Another
unit's ticket and a missing id give the same `404 COMPLAINT_NOT_FOUND`. Comments are visible to
both sides; there are no private engineering notes.
