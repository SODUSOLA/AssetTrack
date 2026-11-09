# Authentication and Roles

Implements SPEC section 5. All routes live under `/api/v1`; errors use
`{ "error": { "code", "message", "details" } }`.

## Sessions

| Piece | Behaviour |
|---|---|
| Passwords | argon2id, 10 to 128 characters. Hashes are upgraded transparently on login if parameters change. |
| Access token | JWT (HS256), 30 min (`ACCESS_TOKEN_MINUTES`), returned in the JSON body, kept **in memory** by the frontend. Claims: `sub`, `role`, `unit_id`, `typ=access`, `iat`, `exp`. |
| Refresh token | Opaque random value in an httpOnly, SameSite=Strict cookie scoped to `/api/v1/auth`, 7 days (`REFRESH_TOKEN_DAYS`). `Secure` is set when `ENV=production`. Only its SHA-256 hash is stored (`refresh_tokens`). |
| Rotation | Each `POST /auth/refresh` revokes the presented token and issues a new one. |
| Reuse detection | Presenting an already-revoked refresh token revokes **every** session of that user (assumed stolen). |
| Logout | Revokes the presented refresh token and clears the cookie. |
| Change password | Needs the old password; ends the user's other sessions, keeps the current one. |
| Admin reset / deactivate | `PATCH /users/{id}` with `password` or `is_active: false` ends all of that user's sessions. |

**The database is the authority, not the token.** `get_current_user` loads the user on every
request and uses the stored role, unit and `is_active`. A demoted or deactivated user loses
access immediately, not when the 30-minute token expires. The claims are informational.

Frontend note (Milestone 8): `api.js` must run at most one refresh at a time. Two parallel
refreshes with the same cookie look like token reuse and end the session.

## Login protection

* 5 attempts per minute per IP (`429 RATE_LIMITED` with `Retry-After`). Storage is in-memory,
  correct for one API process. Behind a reverse proxy the real client IP must be configured
  at deploy time (Milestone 9).
* Unknown email, wrong password and inactive account all return the same `401
  INVALID_CREDENTIALS`, and unknown emails still pay for a password hash check.

## Permission matrix

Enforced by `require_roles(...)` on each route and tested in `backend/tests/test_permissions.py`.

| Endpoint | admin | engineer | auditor | unit_rep |
|---|:-:|:-:|:-:|:-:|
| `POST /auth/login`, `/refresh`, `/logout` | public | public | public | public |
| `GET /auth/me`, `POST /auth/change-password` | yes | yes | yes | yes |
| `GET /units` | yes | yes | yes | yes |
| `POST /units`, `PATCH /units/{id}` | yes | | | |
| `GET, POST /users`, `GET, PATCH /users/{id}` | yes | | | |

Judgment call beyond the spec's table: every signed-in role may list unit names and codes.

## Rules enforced by the service layer

* No public signup. Accounts are created by an admin, who sets the initial password.
* `unit_id` is required for `unit_rep` and rejected for every other role. Leaving the `unit_rep`
  role clears the unit.
* Users are never deleted (audit rows reference them); deactivate instead.
* The last active admin cannot be demoted or deactivated (`409 LAST_ADMIN`).
* Emails are unique case-insensitively (`CITEXT`). Validation is syntactic; the reserved
  `.test` TLD is accepted, other reserved names (`.local`, `.invalid`) are rejected.
* User and unit changes are written to the `app.admin` log with the acting user's id.
  There is no database audit table for them (SPEC does not define one).

## Unit scoping

`backend/app/services/scope.py` is how every unit-owned query must be filtered:

| Helper | Use |
|---|---|
| `scoped_unit_id(user)` | the unit a `unit_rep` may see, or `None` for other roles |
| `apply_unit_scope(stmt, user, column)` | add the `WHERE unit = ...` clause to a query |
| `resolve_unit_filter(user, requested)` | list endpoints: a `unit_rep`'s own unit overrides any `unit_id` query parameter |
| `can_access_unit(user, unit_id)` | boolean form of the above; `False` for another unit *and* for central stock (`None`) |
| `ensure_unit_access(user, unit_id)` | single-object endpoints: `404` (not 403) for another unit's data |

Each module that returns unit data (devices, complaints, events, reports) adds its own
two-unit test, as required by SPEC 12.1 test 3.

## Creating the first admin

```bash
docker compose run --rm api python -m scripts.create_admin \
    --email head@your-domain.example --name "Head of Engineering"
```

The password is prompted for twice, or read from `ADMIN_PASSWORD` for non-interactive use. It is
never accepted as a command-line argument.
