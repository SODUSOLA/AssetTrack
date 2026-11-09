# Frontend

A React single-page app in [`frontend/`](../frontend). It talks to the API only through the typed
client in `src/api/`, and is served by the API itself at `/app/` so the browser sees one origin.

## Why one origin

The refresh token is an httpOnly, SameSite=Strict cookie scoped to `/api/v1/auth`. A browser only
sends it when the app and the API share an origin, so the built app is mounted by FastAPI
(`backend/app/core/spa.py`) and the dev server proxies `/api` to the API. There is no CORS configuration
and none is needed.

## Run it

```bash
docker compose up --build        # the image builds the app; open http://localhost:8000/app/
```

For development, with the API on `:8000`:

```bash
cd frontend
npm ci                           # postinstall runs the iCloud step, see "iCloud" below
npm run dev                      # http://localhost:5173/app/, /api proxied to :8000
```

Try it with sample data (development only; refuses `ENV=production` and a database that already
has users). It prints a random password once:

```bash
cd backend && python -m scripts.seed_demo
```

## Scripts

| Command                | What it does                                                       |
| ---------------------- | ------------------------------------------------------------------ |
| `npm run dev`          | Vite dev server with the API proxy                                 |
| `npm run build`        | Typecheck, then build into `../backend/app/static` (served at `/app/`)      |
| `npm run typecheck`    | `tsc --noEmit`, strict, `noUncheckedIndexedAccess`                  |
| `npm run lint`         | ESLint (React hooks, jsx-a11y, no HTML injection)                   |
| `npm run format:check` | Prettier                                                           |
| `npm test`             | Vitest + Testing Library + MSW + axe                                |
| `npm run api:dump`     | Rewrite `frontend/openapi.json` from the backend                    |
| `npm run api:types`    | Regenerate `src/api/schema.d.ts` from `openapi.json`                |

CI fails if `openapi.json` or `schema.d.ts` is out of date, so an API change cannot reach the app
unnoticed: an invented path or field does not compile.

## Layout

```
src/api/         client, session, errors, generated schema
src/components/  ui/ (design system), layout/
src/features/    auth, dashboard, devices, complaints, acknowledgements, reports, units, users, events
src/lib/         format (Lagos time), labels, permissions, messages
src/styles/      tokens.css (design tokens), base.css, print.css
src/test/        MSW server, render helpers
```

## Session handling

- The access token (30 minutes) is held in memory only: never in storage, never in a URL.
- A reload starts with a silent refresh using the cookie. A refusal shows the sign-in page.
- The server rotates the refresh token and treats a reused one as theft. So refreshes are
  single-flight within a tab and serialised across tabs (Web Locks), with the new token shared
  over a same-origin BroadcastChannel.
- One refresh-and-retry on `401`. A refused refresh ends the session in every tab.

## Complaints

- **List** (`/complaints`): filters for status, priority, unit, "assigned to me" and a date range
  live in the URL. A unit rep sees only their unit and has no unit or assignee filter.
- **Page** (`/complaints/:id`): a progress strip, the description, an append-only thread (the
  server's own entries are styled as recorded changes, apart from people's comments) and the
  device events linked to the ticket.
- **Who can do what** is in `features/complaints/rules.ts`, following `docs/COMPLAINTS.md`. The
  API sends no list of allowed moves, so the UI derives them from role and status and the server
  checks every move: a refusal (`DEVICE_IN_REPAIR`, `AWAITS_ACKNOWLEDGEMENT`, `INVALID_TRANSITION`,
  `TICKET_NOT_ACTIVE`, ...) is shown as a plain sentence from `lib/messages.ts`.
- Staff resolve (a note is required) or close a duplicate or mistaken ticket (a reason is
  required); they are never offered a way to close a *resolved* ticket. Only the unit confirms, or
  reopens with a reason. While a returned device still waits for the unit's answer, the page sends
  the rep to the device instead.
- **Assigning:** only the head of engineering can list users, so only they can pick anyone. An
  engineer can take a complaint for themselves. Giving engineers a staff list would need a small
  API addition.
- A complaint can be raised without a device; engineering links it when the device is taken in.

## Administration

Only the head of engineering (menu: **People**, **Units**; the API refuses anyone else too).

- **People:** add (name, email, role, and unit for a representative), edit name, role and unit,
  reset a password, deactivate or reactivate. The starting password is generated in the browser,
  sent to the API, and shown once in a dialog with a copy button; it is never kept. A reset signs the
  person out everywhere. Nobody is deleted. The head of engineering cannot change their own role or
  deactivate themselves; the server also refuses to remove the last active head of engineering.
- **Units:** add, rename, deactivate or reactivate. The API has no rule stopping a unit with devices
  being deactivated; the dialog says only what is true (it is no longer offered, records stay).

## Reports

- `/reports` shows one of the five reports, chosen and set up through the address (`?report=`,
  `month`, `from`, `to`, `min`, `recent`, `unit`), so a view can be bookmarked or shared. Each
  report shows only the settings it has; a unit rep sees their own unit and no unit filter.
- Every report arrives in one generic shape, and `ReportView` draws any of them: summary figures,
  then a table per section with a totals row and the section's note. A new report in the API needs
  no new screen. Cells are formatted by the column's declared type (Lagos dates and times).
- **Print** (every role that can open reports, including the head of engineering) uses the browser's
  print dialog. `print.css` hides the sidebar and controls, always prints light (`lib/printTheme.ts`
  switches the theme for the duration of `beforeprint`/`afterprint`, so Ctrl+P works too), draws
  real tables with repeating headers, and ends with "Printed from the LASRRA Engineering Audit
  Register". The card layout is screen-only, so paper always gets tables.
- **Excel and PDF** are fetched through the signed-in client (a plain link could not carry the
  token) with the same settings as the screen, then saved under the server's file name.
- **No vendors anywhere** (SPEC v1.2): the backend, the reports and their Excel and PDF files no longer
  have the concept, so the screens have nothing to hide. Browser tests still check that no page or
  report mentions vendors.

## Permissions

`src/lib/permissions.ts` only decides which buttons are shown. The API enforces every rule and
answers identically for "not yours" and "does not exist"; the UI never treats a hidden button as
security.

## Decisions that follow the business

- **No money anywhere** (SPEC v1.1). No price field or column exists in the API
  (`backend/tests/test_no_pricing.py`), so the app has nothing to show.
- **Repairs are in-house** (SPEC v1.2). There is no "send to vendor" step, vendor page, status or
  report column, in the interface or in the API.
- **Acknowledgement is a stamp**, shown with text and an icon as well as colour. Nothing is ever
  confirmed on a unit's behalf; staff see what is waiting but get no way to answer for a unit.
- **Official colours**: dark green, light green and yellow, defined once in
  `src/styles/tokens.css`, with a light and a dark theme. Contrast of every text pair, in both
  themes and the sidebar, is checked by `src/styles/tokens.test.ts`.

## Security

- **Policy.** `/app` is served with `default-src 'self'`, `script-src 'self'` (no inline script, no
  `eval`), `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, plus `nosniff`,
  `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY` (`backend/app/core/spa.py`).
- **The one inline style.** The dialog and menu library locks page scrolling by injecting a
  `<style>` whose text contains the scrollbar width, so it cannot be allowed by hash. The server
  puts a fresh random nonce in each page (`<meta name="csp-nonce">`) and in that page's
  `style-src`, and `lib/cspNonce.ts` hands it to the library. Scripts never get a nonce. If this
  breaks, the browser tests report a policy violation.
- **Tokens.** The access token lives in memory only (never storage or an address); the refresh
  token is an httpOnly, `SameSite=Strict` cookie that only the auth endpoints receive. Replaying a
  rotated refresh token ends every session (tested).
- **Hostile text** (a complaint titled `<img onerror=...>`, markup in the address) is shown as text
  and runs nothing (tested). No `dangerouslySetInnerHTML` or `innerHTML`; ESLint forbids them.
- **Server errors** show a plain sentence, never internals.
- **Dependencies.** `npm audit` reports one moderate advisory (`minimatch`, a denial of service),
  reached only through the lint and type-generation tools. It is not in any shipped (runtime)
  dependency or in the browser bundle. Fixing it needs major upgrades of tools pinned for
  compatibility; revisit at each tool upgrade. The Python dependencies have not been audited.
- Theme is applied by an external `theme-init.js` because the policy forbids inline scripts.

## Accessibility

Radix primitives for dialogs, menus, tabs and tooltips; focus moves to the page title on
navigation; every form field has a label and an error tied to it; tables become cards when their own
width is too small for their columns (`DataTable`'s `cardsBelow`, measured with ResizeObserver); `prefers-reduced-motion` and `prefers-color-scheme` are respected. Pages are checked
with axe in tests. Automated checks do not replace a keyboard and screen-reader pass; do one
before go-live.

## Tests

- `npm test` (223): formatting in Lagos time, permissions, the session and client (including refresh
  races), design-token contrast, the form-versus-OpenAPI contracts, and every screen against a mocked
  network (including axe).
- `scripts/e2e.sh` (Playwright, real browser, real API, throwaway database seeded with demo data):
  - the whole life of a repair, step by step, as the people who do it;
  - who can see what (another unit's device, admin pages, an auditor);
  - sign-in and sign-out, the sign-in limit, reload;
  - reports, Print (emulated paper: no menu, light, tables) and the Excel and PDF downloads;
  - adding, signing in and deactivating a person;
  - **security**: headers, cookie flags, nothing sensitive in storage or addresses, hostile text,
    no policy violations, a replayed refresh token;
  - **keyboard**: skip link, dialog focus, menus, form errors, the phone drawer;
  - **every page at 360, 390, 768, 1024, 1280 and 1440 pixels, light and dark**: no sideways scroll
    and no axe violations.
- Locally it uses your Chrome; CI installs Chromium (`.github/workflows/ci.yml`, job `e2e`, which has
  not yet run on GitHub). Each sign-in comes from its own forwarded address because the API limits
  sign-in to 5 a minute; the e2e server alone is started with `--proxy-headers`.
- `npm run budget` fails the build if the app grows past its size budget (entry script 130 kB, all
  scripts 262 kB, styles 14 kB, gzipped; today 113, 227 and 12).
- Not done: a screen-reader and keyboard pass by a person (see `docs/ACCESSIBILITY.md`), a Lighthouse
  run, WebKit and Firefox runs.

## iCloud

If the project lives under an iCloud-synced folder (Desktop/Documents), `node_modules` is moved to
`node_modules.nosync` and symlinked, so iCloud does not evict or conflict-copy thousands of files.
`npm install` replaces the symlink; run `npm run nosync` afterwards. Cloning the repo outside
iCloud avoids all of this.
