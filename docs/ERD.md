# Entity Relationship Diagram

Source of truth: [`alembic/versions/0001_initial_schema.py`](../backend/alembic/versions/0001_initial_schema.py)
(SPEC.md section 4), [`0002_refresh_tokens.py`](../backend/alembic/versions/0002_refresh_tokens.py) and
[`0003_remove_pricing.py`](../backend/alembic/versions/0003_remove_pricing.py) and
[`0006_remove_vendors.py`](../backend/alembic/versions/0006_remove_vendors.py). Tables marked
**append-only** reject `UPDATE`, `DELETE` and `TRUNCATE` at the database level.

The system records no monetary values (SPEC v1.1), so there is no costs table. Repairs are done
in-house (SPEC v1.2), so there is no vendors table.

```mermaid
erDiagram
    units ||--o{ users : "has representatives/staff"
    units ||--o{ devices : "currently holds"
    units ||--o{ complaints : "raises"

    users ||--o{ complaints : "raised_by / assigned_to"


    devices ||--o{ device_events : "timeline"
    devices ||--o{ complaints : "about (optional)"
    complaints ||--o{ device_events : "linked (optional)"
    complaints ||--o{ complaint_comments : "thread"
    device_events ||--o| acknowledgements : "acknowledged once"
    device_events ||--o{ device_events : "corrects_event_id"
    users ||--o{ device_events : "actor / counterparty"
    users ||--o{ acknowledgements : "acknowledged_by"
    users ||--o{ refresh_tokens : "sessions"

    units {
        uuid id PK
        text name UK
        text code UK
        bool is_active
    }
    users {
        uuid id PK
        citext email UK
        user_role role
        uuid unit_id FK "required for unit_rep"
    }
    devices {
        uuid id PK
        text asset_tag UK "LAS-ENG-000123"
        text serial_number UK "nullable"
        text device_type
        uuid unit_id FK "NULL = central stock"
        device_status status "snapshot"
    }
    complaints {
        uuid id PK
        text ticket_no UK "TKT-YYYY-00001"
        uuid unit_id FK
        uuid device_id FK "optional"
        complaint_status status "snapshot"
    }
    complaint_comments {
        bigint id PK "append-only"
        uuid complaint_id FK
        uuid author_id FK
    }
    device_events {
        bigint id PK "append-only"
        uuid device_id FK
        event_type event_type
        device_status to_status
        uuid actor_id FK
        timestamptz occurred_at "server time"
    }
    acknowledgements {
        bigint id PK "append-only"
        bigint event_id FK, UK
        ack_status status
    }
    refresh_tokens {
        uuid id PK "not part of the audit trail"
        uuid user_id FK
        text token_hash UK "SHA-256 only"
        timestamptz expires_at
        timestamptz revoked_at
    }
```

## Guard behaviour

`device_events`, `acknowledgements` and `complaint_comments` reject `UPDATE`, `DELETE` and
`TRUNCATE` (also via `CASCADE`). All guard exceptions use SQLSTATE `23001`
(`restrict_violation`), so the service layer can catch them by code.
