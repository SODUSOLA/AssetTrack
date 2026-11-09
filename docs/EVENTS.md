# Device events and acknowledgements

Implements SPEC section 8 (v1.1), the audit core. All routes are under `/api/v1`.

| Method | Path | Who |
|---|---|---|
| POST | `/devices/{id}/events` | admin, engineer |
| GET | `/events` | all roles (unit rep: events of devices in their unit) |
| GET | `/events/{id}` | all roles (scoped) |
| POST | `/events/{id}/acknowledge` | unit rep of the event's unit |
| GET | `/acknowledgements/pending` | all roles (unit rep: own unit) |

The log is **append-only**: nothing is ever edited or deleted (database triggers enforce it).
Mistakes are corrected by adding a `note_added` event that names the event it corrects.

## The state machine

| Event | From status | To status | Fields (besides optional `notes`) |
|---|---|---|---|
| `assigned_to_unit` | `in_stock` | `assigned` | `unit_id`, `counterparty_name` (who received), optional `counterparty_user_id` |
| `received_for_repair` | `assigned` | `received_for_repair` | `complaint_id`, `counterparty_name` (who handed it in), optional `counterparty_user_id` |
| `diagnosed` | `received_for_repair` | `diagnosed` | `diagnosis` |
| `repair_started` | `diagnosed`, `awaiting_parts` | `in_repair` | none |
| `parts_requested` | `in_repair` | `awaiting_parts` | `notes` (required) |
| `repair_completed` | `in_repair` | `repaired` | `notes` (required) |
| `returned_to_unit` | `repaired` | `assigned` | `counterparty_name` (who collected), optional `counterparty_user_id` |
| `decommissioned` | any but `decommissioned` | `decommissioned` | `notes` (the reason, required) |
| `note_added` | any | unchanged | `notes` (required), optional `corrects_event_id`, optional `complaint_id` |

`device_registered` is written by the system when a device is registered; it cannot be posted.

* Each event takes **exactly** its own fields. Anything else, including `occurred_at`, `status`,
  `actor_id`, or a `complaint_id` on a repair step, is rejected with 422.
* An event that does not fit the device's status returns
  `409 INVALID_TRANSITION` with the current status and what is allowed:

```json
{"error": {"code": "INVALID_TRANSITION", "message": "...",
  "details": {"current": "assigned", "attempted": "repair_completed",
              "allowed": ["received_for_repair", "decommissioned", "note_added"]}}}
```

## How an event is recorded

One database transaction, all or nothing:

1. lock the **device** row (`SELECT … FOR UPDATE`);
2. check the transition and every reference (unit, ticket, counterparty, corrected event);
3. append the event (actor, unit at that moment, and a database-stamped time), update the device,
   and run the ticket effects below;
4. commit. Any failure, including a ticket rule, rolls everything back.

Because the device is locked, two simultaneous events cannot both succeed from the same state; a
test races eight threads and exactly one wins. Only the device row is locked, never an audit row,
so the production database role needs just `INSERT` and `SELECT` on `device_events`,
`acknowledgements` and `complaint_comments`; a test runs the entire lifecycle under such a role.

The time is `clock_timestamp()` read after the lock is held, so events of one device are timestamped
in the order they actually happened (`now()` is the start of the transaction and could put a later
event before an earlier one).

## Tickets and events

* **Intake** (`received_for_repair`) names the ticket. It must belong to the device's unit and be
  about this device or about none yet (it is then linked to the device). The ticket becomes
  `in_progress`, and if nobody was assigned the engineer logging the intake is.
* Every step from `diagnosed` to `returned_to_unit` is linked to that ticket automatically, so the
  ticket page shows the whole repair.
* **Return** (`returned_to_unit`) makes the ticket `resolved`. The unit's acknowledgement then
  closes it (confirmed) or reopens it (disputed). Engineering logs a new intake against the same
  ticket to start the next cycle.
* A finished (`resolved`/`closed`) ticket cannot take a new intake (`409 TICKET_NOT_ACTIVE`).
* **Decommissioning mid-repair** is allowed. A decommissioned device no longer blocks its ticket,
  so engineering can resolve or close it by hand with a note.

## Acknowledgements

Required for `assigned_to_unit`, `received_for_repair` and `returned_to_unit`.

```
POST /events/{id}/acknowledge   {"status": "confirmed"}
POST /events/{id}/acknowledge   {"status": "disputed", "comment": "The screen is still cracked"}
```

| Case | Answer |
|---|---|
| Rep of the event's unit, first answer | 201, the event with its acknowledgement |
| A dispute without a comment | 422 |
| Already acknowledged (by anyone) | 409 `ALREADY_ACKNOWLEDGED` |
| Another unit's event | 403 `FORBIDDEN` |
| Admin, engineer, auditor | 403 |
| Event that needs no acknowledgement | 409 `ACK_NOT_REQUIRED` |
| Unknown event | 404 |

A dispute **never changes history**: the event, the device and the log stay as they were.
Engineering answers with a `note_added` event (optionally `corrects_event_id`) and/or a ticket
comment. Nothing is ever auto-confirmed.

## Reading

* `GET /events`: newest first. Filters `device_id`, `unit_id` (the unit recorded on the event; staff
  only), `event_type`, `actor_id`, `date_from`, `date_to` (inclusive Africa/Lagos days).
* `GET /acknowledgements/pending`: events still unanswered, **oldest first**, each with
  `pending_days` and `overdue` (older than `ACK_OVERDUE_DAYS`, default 3). Filters `unit_id` (staff)
  and `overdue`.
* Each event carries `ack_state`: `not_required`, `pending`, `confirmed` or `disputed`.
