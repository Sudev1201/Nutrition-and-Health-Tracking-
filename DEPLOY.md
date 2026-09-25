# Deploying healthMonitor

**Nothing has been deployed.** Plan 9 wrote the deploy files and rehearsed them on one machine, with a local Docker image and scratch databases. No account exists on any host, no domain has been bought, no DNS record exists, no image has been pushed to a registry, and no command in this file has been run against a real account. Every host name below is a placeholder.

This runbook is for the first deploy, and it is written in the order you do it.

## What runs where

| Piece | Host | Files in this repo |
|---|---|---|
| API (FastAPI) | Fly.io, one always-on machine in `bom` (Mumbai) | `backend/Dockerfile`, `backend/.dockerignore`, `backend/fly.toml` |
| Database | Neon Postgres, `aws-ap-south-1` (Mumbai) | migrations in `backend/alembic/`, seed data via `backend/scripts/seed_snapshot.py` |
| Web app (the SPA) | Cloudflare Pages, built from `frontend/` | `frontend/public/_headers`, `frontend/public/_redirects`, `frontend/.env.example` |

Both web hosts live under one registrable domain that you own: the app at `app.<domain>` and the API at `api.<domain>`. This is not a style choice:
- The session cookie is set by `api.<domain>`, host-only, `Secure`, `HttpOnly` and `SameSite=Lax`.
- The browser sends a `Lax` cookie with the app's requests only when the app and the API are the same *site*: the same registrable domain, both over https.
- `*.pages.dev`, `*.fly.dev`, `*.vercel.app` and `*.up.railway.app` are public suffixes. An app served from one of those names is a different site from `api.<domain>`, so its sign-in "succeeds" and then every request answers 401.

Check the regions when you sign up. If Neon does not offer Mumbai, use Singapore (`aws-ap-southeast-1`) with Fly's `sin`, and change `primary_region` in `backend/fly.toml` to match.

## What you do by hand, in order

Each step is explained in the sections below. None of it can be done from the repository.

1. **Accounts.** Create accounts at Fly.io (it asks for a card), Neon and Cloudflare, and install `flyctl` on your laptop.
2. **Domain.** Buy a domain, and serve its DNS from Cloudflare.
3. **Database.** Create the Neon project, and copy its **direct** connection string.
4. **Google sign-in.** Add `https://app.<domain>` to the OAuth client's Authorised JavaScript origins.
5. **Secrets.** Generate the session secret, and the optional reminder and AI-description keys. Keep them in a password manager.
6. **Placeholders.** Replace the placeholders in `backend/fly.toml`.
7. **API.** Create the Fly app, store the secrets, and deploy. The release step migrates the database.
8. **Seed data.** Build a snapshot at the deployed commit, and import it into Neon.
9. **API domain.** Add the certificate for `api.<domain>` and its DNS record.
10. **Web app.** Create the Cloudflare Pages project, with its build variables and the custom domain `app.<domain>`, and redirect `*.pages.dev` to it.
11. **Check it.** Sign in and walk the app. Check Safari's cookie lifetime on an iPhone.

## 1. Accounts and tools

- **Fly.io** runs the API. Install `flyctl` (<https://fly.io/docs/flyctl/install/>) and run `fly auth login`.
- **Neon** hosts Postgres. The free plan is enough to start. See "Reminders keep the database awake" below before you choose a plan.
- **Cloudflare** serves DNS and hosts the web app on Pages. Pages builds from the GitHub repository, so nothing else needs installing.
- **Tools you already have:** the repository checkout with `uv` and Node 22, plus Docker with the compose Postgres, to build the seed snapshot (step 8).

## 2. The domain

Buy a domain from any registrar, and add it to Cloudflare (Websites, then Add a site). If the registrar is not Cloudflare, change its nameservers to the two Cloudflare gives you. This runbook writes the domain as `<domain>`, so `app.<domain>` might be `app.example.com`.

## 3. The database

1. Create a Neon project in `aws-ap-south-1`, on Postgres 16 or later. The snapshot import uses `COPY … HEADER MATCH`, which needs Postgres 15 or later, and development runs 16.
2. In the project's connection details, turn **connection pooling off** and copy the connection string. It looks like `postgresql://<user>:<password>@ep-<name>.ap-south-1.aws.neon.tech/neondb?sslmode=require`.
   - Use the **direct** host, never the `-pooler` one. The ETL holds a session-level advisory lock, and psycopg prepares statements, and a transaction pooler breaks both.
   - The app turns `postgresql://` and `postgres://` into the `postgresql+psycopg://` form SQLAlchemy needs, so paste it as Neon gives it.
   - Keep `sslmode=require`.

This URL is a secret. On your laptop, keep it out of your shell history by reading it into a variable. Nothing echoes:

```bash
read -rs NEON_URL      # paste the URL, then press Enter
```

The commands below use `"$NEON_URL"`, and they run from `backend/`.

## 4. Google sign-in

Use the OAuth client from the spec's "Prerequisite: Google OAuth client" section, or create a second Web application client for production.

- Under **Authorised JavaScript origins**, add `https://app.<domain>`: scheme and host only, with no path and no trailing slash. Keep the two localhost origins for development.
- Leave **Authorised redirect URIs** empty. The app uses the Google Identity Services callback.
- **Never deploy the client secret.** The backend checks the ID token against the client ID alone.
- **Who can sign in.** While the consent screen's publishing status is *Testing*, only the listed test users can sign in (up to 100). That is right for family and friends. Moving to *In production* needs only the branding fields filled in, because the app asks for no sensitive scope.
- **Where the client ID goes.** The same client ID goes to the API as `GOOGLE_CLIENT_ID` (step 7) and to the web app's build as `VITE_GOOGLE_CLIENT_ID` (step 10).
- Google says a new origin can take from five minutes to a few hours to take effect.

## 5. Secrets

Generate each one once, and keep it in a password manager. None of them ever goes into git, `fly.toml`, the Dockerfile or CI.

| Secret | Needed for | Generate with |
|---|---|---|
| `SESSION_SECRET` | Everything. It signs every session. | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Meal reminders (optional) | `npx web-push generate-vapid-keys` |
| `LLM_KEY_ENCRYPTION_KEYS` | AI descriptions (optional) | `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (from `backend/`) |

- **`SESSION_SECRET`** must be at least 32 characters, and must not be the development default. The API refuses to start otherwise (see "Production settings" below). Changing it signs everyone out.
- **The VAPID pair is for good.** Browsers subscribe to the public key, so a new pair leaves every device subscribed to a key the server no longer signs with. Those devices read as on and are never reminded until they turn reminders off and on again.
- **`LLM_KEY_ENCRYPTION_KEYS`** encrypts the Anthropic API keys that users save. Losing it makes every saved key unreadable: users are asked to enter theirs again. Leaving it unset turns AI descriptions off on this server.

## 6. Replace the placeholders

Find every placeholder:

```bash
grep -n "example.com\|healthmonitor-api\|primary_region" backend/fly.toml
```

In `backend/fly.toml`:
- `app`: the Fly app name, which must be unique across Fly (the placeholder is `healthmonitor-api`).
- `primary_region`: `bom`, or `sin` (see "What runs where").
- `FRONTEND_ORIGIN`: `https://app.<domain>`, exactly: https, no trailing slash, no `www.` unless the app is served there. CORS allows this one origin and nothing else.
- `VAPID_SUBJECT`: a `mailto:` address that push services can reach you at.

Leave the rest as it is:
- `APP_ENV = "production"`;
- `COOKIE_SECURE = "true"`;
- `SCHEDULER_ENABLED = "true"`;
- the release command;
- `auto_stop_machines = "off"` and `min_machines_running = 1`.

The web app's two placeholders are build variables set in Cloudflare (step 10), not files.

## 7. The API on Fly

From `backend/`:

```bash
fly apps create <app-name>          # the name you put in fly.toml
fly config validate                 # never run in this repo: it needs flyctl and an account
```

Store the secrets. `fly secrets import` reads `NAME=VALUE` lines from standard input, which keeps them out of your shell history. Run it:

```bash
fly secrets import
```

Then type or paste these lines, with your values, and press Ctrl-D. Leave out an optional line you are not using yet:

```
DATABASE_URL=<the Neon direct URL>
SESSION_SECRET=<generated>
GOOGLE_CLIENT_ID=<…apps.googleusercontent.com>
VAPID_PUBLIC_KEY=<generated>
VAPID_PRIVATE_KEY=<generated>
LLM_KEY_ENCRYPTION_KEYS=<generated>
```

The app has no machines yet, so this only stores them for the first deploy. Leave every `ANTHROPIC_*` variable unset on the server. The app never takes a key or a base URL from them, and the SDK would add `ANTHROPIC_CUSTOM_HEADERS` to every user's request.

Deploy:

```bash
fly deploy --ha=false
```

- **`--ha=false` keeps it to one machine.** Fly's documentation says a first deploy otherwise creates two (not verified here), and each would run its own reminder loop. That is safe, because every reminder is claimed in the database before it is sent, but it polls twice as often for nothing. `fly status` should list one machine. If it lists two, run `fly scale count 1`.
- **The release step migrates.** Before the new version takes traffic, Fly runs `alembic upgrade head` on a temporary machine with the app's secrets. If it fails, the deploy stops and nothing changes. With `APP_ENV=production` that step also loads the production settings check, so a missing or development secret fails the deploy here, with the reason in the output.
- **Check it:** `curl -sf https://<app-name>.fly.dev/health` prints `{"status":"ok"}`. `fly logs` shows the app's own log lines at INFO.

The machine is `shared-cpu-1x` with 512 MB, runs `uvicorn --workers 1`, and never stops. A stopped machine sends no reminders, and a reminder more than an hour late is dropped rather than sent.

## 8. Seed data

The API is up, but its reference tables (foods, dishes, nutrients, ICMR values) are empty until this step. Sign-in works without them; targets, logging and the planner do not.

**The snapshot route**, recommended. It takes a few minutes, needs no third-party download at deploy time (only while you build it, unless `backend/etl/.cache` already holds the three source files), and loads in one transaction. Build the snapshot at the commit you deployed: `git status` clean and `git rev-parse HEAD` the same commit. Build it from a scratch database, never from your development database, which holds e2e users.

From the repository root:

```bash
docker compose up -d db
docker compose exec -T db createdb -U healthmonitor healthmonitor_seed
```

From `backend/`:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run python -m etl.run_all
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run python -m scripts.seed_snapshot export --out seed-snapshot
```

The export prints each table's row count: 32 nutrients, 547 ingredients, 1086 dishes, 16747 ingredient nutrients, 60 RDA rows, 16 upper limits, 680 dish ingredients, 29406 dish nutrients and 1022 portion measures. Then check that Neon is at the same revision, and import:

```bash
DATABASE_URL="$NEON_URL" uv run alembic current
DATABASE_URL="$NEON_URL" uv run python -m scripts.seed_snapshot import --from seed-snapshot
```

`alembic current` should print the same revision as `"alembic_revision"` in `seed-snapshot/manifest.json`, followed by `(head)`.

The import refuses, and changes nothing, when:
- Neon is at another alembic revision;
- any of the nine reference tables already holds a row;
- a file's SHA-256 is not the manifest's.

It then loads every table, runs `ANALYZE`, and compares every table's fingerprint with the manifest before it commits. `imported seed-snapshot: every table matches its fingerprint` means the data in Neon is the data you exported.

Afterwards, drop the scratch database (`docker compose exec -T db dropdb -U healthmonitor healthmonitor_seed`, from the repository root). Keep `backend/seed-snapshot/` offline or delete it.
- It is gitignored and dockerignored.
- It is derived from IFCT 2017, which has no open licence. Never commit it or attach it to a public release.

**The ETL route**, if you would rather not use a snapshot:

```bash
DATABASE_URL="$NEON_URL" uv run python -m etl.run_all
DATABASE_URL="$NEON_URL" uv run python -c "from sqlalchemy import text; from app.db import engine; c = engine.connect().execution_options(isolation_level='AUTOCOMMIT'); c.execute(text('ANALYZE')); print('analysed')"
```

- It downloads about 5.6 MB from GitHub, the INDB site and USDA.
- It holds an advisory lock for the whole run, which is why it needs the direct URL. The lock's connection sits idle in a transaction until the end, so a database that sets `idle_in_transaction_session_timeout` can end it partway through a long run.
- It makes several thousand round trips, so over a long network path it takes many minutes. That is an estimate; it has not been measured.
- **`ANALYZE` afterwards is not optional.** Without statistics, the planner's dish-nutrient join has been measured at 28 s per dish instead of 0.09 s.

**Later refreshes** always go through the ETL route. The snapshot loads only into empty tables. The ETL updates rows in place by code, which keeps the ids that users' meal logs and plans point at.

To confirm the planner has dishes to offer, the count of dishes with slot tags must be 72:

```bash
DATABASE_URL="$NEON_URL" uv run python -c "from sqlalchemy import text; from app.db import engine; print(engine.connect().execute(text('select count(*) from dishes where slot_tags is not null')).scalar())"
```

## 9. The API's domain

```bash
fly certs add api.<domain>
```

In Cloudflare DNS, add a `CNAME` record from `api` to `<app-name>.fly.dev`, with the proxy **off** (the grey cloud, "DNS only"). Cloudflare's proxy gets in the way of Fly issuing the certificate, and adds a second TLS hop for nothing. Run `fly certs show api.<domain>` until it reports the certificate issued, then check:

```bash
curl -sf https://api.<domain>/health
```

It should print `{"status":"ok"}`.

## 10. The web app on Cloudflare Pages

In Cloudflare, go to Workers & Pages, then Create, then Pages, then connect the GitHub repository.

| Setting | Value |
|---|---|
| Production branch | `main` |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Environment variable `NODE_VERSION` | `22`, as CI uses |
| Environment variable `VITE_API_BASE` | `https://api.<domain>`, with no trailing slash |
| Environment variable `VITE_GOOGLE_CLIENT_ID` | the same client ID as the API's `GOOGLE_CLIENT_ID` |

- **Never set `VITE_USE_MOCKS` or `VITE_DEMO_AUTH`.** Demo auth hands a session to anyone who asks.
- **The build refuses to run without `VITE_API_BASE`.** Without it, a production bundle would call `http://localhost:8000`. The error names the variable.
- **Everything `VITE_*` is public**, baked into the bundle. None of these is a secret.

Then:
1. **The custom domain.** Under the project's Custom domains, add `app.<domain>`. With DNS on Cloudflare, it creates the record itself.
2. **Redirect `<project>.pages.dev` to `https://app.<domain>`.** Cloudflare's guide for this uses Bulk Redirects. An app served from `pages.dev` cannot sign in (see "What runs where"), so nobody should land there.
3. **Preview deployments.** Every branch builds a preview at `<branch>.<project>.pages.dev`, which cannot sign in, for the same reason. Turn previews off under the project's build settings, or treat them as look-only.

`frontend/public/_headers` and `_redirects` are copied into `dist/`. `_headers` has six `no-cache` rules and two `immutable` ones:
- **`no-cache`:** `/sw.js`, `/push-handlers.js`, `/registerSW.js`, `/manifest.webmanifest`, `/` and `/index.html`, so a new version reaches installed apps. The `/` rule is there because Pages serves the app shell at `/` and redirects `/index.html` to it. The SPA's other routes (`/plan`, `/foods`, …) keep Pages' default, `public, max-age=0, must-revalidate`, which also checks on every load.
- **`immutable`, cached for a year:** the content-hashed files, `/assets/*` and `/workbox-*.js`. A new build gives them new names.
- **`_headers` has no `/*` rule, on purpose.** Pages applies every rule that matches a path and joins a header that two rules set, so a catch-all's value would be added to the immutable one.
- Any other path gets `index.html` from Pages' own SPA fallback, which works only while `dist/` has no top-level `404.html`.
- `_redirects` holds no rule, on purpose, and its comment says why. Never add a `/*` rule to it: Pages applies `_redirects` before it looks for a file, so a catch-all would answer `/sw.js` and every script under `/assets/` with `index.html`, and the app would never load. Never add a `404.html` to `frontend/public/` either, because it switches the fallback off.

The app must stay at the root of its host, because the service worker's scope is `/`.

## 11. Check it

- **The cache headers.** `curl -sI https://app.<domain>/sw.js | grep -i cache-control` shows `no-cache`, and so does the same for `https://app.<domain>/`.
- **The cookie.** Sign in at `https://app.<domain>` with a test user. In the browser's developer tools, the `hm_session` cookie belongs to `api.<domain>` and is `Secure`, `HttpOnly` and `SameSite=Lax`.
- **The app.** Walk the questionnaire, open Today, log a meal, and generate a week's plan.
- **Reminders.** With VAPID keys set, install the app, turn reminders on under More, then Reminders, and wait for a meal time. On an iPhone, reminders need the app added to the Home Screen, and the installed app signs in again, since it has its own cookie jar.
- **AI descriptions.** With the keyring set, save an Anthropic API key under More, then AI descriptions, and add descriptions to a plan. This is the first request that reaches Anthropic.
  - If "Add descriptions" answers "Couldn't reach Anthropic" while Anthropic's status page is green, run `fly logs`. A line `anthropic call failed: BadRequestError (status 400)` means the API refused the request's shape for that model, not an outage.
  - If the Plan screen says "Claude added no new descriptions this time." while some dishes still have no description, the request reached Anthropic and was billed. But Claude declined, was cut off, or wrote nothing the server's check kept. Another click sends those dishes again, and is billed again. When every dish already has a description, the same line means there was nothing left to send.
- **Safari's cookie cap.** Check this on an iPhone or a Mac with Safari. It is documented WebKit behaviour, not verified for this setup.
  - WebKit's tracking prevention caps a cookie at 7 days when a first-party subdomain sets it from a server whose IP address is unlike the page's.
  - `api.<domain>` on Fly and `app.<domain>` on Cloudflare have unlike addresses. So Safari may ask for a sign-in every week, even though a session lasts 30 days.
  - **To check,** sign in with Safari, open Web Inspector, then Storage, then Cookies, and read the expiry of `hm_session` for `api.<domain>`. An expiry 7 days out means the cap applies.
  - **The fix is not built.** It would serve the API from the app's own origin (`app.<domain>/api`, through a Cloudflare Pages Function or Worker), set `VITE_API_BASE=/api`, and change the service worker to leave `/api/` alone.

## Production settings

`APP_ENV=production`, which `backend/fly.toml` sets, makes the API refuse to start, naming every problem at once in one line that begins `Refusing to start in production:`, when:

| Problem | Fix |
|---|---|
| `SESSION_SECRET is the development default or shorter than 32 characters` | Set a generated secret (step 5). |
| `GOOGLE_CLIENT_ID is empty` | Set it (step 4). |
| `COOKIE_SECURE must be true` | Keep `COOKIE_SECURE = "true"` in `fly.toml`. |
| `FRONTEND_ORIGIN must be an https:// origin with no trailing slash` | Fix `FRONTEND_ORIGIN` in `fly.toml`. |
| `DATABASE_URL points at localhost` | Set the Neon URL as a secret. |

The localhost check reads the URL's host (`localhost`, `127.0.0.1` or `::1`). A URL with no host at all, such as the Unix-socket form `postgresql+psycopg:///hm`, is not refused. A hosted Postgres URL always carries a host, so this matters only if you paste something other than Neon's string.

The optional features are not required. With no VAPID keys, the Reminders screen says reminders are not set up on this server. With no `LLM_KEY_ENCRYPTION_KEYS`, the AI descriptions screen says the same. A *malformed* `LLM_KEY_ENCRYPTION_KEYS` stops the API at boot with `ValueError: LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key`. The message is the same whatever is wrong with the entry, and it never quotes the value.

Every variable the API reads:

| Variable | Where it is set | Required | Value |
|---|---|---|---|
| `APP_ENV` | `fly.toml` | yes | `production` |
| `DATABASE_URL` | secret | yes | Neon's direct URL |
| `SESSION_SECRET` | secret | yes | generated, at least 32 characters |
| `GOOGLE_CLIENT_ID` | secret | yes | the OAuth client ID |
| `COOKIE_SECURE` | `fly.toml` | yes | `true` |
| `FRONTEND_ORIGIN` | `fly.toml` | yes | `https://app.<domain>` |
| `SCHEDULER_ENABLED` | `fly.toml` | for reminders | `true`: the API sends reminders itself, once a minute |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | secret | for reminders | the generated pair |
| `VAPID_SUBJECT` | `fly.toml` | for reminders | `mailto:<you>` |
| `LLM_KEY_ENCRYPTION_KEYS` | secret | for AI descriptions | comma-separated Fernet keys, newest first |
| `FORWARDED_ALLOW_IPS` | the Dockerfile | yes | `*`, so the API trusts Fly's proxy about https. Safe only because the machine is reachable through that proxy alone |
| `PORT` | the Dockerfile | yes | `8000` |
| `SESSION_COOKIE_NAME`, `SESSION_TTL_HOURS` | defaults | no | `hm_session`, `720` |

## AI descriptions on the server

- **The feature is off** until `LLM_KEY_ENCRYPTION_KEYS` is set.
- **Users bring their own keys.** Each user who wants descriptions saves their own Anthropic API key, and Anthropic bills that user's account for each request. The server holds no key of its own, and pays for nothing.
- **What is sent.** Only dish names and ingredient names go to Anthropic. Health details, portions and numbers never do.
- **The server-side refusal fallback is on for Claude Opus 5.** With `claude-opus-5`, the default model, each request carries Anthropic's `server-side-fallback-2026-07-01` beta with `fallbacks="default"`.
  - A request that Claude Opus 5 declines is re-run by Anthropic on another Claude model it chooses, and billed at that model's rate.
  - The AI descriptions screen tells users so.
  - Claude Sonnet 5 and Claude Haiku 4.5 are sent without the fallback.
- **What a polish writes.** A polish stores its text in `dish_polish` only, and never writes a plan table: no dish, portion or number changes. When Anthropic refuses the saved key, the polish marks that key `rejected` in `user_settings` and answers 409, and a key that no longer opens is marked `unreadable`, so the AI descriptions screen asks for it again. A provider error rolls back every description written in that request.
- **Keys are write-only.** A saved key is encrypted with the keyring and bound to its user. The API never returns it, only its last four characters, and never logs it. A provider error is logged as its class name and status code only.
  - FastAPI's own 422 quotes the input that failed validation. On `/settings/llm` a validation handler answers a malformed body without quoting it, so even a misspelt or non-string `api_key` never comes back.
  - Every answer on `/settings/llm` except the 401 for a missing session, including the validation handler's 422, is sent `Cache-Control: no-store`.

**Rotating the keyring:**
1. Generate a new key and put it first: `LLM_KEY_ENCRYPTION_KEYS=<new>,<old>`. Store it with `fly secrets import`, as in step 7, which restarts the machine with the new value. New saves use the new key, and every stored key still opens with the old one.
2. Run `fly ssh console -C "python -m scripts.rotate_llm_keys"`. A session may start in `/` rather than the image's `/app`. The image sets `PYTHONPATH=/app` and puts its virtualenv first on `PATH`, so the command works from either. It re-encrypts every key still under an older key, in one transaction, and is safe to re-run. It prints `rotated N, current N, unreadable N`.
   - It opens every stored key, including those already under the new key, and checks that each is bound to the user whose row holds it. A key that no key in the keyring opens, or one bound to another user (a row copied between users), is marked unreadable and left in place; its owner is asked to enter it again.
   - `unreadable` counts those rows again on every run, so it falls only as their owners enter their keys again. It does not have to reach 0 before the next step.
   - `fly ssh console` has never been run against this image (see "What was rehearsed, and what was not"). If the session does not carry the image's `PATH` and `PYTHONPATH`, the command answers `python: not found` or `No module named 'scripts'`. Then run it with the directory and the interpreter spelt out: `fly ssh console -C "sh -c 'cd /app && exec /app/.venv/bin/python -m scripts.rotate_llm_keys'"`.
3. Once a run prints `rotated 0`, remove the old key from `LLM_KEY_ENCRYPTION_KEYS` the same way.

Rotation protects against a keyring that leaks on its own. If the keyring and a copy of the database leak together, it is too late: tell users to revoke their keys at Anthropic.

## Reminders keep the database awake

The in-process scheduler checks once a minute for due reminders, so Neon's compute never scales to zero: that is roughly 730 hours a month of compute. Check that against your Neon plan.

The alternative is to set `SCHEDULER_ENABLED = "false"` and run `python -m scripts.send_reminders` from an external cron every minute. Running both at once is safe. Fly's own scheduled machines run hourly at most, so that cron has to live elsewhere; Railway's cron runs every five minutes at most, so reminders would arrive up to five minutes late.

## Rolling back

- **The API.** `fly releases --image` lists each release's image. `fly deploy --image <image>` redeploys an earlier one.
- **Migrations.** The release step only migrates forward, so going back to older code keeps the newer schema. Plan 9's migration only adds two tables, so plan 8's code runs against it. Before any other rollback, read the migrations in between.
  - If you must undo a migration, run `DATABASE_URL="$NEON_URL" uv run alembic downgrade <revision>` from a checkout that has it.
  - A downgrade drops what the migration added. Plan 9's drops every saved API key and every cached description.
  - Take a Neon branch first: a copy of the database at that moment, which you can restore from.
- **The database.** Neon restores a branch to an earlier point in time, within your plan's history window. Check the window before you need it.
- **The web app.** In the Pages project's Deployments, choose an earlier deployment and "Rollback to this deployment".
- **The seed import** is one transaction. A failed import leaves nothing behind, and can simply be run again.

## When something goes wrong

| What you see | Likely cause |
|---|---|
| The deploy fails in the release step with `Refusing to start in production: …` | A missing or development secret. The message names each one. |
| The deploy fails its health check, and in `fly logs` the app stops at boot with `LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key` | A malformed `LLM_KEY_ENCRYPTION_KEYS`: a key cut short, pasted with quotes around it, or not a Fernet key at all. Store it again exactly as your password manager holds it. A newly generated key would leave every key already saved under the old one unreadable. |
| Every request from the app fails with a CORS error | `FRONTEND_ORIGIN` does not match the app's origin exactly: a trailing slash, `www.`, or http. |
| Google's sign-in button says the origin is not allowed | `https://app.<domain>` is missing from the OAuth client, or has not taken effect yet. |
| Sign-in appears to work, then everything answers 401 | The cookie was not kept. The app is not on `app.<domain>` (a `pages.dev` name, say), or it is on http. |
| A redirect sends the browser to `http://api.…` | `FORWARDED_ALLOW_IPS` is not `*`. |
| The Pages build stops with `VITE_API_BASE is not set` | Set `VITE_API_BASE` in the Pages project. |
| The plan is empty and food search finds nothing | The seed data is not loaded (step 8). |
| The planner is very slow | The tables have no statistics. Run `ANALYZE` (step 8). |
| No reminders arrive | Check, in order: the machine is running, `SCHEDULER_ENABLED` is true, both VAPID keys are set, and the device subscribed under the current pair. |
| "Add descriptions" always answers "Couldn't reach Anthropic" | Check `fly logs` for `anthropic call failed: <error> (status <n>)`. A 400 means the API refused the call's options for the saved model (step 11). |

## Alternatives, not configured

- **Railway** for the API:
  - use the same Dockerfile, with the service's root directory set to `backend`;
  - run `alembic upgrade head` as the pre-deploy command;
  - use one replica, with sleeping off.
  - Railway injects `PORT`, which the image already reads. There is no `railway.json` in this repository.
- **Supabase** for Postgres: use the direct connection or the *session* pooler, never the transaction pooler on port 6543. The free plan's direct host is IPv6 only.
- **Vercel** for the web app:
  - a `vercel.json` would carry the same cache headers and the SPA fallback;
  - a Vercel rewrite can proxy `/api` to the API on the app's own origin, which would also avoid Safari's cookie cap.
  - None of it is in this repository.

## What was rehearsed, and what was not

Rehearsed locally in plan 9:
- **The image.** It builds, runs as a non-root user, and ships no `.env`, no tests and no seed snapshot. Run from `/`, its Python imports `app` and `scripts`.
  - Its HTTPS calls to Anthropic trust the operating system's CA store, which comes from the `python:3.13-slim-bookworm` base image's `ca-certificates` package. The rehearsal found it there, but nothing in the Dockerfile installs or checks it, so a change of base image could drop it.
- **The release step.** `alembic upgrade head` and `alembic check` ran against a scratch database.
- **Boot and refusal.** The image boots and answers `/health`, and refuses a production configuration that still carries development settings.
- **The web app.** The production build refuses a missing `VITE_API_BASE`, carries `_headers` and `_redirects`, and bakes in no localhost address. `wrangler pages dev`, Cloudflare's Pages server run locally, served the headers in step 10 and the SPA fallback from that build.
- **The seed snapshot.** It was exported from a fresh ETL and imported into an empty database, with matching fingerprints.
- **CI's checks, run locally.** The workflow parses and passes `actionlint`. The frontend job's build-output check, and the image job's non-root and refusal checks, were cut out of the YAML and run on this machine. Each passed on a good build and failed on a broken one. CI deploys nothing.

Not verified:
- **CI on GitHub.** The workflow has never run there, because nothing has been pushed. Unchecked until it does:
  - whether `--network host` lets the image's containers reach the Postgres service at `localhost:5433`;
  - whether the `type=gha` Docker layer cache works under `permissions: contents: read`;
  - the existing action pins (`actions/checkout@v4`, `actions/setup-node@v4`, `astral-sh/setup-uv@v5`, `actions/upload-artifact@v4`), which run on the Node 20 actions runtime and may warn, or stop, once GitHub retires it.
- **`flyctl`.** No `fly` command in this file has been run. `backend/fly.toml` has never been checked by `flyctl`: run `fly config validate` first. These commands were written from Fly's documentation, and their flags are unchecked:
  - `fly secrets import`, reading `NAME=VALUE` lines from standard input (step 7);
  - `fly deploy --ha=false`, and that a first `fly deploy` without it creates two machines;
  - `fly releases --image` and `fly deploy --image <image>` (rolling back);
  - `fly ssh console -C`. It has never been run against this image, so it is unchecked whether its session carries the image's `PATH` and `PYTHONPATH`, and the app's secrets. "Rotating the keyring" gives the command with the directory and the interpreter spelt out, for a session that does not.
- **What a deploy does to the one machine.** `fly.toml`'s `strategy = "rolling"` is expected to replace the only machine with a gap of a few seconds in which nothing answers. If Fly starts the new machine before it stops the old one, the two overlap briefly, each with its own reminder loop. That is safe, because every reminder is claimed in the database before it is sent. Neither has been observed.
- The regions (`bom`, `aws-ap-south-1`) have not been checked against what each host offers today.
- Safari's 7-day cookie cap (step 11).
- No request has reached the real Anthropic API. The polish call for each model, including Claude Opus 5's structured outputs with `effort: low` and the refusal-fallback beta, comes from Anthropic's documentation. The first real polish in step 11 is the check.
- How Cloudflare Pages itself applies `_headers` to the service worker files. Only `wrangler pages dev` has served them. Check with `curl -sI` (step 11).
