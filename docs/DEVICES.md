# Devices

Implements SPEC section 6 (v1.1). All routes are under `/api/v1`.

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/devices` | admin, engineer | register |
| GET | `/devices` | all roles (unit rep: own unit only) | filters below |
| GET | `/devices/{id}` | all roles (scoped) | details, unit, open complaint count |
| PATCH | `/devices/{id}` | admin, engineer | metadata only |
| GET | `/devices/{id}/timeline` | all roles (scoped) | the audit view |
| GET | `/units/{id}/devices` | all roles (unit rep: own unit only) | same filters |

List filters: `unit_id`, `status`, `device_type` (case-insensitive exact), `q` (substring of the
asset tag or serial number, case-insensitive, `%` and `_` are literal), plus `page` and
`page_size`. Results are ordered by asset tag. Decommissioned devices are included; filter with
`status=decommissioned`.

## Registering

`POST /devices` creates the device (central stock, status `in_stock`) and a `device_registered`
event in **one transaction**; if either fails neither exists. The asset tag (`LAS-ENG-000123`) is
generated. Only `device_type` is required; `serial_number`, `make`, `model` and `acquired_on` are
optional. Placing the device in a unit is the `assigned_to_unit` event (Milestone 6).

Input rules:

* Unknown fields are rejected with 422, so a client cannot send `status`, `unit_id`,
  `asset_tag`, `created_by` or `occurred_at`.
* `device_type` is trimmed, whitespace-collapsed and lower-cased (`" Laptop  Pro "` becomes
  `laptop pro`) so reports do not split "Laptop" from "laptop".
* Blank `serial_number`, `make` and `model` become NULL.
* Serial numbers are unique ignoring letter case (`409 SERIAL_EXISTS`).

## Correcting metadata

`PATCH /devices/{id}` accepts `device_type`, `serial_number`, `make`, `model`, `acquired_on`.
Omitted fields are unchanged; `null` clears serial, make, model or date (not `device_type`).
Every real change writes **one `note_added` event** with a readable summary:

```
Metadata updated: serial_number "SN-1" -> "SN-1B"; model (none) -> "XPS 13"
```

The event records the actor, the unit at that moment and leaves the device status unchanged.
A patch that changes nothing writes nothing. Status and unit are never patchable.

## Timeline

`GET /devices/{id}/timeline?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`

```jsonc
{
  "device": { "asset_tag": "...", "status": "...", "unit": { ... } },
  "events": [
    {
      "id": 41, "event_type": "returned_to_unit",
      "from_status": "repaired", "to_status": "assigned",
      "occurred_at": "2026-10-27T09:12:03Z",          // UTC, display in Africa/Lagos
      "actor": { "id": "...", "full_name": "..." },    // engineering staff
      "unit": { ... },                                 // unit at the time of the event
      "counterparty_name": "Ada Obi", "counterparty_user": { ... },
      "complaint": { "ticket_no": "TKT-2026-00007" },
      "diagnosis": null, "notes": null, "corrects_event_id": null,
      "ack_state": "pending",       // not_required | pending | confirmed | disputed
      "pending_days": 2, "overdue": false,
      "acknowledgement": null       // or { status, comment, acknowledged_at, acknowledged_by }
    }
  ]
}
```

* Ordered by `occurred_at`, then id.
* `date_from` / `date_to` are **inclusive Lagos calendar days**; an event at 23:30 UTC on 31 Oct
  is 00:30 on 1 Nov in Lagos and belongs to 1 Nov.
* `overdue` is true for an acknowledgement-required event still pending after `ACK_OVERDUE_DAYS`.
  Nothing is ever auto-confirmed.
* A fixed number of database queries however many events there are (tested).
* Not paginated: it is one document per device.
* A unit rep sees the whole history of a device that is currently in their unit.

## Visibility

Admin, engineer and auditor see every device. A unit rep sees only devices whose current unit is
their own. For anything else (another unit's device, a device in central stock, or an id that does
not exist) the answer is the same `404 DEVICE_NOT_FOUND`, so ids cannot be probed.
