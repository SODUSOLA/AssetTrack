# Running the register

How to start it, keep it safe, and check it is ready for people to use. Anything not stated here
is not yet decided or tested: it is marked as such.

## What runs

One container serves both the API (`/api/v1`) and the web app (`/app/`), on the same address, next
to a PostgreSQL 16 database. The same address matters: the sign-in cookie is only sent to the
address that set it.

```bash
cp backend/.env.example backend/.env   # then set SECRET_KEY and ENV=production, see below
docker compose up -d --build
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m scripts.create_admin --email head@your-domain.example --name "Head of Engineering"
```

Open `http://<host>:8000/app/`. The head of engineering then adds everyone else under **People**
(each person is given a starting password once, and changes it after signing in) and the
departments under **Units**.

## Before real people use it

- [ ] **HTTPS.** Put a reverse proxy with a certificate in front. `ENV=production` makes the sign-in
      cookie `Secure`, so signing in will not work over plain HTTP. Not tested here: no proxy is
      configured in this repository.
- [ ] **`ENV=production`** and a long random **`SECRET_KEY`** (the app refuses to start otherwise).
      Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- [ ] **Real client addresses.** Sign-in is limited to 5 a minute per address. Behind a proxy every
      request looks like it comes from the proxy unless uvicorn is told to trust it
      (`--proxy-headers --forwarded-allow-ips=<the proxy's address>`, never `*` on a reachable port).
      Without this, five wrong passwords from anyone lock everybody out for a minute. Not configured
      here; decide when the proxy is chosen.
- [ ] **`CORS_ORIGINS`** is not needed by the web app (same address). Leave it as the app's own
      address.
- [ ] **No demo data.** `backend/scripts/seed_demo.py` refuses to run with `ENV=production`; never run it
      against a real database.
- [ ] **A first sign-in test** as each role (head of engineering, engineer, auditor, a unit
      representative): see `docs/ACCESSIBILITY.md` for the people-side checks.
- [ ] **A screen-reader and keyboard pass** by a person (automated checks cannot replace it).

## Backups

The database is the record; the application holds nothing else.

```bash
docker compose exec -T db pg_dump -U audit -Fc audit > register-$(date +%F).dump   # back up
docker compose exec -T db pg_restore -U audit -d audit --clean < register-DATE.dump  # restore
```

Decide, before go-live: how often, where the copies go (off this machine), who restores, and
practise one restore into an empty database. None of this is automated yet.

The audit tables reject `UPDATE`, `DELETE` and `TRUNCATE` in the database itself. If the database
role the app uses is ever restricted further, it needs only `INSERT` and `SELECT` on them.

## Updating

```bash
git pull
docker compose up -d --build
docker compose run --rm api alembic upgrade head   # only when a release adds a migration
```

Migrations are applied by hand and never by the web process. Take a backup first. Sessions survive
an update; the access token lasts 30 minutes and renews itself.

## People and access

- There is no public sign-up. Only the head of engineering creates accounts.
- People are never deleted (the record points at them). **Deactivate** instead; that also signs
  them out everywhere.
- Resetting a password signs the person out everywhere and shows a new password once.
- At least one active head of engineering must always remain; the system refuses to remove the last.
- Forgotten passwords: the head of engineering resets it. If the head of engineering is locked out,
  create another admin on the server with `python -m scripts.create_admin`.

## When something looks wrong

| Symptom | Likely cause |
| --- | --- |
| Everyone is told "Too many attempts" | The proxy's address is being counted as one person; see "Real client addresses". |
| Signing in does nothing, no error | The site is served over HTTP with `ENV=production` (the cookie is `Secure`). |
| People are signed out when they reload | The app and the API are on different addresses; they must share one. |
| A page is blank after an update | An old copy is cached; the app shell is never cached, but a reload may be needed once. |
| Excel/PDF names show boxes instead of accents | No Unicode font on the host; the Docker image installs one. |

Health: `GET /health` returns 200 when the API is up.

## Tests, and what they cover

```bash
(cd backend && poetry run pytest)   # API: 808 tests
cd frontend && npm test            # screens: 223 tests
scripts/e2e.sh                     # real browser against the real API, throwaway database
```

`scripts/e2e.sh` needs the database container running, a built app (`cd frontend && npm run build`)
and Chrome (or `E2E_BUNDLED=1` after `npx playwright install chromium`). It checks every journey
and every page at six screen sizes, in light and dark, for accessibility violations.
