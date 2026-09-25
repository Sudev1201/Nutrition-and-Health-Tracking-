# AI Descriptions & Deploy Configuration Implementation Plan (plan 9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two things, both stopping short of going live.
- **AI descriptions.** A user who brings their own Anthropic API key can ask for a one-sentence description and a cooking tip for each dish in their week's plan. The planner's dishes, portions, rationale and every number stay exactly as they were.
- **Deploy configuration.** Everything a first deploy needs, rehearsed locally: a container image, a Fly.io config, Cloudflare Pages headers, production settings that refuse to start when misconfigured, a seed-data snapshot that can be exported and imported, CI that builds and boots the image, and a runbook. Nothing is deployed: no account, domain, registry push or `git push`.

**Architecture:**
- **The key.** `user_settings` holds one row per user with the key encrypted at rest. `app/llm/crypto.py` uses `cryptography`'s `MultiFernet` under a server keyring (`LLM_KEY_ENCRYPTION_KEYS`), which is never derived from the session secret. The ciphertext binds the user id, so a row copied to another user does not decrypt. A GET never decrypts and never returns the key, only a four-character hint.
- **The provider.** It sits behind a `Provider` protocol in `app/llm/providers.py`, with one adapter, `AnthropicProvider`, on the official `anthropic` SDK.
  - A key is checked when it is saved, with a zero-token model lookup.
  - Descriptions come from one structured-output call per batch of dishes, on the model the user chose (default `claude-opus-5`).
  - Claude Opus 5 and Claude Sonnet 5 run it at low effort. Claude Haiku 4.5 is sent no effort, because it rejects the parameter.
  - Anthropic's server-side refusal fallback is on for Claude Opus 5 only.
- **What the model sees.** `app/planner/polish.py` sends only dish names and ingredient names. It never sends portions, grams, nutrients, the rationale (which can name a medication) or anything from the profile. It keeps only text that passes a guard (no numeric characters, no `%`, and no number, unit or nutrient words), and caches it per user and dish in `dish_polish`, keyed by a hash of exactly what was sent. Swap, lock, regenerate and re-plan therefore need no invalidation. `describe_week` attaches the cached text as two new, separate fields.
- **When it runs.** Only when the user asks: `POST /plan/week/polish`. `GET /plan/week`, generation and meal logging never wait on a model.
- **Production settings.** `APP_ENV=production` makes `Settings` refuse the development defaults: the development session secret or one shorter than 32 characters, an empty Google client id, insecure cookies, a frontend origin that is not a bare `https://` origin (http, a trailing slash, a path, a query or a fragment), or a database on `localhost`, `127.0.0.1` or `::1`. `DATABASE_URL` accepts the `postgres://` form hosts hand out.
- **Deploy files.** A multi-stage `uv` Dockerfile (non-root, one uvicorn worker because plan 8's scheduler runs per process); `fly.toml` with the migration as the release step and auto-stop off; Cloudflare Pages `_headers` that keep the service worker files uncached, and a `_redirects` that deliberately holds no rule; a build that refuses to bake in a localhost API.
- **Seed data.** `scripts/seed_snapshot.py` exports the nine reference tables from a scratch database built fresh at HEAD, using COPY with explicit columns and filtering out user dishes. It imports them into an empty target in one transaction, checked against the manifest's per-table fingerprints.
- **CI.** CI builds the image, proves it runs as non-root without `.env`, tests or a seed snapshot, runs the release step against Postgres, boots it, and proves it refuses a production config with development secrets. It still never deploys.

**Tech Stack:**
- Backend: FastAPI, SQLAlchemy 2, Alembic, pytest.
- Frontend: React 19, TanStack Query, MSW, Vitest, Playwright.
- **New backend dependencies:** `anthropic>=1.8,<2`, `httpx2>=2.13,<3` and `cryptography>=46`. `httpx2` is the SDK's HTTP client; the adapter and the test guard import it, so it is declared directly. So is `cryptography`, which is already locked through google-auth: the app now imports it too.
- No new frontend dependency.
- Deploy tooling: Docker (the image builds with the classic builder or buildx), Fly.io config, Cloudflare Pages config. None of these CLIs is run against a real account.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`. The relevant parts are:
- "Meal planning": "optional LLM polish when user supplies own API key".
- Architecture: hosting, the managed database, and the seed data.
- The planner's step 5, "Optional LLM polish": it "rewrites descriptions and adds cooking notes for *already-chosen* dishes. It never changes a dish, a portion, or a nutrient number."
- Data Model: "LLM API keys in `user_settings` stored encrypted at rest."
- "Prerequisite: Google OAuth client": the production origin over HTTPS, and no client secret.
- Implementation Sequence steps 12 and 13.

**Status:** Complete as configuration: nothing is deployed, and `DEPLOY.md` lists what the
owner does by hand. 1279 backend tests and 374 frontend tests passing, plus 10 Playwright
end-to-end tests; `ruff`, `alembic check`, `tsc -b`, `oxlint` and `vite build` clean; the
image builds, runs as a non-root user and refuses a production start with development
settings.

**Changed during execution** (rulings made while the tasks ran; the text below is as planned):
- `rotate_all` opens every stored token, including those already under the newest key, and
  re-checks its user binding. A current token copied to another user's row is marked
  `unreadable`, not counted as current.
- A failed polish marks the stored key `rejected` (or `unreadable`) in `user_settings`. "Polish
  writes only to `dish_polish`" therefore means that no plan table is ever written.
- The guard's `BANNED_WORDS` also holds bowl, glass and piece and their plurals, the measures
  the planner's own portions use (see Known gaps).
- The test helpers `set_keyring` and `sql_statements(db)` live in `tests/conftest.py`, shared
  by the LLM and polish tests.
- The AI descriptions screen shares only the presentational `RemoveKeyButton` and
  `RemoveKeyFailed`; each card owns its own delete mutation.
- `PlanScreen` passes the cache-based `regenerating` to `DayPanel`, so the lockout survives a
  remount.
- Final review: polish sends at most 15 dishes a call (`MAX_DISHES_PER_CALL = 15`, was 40) and
  never retries (`max_retries=0`, was 1; the 120 s timeout stays). `POST /plan/week/polish` is
  synchronous, and 40 dishes plus a retry could outlast a hosting proxy's idle cut-off (about
  60 s on Fly, unverified), so the user would see a generic failure and still be billed.
- Final review: production also refuses a `FRONTEND_ORIGIN` or `DATABASE_URL` whose host is
  `example.com` or a name under it, `fly.toml`'s placeholder, with a fixed message that never
  quotes the value.

## Global Constraints

**Backend tooling**
- Python `>=3.12` and ruff line length 100. Run every backend command as `uv run`, from `backend/`.
- Ruff 0.16 runs its broad default rule set: DTZ (never a naive `datetime.now()` or `date.today()`), I001, RUF022 (sorted `__all__`), UP, B, SIM and PT. E501 is off, but keep lines to 100 columns. Do not add `noqa`.
- Code blocks in this plan are written for reading. Wrap any line over 100 columns before committing.
- A dependency change is `uv add '<spec>'`, from `backend/`, which updates `pyproject.toml` and `uv.lock` together. Commit both.

**Models and migrations**
- Every table extends `TimestampedBase`, and every model is registered in `app/models/__init__.py` with `__all__` kept sorted.
- Tests run against the **migrated** schema. After adding a migration, run all three:
  - `DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head`
  - `uv run alembic upgrade head`
  - `uv run alembic check`
- Plan 8's head is `f2a3b4c5d6e7`. Plan 9's one migration is `a3b4c5d6e7f8`. Copy the header style of `alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py`; `script.py.mako` generates one that fails ruff.

**Running tests**
- The full backend suite takes about fifteen minutes by the end of this plan, which is longer than a ten-minute command timeout. During a task, run only the test files you touched; the final task runs everything, in the background.
- Never run two pytest sessions against the test database at once.
- **No new test reaches the network.** The existing ETL tests still download their sources when `etl/.cache` is empty; that is unchanged.
  - An autouse guard in `tests/conftest.py` (Task 3) makes any `AnthropicProvider` built without an explicit HTTP client fail.
  - API tests override `get_provider` with `FakeProvider` (Task 4).
  - Adapter tests hand the real SDK an `httpx2.MockTransport`.

**API conventions**
- Routers commit and services flush. A 422 uses `status.HTTP_422_UNPROCESSABLE_CONTENT`.
- A missing profile answers 404 "Complete your profile first".
- Request and response models live inline in the router as `XxxIn` / `XxxOut`, with both `response_model=` and a return annotation.
- In production, sessions do not autoflush (`sessionmaker(autoflush=False)`), but the test session does. After a write that a later query in the same request reads, `db.flush()` explicitly.

**Frontend checks and test conventions**
- Checks: `npx tsc -b` (never `--noEmit` alone), `npx vitest run`, `npm run lint`, `npm run build`.
- Stub endpoints per test with `server.use(...)`. Unhandled requests fail the test.
- Each test file builds its own `QueryClient` with `retry: false`, wrapped in `MemoryRouter` when the screen links anywhere.
- After Task 10, `npm run build` needs `VITE_API_BASE`. Locally it comes from `frontend/.env.local`, and in CI from the step's `env`.

**The API key is a secret**
- The key only ever travels in a JSON body: never in a path, a query string, a log line, an error message or a response.
- Tests use obviously fake keys (for example `"sk-ant-api03-" + "x" * 40 + "WXYZ"`), so a failing assert that prints one leaks nothing.
- The request field is a `SecretStr` with **no** pydantic constraints, because a failing constraint echoes the input in the 422 body. It is validated in the handler, with fixed messages.
- A body that fails validation before the handler runs (a misspelt `api_key`, or one that is not a string) would come back quoted in FastAPI's own 422. On `/settings/llm` that 422 is answered without the submitted input, and a test proves the key is not in it.
- `get_secret_value()` is called once, in the router, to hand the key to the service.
- Plaintext never reaches SQL. It is encrypted before the row is written.
- The key is decrypted for use in exactly one place, `llm.service.key_for`, and only for the signed-in user's own plan. `scripts.rotate_llm_keys` (`llm.service.rotate_all`) also opens every token, to re-encrypt it and to re-check its user binding; nothing else decrypts. Nothing on the household path reads `user_settings` or `dish_polish`.
- Provider errors are logged as `type(exc).__name__` and the status code only. Never log `str(exc)`, and never pass `exc_info=True` for them.
- Every answer from the three `/settings/llm` handlers carries `Cache-Control: no-store`, refusals included, and so does the 422 the `/settings/llm` validation handler gives. The 401 for a missing session comes from the shared auth dependency and carries no key.

**Privacy**
- Health data never leaves its owner. That covers conditions, medications, weight, cycle, and any target figure.
- The model sees dish names and ingredient names only. It never sees the rationale, which can name levothyroxine and a nutrient percentage, nor portions, grams, nutrients, favourites or anything else from the profile.

**The spec's promise, enforced in code**
- Polish never changes a dish, a portion, a rationale or a number. Its text arrives as two new fields, `description` and `cooking_note`.
- Polish writes only to `dish_polish`: never to `meal_plans`, `meal_plan_items` or any other table. A test watches the SQL to prove it.

**The profile-save trap**
- Never add a table to `profiles.service.CHILD_MODELS`. A profile save deletes every row in those tables.

**Nothing goes live**
- No task creates an account, buys or configures a domain, pushes an image to a registry, runs `flyctl`, `wrangler` or `railway` against a real account, or pushes git.
- The deploy files use placeholder hosts (`app.example.com`, `api.example.com`). `DEPLOY.md` says where to replace them.
- A local Docker rehearsal (colima) is expected, and so are scratch databases in the compose Postgres, as long as the task that creates them drops them. Never drop, truncate or restore into `healthmonitor` or `healthmonitor_test`.

**Commits**
- Commit after each task, on `tracking-loop-and-ui-foundation`. Do not push.
- Use a conventional prefix and a body that explains the *why*.
- Every message ends with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Decisions taken before starting

Recorded here so the implementer does not re-litigate them; the closeout carries them forward.

**What polish writes**
- **Two new strings per dish, never a rewrite.**
  - No dish has a description today. `Dish` has no prose column, and the ETL's recipes carry none.
  - "Rewrites descriptions" in the spec therefore means `description` (one sentence) and `cooking_note` (one tip, or none).
  - `dish_name`, `portion`, `rationale` and the day's `vegetarian_reason` are never touched. The rationale stays deterministic because it carries a computed percentage and a medication-timing note.
- **Cached per user and dish, in `dish_polish`, keyed by what was sent.**
  - `brief_hash` is a SHA-256 over `PROMPT_VERSION`, the dish name and its ingredient names.
  - A cached row whose hash no longer matches, because a re-seed renamed an ingredient or the prompt changed, is ignored when read and replaced on the next polish.
  - Nothing is keyed to plan-item ids, so regenerate, swap, lock and re-plan need no invalidation. A swapped-in dish shows its own cached text or none. It is per user because the user pays, and it cascades with the account.
  - Rejected alternative: columns on `meal_plan_items`. Those would need clearing on every in-place swap, and the same dish would be paid for again every week.
- **On demand only.** `POST /plan/week/polish {start}` polishes the dishes in that week's plan that have no current cached text, in one call per 40 dishes, and returns the week, with the number of dishes it stored new text for in an `X-Dishes-Described` header, which CORS exposes; `0` is still a 200.
  - Generation, `GET /plan/week`, re-plan after logging, and plan 8's reminder loop never call a model.
  - There is no automatic polish setting and no background job.
- **The guard.** A description or cooking note is kept only when, stripped, it:
  - is non-empty and at most 280 characters;
  - contains no numeric character (`str.isnumeric`, which also catches "½" and "²") and no `%`;
  - contains none of the number, unit and nutrient words in `polish.BANNED_WORDS`, matched as whole words, case-insensitively.

  The list also covers the number words thirteen to nineteen and sixty to ninety, the multipliers (twice, double, triple, halve, halved) and the household measures (katori, tumbler, ladle, ladleful). A health or nutrition claim in other words ("rich in iron", "good for the heart") is not caught, and is recorded as a gap.

  "gram" is deliberately not banned (only "grams" is): IFCT names the pulses Bengal gram, Black gram, Green gram and Red gram, and 39 of the authored recipes use them.

  A dish whose description fails the guard gets no row. A failing cooking note is stored as null. Refs the service did not send are dropped.
- **Failures leave the plan alone.**
  - A provider error rolls back every row written in that request.
  - A rejected key marks the stored key `rejected` and answers 409.
  - A refusal, or a response cut off at `max_tokens`, is not an error: those dishes stay undescribed and the call answers 200.

**The key**
- **Where it lives.** A `user_settings` row, one per user, outside the profile: a profile save replaces the questionnaire's tables wholesale. It holds:
  - `llm_provider`, always `'anthropic'` today;
  - `llm_model`;
  - `llm_key_ciphertext`;
  - `llm_key_hint`, the last four characters;
  - `llm_key_status`: `ok`, `rejected` or `unreadable`;
  - `llm_key_set_at`.

  A CHECK constraint keeps those six all set or all null. Deleting the key nulls them rather than deleting the row.
- **Encryption.**
  - `MultiFernet` over the comma-separated `LLM_KEY_ENCRYPTION_KEYS`: the first key encrypts and all of them decrypt. The plaintext is `f"{user_id}:{api_key}"`, and decrypting checks the prefix.
  - An unset keyring turns the feature off: `available: false`, and the save (`PUT /settings/llm`) and polish endpoints answer 503 "AI descriptions are not set up on this server". `DELETE /settings/llm` still works, so a user can always take their key back.
  - A malformed keyring (bad base64, a key of the wrong length, a non-ASCII character) stops the app at boot with the fixed message "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key". The message never quotes the value.
  - `scripts/rotate_llm_keys.py` re-encrypts every row under the first key. It is safe to re-run.
  - A row that no longer decrypts is marked `unreadable`, never a 500.
- **Checked on save, with no tokens spent.** `client.models.retrieve(model)` returns:
  - 401/403, answered as 422 "Anthropic refused this key";
  - 404, answered as 422 "Your Anthropic account can't use {model label}";
  - an unreachable provider (connection, timeout, 429 or 5xx), answered as 503 "Couldn't reach Anthropic to check the key. Nothing was saved."

  A failed check leaves any earlier key untouched. The lookup cannot see an account with no credit; that surfaces on the first polish, as 409 "Your Anthropic account has no credit left".
- **The format check.** After stripping, the key must:
  - be 20 to 300 characters of `[A-Za-z0-9_-]`;
  - start with `sk-ant-`;
  - not start with `sk-ant-admin`, since an admin key is an organisation credential this feature must never hold.
- **Models.** The user chooses one of `providers.MODELS`: `claude-opus-5` (the default), `claude-sonnet-5` or `claude-haiku-4-5`. It is stored per user. Changing the model means entering the key again, which re-checks it against that model.

**The Anthropic call**
- **Always explicit.** The client is built with the stored key as `api_key`, `base_url="https://api.anthropic.com"` pinned, and an explicit `timeout` and `max_retries`.
  - An explicit key stops the SDK falling back to `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` (verified on `anthropic` 1.8.0).
  - The pinned base URL stops an `ANTHROPIC_BASE_URL` in the environment redirecting users' keys to another host (also verified).
- **Timeouts and retries.** The key check uses `timeout=10.0, max_retries=0`. Polish uses `timeout=120.0, max_retries=1`.
- **Polish is one call per batch.** `client.beta.messages.parse(...)` with:
  - `output_format=PolishBatch`, a pydantic model with `extra="forbid"`;
  - `output_config={"effort": "low"}`;
  - `max_tokens=8000`, non-streaming;
  - the system prompt `providers.SYSTEM_PROMPT`;
  - one user message holding the batch as JSON.

  It sends no `temperature` or `top_p`, which the current models reject. `effort` goes only to the models in `providers.EFFORT_MODELS` (Claude Opus 5 and Claude Sonnet 5): Claude Haiku 4.5 rejects the parameter.
- **The refusal fallback is on for Claude Opus 5.** With `claude-opus-5`, the call adds `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`. A policy decline is then re-run server-side on the model Anthropic recommends, and is billed at that model's rates.
  - The other two models are sent without it: whether they accept `fallbacks="default"` is not verified, and a 400 there would break polish.
  - The AI descriptions screen tells the user the fallback exists.
- **Stop reasons are checked before content.** For `stop_reason` of `refusal` or `max_tokens`, or when `parsed_output` is `None`, the batch yields no text. On `anthropic` 1.8.0 a response cut off mid-JSON makes `parse` raise pydantic's `ValidationError` before the stop reason can be read, so that too yields no text rather than a 500.

**Production settings**
- **`APP_ENV`, `development` by default.** Under `production`, `Settings` refuses to load, naming every problem at once, when:
  - `SESSION_SECRET` is the development default or shorter than 32 characters;
  - `GOOGLE_CLIENT_ID` is empty;
  - `COOKIE_SECURE` is false;
  - `FRONTEND_ORIGIN` is not a bare `https://` origin: it is http, ends in `/`, or carries a path, a query or a fragment;
  - `DATABASE_URL` points at `localhost`, `127.0.0.1` or `::1`.

  The optional features (VAPID keys, the LLM keyring) are not required. An `APP_ENV` other than the two values is refused rather than read as development, and `hide_input_in_errors=True` keeps a rejected secret out of the error text.
- **`DATABASE_URL` normalising.** `postgres://` and `postgresql://` become `postgresql+psycopg://`, because Neon and Supabase hand out the libpq form and SQLAlchemy would reach for psycopg2.
- **Alembic.** Alembic escapes `%` in the URL, so a URL-encoded password works.
- **Logout.** Logout deletes the cookie with the same `secure`, `httponly` and `samesite` attributes it was set with.
- **Logging.** The app's own `app.*` loggers get a stderr handler at INFO in the lifespan, so plan 8's reminder logs and plan 9's provider logs reach the platform's log stream.

**Where it runs**
- **API on Fly.io, database on Neon, SPA on Cloudflare Pages**, under one registrable domain: `app.<domain>` and `api.<domain>`. The cookie stays host-only on `api.` and same-site with `app.`.
  - Railway, Supabase and Vercel stay alternatives, named in `DEPLOY.md` only.
  - The region is `bom` (Mumbai) beside Neon's `aws-ap-south-1`; check both are offered at deploy time.
- **The image builds without BuildKit.** It uses no `RUN --mount`, so the classic builder (colima here has no buildx) and CI's buildx both build it. Dependencies are cached in a layer keyed on `pyproject.toml`, `uv.lock` and `.python-version`.
- **Scripts run from any directory.** The image sets `PYTHONPATH=/app`, so `python -m scripts.<name>` works from any working directory. A `fly ssh console` session need not start in the image's `WORKDIR`.
- **One always-on machine.** The API runs `--workers 1`, with `auto_stop_machines = "off"` and `min_machines_running = 1`. Plan 8's scheduler runs once per process, and a stopped machine sends no reminders.
- **Migrations and secrets.** Migrations run as Fly's `release_command`, never in the container's `CMD`. Secrets go in as `fly secrets`, never in `fly.toml`, the Dockerfile or CI.
- **The SPA.** It is served at the root of its own host.
  - `_headers` marks `sw.js`, `push-handlers.js`, `registerSW.js`, `manifest.webmanifest`, `index.html` and `/` (Pages redirects `/index.html` there) `no-cache`, and the hashed files (`/assets/*`, `/workbox-*.js`) immutable.
  - `_redirects` holds no rule, only a comment saying why. Cloudflare Pages already serves `index.html` for an unknown path when the build has no `404.html`. A `/* /index.html 200` rule is dropped by wrangler as an infinite loop, and Pages checks redirect rules before real files, so a catch-all would serve `sw.js` as HTML.
  - The workbox navigation denylist goes: with the API on another origin it only broke an offline reload of `/foods`.
- **The build refuses to bake in localhost.** `vite build` in production mode throws when `VITE_API_BASE` is unset, unless `VITE_USE_MOCKS=true`. `vite preview` loads the same config in production mode but serves a finished build, so the guard checks the command as well as the mode.

**Seed data**
- **A snapshot of a scratch database built at HEAD, not of the dev database.**
  - The dev database holds e2e users, and possibly orphan rows from before the ETL's advisory lock.
  - A scratch database built fresh with `alembic upgrade head` plus `etl.run_all` holds exactly the ETL's output.
- **Exported and imported by our own script, not `pg_dump`.**
  - `scripts/seed_snapshot.py` uses COPY with column lists read from the SQLAlchemy models. It filters out user dishes and their children, keeps the source's UUIDs, and writes one CSV per table plus a manifest: row counts, SHA-256 per file, per-table fingerprints over natural keys, the alembic revision and the git commit.
  - Import runs in one transaction. It refuses a target whose alembic revision differs, or whose reference tables are not empty. It then checks every file's hash, loads in foreign-key order, runs `ANALYZE`, and re-fingerprints against the manifest before committing.
  - Why not `pg_dump`: it needs matching v16+ client binaries, cannot filter rows, and cannot be exercised by the test suite.
- **A one-time load.** The snapshot loads only into an empty database. Refreshing a live database that already has users goes through `etl.run_all`, which upserts by code.
- **Never committed or published.** The snapshot directory is gitignored and dockerignored. IFCT has no open licence (spec, "Seed data sources"), so the snapshot must not be attached to a public release.
- **`cached_download` writes through a `.part` file and renames**, so an interrupted download can no longer leave a truncated file that later runs trust.

**CI**
- CI builds and checks, and never deploys. It has no registry push, no `flyctl` and no deploy secrets.
- `push` runs on `main` only, so a pull request no longer runs twice. `permissions: contents: read`.
- `uv sync --locked`.
- The Python version comes from `backend/.python-version` (`3.13`), which matches the image.

---

## File structure

Paths are relative to `backend/`, `frontend/`, or the repository root where marked.

**Backend — create**

| File | Responsibility |
|---|---|
| `app/llm/__init__.py`, `app/llm/crypto.py` | The server keyring: encrypt, decrypt, rotate, all bound to the user id |
| `app/llm/providers.py` | The `Provider` protocol, its errors, `DishBrief`/`DishText`, and `AnthropicProvider` on the official SDK |
| `app/llm/service.py`, `app/llm/router.py` | Saving, checking, summarising and removing the key; `GET/PUT/DELETE /settings/llm` |
| `app/models/llm.py` | `UserSettings`, `DishPolish` |
| `alembic/versions/a3b4c5d6e7f8_ai_descriptions.py` | The two tables |
| `app/planner/polish.py` | The guard, the brief hash, the cache read, and `polish_week` |
| `scripts/rotate_llm_keys.py` | Re-encrypts every stored key under the newest keyring key |
| `scripts/seed_snapshot.py` | Export, import and fingerprint the nine reference tables |
| `Dockerfile`, `.dockerignore`, `fly.toml`, `.python-version` | The image and its Fly.io configuration |
| tests | `test_llm_crypto.py`, `test_llm_models.py`, `test_anthropic_provider.py`, `test_llm_settings_api.py`, `test_rotate_llm_keys.py`, `test_polish_guard.py`, `test_plan_polish_api.py`, `test_config.py`, `test_app_logging.py`, `test_seed_snapshot.py`, `test_cached_download.py`, `test_usda_extract.py` |

**Backend — modify**

| File | Change |
|---|---|
| `app/config.py` | `llm_key_encryption_keys`; `app_env` and the production refusal; the `postgres://` normaliser |
| `app/main.py` | The AI descriptions settings router (`llm_router`); CORS exposes `X-Dishes-Described`; the lifespan configures logging and loads the keyring; the `/settings/llm` validation handler |
| `app/planner/service.py`, `app/planner/router.py` | `ItemView`/`PlanItemOut` gain `description` and `cooking_note`; `POST /plan/week/polish` and its `X-Dishes-Described` header |
| `app/auth/router.py` | Logout deletes the cookie with the attributes it was set with |
| `alembic/env.py` | `%` escaped in the database URL |
| `etl/common.py` | `cached_download` writes through a `.part` file |
| `etl/run_all.py` | `_usda_csv_paths` extracts through a `.part` directory |
| `app/models/__init__.py`, `scripts/e2e_session.py` | Registration; `OWNED_MODELS` |
| `pyproject.toml`, `uv.lock` | `cryptography`, `anthropic`, `httpx2` |
| `.env.example` | The keyring and `APP_ENV`, documented |
| `tests/conftest.py` | The no-network guard, `FakeProvider`, `llm_keyring`, `fake_provider` |
| `tests/test_planner_api.py`, `tests/test_auth_api.py` | `build_planner_pool` for reuse; logout attributes |

**Frontend — create and modify**

| File | Change |
|---|---|
| `src/settings/AiDescriptionsScreen.tsx`, `useLlmSettings.ts`, test (create); `src/settings/types.ts` | The AI descriptions screen and its contract |
| `src/lib/api.ts`, `src/lib/api.test.ts` | `errorDetail`, reading a server `detail`; a shared `send` and `postWithHeaders` |
| `src/shell/navigation.ts`, its test, `src/shell/Sidebar.tsx`, `src/App.tsx` | The menu entry and the route |
| `src/plan/types.ts`, `usePlan.ts`, `PlanScreen.tsx`, `PlanScreen.test.tsx`, `src/mocks/fixtures/plan.ts` | Descriptions and cooking tips on the Plan screen |
| `public/_headers`, `public/_redirects`, `.env.example` (create); `vite.config.ts` | Cloudflare Pages caching, the build guard, no navigation denylist |
| `e2e/smoke.spec.ts`, `README.md` | The AI descriptions walk; the READMEs |

**Repository root:** `DEPLOY.md` (create), `README.md`, `.gitignore`, `.github/workflows/ci.yml`, `docs/superpowers/plans/README.md`, the UI-foundation contract table, and this plan's Status line.

---

## Task 1: The encryption keyring

A user's Anthropic API key is a credential that spends their money, so it is stored encrypted at rest, under a keyring only the server holds. This task builds that keyring and nothing else: no table, no endpoint. Tasks 2 and 4 store and use what it produces.

The keyring is `cryptography`'s `MultiFernet` over a new setting, `LLM_KEY_ENCRYPTION_KEYS`: comma-separated Fernet keys, of which the first encrypts and every one decrypts. That makes rotation possible without a flag day: a new key goes first, tokens under the old one still open, and `rotate()` moves each token onto the new key. Four choices here are deliberate:
- **The user id is inside the ciphertext.** The plaintext is `f"{user_id}:{api_key}"`, and `decrypt` checks the prefix. Fernet has no associated data, so this is how a token is bound to its row: someone who can write to the database cannot copy one user's token onto another user's row and spend the first user's credit.
- **Anything that does not open cleanly is `Unreadable`.** That covers a wrong keyring, an altered token, a token bound to someone else, or something that is not a token at all. Task 4 turns it into a stored status of `unreadable`, never a 500 and never a wrong key.
- **No keyring is `NotConfigured`, not `Unreadable`.** An unset keyring turns the feature off on that server. A server started without its keyring must not look as if every stored key had gone bad, or Task 4 would mark them all unreadable.
- **The keyring is never derived from `SESSION_SECRET`.** Rotating a leaked session secret must not destroy every stored key, and that secret has a development default that a misconfigured deploy would use silently.

The parsed keyring is cached with `functools.lru_cache`, keyed on the setting's string value, so a test that monkeypatches the setting takes effect at once. A malformed key raises `ValueError("LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key")` the moment anything asks for the keyring. The message is the same whatever is wrong with the entry (not base64, the wrong length, a curly quote pasted around it), it never quotes the entry, and no other error is chained to it. Task 4's lifespan asks once, so a bad value stops the app at boot.

All commands run from `backend/`, and the commit from the repository root.

**Files:**
- Create: `backend/app/llm/__init__.py`, `backend/app/llm/crypto.py`
- Modify:
  - `backend/app/config.py`: the `llm_key_encryption_keys` setting
  - `backend/.env.example`: the setting, documented
  - `backend/pyproject.toml`, `backend/uv.lock`: `cryptography` declared directly
- Test: `backend/tests/test_llm_crypto.py` (create). It is pure: no database, no network.

**Interfaces:**
- Consumes:
  - Plan 8's final `app/config.py`, whose last field is `scheduler_enabled: bool = False` (plan 8 Task 10).
  - Plan 8's `backend/.env.example`, whose last line is `# SCHEDULER_ENABLED=true` (plan 8 Task 10).
  - `cryptography` 50.0.0, already in `uv.lock` through `google-auth`.
- Produces:
```python
# app/config.py Settings
llm_key_encryption_keys: str = ""     # comma-separated Fernet keys, newest first; "" = feature off

# app/llm/crypto.py
_MALFORMED = "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"
class NotConfigured(RuntimeError)     # the server has no keyring
class Unreadable(ValueError)          # wrong keyring, altered token, or bound to another user
def _fernet(entry: str) -> Fernet | None       # None when Fernet(entry) raises ValueError
                                                # (binascii.Error, UnicodeError) or TypeError
def _fernets(raw: str) -> tuple[Fernet, ...]   # lru_cache(maxsize=4); one per entry, in order;
                                                # a malformed entry raises ValueError(_MALFORMED)
def _keyring(raw: str) -> MultiFernet | None   # lru_cache(maxsize=4); "" -> None;
                                                # a malformed key raises ValueError(_MALFORMED)
def keyring() -> MultiFernet | None   # _keyring(settings.llm_key_encryption_keys.strip())
def available() -> bool               # keyring() is not None
def encrypt(api_key: str, *, user_id: uuid.UUID) -> str   # token of f"{user_id}:{api_key}"
def decrypt(token: str, *, user_id: uuid.UUID) -> str     # the api_key, or Unreadable
def is_current(token: str) -> bool    # the first key alone opens it (no user check);
                                      # False for a token no key opens
def rotate(token: str) -> str         # re-encrypted under the first key; Unreadable if no key
                                      # opens it; carries the user prefix over unchecked
# encrypt, decrypt, is_current and rotate all raise NotConfigured when there is no keyring.
# keyring() and available() raise ValueError(_MALFORMED) when any entry in the setting is
# not a Fernet key, whatever is wrong with it (bad base64, wrong length, a non-ASCII
# character such as a curly quote). str(exc) is exactly _MALFORMED, and __cause__ and
# __context__ are both None. Tasks 4 and 13 quote this message. It is not Fernet's own
# "Fernet key must be 32 url-safe base64-encoded bytes.", which a non-ASCII entry never gets.
# No message raised from here quotes a key, a token or a plaintext.
```
- Used by:
  - Task 4: `encrypt` in `save_key`, `decrypt` in `key_for` (the only decrypt call site), `available` in the router, `keyring()` in the lifespan, and `is_current` / `rotate` in `rotate_all`. `rotate` does not check the user prefix, so `rotate_all` checks it by decrypting the new token with the row's `user_id`.
  - Task 8 adds its settings to the same `Settings` class; the new field here is the class's last line until then.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_llm_crypto.py`:

```python
"""The keyring that encrypts users' API keys. No database, no network.

A stored key is only as safe as three properties, and each is pinned here:
- it never sits in the clear: the token holds neither the key nor its owner;
- it opens only for its owner, and only intact: a token copied onto another
  user's row, altered, or read under another server's keyring is Unreadable,
  never a wrong key;
- the keyring rotates without a flag day: a new key goes first, old tokens still
  open, and rotate() moves each one onto the new key.
"""

import base64
import uuid

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.llm import crypto

# Shaped like an Anthropic key, and obviously not one.
API_KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
OWNER = uuid.UUID("11111111-1111-4111-8111-111111111111")
SOMEONE_ELSE = uuid.UUID("22222222-2222-4222-8222-222222222222")

# Two throwaway server keys, generated fresh for each run; no server uses them.
K1 = Fernet.generate_key().decode()
K2 = Fernet.generate_key().decode()


@pytest.fixture
def use_keyring(monkeypatch):
    """Set the server's keyring to these keys, newest first, for this test only."""

    def use(*keys: str) -> None:
        monkeypatch.setattr(settings, "llm_key_encryption_keys", ",".join(keys))

    return use


def altered(token: str) -> str:
    """The token with one character in the middle of its ciphertext changed."""
    middle = len(token) // 2
    replacement = "B" if token[middle] == "A" else "A"
    return token[:middle] + replacement + token[middle + 1 :]


# --- the round trip ------------------------------------------------------------------


def test_a_key_comes_back_for_its_owner(use_keyring):
    use_keyring(K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert crypto.decrypt(token, user_id=OWNER) == API_KEY


def test_the_token_holds_neither_the_key_nor_its_owner(use_keyring):
    use_keyring(K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert API_KEY not in token
    assert str(OWNER) not in token
    # Nor is it merely encoded: the token's own bytes do not carry the key either.
    raw = base64.urlsafe_b64decode(token)
    assert API_KEY.encode() not in raw
    assert str(OWNER).encode() not in raw


def test_encrypting_the_same_key_twice_gives_two_tokens(use_keyring):
    """Equal tokens would show which users share a key."""
    use_keyring(K1)

    first = crypto.encrypt(API_KEY, user_id=OWNER)
    second = crypto.encrypt(API_KEY, user_id=OWNER)

    assert first != second
    assert crypto.decrypt(first, user_id=OWNER) == API_KEY
    assert crypto.decrypt(second, user_id=OWNER) == API_KEY


# --- what does not open --------------------------------------------------------------


def test_a_token_copied_onto_another_users_row_does_not_open(use_keyring):
    """Write access to the database must not let one user spend another's credit."""
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)

    with pytest.raises(crypto.Unreadable) as excinfo:
        crypto.decrypt(token, user_id=SOMEONE_ELSE)

    assert API_KEY not in str(excinfo.value)
    assert token not in str(excinfo.value)


def test_an_altered_token_does_not_open(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(altered(token), user_id=OWNER)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("not-a-token", id="not-base64"),
        pytest.param("gAAAAAB" + "é" * 20, id="not-ascii"),
    ],
)
def test_something_that_is_not_a_token_does_not_open(use_keyring, token):
    use_keyring(K1)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(token, user_id=OWNER)


def test_a_token_from_another_servers_keyring_does_not_open(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring(K2)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(token, user_id=OWNER)


# --- rotation --------------------------------------------------------------------------


def test_a_new_token_is_under_the_first_key(use_keyring):
    use_keyring(K2, K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert crypto.is_current(token)
    assert Fernet(K2).decrypt(token) == f"{OWNER}:{API_KEY}".encode()


def test_rotation_moves_a_token_onto_the_new_key(use_keyring):
    use_keyring(K1)
    old = crypto.encrypt(API_KEY, user_id=OWNER)
    assert crypto.is_current(old)

    # Step one of a rotation: the new key goes first, and the old one stays.
    use_keyring(K2, K1)
    assert crypto.decrypt(old, user_id=OWNER) == API_KEY
    assert not crypto.is_current(old)

    new = crypto.rotate(old)
    assert crypto.is_current(new)
    assert crypto.decrypt(new, user_id=OWNER) == API_KEY
    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(new, user_id=SOMEONE_ELSE)

    # Last step, once every row is current: the old key goes.
    use_keyring(K2)
    assert crypto.decrypt(new, user_id=OWNER) == API_KEY
    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(old, user_id=OWNER)


def test_a_token_no_key_opens_is_not_current_and_cannot_be_rotated(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring(K2)

    assert not crypto.is_current(token)
    with pytest.raises(crypto.Unreadable):
        crypto.rotate(token)


# --- the setting ---------------------------------------------------------------------


def test_spaces_and_empty_entries_in_the_setting_are_ignored(use_keyring):
    use_keyring(f" {K2} , ,{K1},")

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert Fernet(K2).decrypt(token) == f"{OWNER}:{API_KEY}".encode()


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not-a-fernet-key", id="not-a-key"),
        pytest.param(K1[:-4], id="truncated"),
        pytest.param(K1[:-1], id="bad-padding"),
        pytest.param(base64.urlsafe_b64encode(b"k" * 16).decode(), id="sixteen-bytes"),
        pytest.param(f"{K1},not-a-fernet-key", id="bad-key-after-a-good-one"),
        # Pasted from a document that curled the quotes around it.
        pytest.param(f"\u201c{K1}\u201d", id="in-curly-quotes"),
        pytest.param(K1[:10] + "é" + K1[11:], id="an-accented-letter"),
    ],
)
def test_a_malformed_keyring_is_refused_without_quoting_it(use_keyring, raw):
    """Loudly, and at boot: the lifespan asks for the keyring once. The message is
    fixed whatever went wrong, and no error chained to it carries the value either."""
    use_keyring(raw)

    with pytest.raises(ValueError) as refused:
        crypto.keyring()

    message = str(refused.value)
    assert message == "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"
    for entry in raw.split(","):
        assert entry not in message
    assert refused.value.__cause__ is None
    assert refused.value.__context__ is None


@pytest.mark.parametrize("raw", [pytest.param("", id="empty"), pytest.param("   ", id="blank")])
def test_without_a_keyring_the_feature_is_off(use_keyring, raw):
    use_keyring(raw)

    assert crypto.keyring() is None
    assert crypto.available() is False


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda token: crypto.encrypt(API_KEY, user_id=OWNER), id="encrypt"),
        pytest.param(lambda token: crypto.decrypt(token, user_id=OWNER), id="decrypt"),
        pytest.param(crypto.is_current, id="is_current"),
        pytest.param(crypto.rotate, id="rotate"),
    ],
)
def test_without_a_keyring_every_operation_says_so(use_keyring, operation):
    """NotConfigured, not Unreadable: a server started without its keyring must not
    look to the caller as if every stored key had gone bad."""
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring("")

    with pytest.raises(crypto.NotConfigured):
        operation(token)


def test_a_changed_setting_takes_effect_at_once(use_keyring):
    """The parsed keyring is cached on the setting's value, not captured at import."""
    use_keyring(K1)
    ring = crypto.keyring()
    assert crypto.keyring() is ring

    use_keyring(K2)
    assert crypto.keyring() is not ring

    use_keyring(K1)
    assert crypto.keyring() is ring
    assert crypto.available() is True
```

The API key is shaped like a real one and obviously fake. The two server keys are generated fresh for each run, and each parametrized case carries an `id`, so no key string lands in a test id. Every key in this file is a fake, so a plain `assert` that prints one when it fails is fine. The two non-ASCII cases in `test_a_malformed_keyring_is_refused_without_quoting_it` are the ones Fernet itself does not word as a key error: for them `base64` raises `ValueError("string argument should contain only ASCII characters")`, chained to a `UnicodeEncodeError` whose `.object` is the entry. The `\u201c` and `\u201d` escapes are the curly quotes; keep them as escapes so no editor straightens them. The `use_keyring` fixture belongs to this file. Task 4 adds an `llm_keyring` fixture to `conftest.py` for the API tests, and the two do not clash.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_llm_crypto.py -q`

Expected: FAIL at collection, with `1 error during collection`:
```
E   ModuleNotFoundError: No module named 'app.llm'
```

- [ ] **Step 3: Declare cryptography**

Run: `uv add 'cryptography>=46'`

`cryptography` is already locked, at 50.0.0, because `google-auth` depends on it (so does plan 8's `pywebpush`, through `py-vapid`). The app now imports it directly, so it is declared: a transitive dependency disappears when the library that brought it stops needing it. `uv add` keeps the locked 50.0.0, which satisfies `>=46`. It appends `"cryptography>=46",` to `[project] dependencies` in `pyproject.toml`, and adds `cryptography` to the project's own entry in `uv.lock`. No other package in the lock changes.

Run: `uv run python -c "import cryptography; print(cryptography.__version__)"`

Expected: `50.0.0`

- [ ] **Step 4: The setting**

In `backend/app/config.py`, find plan 8's last field:

```python
    # Sends reminders from the API process, checking every minute. Off by default:
    # every API test's TestClient runs the app's lifespan, and a loop there would
    # read the development database.
    scheduler_enabled: bool = False
```

Directly below it, after one blank line and still inside `class Settings`, add:

```python
    # AI descriptions (plan 9). Comma-separated Fernet keys: the first encrypts, every one
    # decrypts, so a new key goes first and an old one stays until scripts.rotate_llm_keys
    # has re-encrypted every row. Empty turns the feature off on this server. Never derived
    # from session_secret: rotating a leaked session secret must not destroy stored keys.
    llm_key_encryption_keys: str = ""
```

Keep it a plain `str`. A `list[str]` field would make pydantic-settings expect JSON in the environment variable, and a comma-separated value is what an operator pastes into `fly secrets set`.

- [ ] **Step 5: The keyring**

Create `backend/app/llm/__init__.py`, a package docstring and nothing else:

```python
"""AI descriptions: the API key a user brings, kept encrypted, and the model it pays for."""
```

Create `backend/app/llm/crypto.py`:

```python
"""The server's keyring, which encrypts the API keys users bring.

A stored key is a Fernet token (AES-128-CBC with an HMAC-SHA256 over the whole
token, from `cryptography`), so a token whose contents have been altered fails to
open rather than opening to something else. `MultiFernet` over
`LLM_KEY_ENCRYPTION_KEYS` makes the keyring rotatable: the first key encrypts,
and every key decrypts.

The plaintext is `f"{user_id}:{api_key}"`, and `decrypt` checks the prefix. Fernet
has no associated data to bind a token to its row, so the binding travels inside
the ciphertext instead. Someone able to write to the database therefore cannot
copy one user's token onto another user's row and spend the first user's credit:
the copy decrypts, names the wrong user, and is Unreadable.

The keyring is parsed from the setting's current value through an LRU cache
keyed on that value. A test that monkeypatches the setting takes effect at once,
and a malformed keyring raises the moment anything asks for it; the app's
lifespan asks once, so a bad value stops the app at boot.

The key is never derived from `session_secret`. Rotating a leaked session secret
must not make every stored key unreadable, and that secret has a development
default a misconfigured deploy would use without a word.
"""

import functools
import uuid

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

# Fixed messages: nothing raised from here quotes a key, a token or a plaintext.
_NOT_CONFIGURED = "LLM_KEY_ENCRYPTION_KEYS is not set on this server"
_UNREADABLE = "the stored API key cannot be read with this server's keyring"
_MALFORMED = "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"


class NotConfigured(RuntimeError):
    """The server has no keyring: the feature is off."""


class Unreadable(ValueError):
    """Wrong keyring, tampered token, or a token bound to another user."""


def _fernet(entry: str) -> Fernet | None:
    """A Fernet for one keyring entry, or None when the entry is not a Fernet key."""
    try:
        return Fernet(entry)
    except (ValueError, TypeError):
        # Any failure means the entry is not a key. binascii.Error (not base64) and
        # UnicodeError (a non-ASCII character, such as a curly quote) are ValueErrors;
        # TypeError is Fernet's answer to a value that is neither str nor bytes.
        return None


@functools.lru_cache(maxsize=4)
def _fernets(raw: str) -> tuple[Fernet, ...]:
    """One Fernet per comma-separated key, in order. A malformed key raises ValueError."""
    fernets = []
    for part in raw.split(","):
        entry = part.strip()
        if not entry:
            continue
        fernet = _fernet(entry)
        if fernet is None:
            # Raised outside any except block, so no error is chained to it: for a
            # non-ASCII entry, Fernet's error chains one whose .object is the entry.
            raise ValueError(_MALFORMED) from None
        fernets.append(fernet)
    return tuple(fernets)


@functools.lru_cache(maxsize=4)
def _keyring(raw: str) -> MultiFernet | None:
    """The keyring for this setting value, or None when it names no key at all."""
    fernets = _fernets(raw)
    return MultiFernet(fernets) if fernets else None


def _raw() -> str:
    return settings.llm_key_encryption_keys.strip()


def keyring() -> MultiFernet | None:
    """This server's keyring, or None when the feature is off here."""
    return _keyring(_raw())


def available() -> bool:
    """Whether this server can store keys at all."""
    return keyring() is not None


def _require() -> MultiFernet:
    ring = keyring()
    if ring is None:
        raise NotConfigured(_NOT_CONFIGURED)
    return ring


def encrypt(api_key: str, *, user_id: uuid.UUID) -> str:
    """A token for `api_key` that only this user's row can open, under the first key."""
    return _require().encrypt(f"{user_id}:{api_key}".encode()).decode("ascii")


def decrypt(token: str, *, user_id: uuid.UUID) -> str:
    """The API key in `token`, which must have been encrypted for this user.

    NotConfigured rather than Unreadable when there is no keyring: a server
    started without one must not mark every stored key unreadable.
    """
    ring = _require()
    try:
        plaintext = ring.decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        # ValueError: a token that is not ASCII, or a plaintext that is not UTF-8.
        raise Unreadable(_UNREADABLE) from None
    prefix = f"{user_id}:"
    if not plaintext.startswith(prefix):
        raise Unreadable(_UNREADABLE)
    return plaintext.removeprefix(prefix)


def is_current(token: str) -> bool:
    """Whether the first key alone opens `token`, so rotating it would change nothing.

    No user check: this only says which key a token is under. A token no key
    opens is not current, and `rotate` then says it is Unreadable.
    """
    _require()
    newest = _fernets(_raw())[0]
    try:
        newest.decrypt(token)
    except (InvalidToken, ValueError):
        return False
    return True


def rotate(token: str) -> str:
    """`token` re-encrypted under the first key, whichever key it was under.

    The plaintext is carried over untouched, user prefix included. Checking that
    the prefix names the row's user is the caller's job.
    """
    ring = _require()
    try:
        return ring.rotate(token).decode("ascii")
    except (InvalidToken, ValueError):
        raise Unreadable(_UNREADABLE) from None
```

Four details in it are deliberate:
- A malformed keyring entry always raises `ValueError(_MALFORMED)`, never Fernet's own error. Fernet words most bad keys as `Fernet key must be 32 url-safe base64-encoded bytes.`, but not all of them: for an entry holding a non-ASCII character, such as a key pasted between curly quotes, `base64` raises `ValueError("string argument should contain only ASCII characters")`, chained to a `UnicodeEncodeError` whose `.object` is the whole entry (checked against `cryptography` 50.0.0). `_fernet` turns every failure into `None`, and `_fernets` raises only after that handler has finished, so the error it raises has no `__cause__` and no `__context__` (its `from None` is only a backstop; the test checks both directly): nothing attached to it holds the entry for a log or an error reporter to record. Raising inside the handler would not do: `from None` hides the chain from a printed traceback, but the context is still attached.
- `ValueError` is caught next to `InvalidToken`. Fernet raises a plain `ValueError`, not `InvalidToken`, for a token string that is not ASCII (checked against `cryptography` 50.0.0), and a plaintext that is not UTF-8 would raise one too. Both mean the token is not one this keyring made.
- `from None` in `decrypt` and `rotate` keeps the `InvalidToken` out of a printed traceback, which then carries only the fixed message.
- `is_current` opens the token with the first key alone. `MultiFernet` keeps its keys private, so `_fernets` keeps the parsed keys where `is_current` can reach the first one. It is cached on the same value, so the keyring is still parsed once per value.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_llm_crypto.py -q`

Expected: `27 passed`. No test in this file opens a database connection.

- [ ] **Step 7: Document the setting**

Append to the end of `backend/.env.example`, leaving one blank line after plan 8's last line, `# SCHEDULER_ENABLED=true`:

```
# --- AI descriptions, on each user's own Anthropic key -----------------------
# AI descriptions: comma-separated Fernet keys, newest first. Generate one with
#   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# LLM_KEY_ENCRYPTION_KEYS=
# These encrypt the API keys users save; they are not Anthropic keys. Left
# unset, the feature is off on this server and its screen says so. A malformed
# value stops the app at boot. Keep them out of version control, and keep every
# key still in use: a saved API key that no key here opens is unreadable, and
# its user has to enter it again.
# To rotate, put a new key first with the old one after it, restart, then run
#   uv run python -m scripts.rotate_llm_keys
# and remove the old key once a second run rotates nothing.
```

Like every other line in the file, it is commented out. Copying the file to `.env` therefore leaves the feature off until someone sets a key.

`scripts/rotate_llm_keys.py` arrives in Task 4. The comment names it now, because the setting and its rotation belong together.

- [ ] **Step 8: Run the checks**

Run: `uv run ruff check .`

Expected: `All checks passed!`

Check that the command the comment gives works:

Run: `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Expected: a 44-character key ending in `=`. Nothing stores it; this only proves the documented command works.

Run: `uv run python -c "from app.llm import crypto; print(crypto.available())"`

Expected: `False`, because the development `.env` does not set the keyring. If yours already sets `LLM_KEY_ENCRYPTION_KEYS`, the output is `True`.

- [ ] **Step 9: Commit**

From the repository root:

```bash
git add backend/app/llm/__init__.py backend/app/llm/crypto.py backend/app/config.py \
  backend/.env.example backend/pyproject.toml backend/uv.lock backend/tests/test_llm_crypto.py
git commit -m "feat(backend): add the keyring that encrypts users' API keys

Plan 9 lets a user bring their own Anthropic API key, and a key that spends
someone's money is stored encrypted at rest. The keyring is a new setting,
LLM_KEY_ENCRYPTION_KEYS, and it is never derived from the session secret:
rotating a leaked session secret must not make every stored key unreadable.

app/llm/crypto.py wraps cryptography's MultiFernet. The first key encrypts
and every key decrypts, so a new key can go first while old tokens still
open, and rotate() moves a token onto it. The plaintext carries the user
id, and decrypt checks it. Fernet has no associated data, so this is what
stops a token copied onto another user's row from spending the first
user's credit. Anything that does not open cleanly is Unreadable, never a
wrong key.

An empty keyring turns the feature off and says NotConfigured, so a server
started without one cannot be mistaken for one whose stored keys went bad.
A malformed keyring raises as soon as it is read, always with one fixed
message and nothing chained to it, so no part of the value reaches a log,
even for a key pasted between curly quotes. cryptography was already
locked through google-auth; it is declared now that the app imports it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The two tables

Two per-user tables, and nothing reads or writes them yet: Task 4 stores the key and Task 5 stores the text.

`user_settings` holds a user's API key, one row per user. It sits outside the profile, because a profile save deletes and re-inserts every table in `profiles.service.CHILD_MODELS`, and editing a meal time must not forget a key someone pays for. The key is six columns that mean something only together: provider, model, ciphertext, a four-character hint, a status and when it was set. The database refuses a half-written key rather than trusting every writer to be careful: `ck_user_settings_llm_complete` keeps the six all set or all null, and `ck_user_settings_llm_status` limits the status to `ok`, `rejected` and `unreadable`. Removing a key nulls the six and keeps the row.

`dish_polish` caches the model's description and cooking tip, per user and dish. It is keyed to the dish rather than to plan items, because a swap rewrites an item in place and a regenerate deletes and re-inserts them. So a swap, a lock, a regenerate or next week's plan all reuse it with nothing to invalidate. `brief_hash` records exactly what was sent (Task 5 computes it), so a cached row whose dish or ingredient names have since changed can be recognised as stale. It is per user because each user pays for their own.

Both tables cascade with their user, and `dish_polish` with its dish too, so nothing a user paid for outlives their account. The two unique keys are named, because Tasks 4 and 5 upsert on them by name. Neither table may ever be added to `CHILD_MODELS`.

All commands run from `backend/`, and the commit from the repository root.

**Files:**
- Create: `backend/app/models/llm.py`, `backend/alembic/versions/a3b4c5d6e7f8_ai_descriptions.py`
- Modify:
  - `backend/app/models/__init__.py`: registration
  - `backend/scripts/e2e_session.py`: `OWNED_MODELS` gains `DishPolish` and `UserSettings`
- Test: `backend/tests/test_llm_models.py` (create)

**Interfaces:**
- Consumes:
  - Plan 8's migration head, `f2a3b4c5d6e7`.
  - `TimestampedBase` (`id`, `created_at`; there is no `updated_at`), `users.id` and `dishes.id`.
  - Plan 8's final `app/models/__init__.py` and `scripts/e2e_session.py` (plan 8 Task 3).
- Produces:
```python
# app/models/llm.py
class UserSettings(TimestampedBase):      # table user_settings
    user_id: uuid.UUID                     # FK users.id ON DELETE CASCADE, indexed
    llm_provider: str | None               # String(16): 'anthropic'
    llm_model: str | None                  # String(40)
    llm_key_ciphertext: str | None         # Text: a token from app.llm.crypto.encrypt
    llm_key_hint: str | None               # String(4): the key's last four characters
    llm_key_status: str | None             # String(12): ok | rejected | unreadable
    llm_key_set_at: datetime.datetime | None   # timestamptz
    # uq_user_settings_user (user_id)
    # ck_user_settings_llm_complete: num_nulls(the six llm_* columns) IN (0, 6)
    # ck_user_settings_llm_status: llm_key_status IN ('ok', 'rejected', 'unreadable')

class DishPolish(TimestampedBase):        # table dish_polish
    user_id: uuid.UUID                     # FK users.id ON DELETE CASCADE, indexed
    dish_id: uuid.UUID                     # FK dishes.id ON DELETE CASCADE, indexed
    brief_hash: str                        # String(64), not null: SHA-256 hex
    description: str                       # Text, not null
    cooking_note: str | None               # Text
    model: str                             # String(40), not null
    # uq_dish_polish_user_dish (user_id, dish_id)

# migration a3b4c5d6e7f8 (down_revision f2a3b4c5d6e7): both tables; downgrade drops them
```
- Used by:
  - Task 4 upserts `UserSettings` with `insert(...).on_conflict_do_update(constraint="uq_user_settings_user", ...)`. Any write that sets or clears the key must write all six `llm_*` columns in one statement. Changing only `llm_key_status` on a stored key is fine.
  - Task 5 upserts `DishPolish` on `uq_dish_polish_user_dish`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_llm_models.py`:

```python
"""The saved API key and the cached dish text, on the migrated schema.

A key is six columns that mean something only together, so the database refuses
a half-written one rather than trusting every writer to be careful. Each user has
one settings row, and one cached text per dish: those are the unique keys the
upserts in app.llm.service and app.planner.polish name as their conflict targets.
And both go with their user, the cached text with its dish too, so nothing a
user paid for outlives their account.
"""

import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.models.food import Dish
from app.models.llm import DishPolish, UserSettings
from app.models.user import User

SET_AT = datetime.datetime(2026, 9, 24, 9, 30, tzinfo=datetime.UTC)

# A complete key, as app.llm.service writes one. The ciphertext is a stand-in:
# the schema cannot tell a token from any other text, and does not need to.
KEY = {
    "llm_provider": "anthropic",
    "llm_model": "claude-opus-5",
    "llm_key_ciphertext": "gAAAAAB-stand-in-for-a-fernet-token",
    "llm_key_hint": "WXYZ",
    "llm_key_status": "ok",
    "llm_key_set_at": SET_AT,
}
NO_KEY = dict.fromkeys(KEY)


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


def make_dish(db, code: str) -> Dish:
    dish = Dish(code=f"test:{code}", name=code.title(), source="authored")
    db.add(dish)
    db.flush()
    return dish


@pytest.fixture
def user(db) -> User:
    return make_user(db, "llm")


@pytest.fixture
def dish(db) -> Dish:
    return make_dish(db, "idli")


def polish(
    user: User, dish: Dish, description: str | None = "Soft steamed rice cakes."
) -> DishPolish:
    return DishPolish(
        user_id=user.id,
        dish_id=dish.id,
        brief_hash="a" * 64,
        description=description,
        cooking_note=None,
        model="claude-opus-5",
    )


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def key_columns(db, user: User) -> list[tuple]:
    return [
        tuple(row)
        for row in db.execute(
            select(UserSettings.llm_key_ciphertext, UserSettings.llm_key_status).where(
                UserSettings.user_id == user.id
            )
        )
    ]


# --- user_settings -----------------------------------------------------------------


def test_a_complete_key_is_stored(db, user):
    db.add(UserSettings(user_id=user.id, **KEY))
    db.flush()

    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], "ok")]


def test_a_row_with_no_key_is_allowed(db, user):
    db.add(UserSettings(user_id=user.id))
    db.flush()

    assert key_columns(db, user) == [(None, None)]


def test_removing_a_key_nulls_it_and_keeps_the_row(db, user):
    row = UserSettings(user_id=user.id, **KEY)
    db.add(row)
    db.flush()

    for column, value in NO_KEY.items():
        setattr(row, column, value)
    db.flush()

    assert key_columns(db, user) == [(None, None)]


@pytest.mark.parametrize("missing", sorted(KEY))
def test_a_key_missing_any_one_column_is_refused(db, user, missing):
    refused(db, UserSettings(user_id=user.id, **{**KEY, missing: None}))


@pytest.mark.parametrize("present", sorted(KEY))
def test_one_key_column_on_its_own_is_refused(db, user, present):
    refused(db, UserSettings(user_id=user.id, **{**NO_KEY, present: KEY[present]}))


@pytest.mark.parametrize("status", ["ok", "rejected", "unreadable"])
def test_each_key_status_is_accepted(db, user, status):
    db.add(UserSettings(user_id=user.id, **{**KEY, "llm_key_status": status}))
    db.flush()

    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], status)]


@pytest.mark.parametrize("status", ["expired", "OK", ""])
def test_any_other_key_status_is_refused(db, user, status):
    refused(db, UserSettings(user_id=user.id, **{**KEY, "llm_key_status": status}))


def test_one_settings_row_per_user(db, user):
    db.add(UserSettings(user_id=user.id, **KEY))
    db.flush()
    refused(db, UserSettings(user_id=user.id))


def test_saving_a_key_again_replaces_it_in_place(db, user):
    """The service's upsert, which names the unique key as its conflict target."""

    def save(hint: str):
        return db.execute(
            insert(UserSettings)
            .values(user_id=user.id, **{**KEY, "llm_key_hint": hint})
            .on_conflict_do_update(constraint="uq_user_settings_user", set_={"llm_key_hint": hint})
            .returning(UserSettings.id)
        ).scalar_one()

    first = save("WXYZ")
    second = save("ABCD")

    assert second == first
    hints = db.scalars(
        select(UserSettings.llm_key_hint).where(UserSettings.user_id == user.id)
    ).all()
    assert hints == ["ABCD"]


# --- dish_polish ------------------------------------------------------------------


def test_one_cached_text_per_user_and_dish(db, user, dish):
    db.add(polish(user, dish))
    db.flush()
    refused(db, polish(user, dish, "Another take on the same dish."))


def test_another_user_or_another_dish_is_a_row_of_its_own(db, user, dish):
    other = make_user(db, "other")
    dosa = make_dish(db, "dosa")

    db.add_all([polish(user, dish), polish(other, dish), polish(user, dosa)])
    db.flush()

    rows = db.execute(
        select(DishPolish.user_id, DishPolish.dish_id).where(
            DishPolish.user_id.in_([user.id, other.id])
        )
    )
    assert {tuple(row) for row in rows} == {
        (user.id, dish.id),
        (other.id, dish.id),
        (user.id, dosa.id),
    }


def test_a_cached_text_needs_a_description(db, user, dish):
    refused(db, polish(user, dish, None))


def test_polishing_a_dish_again_replaces_its_text_in_place(db, user, dish):
    """The polish upsert, which names the unique key as its conflict target."""

    def save(brief_hash: str):
        return db.execute(
            insert(DishPolish)
            .values(
                user_id=user.id,
                dish_id=dish.id,
                brief_hash=brief_hash,
                description="Soft steamed rice cakes.",
                model="claude-opus-5",
            )
            .on_conflict_do_update(
                constraint="uq_dish_polish_user_dish", set_={"brief_hash": brief_hash}
            )
            .returning(DishPolish.id)
        ).scalar_one()

    first = save("a" * 64)
    second = save("b" * 64)

    assert second == first
    hashes = db.scalars(select(DishPolish.brief_hash).where(DishPolish.user_id == user.id)).all()
    assert hashes == ["b" * 64]


# --- cascades -----------------------------------------------------------------------


def test_the_key_and_the_cached_text_go_with_their_user(db, user, dish):
    user_id = user.id
    db.add_all([UserSettings(user_id=user.id, **KEY), polish(user, dish)])
    db.flush()

    db.delete(user)
    db.flush()

    assert db.scalars(select(UserSettings).where(UserSettings.user_id == user_id)).all() == []
    assert db.scalars(select(DishPolish).where(DishPolish.user_id == user_id)).all() == []


def test_the_cached_text_goes_with_its_dish(db, user, dish):
    dish_id = dish.id
    db.add_all([UserSettings(user_id=user.id, **KEY), polish(user, dish)])
    db.flush()

    db.delete(dish)
    db.flush()

    assert db.scalars(select(DishPolish).where(DishPolish.dish_id == dish_id)).all() == []
    # The key is the user's, not the dish's.
    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], "ok")]
```

Each test that expects a refusal makes exactly one, and it is the test's last statement. After an `IntegrityError` the session has to roll back, and in the `db` fixture that rollback would also take this test's user and dish with it.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_llm_models.py -q`

Expected: FAIL at collection, with `1 error during collection`:
```
E   ModuleNotFoundError: No module named 'app.models.llm'
```

- [ ] **Step 3: Write the models**

Create `backend/app/models/llm.py`:

```python
import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class UserSettings(TimestampedBase):
    """A user's own settings that belong to no questionnaire: today, their LLM key.

    Its own table rather than profile columns: a profile save replaces the whole
    questionnaire, and editing a meal time must not forget a key the user paid for.
    It belongs to the user, not the profile, so it must never join
    `profiles.service.CHILD_MODELS` either.

    The six `llm_*` columns are one key, set together and cleared together:
    removing the key nulls them and keeps the row. The key itself is only ever
    here as `llm_key_ciphertext`, a token from `app.llm.crypto` that opens for
    this user alone. `llm_key_hint` is its last four characters, stored so that
    showing which key is saved never needs a decrypt.
    """

    __tablename__ = "user_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_settings_user"),
        # A half-written key -- a ciphertext with no status, a hint with no
        # ciphertext -- would read as saved and then fail on first use.
        CheckConstraint(
            "num_nulls(llm_provider, llm_model, llm_key_ciphertext, llm_key_hint,"
            " llm_key_status, llm_key_set_at) IN (0, 6)",
            name="ck_user_settings_llm_complete",
        ),
        CheckConstraint(
            "llm_key_status IN ('ok', 'rejected', 'unreadable')",
            name="ck_user_settings_llm_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 'anthropic', the one provider today.
    llm_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # One of app.llm.providers.MODELS, checked against the key when it was saved.
    llm_model: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_key_hint: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # ok | rejected (the provider refused it on use) | unreadable (this server's
    # keyring no longer opens it). Either of the last two asks for the key again.
    llm_key_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # When the key was saved. TimestampedBase has no updated_at, and created_at is
    # when the row first appeared, which a replaced key does not change.
    llm_key_set_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DishPolish(TimestampedBase):
    """The model's description and cooking tip for one dish, as one user paid for them.

    Keyed by user and dish, never by plan item: a swap, a lock, a regenerate or
    next week's plan all reuse it with nothing to invalidate. `brief_hash` is a
    hash of exactly what was sent (the prompt version, the dish name and its
    ingredient names), and a row whose hash no longer matches is ignored when read
    and replaced on the next polish. Per user, because each user pays for their
    own, and it goes with their account.

    Nothing here is a number, and nothing changes the dish: the planner's dish,
    portion and rationale stay exactly as they are, and this text sits beside them.
    """

    __tablename__ = "dish_polish"
    __table_args__ = (UniqueConstraint("user_id", "dish_id", name="uq_dish_polish_user_dish"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex digest of what was sent for this dish; see app.planner.polish.
    brief_hash: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    # None when the model had no tip, or its tip failed the guard.
    cooking_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The model asked for, one of app.llm.providers.MODELS. Under Claude Opus 5's
    # refusal fallback, Anthropic may have answered on another.
    model: Mapped[str] = mapped_column(String(40))
```

`num_nulls` is a Postgres built-in (9.6 and later) that counts its null arguments. It says "all six or none" in one line, where the portable form needs twelve `IS NULL` / `IS NOT NULL` terms. A null `llm_key_status` passes `ck_user_settings_llm_status`, because a CHECK fails only on false; the other constraint is what requires a status once a key exists.

In `backend/app/models/__init__.py`, directly after the line

```python
from app.models.household import Household, HouseholdInvite, HouseholdMember
```

add

```python
from app.models.llm import DishPolish, UserSettings
```

In `__all__`, add `"DishPolish"` directly after `"DishNutrient"`, and `"UserSettings"` directly after `"User"` (and before `"UsualIntakeItem"`). That is RUF022's order.

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/a3b4c5d6e7f8_ai_descriptions.py`:

```python
"""ai descriptions

Two per-user tables.

`user_settings` holds one row per user, outside the profile: a profile save
replaces the questionnaire's tables wholesale, and a saved API key must survive
an edit to someone's meal times. Its six `llm_*` columns are one key, set or
cleared together, which `ck_user_settings_llm_complete` enforces;
`ck_user_settings_llm_status` limits the status to ok, rejected and unreadable.
The key is stored only as ciphertext that opens for its own user.

`dish_polish` caches the model's description and cooking tip per user and dish,
keyed by a hash of exactly what was sent. It is keyed to the dish rather than to
plan items, so a swap, a lock, a regenerate or the next week's plan reuse it
with nothing to invalidate. It goes with its user and with its dish.

Both tables start empty, so there is nothing to backfill.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned(
    name: str, *items: sa.Column | sa.Constraint, unique: tuple[str, ...], constraint: str
) -> None:
    """A per-user table: the model's columns and constraints, then id and created_at,
    then keys."""
    op.create_table(
        name,
        sa.Column("user_id", sa.UUID(), nullable=False),
        *items,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(*unique, name=constraint),
    )
    op.create_index(op.f(f"ix_{name}_user_id"), name, ["user_id"], unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    _owned(
        "user_settings",
        sa.Column("llm_provider", sa.String(length=16), nullable=True),
        sa.Column("llm_model", sa.String(length=40), nullable=True),
        sa.Column("llm_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("llm_key_hint", sa.String(length=4), nullable=True),
        sa.Column("llm_key_status", sa.String(length=12), nullable=True),
        sa.Column("llm_key_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "num_nulls(llm_provider, llm_model, llm_key_ciphertext, llm_key_hint,"
            " llm_key_status, llm_key_set_at) IN (0, 6)",
            name="ck_user_settings_llm_complete",
        ),
        sa.CheckConstraint(
            "llm_key_status IN ('ok', 'rejected', 'unreadable')",
            name="ck_user_settings_llm_status",
        ),
        unique=("user_id",),
        constraint="uq_user_settings_user",
    )
    _owned(
        "dish_polish",
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("brief_hash", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cooking_note", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
        unique=("user_id", "dish_id"),
        constraint="uq_dish_polish_user_dish",
    )
    op.create_index(op.f("ix_dish_polish_dish_id"), "dish_polish", ["dish_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_dish_polish_dish_id"), table_name="dish_polish")
    for name in ("dish_polish", "user_settings"):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
```

`_owned` is the helper from `e1f2a3b4c5d6_weight_and_cycle.py`, with one change: its extra arguments may also be constraints, since `op.create_table` takes columns and constraints alike. That is how the two CHECK constraints and the dish foreign key go in.

Migrate both databases, then check that the models and the migration agree:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test \
  uv run alembic upgrade head
uv run alembic upgrade head
uv run alembic check
```

Expected:
- Each upgrade logs `Running upgrade f2a3b4c5d6e7 -> a3b4c5d6e7f8, ai descriptions`.
- `check` ends with `No new upgrade operations detected.`

If `check` reports a difference, fix the **migration** to match the model. `check` compares the tables, columns, types, nullability, indexes, unique constraints and foreign keys, including `ON DELETE`. It compares CHECK constraints by name only (this is alembic 1.19.1), not by their condition. That is why the tests pin what each CHECK refuses.

Then prove the downgrade works, and return to head:

```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: `Running downgrade a3b4c5d6e7f8 -> f2a3b4c5d6e7, ai descriptions`, then `Running upgrade f2a3b4c5d6e7 -> a3b4c5d6e7f8, ai descriptions`. Both tables are still empty at this point, so the round trip loses nothing.

Run: `uv run alembic heads`

Expected: `a3b4c5d6e7f8 (head)`, and only that line.

- [ ] **Step 5: Reset the new tables in the end-to-end run**

`scripts/e2e_session.py --reset` clears every table the throwaway end-to-end user writes to. Without these two, a second run would start with the first run's saved key and cached text. Each has only one owned parent, `users`, which `--reset` never deletes; `dish_polish`'s other parent is `dishes`, which it never deletes either. So their place in the tuple does not matter for foreign keys. They go beside plan 8's `PushSubscription`, with the other rows that belong to the user rather than to the profile.

In `backend/scripts/e2e_session.py`, make four edits against plan 8's version of the file.

1. Directly after the line

```python
from app.models.diary import MealLog, MealSlotSkip
```

add

```python
from app.models.llm import DishPolish, UserSettings
```

2. Replace the docstring's `--reset` paragraph, which plan 8 left as

```
`--reset` deletes everything the user has logged, planned, answered and
subscribed, so a run starts from onboarding. It never touches any user but this
one.
```

with

```
`--reset` deletes everything the user has logged, planned, answered,
subscribed and saved, so a run starts from onboarding. It never touches any
user but this one.
```

3. In the comment above `OWNED_MODELS`, replace its last two lines,

```python
# grows every run, cycle tracking already switched on, or a device still
# subscribed to the last run's reminders.
```

with

```python
# grows every run, cycle tracking already switched on, a device still
# subscribed to the last run's reminders, or an API key the last run saved.
```

4. In the `OWNED_MODELS` tuple, directly after the line `    PushSubscription,`, add

```python
    DishPolish,
    UserSettings,
```

- [ ] **Step 6: Run the tests and the checks**

Run: `uv run pytest tests/test_llm_models.py -q`

Expected: `29 passed`. If pytest instead stops with a usage error saying the test database "is at ['f2a3b4c5d6e7'] but the migrations head is a3b4c5d6e7f8", the first command in Step 4 was skipped.

Run: `uv run ruff check .`

Expected: `All checks passed!`

Check that the reset script imports and lists both tables, without running it:

Run: `uv run python -c "from scripts.e2e_session import OWNED_MODELS; print(len(OWNED_MODELS), sorted(m.__tablename__ for m in OWNED_MODELS if m.__tablename__ in {'dish_polish', 'user_settings'}))"`

Expected: `21 ['dish_polish', 'user_settings']`. Importing the script opens no database connection.

- [ ] **Step 7: Commit**

From the repository root:

```bash
git add backend/app/models/llm.py backend/app/models/__init__.py \
  backend/alembic/versions/a3b4c5d6e7f8_ai_descriptions.py backend/scripts/e2e_session.py \
  backend/tests/test_llm_models.py
git commit -m "feat(backend): add the user_settings and dish_polish tables

user_settings holds one row per user for the API key they bring: the
provider, the model, the ciphertext, a four-character hint, a status and
when it was set. It sits outside the profile, because a profile save
replaces the questionnaire's tables and a saved key must survive an edit
to a meal time. A CHECK keeps the six key columns all set or all null, so a
half-written key can never read as saved. Another limits the status to
ok, rejected and unreadable. Removing a key will null the six columns and
keep the row.

dish_polish caches a dish's description and cooking tip per user, with a
hash of exactly what was sent to the model. It is keyed to the dish, not
to plan items, so a swap, a lock, a regenerate or next week's plan reuse
it with nothing to invalidate. Both tables cascade with their user, and
the cache with its dish too. Both unique keys are named, since the upserts
to come target them by name.

The end-to-end reset clears both tables for its throwaway user.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: The Anthropic adapter

This task adds the one piece of the app that talks to a model. `app/llm/providers.py` holds a `Provider` protocol and its only adapter, `AnthropicProvider`, on the official `anthropic` SDK. The adapter makes two calls, both with the user's own key:
- `check_key(api_key, model)` looks the chosen model up with `client.models.retrieve(model)`. That is `GET /v1/models/{id}`, which spends no tokens. Task 4 calls it when a key is saved.
- `polish(api_key, model, dishes)` asks for a description and a cooking tip for every dish in a batch, in one `client.beta.messages.parse(...)` call with a pydantic output format. Task 5 calls it once per 40 dishes.

The adapter is deliberately thin. It sends what it is handed (an opaque reference, a dish name, ingredient names) and returns the model's text **unfiltered**. The guard against digits, number words and nutrient claims belongs to Task 5's `app/planner/polish.py`, which also drops any reference it never sent.

Three things here are about the key, which is a secret:
- **Where it goes.** Every SDK client is built with `api_key=`, `base_url="https://api.anthropic.com"`, `timeout=` and `max_retries=` all explicit. On `anthropic` 1.8.0 an explicit `api_key` stops the SDK reading `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`, and an explicit `base_url` beats `ANTHROPIC_BASE_URL`. So nothing in the server's environment can send a user's key to another host.
- **What an error carries.** The SDK's exception message is the provider's own text, and that text can quote the request. Every SDK error therefore becomes one of four `ProviderError` subclasses that carry nothing, raised `from None`. The log line names only the SDK's error class and the status code, never `str(exc)`.
- **The tests' own output.** pytest prints both sides of a failed `==` or `in`, so the tests compare the key only inside small helpers that return a bool.

`conftest.py` gains an autouse guard. `AnthropicProvider` takes an optional `http_client`, and tests always pass one. A provider built without one asks the module-level `_default_http_client()` for its client. In production that returns `None`, so the SDK builds its own. Under the suite, the guard patches it to return an `httpx2.Client` whose transport records the request and raises `RuntimeError`. Verified on `anthropic` 1.8.0: the SDK wraps any exception its transport raises in `APIConnectionError` (with the `RuntimeError` as `__cause__`), and the adapter turns that into `ProviderUnavailable`. A test that forgot Task 4's `FakeProvider` therefore fails on a 502 or 503 without a request leaving the machine.

The guard's own self-check must not reach the network even if the adapter never asks `_default_http_client`, so it also points the proxy variables at a closed local port. Verified on `anthropic` 1.8.0 and `httpx2` 2.13.1, with a probe that recorded every socket connection:
- A client the SDK builds itself (`http_client=None`) honours `HTTPS_PROXY` and `HTTP_PROXY`. It builds its proxy mounts from `urllib.request.getproxies()`. With both set to `http://127.0.0.1:1`, the one connection it tried was to `127.0.0.1:1`, which refused it.
- A lowercase `https_proxy` beats an uppercase `HTTPS_PROXY`, and `NO_PROXY=*` bypasses every proxy. So the self-check sets both cases of both variables and clears `NO_PROXY` and `no_proxy`.

With those variables set, an adapter that skipped the hook is refused locally, and the self-check's last assertion names what went wrong: the guard's transport saw no request.

These SDK behaviours were checked against `anthropic` 1.8.0 with a mock transport before this task was written, and the tests below pin each one:
- `beta.messages.parse` raises pydantic's `ValidationError`, not an SDK error, when the text is partial JSON. That happens when the answer is cut off at `max_tokens` or declined partway. The adapter catches it and returns `{}`, which is the Decision's "not an error, the dishes stay undescribed".
- The SDK sends `anthropic-beta: structured-outputs-2025-12-15` on every `parse` call. For Claude Opus 5 the header becomes `server-side-fallback-2026-07-01,structured-outputs-2025-12-15`. The tests therefore check that the fallback beta is absent for the other models, not that the header is.
- A 402 surfaces as a plain `APIStatusError` with `status_code == 402`. There is no subclass for it.
- A 529 surfaces as `OverloadedError`, a 413 as `RequestTooLargeError`. Both are `APIStatusError` subclasses and both map to `ProviderUnavailable`.
- The SDK does not validate a 200's body. If the body is an HTML page, such as an intercepting proxy's sign-in page, the SDK hands it to `parse`'s post-parser as a `str`, and `parse` raises `AttributeError` (`'str' object has no attribute 'content'`). JSON of another shape raises `TypeError` there. Neither is an SDK error, so the adapter catches them as well, and a 200 that is not a message becomes `ProviderUnavailable`.
- The SDK obeys a `retry-after-ms` header, so the tests' error responses carry `retry-after-ms: 1`, and polish's one retry does not sleep the half-second backoff.

**Two departures from the skeleton, both flagged in the code:**
- **Effort is sent only where the model takes it.** Claude Haiku 4.5 answers `output_config.effort` with a 400. Anthropic's model reference lists effort for the Opus line from 4.5 and the Sonnet line from 4.6, and marks it an error on Haiku 4.5. With the skeleton's unconditional `{"effort": "low"}`, every polish on Haiku would come back as `ProviderUnavailable`, answered 502 "Couldn't reach Anthropic". `EFFORT_MODELS` names the two models that take it. For Haiku the call leaves `output_config` out, and the SDK still sends `output_config.format`.
- **`httpx2` is declared directly.** `providers.py` and `conftest.py` both import it. It arrives with `anthropic` anyway, and is declared for the same reason the header gives for `cryptography`: the app now imports it.

**`httpx2` changes the whole suite's HTTP client.** `starlette/testclient.py` (Starlette 1.6.0) tries `import httpx2 as httpx` first. Only when that fails does it fall back to `httpx`, with the `StarletteDeprecationWarning` "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." That warning is in the suite's warnings summary today. Once Step 1 installs `httpx2`, every `TestClient` in the suite runs on it: every API test, and every sign-in fixture's cookies. Step 8 therefore runs the full backend suite, not only this task's files.

**Files:**
- Create: `backend/app/llm/providers.py`, `backend/tests/test_anthropic_provider.py`
- Modify:
  - `backend/tests/conftest.py` (two imports and the autouse `no_llm_network` guard)
  - `backend/pyproject.toml` and `backend/uv.lock` (`uv add`)
- Test: `backend/tests/test_anthropic_provider.py`

Run every command from `backend/`.

**Interfaces:**
- Consumes: Task 1's package `app/llm/__init__.py`. Nothing else in the app. This module imports no model, no settings and no database code.
- Produces (`app/llm/providers.py`):
```python
MODELS: tuple[str, ...] = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
DEFAULT_MODEL = "claude-opus-5"
MODEL_LABELS: Mapping[str, str]           # model id -> "Claude Opus 5", "Claude Sonnet 5", "Claude Haiku 4.5"
EFFORT_MODELS: frozenset[str] = frozenset({"claude-opus-5", "claude-sonnet-5"})   # beyond the skeleton
FALLBACK_MODELS: frozenset[str] = frozenset({"claude-opus-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
BASE_URL = "https://api.anthropic.com"
PROMPT_VERSION = 1                        # Task 5 hashes it into every cached description
SYSTEM_PROMPT: str                        # the ten lines below, verbatim

class ProviderError(Exception)            # raised with no arguments: str(exc) == ""
class KeyRejected(ProviderError)          # 401, 403
class ModelUnavailable(ProviderError)     # 404
class NoCredit(ProviderError)             # 402
class ProviderUnavailable(ProviderError)  # connection, timeout, 429, >= 500, any other status

@dataclass(frozen=True)
class DishBrief:
    ref: str                              # "d1", "d2", ... per call
    name: str
    ingredients: tuple[str, ...]          # ingredient names, sorted by the caller

@dataclass(frozen=True)
class DishText:
    description: str
    cooking_note: str | None

class Provider(Protocol):
    def check_key(self, api_key: str, model: str) -> None: ...
    def polish(self, api_key: str, model: str, dishes: Sequence[DishBrief]) -> dict[str, DishText]: ...

class PolishBatch(BaseModel)              # {"dishes": [{"ref", "description", "cooking_note"}]}, extra="forbid"
                                          # no docstring: pydantic would send it to the model

class AnthropicProvider:
    def __init__(self, http_client: httpx2.Client | None = None) -> None
    def check_key(self, api_key: str, model: str) -> None
        # models.retrieve(model); timeout 10.0, max_retries 0; raises a ProviderError
    def polish(self, api_key: str, model: str, dishes: Sequence[DishBrief]) -> dict[str, DishText]
        # timeout 120.0, max_retries 1. {} for an empty batch (no request), a refusal, a
        # max_tokens stop, no text, or text that does not parse. Otherwise every returned
        # ref, unfiltered, including refs that were never sent. Raises a ProviderError:
        # ProviderUnavailable also for a 200 whose body is not a message (an HTML page).
    # Both raise ValueError("empty API key") for "" before any client or request exists.

def get_provider() -> Provider             # FastAPI dependency: AnthropicProvider()
```
- For Task 4 and Task 5:
  - Each `ProviderError` is raised with no arguments, so `str(exc) == ""`. `FakeProvider.error` can be set to any of the four subclasses, for example `KeyRejected()`.
  - After this task, `tests/conftest.py` already imports `httpx2` and `from app.llm import providers`.
  - The `no_llm_network` fixture is function-scoped and autouse. It needs nothing from the tests. Its value is the list of requests its transport refused, which only this task's self-check reads.
  - From Step 1 on, `httpx2` is installed, so Starlette's `TestClient` runs on `httpx2` everywhere in the suite, not on `httpx`.
- For Task 8: `test_anthropic_provider.py` reads the adapter's warnings through `caplog`, whose handler sits on the root logger. `_configure_logging` may add a handler to the `app` logger and set its level, but it must not set `propagate = False` on it. That would hide these records from `caplog`.

- [ ] **Step 1: Add the SDK**

First, note the suite's size before anything changes. Collecting opens no database connection.

Run: `uv run pytest --collect-only -q | tail -8`

Expected: the last line is `N tests collected in …`. Write N down, because Step 8 checks the full run against it. The warnings summary just above that line lists the `StarletteDeprecationWarning` "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead."

Run: `uv add 'anthropic>=1.8,<2' 'httpx2>=2.13,<3'`

Expected:
- `pyproject.toml`'s `dependencies` gains `"anthropic>=1.8,<2"` and `"httpx2>=2.13,<3"`.
- `uv.lock` gains `anthropic`, `httpx2`, `httpcore2`, `httpx2-jsfetch`, `jiter`, `docstring-parser`, `sniffio` and `truststore`. When this plan was written that meant `anthropic` 1.8.0 and `httpx2` 2.13.1. `pydantic` stays at the locked 2.13.4.

Run: `uv run python -c "import anthropic, httpx2; print(anthropic.__version__, httpx2.__version__)"`

Expected: `1.8.0 2.13.1`. A later 1.x and 2.x is fine, because the tests below pin every SDK behaviour this task relies on.

Run: `uv run pytest --collect-only -q | tail -8`

Expected: the same `N tests collected`, and no `StarletteDeprecationWarning` above it. Starlette's `TestClient` now imports `httpx2`, so from here on every API test in the suite runs on it. Step 8 runs the whole suite to show that nothing else changed.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_anthropic_provider.py`:

```python
"""The Anthropic adapter, run on the real SDK with a mock transport.

No request leaves the process. Each provider here gets an httpx2 client whose transport
records the request and answers it in Anthropic's wire format, so these tests see exactly what
the SDK would send: the headers, the path and the JSON body.

The key is a secret. It must reach Anthropic's host in the x-api-key header and nowhere else:
not in a log line, not in an exception, not at a host an environment variable names. That
includes these tests' own failure output. pytest prints both sides of a failed comparison,
so the key is only ever compared inside a helper that returns a bool.
"""

import json
from collections.abc import Callable

import httpx2
import pytest

from app.llm import providers
from app.llm.providers import (
    DEFAULT_MODEL,
    EFFORT_MODELS,
    FALLBACK_BETA,
    FALLBACK_MODELS,
    MODEL_LABELS,
    MODELS,
    SYSTEM_PROMPT,
    AnthropicProvider,
    DishBrief,
    DishText,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    ProviderUnavailable,
)

KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
# What every error body's message says. Anthropic's own messages can quote the request, so
# none of this may reach a log line or a ProviderError.
PROVIDER_MESSAGE = "provider-text-that-may-quote-the-request"

BRIEFS = (
    DishBrief(ref="d1", name="Idli", ingredients=("Black gram, dal", "Rice, parboiled, milled")),
    DishBrief(ref="d2", name="Mor kuzhambu", ingredients=("Curd", "Tamarind, pulp")),
)
OUTPUT = {
    "dishes": [
        {
            "ref": "d1",
            "description": "Soft steamed cakes of rice and black gram, mild and fluffy.",
            "cooking_note": "Let the batter ferment overnight somewhere warm.",
        },
        {
            "ref": "d2",
            "description": "A tangy curd curry, gently spiced and cooling.",
            "cooking_note": None,
        },
    ]
}
MODEL_INFO = {
    "type": "model",
    "id": "claude-opus-5",
    "display_name": "Claude Opus 5",
    "created_at": "2026-01-01T00:00:00Z",
}


class AnthropicStub:
    """A stand-in for api.anthropic.com: records every request, answers with `respond`."""

    def __init__(self, respond: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.respond(request)

    def provider(self) -> AnthropicProvider:
        return AnthropicProvider(http_client=httpx2.Client(transport=httpx2.MockTransport(self)))

    @property
    def request(self) -> httpx2.Request:
        assert len(self.requests) == 1, f"expected one request, got {len(self.requests)}"
        return self.requests[0]

    @property
    def body(self) -> dict:
        return json.loads(self.request.content)


def answering(response: httpx2.Response) -> AnthropicStub:
    return AnthropicStub(lambda request: response)


def message(stop_reason: str = "end_turn", text: str | None = None) -> httpx2.Response:
    """A Messages API answer with at most one text block."""
    content = [] if text is None else [{"type": "text", "text": text}]
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 120, "output_tokens": 80},
        },
    )


def error(status: int, kind: str) -> httpx2.Response:
    # retry-after-ms: the SDK honours it, so polish's one retry of a 429 or a 5xx waits a
    # millisecond instead of its half-second backoff.
    return httpx2.Response(
        status,
        headers={"retry-after-ms": "1"},
        json={"type": "error", "error": {"type": kind, "message": PROVIDER_MESSAGE}},
    )


def call(provider: AnthropicProvider, which: str, *, key: str = KEY):
    """Make one of the adapter's two calls, with the default model."""
    if which == "check_key":
        return provider.check_key(key, DEFAULT_MODEL)
    return provider.polish(key, DEFAULT_MODEL, BRIEFS)


def sends_the_key(request: httpx2.Request) -> bool:
    return request.headers.get("x-api-key") == KEY


def has_header(request: httpx2.Request, name: str) -> bool:
    return name in request.headers


def betas_sent(request: httpx2.Request) -> list[str]:
    return request.headers.get("anthropic-beta", "").split(",")


def key_logged(caplog) -> bool:
    return KEY in caplog.text


def provider_message_logged(caplog) -> bool:
    return PROVIDER_MESSAGE in caplog.text


def adapter_log(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == providers.__name__]


# --- the models on offer -----------------------------------------------------


def test_the_default_model_is_listed_first_and_every_model_has_a_label():
    assert MODELS[0] == DEFAULT_MODEL == "claude-opus-5"
    assert set(MODEL_LABELS) == set(MODELS)
    assert FALLBACK_MODELS <= set(MODELS)
    assert EFFORT_MODELS <= set(MODELS)


def test_the_system_prompt_is_ten_clean_lines():
    lines = SYSTEM_PROMPT.split("\n")

    assert len(lines) == 10
    assert all(line and line == line.strip() for line in lines)
    assert lines[6].startswith("- Never mention amounts, portions, weights")


# --- checking a key ----------------------------------------------------------


def test_a_key_is_checked_by_looking_the_model_up():
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))

    anthropic.provider().check_key(KEY, "claude-sonnet-5")

    request = anthropic.request
    assert request.method == "GET"
    assert str(request.url) == "https://api.anthropic.com/v1/models/claude-sonnet-5"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert request.content == b""
    assert request.extensions["timeout"]["read"] == 10.0


def test_a_key_check_is_not_retried():
    anthropic = answering(error(500, "api_error"))

    with pytest.raises(ProviderUnavailable):
        anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    assert len(anthropic.requests) == 1


def test_the_key_goes_to_anthropic_whatever_the_environment_says(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://llm-proxy.example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-" + "e" * 40 + "ENVK")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "environment-token")
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))

    anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    request = anthropic.request
    assert request.url.host == "api.anthropic.com"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert not has_header(request, "authorization")


# --- polishing a batch -------------------------------------------------------


def test_polish_is_one_structured_call_at_low_effort():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, "claude-opus-5", BRIEFS)

    request, body = anthropic.request, anthropic.body
    assert request.method == "POST"
    assert request.url.host == "api.anthropic.com"
    assert request.url.path == "/v1/messages"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert request.extensions["timeout"]["read"] == 120.0
    # Exactly these fields: no temperature or top_p, which the current models reject, and
    # no stream or thinking settings.
    assert set(body) == {
        "model",
        "max_tokens",
        "system",
        "messages",
        "output_config",
        "fallbacks",
    }
    assert body["model"] == "claude-opus-5"
    assert body["max_tokens"] == 8000
    assert body["system"] == SYSTEM_PROMPT
    assert body["output_config"]["effort"] == "low"
    output_format = body["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    schema = output_format["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["dishes"]
    # The schema is prompt too, and pydantic sends a class docstring as an object's
    # "description". No implementation note may reach the model that way.
    assert "description" not in schema
    assert all("description" not in definition for definition in schema["$defs"].values())


def test_claude_opus_5_is_sent_with_the_refusal_fallback():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, "claude-opus-5", BRIEFS)

    assert anthropic.body["fallbacks"] == "default"
    assert FALLBACK_BETA in betas_sent(anthropic.request)


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-haiku-4-5"])
def test_the_other_models_are_sent_without_it(model):
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, model, BRIEFS)

    assert anthropic.body["model"] == model
    assert "fallbacks" not in anthropic.body
    # The SDK sends a beta header of its own for structured outputs; the fallback's is absent.
    assert FALLBACK_BETA not in betas_sent(anthropic.request)


@pytest.mark.parametrize(
    ("model", "effort"),
    [("claude-opus-5", "low"), ("claude-sonnet-5", "low"), ("claude-haiku-4-5", None)],
)
def test_effort_is_sent_only_to_the_models_that_take_it(model, effort):
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, model, BRIEFS)

    output_config = anthropic.body["output_config"]
    assert output_config.get("effort") == effort
    assert output_config["format"]["type"] == "json_schema"


def test_the_model_sees_only_references_names_and_ingredient_names():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    messages = anthropic.body["messages"]
    assert [item["role"] for item in messages] == ["user"]
    assert json.loads(messages[0]["content"]) == {
        "dishes": [
            {
                "ref": "d1",
                "name": "Idli",
                "ingredients": ["Black gram, dal", "Rice, parboiled, milled"],
            },
            {"ref": "d2", "name": "Mor kuzhambu", "ingredients": ["Curd", "Tamarind, pulp"]},
        ]
    }


def test_names_go_out_as_written_not_escaped():
    anthropic = answering(message(text=json.dumps({"dishes": []})))
    brief = DishBrief(ref="d1", name="Pongal — ven", ingredients=("Rice, raw, milled",))

    anthropic.provider().polish(KEY, DEFAULT_MODEL, [brief])

    assert "Pongal — ven" in anthropic.body["messages"][0]["content"]


def test_polish_returns_each_dishs_text_by_reference():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    texts = anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert texts == {
        "d1": DishText(
            description="Soft steamed cakes of rice and black gram, mild and fluffy.",
            cooking_note="Let the batter ferment overnight somewhere warm.",
        ),
        "d2": DishText(
            description="A tangy curd curry, gently spiced and cooling.", cooking_note=None
        ),
    }


def test_polish_passes_the_text_through_unfiltered():
    """The guard belongs to app.planner.polish, which also drops references it never sent."""
    output = {
        "dishes": [{"ref": "d9", "description": "Serves 2, at 300 kcal.", "cooking_note": None}]
    }
    anthropic = answering(message(text=json.dumps(output)))

    texts = anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert texts == {"d9": DishText(description="Serves 2, at 300 kcal.", cooking_note=None)}


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(message("refusal"), id="refused-before-any-output"),
        pytest.param(message("refusal", '{"dishes": [{"ref": "d1", "desc'), id="refused-partway"),
        pytest.param(message("max_tokens", '{"dishes": [{"ref": "d1", "desc'), id="cut-off"),
        # The stop reason is read before the content: neither a refusal nor a cut-off answer
        # is an answer, even when its text parses.
        pytest.param(message("refusal", json.dumps(OUTPUT)), id="refused-but-it-parses"),
        pytest.param(message("max_tokens", json.dumps(OUTPUT)), id="cut-off-but-it-parses"),
        pytest.param(message("end_turn"), id="no-text-at-all"),
    ],
)
def test_a_refusal_or_a_cut_off_answer_yields_no_text(response):
    anthropic = answering(response)

    assert anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS) == {}


def test_an_empty_batch_is_not_sent():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    assert anthropic.provider().polish(KEY, DEFAULT_MODEL, []) == {}
    assert anthropic.requests == []


def test_polish_retries_once_then_gives_up():
    anthropic = answering(error(529, "overloaded_error"))

    with pytest.raises(ProviderUnavailable):
        anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert len(anthropic.requests) == 2


# --- failures ----------------------------------------------------------------


@pytest.mark.parametrize("which", ["check_key", "polish"])
@pytest.mark.parametrize(
    ("status", "kind", "expected"),
    [
        (401, "authentication_error", KeyRejected),
        (403, "permission_error", KeyRejected),
        (404, "not_found_error", ModelUnavailable),
        (402, "billing_error", NoCredit),
        (400, "invalid_request_error", ProviderUnavailable),
        (429, "rate_limit_error", ProviderUnavailable),
        (500, "api_error", ProviderUnavailable),
        (529, "overloaded_error", ProviderUnavailable),
    ],
)
def test_each_status_becomes_its_provider_error(which, status, kind, expected):
    anthropic = answering(error(status, kind))

    with pytest.raises(expected):
        call(anthropic.provider(), which)


def connection_refused(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


def timed_out(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize("which", ["check_key", "polish"])
@pytest.mark.parametrize("failure", [connection_refused, timed_out])
def test_an_unreachable_anthropic_is_unavailable(which, failure):
    anthropic = AnthropicStub(failure)

    with pytest.raises(ProviderUnavailable):
        call(anthropic.provider(), which)


@pytest.mark.parametrize("which", ["check_key", "polish"])
def test_an_empty_key_is_refused_before_any_request(which):
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))
    provider = anthropic.provider()

    with pytest.raises(ValueError, match="empty API key"):
        call(provider, which, key="")

    assert anthropic.requests == []


def test_a_failure_is_logged_by_error_class_and_status_only(caplog):
    anthropic = answering(error(401, "authentication_error"))

    with pytest.raises(KeyRejected) as raised:
        anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    assert adapter_log(caplog) == ["anthropic call failed: AuthenticationError (status 401)"]
    assert not key_logged(caplog), "the key reached a log line"
    assert not provider_message_logged(caplog), "the provider's message reached a log line"
    # Nothing of the SDK's error rides along: no message, and no exception shown as its cause.
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_a_connection_failure_is_logged_without_a_status(caplog):
    with pytest.raises(ProviderUnavailable):
        AnthropicStub(connection_refused).provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert adapter_log(caplog) == ["anthropic call failed: APIConnectionError (status None)"]
    assert not key_logged(caplog), "the key reached a log line"


def test_a_200_that_is_not_a_message_is_unavailable(caplog):
    """An intercepting proxy's sign-in page, say. The SDK does not validate a 200's body."""
    page = f"<html><body><p>Sign in to continue. {PROVIDER_MESSAGE}</p></body></html>"
    anthropic = answering(httpx2.Response(200, headers={"content-type": "text/html"}, text=page))

    with pytest.raises(ProviderUnavailable) as raised:
        anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert len(anthropic.requests) == 1
    assert adapter_log(caplog) == ["anthropic call failed: AttributeError (unreadable answer)"]
    assert not provider_message_logged(caplog), "the page reached a log line"
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


# --- the no-network guard ----------------------------------------------------


def test_a_provider_built_without_a_client_never_reaches_the_network(no_llm_network, monkeypatch):
    """conftest's no_llm_network guard: the client the SDK would build refuses every request.

    Two things keep this self-check off the network when it fails. It asks for the guard by
    name, so without the guard pytest stops at setup and the check_key below never runs. And
    every proxy variable points at a closed local port, so an adapter that skipped
    _default_http_client, letting the SDK build a client of its own, is refused on this
    machine. Then the guard saw no request, and the last assertion says so. Both cases are
    set, because a lowercase variable beats its uppercase twin, and NO_PROXY is cleared,
    because it would route the request around the proxy.
    """
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:1")

    with pytest.raises(ProviderUnavailable):
        AnthropicProvider().check_key(KEY, DEFAULT_MODEL)

    # The guard's transport refused the one request: the adapter used _default_http_client.
    assert [request.url.host for request in no_llm_network] == ["api.anthropic.com"]


def test_the_dependency_is_the_anthropic_adapter():
    assert isinstance(providers.get_provider(), AnthropicProvider)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_anthropic_provider.py -q`

Expected: a collection error, `ImportError: cannot import name 'providers' from 'app.llm'`, because the module does not exist yet.

- [ ] **Step 4: Write the adapter**

Create `app/llm/providers.py`:

```python
"""The model behind AI descriptions: a Provider protocol, and one adapter on the Anthropic SDK.

The adapter makes two calls, both with the user's own key:
- `check_key` looks the chosen model up (`GET /v1/models/{id}`) when a key is saved. The
  lookup spends no tokens.
- `polish` asks for a description and a cooking tip for each dish in a batch, in one
  structured-output call.

What goes out is only what `app.planner.polish` hands over: an opaque reference, a dish name
and ingredient names. What comes back is returned unfiltered, because `polish` owns the guard.

Every SDK error, and a 200 that is not a message, becomes one of four `ProviderError`s, which
carry nothing from the provider's message: that message can quote the request. The log line
names the error class and the status code, and never uses `str(exc)`.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

MODELS: tuple[str, ...] = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
DEFAULT_MODEL = "claude-opus-5"
MODEL_LABELS: Mapping[str, str] = {
    "claude-opus-5": "Claude Opus 5",
    "claude-sonnet-5": "Claude Sonnet 5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
}
# The models that take `output_config.effort`. Claude Haiku 4.5 answers a 400 to it.
EFFORT_MODELS: frozenset[str] = frozenset({"claude-opus-5", "claude-sonnet-5"})
# The models sent with Anthropic's server-side refusal fallback. Whether the other two accept
# `fallbacks="default"` is not verified, and a 400 there would break polish for their users.
FALLBACK_MODELS: frozenset[str] = frozenset({"claude-opus-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Pinned, so an ANTHROPIC_BASE_URL in the server's environment cannot send users' keys to
# another host.
BASE_URL = "https://api.anthropic.com"
# Part of every cached description's hash: bumping it re-describes every dish once.
PROMPT_VERSION = 1

# The system prompt, verbatim: ten lines. The output schema is prompt too: the model reads
# PolishBatch's and _DishOut's class names, field names and any docstring. Changing either
# means bumping PROMPT_VERSION, so every cached description is written again under the new
# rules.
SYSTEM_PROMPT = (
    "You write short, friendly descriptions of South Indian home-cooked dishes for a"
    " meal-planning app.\n"
    "Each dish comes with a reference, its name, and the names of its ingredients as a"
    ' food-composition table lists them (for example "Rice, parboiled, milled").\n'
    "For every reference, return:\n"
    "- description: one sentence of at most 25 words on what the dish is and how it"
    " tastes.\n"
    "- cooking_note: one practical tip of at most 30 words for cooking it at home, or null"
    " when you have nothing useful to add.\n"
    "Rules:\n"
    "- Never mention amounts, portions, weights, calories, nutrients, percentages or any"
    " number, in digits or in words.\n"
    "- Never give medical, dietary or health advice, and never suggest changing the dish or"
    " its ingredients.\n"
    "- Write plain English; regional dish names are fine.\n"
    "- Return every reference you were given exactly once, and no others."
)


class ProviderError(Exception):
    """A provider call failed. Carries nothing from the provider's message."""


class KeyRejected(ProviderError):
    """The provider refused the key (401 or 403)."""


class ModelUnavailable(ProviderError):
    """The key's account cannot use the model (404)."""


class NoCredit(ProviderError):
    """The key's account has no credit left (402)."""


class ProviderUnavailable(ProviderError):
    """No usable answer: connection, timeout, 429, 5xx, or any other status."""


@dataclass(frozen=True)
class DishBrief:
    """All the model is told about one dish."""

    ref: str  # an opaque reference for this call only: "d1", "d2", ...
    name: str
    ingredients: tuple[str, ...]  # ingredient names, sorted


@dataclass(frozen=True)
class DishText:
    """What the model wrote for one dish, before any guard."""

    description: str
    cooking_note: str | None


class Provider(Protocol):
    def check_key(self, api_key: str, model: str) -> None: ...

    def polish(
        self, api_key: str, model: str, dishes: Sequence[DishBrief]
    ) -> dict[str, DishText]: ...


# The structured output polish asks for. The SDK sends these two classes to the model as a
# JSON schema, and pydantic would put a class docstring into it as the object's
# "description". So their notes are comments, and changing the classes means bumping
# PROMPT_VERSION. `extra="forbid"` puts `additionalProperties: false` on every object,
# which structured outputs require.
class _DishOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    description: str
    cooking_note: str | None


class PolishBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dishes: list[_DishOut]


def _default_http_client() -> httpx2.Client | None:
    """The HTTP client for a provider built without one: None, so the SDK builds its own.

    `tests/conftest.py` replaces this with a client that refuses every request, so no test
    can reach the network.
    """
    return None


class AnthropicProvider:
    """The Provider on the official SDK.

    A new SDK client per call, because every call carries its own user's key. `http_client`
    is for tests, which hand the SDK a mock transport.
    """

    def __init__(self, http_client: httpx2.Client | None = None) -> None:
        self._http_client = http_client

    def _client(self, api_key: str, *, timeout: float, max_retries: int) -> anthropic.Anthropic:
        # The SDK would send an empty key as an empty x-api-key header.
        if not api_key:
            raise ValueError("empty API key")
        http_client = self._http_client
        if http_client is None:
            http_client = _default_http_client()
        # An explicit api_key stops the SDK reading ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN
        # from the environment, and the explicit base_url beats ANTHROPIC_BASE_URL. With
        # http_client None, the SDK builds its own, which it closes when it is collected.
        return anthropic.Anthropic(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    def check_key(self, api_key: str, model: str) -> None:
        """Raise unless this key can use this model. Spends no tokens."""
        # No retry: the user is waiting on the save, and a failed check saves nothing.
        client = self._client(api_key, timeout=10.0, max_retries=0)
        try:
            client.models.retrieve(model)
        except anthropic.APIError as exc:
            raise _translate(exc) from None

    def polish(self, api_key: str, model: str, dishes: Sequence[DishBrief]) -> dict[str, DishText]:
        """Text per reference, unfiltered, or {} when the model refused or was cut off."""
        client = self._client(api_key, timeout=120.0, max_retries=1)
        if not dishes:
            return {}
        options: dict[str, Any] = {}
        if model in EFFORT_MODELS:
            options["output_config"] = {"effort": "low"}
        if model in FALLBACK_MODELS:
            # A policy decline is re-run server-side on the model Anthropic recommends for it,
            # billed at that model's rates. The AI descriptions screen says so.
            options["betas"] = [FALLBACK_BETA]
            options["fallbacks"] = "default"
        try:
            # Non-streaming, and no temperature or top_p: the current models reject both.
            message = client.beta.messages.parse(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _batch_json(dishes)}],
                output_format=PolishBatch,
                **options,
            )
            stop_reason = message.stop_reason
            parsed = message.parsed_output
        except anthropic.APIError as exc:
            raise _translate(exc) from None
        except ValidationError:
            # A response cut off at max_tokens, or declined partway, ends in partial JSON, and
            # parse raises on it before the stop reason can be read. Not an error: the dishes
            # stay undescribed. The exception is not logged, because it quotes the output.
            logger.info("anthropic polish returned no text: the output did not parse")
            return {}
        except (AttributeError, TypeError, KeyError) as exc:
            # A 200 whose body is not a message: an HTML page from a proxy in between, or JSON
            # of another shape. The SDK does not validate a 200's body, so parse fails reading
            # it. No usable answer, like a 5xx. Logged by class name only, because the
            # exception's message can quote the body.
            logger.warning("anthropic call failed: %s (unreadable answer)", type(exc).__name__)
            raise ProviderUnavailable() from None
        # Stop reasons first: a refusal's or a cut-off's text is not an answer, even when it
        # happens to parse.
        if stop_reason in ("refusal", "max_tokens") or parsed is None:
            logger.info("anthropic polish returned no text: stop reason %s", stop_reason)
            return {}
        return {
            dish.ref: DishText(description=dish.description, cooking_note=dish.cooking_note)
            for dish in parsed.dishes
        }


def _batch_json(dishes: Sequence[DishBrief]) -> str:
    """The user message: each dish's reference, name and ingredient names, and nothing else."""
    return json.dumps(
        {
            "dishes": [
                {"ref": dish.ref, "name": dish.name, "ingredients": list(dish.ingredients)}
                for dish in dishes
            ]
        },
        ensure_ascii=False,
    )


def _translate(exc: anthropic.APIError) -> ProviderError:
    """The ProviderError for an SDK error, logged by class name and status code only.

    The caller raises it `from None`, so the SDK's error, whose message is the provider's own
    text and can quote the request, is not chained into the traceback either.
    """
    status = getattr(exc, "status_code", None)
    logger.warning("anthropic call failed: %s (status %s)", type(exc).__name__, status)
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return KeyRejected()
    if isinstance(exc, anthropic.NotFoundError):
        return ModelUnavailable()
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 402:
        return NoCredit()
    # Any other status (400, 408, 409, 413, 422, 429, 5xx), a connection error or a timeout.
    return ProviderUnavailable()


def get_provider() -> Provider:
    """The FastAPI dependency. API tests override it with conftest's FakeProvider."""
    return AnthropicProvider()
```

Why the code looks the way it does, where the reason is not obvious:
- **A new SDK client per call.** Each call carries its own user's key. When `http_client` is `None`, the SDK builds an `httpx2` client wrapped in its own `SyncHttpxClientWrapper`, which closes itself when it is garbage-collected (`anthropic/_base_client.py`). The adapter therefore never closes a client, and never closes one a test handed it.
- **`options` is built as a dict.** It holds only the fields a model takes: `output_config` for the two effort models, and `betas` plus `fallbacks` for Claude Opus 5. For Haiku, `output_config` is absent, and `parse` still fills in `output_config.format` from `output_format`.
- **`except anthropic.APIError`** covers `APIStatusError` and all its subclasses, `APIConnectionError` and `APITimeoutError`, and `APIResponseValidationError`. `_translate` maps anything that is not 401, 403, 404 or 402 to `ProviderUnavailable`.
- **`except (AttributeError, TypeError, KeyError)`** is for a 200 that is not a message. The SDK hands `parse`'s post-parser an HTML body as a `str`, and JSON of another shape as a half-built message, and the post-parser fails reading it. Reading `stop_reason` and `parsed_output` sits inside the same `try`. Without the catch, Task 5's endpoint would answer 500 instead of its 502. The same catch would also take a `TypeError` from the call itself, for example after an SDK upgrade renames a parameter. The happy-path tests would then fail on `ProviderUnavailable`, and the log line would name the class, so the break still shows.
- **`check_key` does not read the answer.** Any 200 counts as a good key, because checking the returned id against the model asked for would reject good keys: a lookup by alias can answer with the model's canonical id.
- **The two `logger.info` lines** name a stop reason or a parse failure, and never any text. An operator whose users see no descriptions can find why in the log.
- **No docstring on `PolishBatch` or `_DishOut`.** pydantic sends a class docstring as the schema's `description`, and the SDK sends the schema with every polish call, so a docstring would be read by the model. `test_polish_is_one_structured_call_at_low_effort` asserts the schema has none.

- [ ] **Step 5: Run the tests again**

Run: `uv run pytest tests/test_anthropic_provider.py -q`

Expected: `50 passed, 1 error`. The error is `test_a_provider_built_without_a_client_never_reaches_the_network`, at setup:

```
E       fixture 'no_llm_network' not found
```

That test asks for the guard by name, so without the guard pytest never runs its body. The `check_key` in it, which would go out to the real API, never runs.

- [ ] **Step 6: Add the no-network guard**

In `tests/conftest.py`:
- Add `import httpx2` directly above `import pytest`.
- Add `from app.llm import providers` directly after `from app.config import settings`.
- Add this fixture directly below plan 8's `scheduler_off` fixture, which ends with the two lines `        patch.setattr(settings, "scheduler_enabled", False)` and `        yield`. That puts it directly above `@pytest.fixture(scope="session")` / `def engine():`.

```python
@pytest.fixture(autouse=True)
def no_llm_network(monkeypatch) -> list[httpx2.Request]:
    """Any AnthropicProvider built without an explicit client fails before reaching the network.

    A provider built without one asks `providers._default_http_client` for its HTTP client,
    and in production gets None, so the SDK builds a real one. Here it gets a client whose
    transport raises instead. The SDK reports that as a connection error, which the adapter
    turns into ProviderUnavailable, so a test that forgot its fake fails without a request
    ever leaving the machine. Adapter tests pass their own mock client and are unaffected.

    The value is the list of requests refused, which the adapter's self-check reads.
    """
    refused: list[httpx2.Request] = []

    def refuse(request: httpx2.Request) -> httpx2.Response:
        refused.append(request)
        raise RuntimeError("tests never reach a real LLM")

    monkeypatch.setattr(
        providers,
        "_default_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(refuse)),
    )
    return refused
```

The patch is function-scoped: `monkeypatch` undoes it after each test, so this module's `_default_http_client` is only ever replaced while a test runs. Every test gets its own `refused` list.

- [ ] **Step 7: Run the tests and the checks**

Run: `uv run pytest tests/test_anthropic_provider.py tests/test_health.py -q && uv run ruff check .`

Expected: `52 passed`, then `All checks passed!`.
- That is the 51 adapter tests and `test_health.py`'s one.
- `test_health.py` runs the app's lifespan through the `client` fixture. It shows the edited conftest still loads the app.
- The adapter tests take about two seconds. Three of them are polish calls whose transport raises instead of answering: a refused connection twice, and a timeout once. Each waits out one real half-second retry backoff, because a raised exception carries no `retry-after-ms` to shorten it.
- No test touches the database. None of this file's tests requests the `db` fixture.

- [ ] **Step 8: Run the full backend suite**

Step 1 moved every `TestClient` in the suite from `httpx` to `httpx2`, and Step 6's autouse guard now wraps every test. Only the whole suite shows that nothing else changed.

The suite takes about 11 minutes, longer than a ten-minute command timeout, so run it in the background and wait for it to finish. Colima and the test database must be up. Run nothing else against the test database meanwhile: no other pytest session, and no `alembic` command with the test database's URL.

Run, in the background: `uv run pytest -q > /tmp/task3-suite.log 2>&1; echo "exit $?" >> /tmp/task3-suite.log`

When it has finished, run: `tail -15 /tmp/task3-suite.log`

Expected:
- The last line is `exit 0`. Above it, pytest's summary line reads `M passed`, where M is Step 1's count N plus 51, the tests in `test_anthropic_provider.py`. On a Sunday it reads `M-1 passed, 1 skipped`, because `test_planner_api.py::test_logging_into_a_day_that_has_ended_does_not_replan_it` skips when the week has no past day. If the line also counts warnings, as in `M passed, 1 warning`, that is fine.
- The warnings summary no longer lists ``StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.`` Any other warning it listed before stays, such as `test_session_token.py`'s `InsecureKeyLengthWarning`.

If any test fails or errors, stop here and do not commit. Do not change the test, a fixture, the conftest or the dependency pins to make it pass. Report the failing test's name and its error, because it means `httpx2` or the guard changed something the suite relies on.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock app/llm/providers.py tests/conftest.py \
  tests/test_anthropic_provider.py
git commit -m "feat(backend): add the Anthropic provider behind AI descriptions

A Provider protocol with one adapter on the official anthropic SDK. It
makes two calls, each with the user's own key. check_key looks the chosen
model up, which spends no tokens. polish asks for a description and a
cooking tip per dish, in one structured-output call per batch.

Every client is built with the key, the base URL pinned to
api.anthropic.com, and an explicit timeout and retry count. So neither
ANTHROPIC_API_KEY nor ANTHROPIC_BASE_URL in the server's environment can
change which key is used or where it goes. The model sees a reference, a
dish name and ingredient names, and nothing else. Polish runs at low effort
where the model takes the setting; Claude Haiku 4.5 rejects it. Claude Opus
5 is sent with Anthropic's server-side refusal fallback.

A refusal, or an answer cut off at max_tokens, yields no text rather than
an error, even when its text parses. That includes the partial JSON on
which the SDK's parse raises before the stop reason can be read. Every SDK
error becomes one of four ProviderErrors that carry nothing from the
provider's message, which can quote the request. So does a 200 whose body
is not a message, such as a proxy's HTML page. The log line names only the
error class and the status. No docstring sits on the output schema's
classes, because pydantic would send it to the model.

conftest gains an autouse guard. A provider built without an explicit HTTP
client gets one that refuses every request, so no test can reach the
network. The guard's self-check also points the proxy variables at a
closed local port, so it stays off the network even if the adapter
bypasses the guard.

With httpx2 installed, Starlette's TestClient runs on it instead of
httpx, which retires the suite's StarletteDeprecationWarning. The full
backend suite passes on it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

---

## Task 4: Saving, checking and removing the key

This task puts the user's own Anthropic API key behind `GET`, `PUT` and `DELETE /settings/llm`. The key is write-only:
- `PUT` takes it in the JSON body, checks it with Anthropic's zero-token model lookup, and stores it encrypted in the user's `user_settings` row. Nothing is written until the check has passed, so a refused or unchecked key leaves any earlier key exactly as it was. A body that fails validation before the handler even runs is answered with one fixed sentence, because FastAPI's own 422 would quote the key back.
- `GET` never decrypts. It shows the provider, the model, the key's last four characters and a status, all read from plain columns beside the ciphertext. A stolen session cookie can therefore replace or remove a key, but never read one.
- `DELETE` nulls the six key columns. It works even on a server whose keyring is gone, so a user can always take their key back.

`app/llm/service.py` also holds `key_for`, the one place a key is ever decrypted, which Task 5's polish uses. A key that no longer decrypts is marked `unreadable` there rather than raising. `scripts/rotate_llm_keys.py` re-encrypts every stored key under the keyring's first key, so an old encryption key can be retired. Finally, the lifespan parses the keyring once, so a malformed `LLM_KEY_ENCRYPTION_KEYS` stops the app at boot instead of failing the first user who saves a key.

The test fixtures every later LLM test uses arrive here too: `FakeProvider`, which stands in for Anthropic and records what it was sent, the `fake_provider` fixture that installs it behind `get_provider`, and `llm_keyring`.

Run every command from `backend/`.

**Files:**
- Create: `backend/app/llm/service.py`, `backend/app/llm/router.py`, `backend/scripts/rotate_llm_keys.py`
- Modify:
  - `backend/app/main.py`: mount the router; parse the keyring in the lifespan; answer a failed request validation on `/settings/llm` without its input
  - `backend/tests/conftest.py`: `FakeProvider`, `llm_keyring`, `fake_provider`
- Test: `backend/tests/test_llm_settings_api.py` (create), `backend/tests/test_rotate_llm_keys.py` (create)

**Interfaces:**
- Consumes:
  - Task 1, `app/llm/crypto.py`: `NotConfigured`, `Unreadable`, `keyring()`, `available()`, `encrypt(api_key, *, user_id) -> str`, `decrypt(token, *, user_id) -> str`, `is_current(token) -> bool`, `rotate(token) -> str`; and `settings.llm_key_encryption_keys`. A malformed key in the keyring, whatever is wrong with it (a non-ASCII character included), makes `keyring()` raise `ValueError("LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key")`: Task 1's fixed message, not Fernet's own, and it quotes no part of the keyring.
  - Task 2, `app/models/llm.py`: `UserSettings` with `user_id`, `llm_provider`, `llm_model`, `llm_key_ciphertext`, `llm_key_hint`, `llm_key_status`, `llm_key_set_at`; the named unique constraint `uq_user_settings_user`, which the upsert targets; and the CHECK that keeps the six `llm_*` columns all set or all null.
  - Task 3, `app/llm/providers.py`: `MODELS`, `DEFAULT_MODEL`, `MODEL_LABELS`, `ProviderError`, `KeyRejected`, `ModelUnavailable`, `NoCredit`, `ProviderUnavailable` (each constructible with no arguments), `DishBrief`, `DishText`, `Provider`, `get_provider`; and the autouse `no_llm_network` guard in `tests/conftest.py`.
  - Plan 8's `app/main.py`: the `lifespan` context manager (Task 11) and the `settings_router` / `push_router` includes (Task 10). Plan 8's `settings_router` has the prefix `/settings` and only the route `/reminders`, so it does not collide with `/settings/llm`. Its `PATCH /settings/reminders` takes `ReminderIn {slot: str, reminder_on: bool}`, both required; a test sends it a body without `reminder_on` to show that other routes keep FastAPI's own 422.
  - FastAPI's `RequestValidationError` and its default handler, `fastapi.exception_handlers.request_validation_exception_handler(request, exc)` (async; answers 422 `{"detail": [<errors, each with its "input">]}`).
  - Existing: `get_current_user`, `get_db`, the `api_client` and `signed_in` fixtures, `tests.test_tracking_api.PROFILE`, `profiles.service.CHILD_MODELS`.
- Produces:
```python
# app/llm/service.py -- services flush, never commit
PROVIDER = "anthropic"
KEY_PATTERN = re.compile(r"^sk-ant-[A-Za-z0-9_-]+$")
FORMAT_MESSAGE = "That doesn't look like an Anthropic API key"
KEY_STATUSES = ("ok", "rejected", "unreadable")
class InvalidKeyFormat(ValueError)       # str(exc) is always FORMAT_MESSAGE
@dataclass(frozen=True)
class KeySummary:
    available: bool; provider: str | None; model: str | None; hint: str | None
    status: str                          # "none" | "ok" | "rejected" | "unreadable"
@dataclass(frozen=True)
class RotationCounts: rotated: int; current: int; unreadable: int
def normalise_key(raw: str) -> str       # strip; 20..300 chars; KEY_PATTERN; not sk-ant-admin
def summary(db, user) -> KeySummary      # never decrypts
def save_key(db, user, *, api_key: str, model: str, provider: Provider) -> KeySummary
    # NotConfigured before the provider is called; provider.check_key(api_key, model), whose
    # ProviderError propagates with nothing written; then encrypt + upsert, status "ok"
def delete_key(db, user) -> None         # nulls the six columns; no row -> no-op
def key_for(db, user) -> tuple[str, str] | None
    # (api_key, model). NotConfigured FIRST, before the row is read. None for no row, no
    # key, or status != "ok". A key that no longer decrypts: status "unreadable", flushed
    # (the CALLER commits it), None.
def mark_status(db, user, status: str) -> None   # ValueError for a status not in KEY_STATUSES;
                                                 # no key -> no-op
def rotate_all(db) -> RotationCounts     # locks the rows; current -> left; else rotated and
                                         # checked against its user; Unreadable -> marked

# app/llm/router.py
router = APIRouter(prefix="/settings/llm", tags=["settings"])
NOT_SET_UP = "AI descriptions are not set up on this server"
UNREACHABLE = "Couldn't reach Anthropic to check the key. Nothing was saved."
REFUSED = "Anthropic refused this key"
MODEL_MESSAGE = "Your Anthropic account can't use {label}"
UNKNOWN_MODEL = "Choose one of the listed models"
NOT_UNDERSTOOD = "The request was not understood"   # a body that failed validation
NO_STORE = "no-store"                               # Cache-Control on the handlers' answers and refusals
class LlmKeyIn(BaseModel): api_key: SecretStr; model: str = DEFAULT_MODEL
class LlmSettingsOut(BaseModel):
    available: bool; provider: Literal["anthropic"] | None; model: str | None
    key_hint: str | None; status: Literal["none", "ok", "rejected", "unreadable"]
    models: list[str]

# app/main.py
@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse
    # path under "/settings/llm": 422 {"detail": NOT_UNDERSTOOD}, Cache-Control: no-store,
    # nothing of the submitted input. Any other path: FastAPI's own
    # request_validation_exception_handler(request, exc), unchanged.

# scripts/rotate_llm_keys.py
def main() -> int     # 1 with no keyring (no session opened); else rotates, commits, prints
                      # "rotated N, current M, unreadable K" and returns 0

# tests/conftest.py
class FakeProvider:
    checked: list[tuple[str, str]]                              # (api_key, model)
    polished: list[tuple[str, str, tuple[DishBrief, ...]]]      # (api_key, model, briefs)
    texts: dict[str, DishText] | None   # None: DishText(f"A home-style {brief.name}.", None) per ref
    error: ProviderError | None         # raised by both methods, after the call is recorded
@pytest.fixture
def llm_keyring(monkeypatch) -> str     # a fresh one-key keyring; returns that Fernet key
@pytest.fixture
def fake_provider(api_client) -> Iterator[FakeProvider]   # installed behind get_provider
```

The HTTP contract, which Task 6 builds the screen on. Every route answers 401 without a session (a `PUT` body that is not even valid JSON is refused before the session is read, with 422 `NOT_UNDERSTOOD`), and needs no profile. `Cache-Control: no-store` is on every answer and every refusal the three handlers give, and on the validation handler's 422 `NOT_UNDERSTOOD`. The 401 does not carry it: it comes from the shared `get_current_user` dependency before any of this task's code runs, and its body is the fixed `{"detail": "Not signed in"}`, with nothing of the request and no key. An error's body is `{"detail": "<message>"}`, a string, never FastAPI's usual list.

| Method and path | Body | Answer |
|---|---|---|
| `GET /settings/llm` | none | 200 `LlmSettingsOut` |
| `PUT /settings/llm` | `{api_key, model?}` | 200 `LlmSettingsOut`. A body FastAPI itself cannot validate (not JSON, `api_key` missing or not a string) is 422 `NOT_UNDERSTOOD`, before the handler runs. Then 422 `UNKNOWN_MODEL`, 422 `FORMAT_MESSAGE` and 503 `NOT_SET_UP`, checked in that order before Anthropic is asked. Then 422 `REFUSED` (KeyRejected), 422 `MODEL_MESSAGE` with the model's label (ModelUnavailable), or 503 `UNREACHABLE` (any other ProviderError). Nothing is written on any of them. |
| `DELETE /settings/llm` | none | 204, also when there is no key, and also on a server with no keyring (`available: false`), which can still hold a key saved before its keyring went. The screen should therefore offer removal whenever `status` is not `"none"`, whatever `available` says. |

```
LlmSettingsOut {
  available: bool                         # false: this server has no keyring
  provider: "anthropic" | null
  model: str | null                       # one of `models`
  key_hint: str | null                    # the key's last four characters
  status: "none" | "ok" | "rejected" | "unreadable"
  models: ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]   # default first, always
}
```

- [ ] **Step 1: Write the failing tests**

First, the fixtures, in `tests/conftest.py`. Add three imports:
- `from collections.abc import Iterator, Sequence` as the first line of the file, above `from pathlib import Path`;
- `from cryptography.fernet import Fernet` directly below `from alembic.script import ScriptDirectory`;
- `from app.llm.providers import DishBrief, DishText, ProviderError, get_provider` directly below the `from app.llm import providers` line that Task 3 added.

With Task 3's `httpx2` and `providers` imports, the top of the file then reads as below. If Task 3 imported any of these names already, merge rather than repeat them.

```python
from collections.abc import Iterator, Sequence
from pathlib import Path

import httpx2
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from app.auth import google as google_auth
from app.config import settings
from app.llm import providers
from app.llm.providers import DishBrief, DishText, ProviderError, get_provider
from app.main import app
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
```

Then append to the end of the file, after the `signed_in` fixture:

```python


class FakeProvider:
    """Stands in for Anthropic: records every call, returns `texts`, raises `error` when set.

    Both methods record the call before raising, so a test can check what was sent even
    when the call failed.
    """

    def __init__(self) -> None:
        self.checked: list[tuple[str, str]] = []  # (api_key, model)
        self.polished: list[tuple[str, str, tuple[DishBrief, ...]]] = []
        self.texts: dict[str, DishText] | None = None  # None: a default text per ref
        self.error: ProviderError | None = None

    def check_key(self, api_key: str, model: str) -> None:
        self.checked.append((api_key, model))
        if self.error is not None:
            raise self.error

    def polish(
        self, api_key: str, model: str, dishes: Sequence[DishBrief]
    ) -> dict[str, DishText]:
        self.polished.append((api_key, model, tuple(dishes)))
        if self.error is not None:
            raise self.error
        if self.texts is not None:
            return dict(self.texts)
        # No digits and no number or nutrient words, so the planner's guard keeps it.
        return {brief.ref: DishText(f"A home-style {brief.name}.", None) for brief in dishes}


@pytest.fixture
def llm_keyring(monkeypatch) -> str:
    """AI descriptions switched on, under a fresh one-key keyring. Returns that key.

    Set explicitly, as the VAPID keys are: a developer's .env may carry a real keyring,
    and nothing in the suite may encrypt under it.
    """
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "llm_key_encryption_keys", key)
    return key


@pytest.fixture
def fake_provider(api_client) -> Iterator[FakeProvider]:
    """The provider every request gets instead of Anthropic's."""
    fake = FakeProvider()
    app.dependency_overrides[get_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_provider, None)
```

`fake_provider` depends on `api_client`, so the override is installed on the same app the test's requests go to. `api_client`'s teardown clears every override anyway; the fixture removes its own first so it never depends on that. `llm_keyring` returns its key, so a test can put a newer key in front of it: `f"{new},{llm_keyring}"`.

Create `tests/test_llm_settings_api.py`:

```python
"""The user's own Anthropic API key, over HTTP: checked, stored encrypted, never returned.

PUT checks the key with the provider before anything is written, then stores it encrypted
and bound to its user. GET never decrypts and shows only the last four characters. Every
key here is an obvious fake, and no test reaches Anthropic: `fake_provider` stands in.
"""

import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.auth import google as google_auth
from app.config import settings
from app.llm import crypto, service
from app.llm.providers import KeyRejected, ModelUnavailable, NoCredit, ProviderUnavailable
from app.main import app
from app.models.llm import UserSettings
from app.models.user import User
from app.profiles import service as profiles
from tests.test_tracking_api import PROFILE

KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
OTHER_KEY = "sk-ant-api03-" + "y" * 40 + "ABCD"
# The frontend's model list, default first.
OFFERED = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
FORMAT_MESSAGE = "That doesn't look like an Anthropic API key"
# Task 1's answer to a malformed keyring: fixed, so no part of the keyring reaches a log.
MALFORMED_KEYRING = "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"


def put_key(client, api_key: str = KEY, model: str = "claude-opus-5"):
    return client.put("/settings/llm", json={"api_key": api_key, "model": model})


def read(client) -> dict:
    return client.get("/settings/llm").json()


def the_row(db, user: User) -> UserSettings | None:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one_or_none()


def sign_in_as(client, monkeypatch, sub: str, email: str) -> None:
    """Sign out, then in again as someone else, on the same client."""
    client.post("/auth/logout")
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": email,
        },
    )
    client.post("/auth/google", json={"credential": "t"})


@pytest.fixture
def me(signed_in, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def no_keyring(monkeypatch):
    """A server with AI descriptions off. Set explicitly: a developer's .env may have a keyring."""
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")


# --- reading ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "body"),
    [("GET", None), ("PUT", {"api_key": KEY, "model": "claude-opus-5"}), ("DELETE", None)],
)
def test_the_key_routes_need_a_session(api_client, method, body):
    response = api_client.request(method, "/settings/llm", json=body)

    assert response.status_code == 401
    # The shared auth dependency answers before any handler here runs, so this is the one
    # answer without no-store. Its body is fixed: nothing of the request, and no key.
    assert response.json() == {"detail": "Not signed in"}


def test_before_any_key_there_is_nothing_to_show(signed_in, llm_keyring):
    response = signed_in.get("/settings/llm")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "provider": None,
        "model": None,
        "key_hint": None,
        "status": "none",
        "models": OFFERED,
    }


def test_without_a_keyring_the_feature_is_off(signed_in, no_keyring, fake_provider, db, me):
    assert read(signed_in) == {
        "available": False,
        "provider": None,
        "model": None,
        "key_hint": None,
        "status": "none",
        "models": OFFERED,
    }

    response = put_key(signed_in)

    assert response.status_code == 503
    assert response.json() == {"detail": "AI descriptions are not set up on this server"}
    # A key this server cannot store is never sent to Anthropic.
    assert fake_provider.checked == []
    assert the_row(db, me) is None


# --- saving ----------------------------------------------------------------------------


def test_a_key_is_checked_then_stored_encrypted(signed_in, llm_keyring, fake_provider, db, me):
    response = put_key(signed_in, model="claude-sonnet-5")

    assert response.status_code == 200
    # Exactly these six fields: nothing that is, or could be turned back into, the key.
    assert response.json() == {
        "available": True,
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "key_hint": "WXYZ",
        "status": "ok",
        "models": OFFERED,
    }
    assert KEY not in response.text
    assert fake_provider.checked == [(KEY, "claude-sonnet-5")]

    row = the_row(db, me)
    assert KEY not in row.llm_key_ciphertext
    assert "x" * 40 not in row.llm_key_ciphertext
    assert crypto.decrypt(row.llm_key_ciphertext, user_id=me.id) == KEY
    assert row.llm_key_set_at.tzinfo is not None
    # And a later GET shows what the PUT answered.
    assert read(signed_in) == response.json()


def test_the_plain_key_never_reaches_the_database(signed_in, llm_keyring, fake_provider, db):
    sent: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        sent.append(f"{statement} {parameters!r}")

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        assert put_key(signed_in).status_code == 200
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert any("user_settings" in line for line in sent)
    # Not the key, nor the 40 characters in the middle of it.
    assert not any("x" * 40 in line for line in sent)


def test_the_model_defaults_to_claude_opus_5(signed_in, llm_keyring, fake_provider):
    response = signed_in.put("/settings/llm", json={"api_key": KEY})

    assert response.status_code == 200
    assert response.json()["model"] == "claude-opus-5"
    assert fake_provider.checked == [(KEY, "claude-opus-5")]


def test_the_key_is_stripped_before_it_is_checked(signed_in, llm_keyring, fake_provider):
    response = put_key(signed_in, f"  {KEY}\n")

    assert response.status_code == 200
    assert response.json()["key_hint"] == "WXYZ"
    assert fake_provider.checked == [(KEY, "claude-opus-5")]


def test_a_new_key_replaces_the_old_one(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)
    service.mark_status(db, me, "rejected")
    # Held across the second save, so the old row is still in the session's identity map
    # when the upsert returns it. The answer must show what the upsert wrote over it.
    earlier = the_row(db, me)

    response = put_key(signed_in, OTHER_KEY, model="claude-haiku-4-5")

    assert response.status_code == 200
    body = response.json()
    assert (body["key_hint"], body["model"], body["status"]) == ("ABCD", "claude-haiku-4-5", "ok")
    assert (earlier.llm_key_hint, earlier.llm_key_status) == ("ABCD", "ok")
    rows = db.scalars(select(UserSettings).where(UserSettings.user_id == me.id)).all()
    assert len(rows) == 1
    assert service.key_for(db, me) == (OTHER_KEY, "claude-haiku-4-5")


@pytest.mark.parametrize(
    "api_key",
    [
        pytest.param("sk-ant-api03-" + "x" * 284 + "WXYZ", id="301-characters"),
        pytest.param("sk-proj-" + "x" * 40 + "WXYZ", id="not-sk-ant"),
        # An Admin API key manages a whole organisation: never one to hold.
        pytest.param("sk-ant-admin01-" + "x" * 40 + "WXYZ", id="admin-key"),
        pytest.param("sk-ant-api03-WXYZ", id="too-short"),
        pytest.param("sk-ant-api03-" + "x" * 20 + " " + "x" * 20, id="inner-space"),
    ],
)
def test_a_malformed_key_is_refused_without_echoing_it(
    signed_in, llm_keyring, fake_provider, db, me, api_key
):
    response = put_key(signed_in, api_key)

    assert response.status_code == 422
    assert response.json() == {"detail": FORMAT_MESSAGE}
    assert api_key not in response.text
    assert fake_provider.checked == []
    assert the_row(db, me) is None


@pytest.mark.parametrize(
    "sent",
    [
        # FastAPI's own 422 would quote the whole body back, key and all...
        pytest.param({"json": {"apiKey": KEY}}, id="misspelt-field"),
        # ...or the value that is not a string...
        pytest.param({"json": {"api_key": 12345678901234567890}}, id="not-a-string"),
        # ...or the raw body, which it tries to read as the model.
        pytest.param({"content": KEY, "headers": {"content-type": "text/plain"}}, id="not-json"),
    ],
)
def test_a_body_that_fails_validation_is_not_echoed(
    signed_in, llm_keyring, fake_provider, db, me, sent
):
    response = signed_in.put("/settings/llm", **sent)

    assert response.status_code == 422
    assert response.json() == {"detail": "The request was not understood"}
    assert response.headers.get("cache-control") == "no-store"
    assert "x" * 40 not in response.text
    assert "12345678901234567890" not in response.text
    assert fake_provider.checked == []
    assert the_row(db, me) is None


def test_other_routes_keep_fastapis_own_422(signed_in):
    # A sibling under /settings: the fixed answer is for /settings/llm alone.
    response = signed_in.patch("/settings/reminders", json={"slot": "breakfast"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "reminder_on"],
                "msg": "Field required",
                "input": {"slot": "breakfast"},
            }
        ]
    }


def test_a_model_not_on_the_list_is_refused(signed_in, llm_keyring, fake_provider, db, me):
    response = put_key(signed_in, model="claude-3-opus")

    assert response.status_code == 422
    assert response.json() == {"detail": "Choose one of the listed models"}
    assert fake_provider.checked == []
    assert the_row(db, me) is None


def test_a_refused_key_leaves_the_earlier_one(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)
    fake_provider.error = KeyRejected()

    response = put_key(signed_in, OTHER_KEY)

    assert response.status_code == 422
    assert response.json() == {"detail": "Anthropic refused this key"}
    assert OTHER_KEY not in response.text
    assert fake_provider.checked == [(KEY, "claude-opus-5"), (OTHER_KEY, "claude-opus-5")]
    kept = read(signed_in)
    assert (kept["key_hint"], kept["status"]) == ("WXYZ", "ok")
    assert service.key_for(db, me) == (KEY, "claude-opus-5")


def test_a_model_the_account_cannot_use_is_named(signed_in, llm_keyring, fake_provider, db, me):
    fake_provider.error = ModelUnavailable()

    response = put_key(signed_in, model="claude-haiku-4-5")

    assert response.status_code == 422
    assert response.json() == {"detail": "Your Anthropic account can't use Claude Haiku 4.5"}
    assert the_row(db, me) is None


@pytest.mark.parametrize("error", [ProviderUnavailable, NoCredit])
def test_an_unreachable_anthropic_saves_nothing(
    signed_in, llm_keyring, fake_provider, db, me, error
):
    fake_provider.error = error()

    response = put_key(signed_in)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Couldn't reach Anthropic to check the key. Nothing was saved."
    }
    assert the_row(db, me) is None
    assert read(signed_in)["status"] == "none"


# --- removing --------------------------------------------------------------------------


def test_removing_the_key(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)

    response = signed_in.delete("/settings/llm")

    assert response.status_code == 204
    assert response.content == b""
    assert read(signed_in)["status"] == "none"
    # The row stays, with every key column empty.
    row = the_row(db, me)
    assert (
        row.llm_provider,
        row.llm_model,
        row.llm_key_ciphertext,
        row.llm_key_hint,
        row.llm_key_status,
        row.llm_key_set_at,
    ) == (None, None, None, None, None, None)
    # And removing it again is no error.
    assert signed_in.delete("/settings/llm").status_code == 204


def test_removing_a_key_that_was_never_saved(signed_in, db, me):
    assert signed_in.delete("/settings/llm").status_code == 204
    assert the_row(db, me) is None


def test_a_key_can_be_removed_from_a_server_without_a_keyring(
    signed_in, llm_keyring, fake_provider, monkeypatch
):
    put_key(signed_in)
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")

    assert signed_in.delete("/settings/llm").status_code == 204
    assert read(signed_in)["status"] == "none"


# --- whose key -------------------------------------------------------------------------


def test_each_user_sees_only_their_own_key(signed_in, llm_keyring, fake_provider, monkeypatch):
    put_key(signed_in)

    sign_in_as(signed_in, monkeypatch, "sub-other", "other@example.com")
    assert read(signed_in)["status"] == "none"
    assert put_key(signed_in, OTHER_KEY).json()["key_hint"] == "ABCD"
    assert signed_in.delete("/settings/llm").status_code == 204

    sign_in_as(signed_in, monkeypatch, "sub-track", "track@example.com")
    mine = read(signed_in)
    assert (mine["key_hint"], mine["status"]) == ("WXYZ", "ok")


def test_no_answer_is_cached(signed_in, llm_keyring, fake_provider):
    answers = [
        signed_in.get("/settings/llm"),
        put_key(signed_in),
        put_key(signed_in, "not-a-key"),
        signed_in.delete("/settings/llm"),
    ]

    assert [answer.status_code for answer in answers] == [200, 200, 422, 204]
    assert [answer.headers.get("cache-control") for answer in answers] == ["no-store"] * 4


def test_a_profile_save_leaves_the_key_alone(signed_in, llm_keyring, fake_provider):
    """A profile save replaces its child tables wholesale; the key is not one of them."""
    assert UserSettings not in profiles.CHILD_MODELS
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    put_key(signed_in)

    assert signed_in.put("/profile", json=PROFILE).status_code == 200

    after = read(signed_in)
    assert (after["key_hint"], after["status"]) == ("WXYZ", "ok")


# --- the one place a key is decrypted --------------------------------------------------


def test_a_key_under_another_keyring_reads_as_ok_until_it_is_used(
    signed_in, llm_keyring, fake_provider, db, me, monkeypatch
):
    put_key(signed_in)
    monkeypatch.setattr(settings, "llm_key_encryption_keys", Fernet.generate_key().decode())

    # A GET never decrypts, so it cannot tell yet.
    assert read(signed_in)["status"] == "ok"

    assert service.key_for(db, me) is None
    assert the_row(db, me).llm_key_status == "unreadable"
    after = signed_in.get("/settings/llm")
    assert after.status_code == 200
    assert after.json()["status"] == "unreadable"


def test_a_key_marked_rejected_is_not_handed_out(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)

    service.mark_status(db, me, "rejected")

    assert service.key_for(db, me) is None
    assert read(signed_in)["status"] == "rejected"
    with pytest.raises(ValueError, match="unknown key status"):
        service.mark_status(db, me, "maybe")


def test_without_a_keyring_key_for_says_so(db, me, no_keyring):
    with pytest.raises(crypto.NotConfigured):
        service.key_for(db, me)


def test_a_key_copied_into_another_users_row_does_not_decrypt(
    signed_in, llm_keyring, fake_provider, db, me
):
    put_key(signed_in)
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(
        UserSettings(
            user_id=other.id,
            llm_provider="anthropic",
            llm_model="claude-opus-5",
            llm_key_ciphertext=the_row(db, me).llm_key_ciphertext,
            llm_key_hint="WXYZ",
            llm_key_status="ok",
            llm_key_set_at=datetime.datetime.now(datetime.UTC),
        )
    )
    db.flush()

    assert service.key_for(db, other) is None
    assert the_row(db, other).llm_key_status == "unreadable"
    assert service.key_for(db, me) == (KEY, "claude-opus-5")


# --- boot ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyring",
    [
        pytest.param("not-a-fernet-key", id="garbage"),
        pytest.param(Fernet.generate_key().decode() + ",too-short", id="second-key-bad"),
    ],
)
def test_a_malformed_keyring_stops_the_app_at_boot(monkeypatch, keyring):
    monkeypatch.setattr(settings, "llm_key_encryption_keys", keyring)

    with (
        pytest.raises(ValueError, match=MALFORMED_KEYRING) as refused,
        TestClient(app),
    ):
        pass

    # Task 1's fixed message, not Fernet's: no part of the keyring is quoted in a boot log.
    for part in keyring.split(","):
        assert part not in str(refused.value)


def test_an_empty_keyring_boots_with_ai_descriptions_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
```

Four notes on these tests:
- `test_the_plain_key_never_reaches_the_database` listens on the test transaction's own connection, which every request shares through the `get_db` override. It checks the SQL and its bound parameters, not only the stored row. SQLAlchemy quotes bound parameters in its error messages, so a plaintext key in any parameter could end up in a log.
- `test_a_body_that_fails_validation_is_not_echoed` covers the one 422 the handler never sees: pydantic's, raised before the route runs. Without the handler in `app/main.py`, each case comes back with the key or the number in its `input`. The not-JSON case sends `text/plain`, because FastAPI then validates the raw body against `LlmKeyIn` and would quote all of it. `test_other_routes_keep_fastapis_own_422` shows the handler leaves every other route's 422 exactly as FastAPI writes it; `PATCH /settings/reminders` checks the body before its handler asks for a profile, so a signed-in user without one is enough.
- The boot tests enter a plain `TestClient(app)`, which runs the lifespan, and make no request, so they touch no database. Starlette re-raises a failed startup from `__enter__`, which is what `pytest.raises` sees.
- `sign_in_as` follows `test_household_api.py`: sign out, patch Google's verifier to a new identity, and sign in again on the same client.

Create `tests/test_rotate_llm_keys.py`:

```python
"""Re-encrypting the stored API keys under the keyring's first key: scripts.rotate_llm_keys.

Rotation is how an old encryption key is retired. The new key goes first in
LLM_KEY_ENCRYPTION_KEYS, the script moves every row onto it, and the old key can then be
removed without anyone losing their saved key.
"""

import contextlib

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.llm import crypto, service
from app.llm.providers import DEFAULT_MODEL
from app.models.llm import UserSettings
from app.models.user import User
from scripts import rotate_llm_keys
from tests.conftest import FakeProvider

KEY_A = "sk-ant-api03-" + "a" * 40 + "AAAA"
KEY_B = "sk-ant-api03-" + "b" * 40 + "BBBB"
KEY_C = "sk-ant-api03-" + "c" * 40 + "CCCC"


def fresh_key() -> str:
    return Fernet.generate_key().decode()


def use_keyring(monkeypatch, *keys: str) -> None:
    monkeypatch.setattr(settings, "llm_key_encryption_keys", ",".join(keys))


def user_with_key(db, name: str, api_key: str) -> User:
    """A user who saved `api_key` under whatever keyring is set now."""
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    service.save_key(db, user, api_key=api_key, model=DEFAULT_MODEL, provider=FakeProvider())
    return user


def stored(db, user: User) -> UserSettings:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one()


@pytest.fixture
def script_session(db, monkeypatch):
    """The script's session, pointed at the test transaction instead of the dev database."""

    @contextlib.contextmanager
    def session():
        yield db

    monkeypatch.setattr(rotate_llm_keys, "SessionLocal", session)


def test_keys_under_an_old_key_move_to_the_first(db, monkeypatch):
    old, new = fresh_key(), fresh_key()
    use_keyring(monkeypatch, old)
    asha = user_with_key(db, "asha", KEY_A)
    ravi = user_with_key(db, "ravi", KEY_B)
    use_keyring(monkeypatch, new, old)

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=2, current=0, unreadable=0)
    assert crypto.is_current(stored(db, asha).llm_key_ciphertext)
    # With the old key gone, each still decrypts, for its own user.
    use_keyring(monkeypatch, new)
    assert service.key_for(db, asha) == (KEY_A, DEFAULT_MODEL)
    assert service.key_for(db, ravi) == (KEY_B, DEFAULT_MODEL)


def test_a_second_run_finds_every_key_current(db, monkeypatch):
    old, new = fresh_key(), fresh_key()
    use_keyring(monkeypatch, old)
    asha = user_with_key(db, "asha", KEY_A)
    user_with_key(db, "ravi", KEY_B)
    use_keyring(monkeypatch, new, old)
    # Saved after the new key went first, so under it already.
    user_with_key(db, "meena", KEY_C)

    assert service.rotate_all(db) == service.RotationCounts(rotated=2, current=1, unreadable=0)
    rotated = stored(db, asha).llm_key_ciphertext

    assert service.rotate_all(db) == service.RotationCounts(rotated=0, current=3, unreadable=0)
    # A current key is left as it is, not encrypted again.
    assert stored(db, asha).llm_key_ciphertext == rotated


def test_a_key_nothing_in_the_keyring_can_read_is_marked_and_left(db, monkeypatch):
    use_keyring(monkeypatch, fresh_key())
    asha = user_with_key(db, "asha", KEY_A)
    before = stored(db, asha).llm_key_ciphertext
    # The key it was saved under is gone: removed before rotating.
    use_keyring(monkeypatch, fresh_key())

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=0, current=0, unreadable=1)
    row = stored(db, asha)
    assert row.llm_key_status == "unreadable"
    assert row.llm_key_ciphertext == before
    # Its owner is asked for the key again, and nothing tries to use it meanwhile.
    assert service.summary(db, asha).status == "unreadable"
    assert service.key_for(db, asha) is None


def test_a_key_copied_from_another_user_is_not_rotated_into_their_row(db, monkeypatch):
    old, new = fresh_key(), fresh_key()
    use_keyring(monkeypatch, old)
    asha = user_with_key(db, "asha", KEY_A)
    ravi = user_with_key(db, "ravi", KEY_B)
    copied = stored(db, asha).llm_key_ciphertext
    stored(db, ravi).llm_key_ciphertext = copied
    db.flush()
    use_keyring(monkeypatch, new, old)

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=1, current=0, unreadable=1)
    assert stored(db, ravi).llm_key_status == "unreadable"
    assert stored(db, ravi).llm_key_ciphertext == copied
    assert service.key_for(db, asha) == (KEY_A, DEFAULT_MODEL)


def test_the_script_rotates_and_reports(db, monkeypatch, capsys, script_session):
    old, new = fresh_key(), fresh_key()
    use_keyring(monkeypatch, old)
    asha = user_with_key(db, "asha", KEY_A)
    use_keyring(monkeypatch, new, old)

    assert rotate_llm_keys.main() == 0

    assert capsys.readouterr().out == "rotated 1, current 0, unreadable 0\n"
    assert crypto.is_current(stored(db, asha).llm_key_ciphertext)


def test_the_script_refuses_without_a_keyring(monkeypatch, capsys):
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")

    def no_session():
        raise AssertionError("the script opened a database session")

    monkeypatch.setattr(rotate_llm_keys, "SessionLocal", no_session)

    assert rotate_llm_keys.main() == 1
    assert "LLM_KEY_ENCRYPTION_KEYS is not set" in capsys.readouterr().err
```

`rotate_all` walks the whole table, so these counts assume the test transaction holds the only `user_settings` rows. It does: the test database carries no rows between tests. `script_session` hands the script the test's own session through a context manager that does not close it. The script's `db.commit()` then commits a savepoint, and the test's outer transaction still rolls everything back.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_llm_settings_api.py tests/test_rotate_llm_keys.py -q`

Expected: 2 errors during collection, one per file, both `ImportError: cannot import name 'service' from 'app.llm'`. Neither `app/llm/service.py` nor `scripts/rotate_llm_keys.py` exists yet.

- [ ] **Step 3: Write the service**

Create `app/llm/service.py`:

```python
"""A user's own Anthropic API key: checked when saved, stored encrypted, never shown again.

The key belongs to the user, not the profile, so it lives in `user_settings`, a table a
profile save never touches. What the settings screen reads -- the provider, the model, the
last four characters and a status -- sits beside the ciphertext in plain columns, so a GET
never decrypts. `key_for` is the one place a key is decrypted, and it serves only the
signed-in user's own plan.

Services flush and never commit; the router commits.
"""

import datetime
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.llm import crypto
from app.llm.providers import Provider
from app.models.llm import UserSettings
from app.models.user import User

PROVIDER = "anthropic"
KEY_PATTERN = re.compile(r"^sk-ant-[A-Za-z0-9_-]+$")
# An Admin API key is an organisation credential: it manages members, keys and billing.
# Descriptions need an ordinary API key, and this server must never hold anything more.
ADMIN_PREFIX = "sk-ant-admin"
MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 300
FORMAT_MESSAGE = "That doesn't look like an Anthropic API key"
KEY_STATUSES = ("ok", "rejected", "unreadable")


class InvalidKeyFormat(ValueError):
    """The key fails the format check. The message is always FORMAT_MESSAGE.

    Never the value: a key that fails the check can still be most of a real key.
    """

    def __init__(self) -> None:
        super().__init__(FORMAT_MESSAGE)


@dataclass(frozen=True)
class KeySummary:
    """What the settings screen may know about a key: everything but the key."""

    available: bool
    provider: str | None
    model: str | None
    hint: str | None
    status: str  # "none" | "ok" | "rejected" | "unreadable"


@dataclass(frozen=True)
class RotationCounts:
    rotated: int
    current: int
    unreadable: int


def normalise_key(raw: str) -> str:
    """The key as typed, stripped. InvalidKeyFormat unless it looks like an API key."""
    key = raw.strip()
    if not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
        raise InvalidKeyFormat
    if KEY_PATTERN.fullmatch(key) is None or key.startswith(ADMIN_PREFIX):
        raise InvalidKeyFormat
    return key


def summary(db: Session, user: User) -> KeySummary:
    """The user's key as the settings screen shows it. Never decrypts."""
    return _summary_of(_row(db, user))


def save_key(
    db: Session, user: User, *, api_key: str, model: str, provider: Provider
) -> KeySummary:
    """Check the key with the provider, then store it encrypted, replacing any earlier one.

    Nothing is written until the check has passed, and the provider's error propagates.
    A key Anthropic refuses, or one it could not be asked about, therefore leaves the
    earlier key exactly as it was.
    """
    if not crypto.available():
        raise crypto.NotConfigured
    provider.check_key(api_key, model)

    values = {
        "llm_provider": PROVIDER,
        "llm_model": model,
        # Encrypted here, before any SQL is built: the plaintext never reaches the database,
        # nor a SQLAlchemy error message, which quotes its bound parameters.
        "llm_key_ciphertext": crypto.encrypt(api_key, user_id=user.id),
        "llm_key_hint": api_key[-4:],
        "llm_key_status": "ok",
        "llm_key_set_at": datetime.datetime.now(datetime.UTC),
    }
    # One statement rather than a read and a write, so two saves at once cannot both insert.
    statement = insert(UserSettings).values(user_id=user.id, **values)
    statement = statement.on_conflict_do_update(constraint="uq_user_settings_user", set_=values)
    row = db.scalars(
        statement.returning(UserSettings),
        # The row may already be in this session's identity map, loaded earlier and still
        # held. Load what the statement wrote over it, not what the session remembers.
        execution_options={"populate_existing": True},
    ).one()
    return _summary_of(row)


def delete_key(db: Session, user: User) -> None:
    """Forget the key. Removing a key that is not there is not an error.

    The row stays, with all six key columns null, so a future setting that is not about
    the key survives the key's removal.
    """
    row = _row(db, user)
    if row is None:
        return
    row.llm_provider = None
    row.llm_model = None
    row.llm_key_ciphertext = None
    row.llm_key_hint = None
    row.llm_key_status = None
    row.llm_key_set_at = None
    db.flush()


def key_for(db: Session, user: User) -> tuple[str, str] | None:
    """The user's own key and model, decrypted, for polishing their own plan.

    None when there is no key to use: no row, no key, or a key whose status is not "ok".
    A key that no longer decrypts -- the keyring lost its key, or the row was copied from
    another user -- is marked "unreadable" and flushed, so the settings screen asks for
    it again, and is then treated as no key rather than a 500. The caller commits that
    mark. NotConfigured is raised before anything else, so a server with no keyring says
    so instead of telling the user to add a key they cannot save.
    """
    if not crypto.available():
        raise crypto.NotConfigured
    row = _row(db, user)
    if row is None or row.llm_key_ciphertext is None or row.llm_key_status != "ok":
        return None
    try:
        api_key = crypto.decrypt(row.llm_key_ciphertext, user_id=user.id)
    except crypto.Unreadable:
        row.llm_key_status = "unreadable"
        db.flush()
        return None
    return api_key, row.llm_model


def mark_status(db: Session, user: User, status: str) -> None:
    """Record what became of the stored key, such as "rejected" after Anthropic's 401."""
    if status not in KEY_STATUSES:
        raise ValueError(f"unknown key status {status!r}")
    row = _row(db, user)
    if row is None or row.llm_key_ciphertext is None:
        return
    row.llm_key_status = status
    db.flush()


def rotate_all(db: Session) -> RotationCounts:
    """Re-encrypt every stored key under the keyring's first key. Safe to re-run.

    A key already under the first key is counted as current and left alone. A key no key
    in the keyring can read, or one that decrypts to another user's key, is marked
    unreadable and left in place for its owner to replace.

    The rows are locked for the run. Otherwise a key saved while the script runs could
    be overwritten by the rotated copy of the key it had just replaced.
    """
    rows = db.scalars(
        select(UserSettings)
        .where(UserSettings.llm_key_ciphertext.is_not(None))
        .order_by(UserSettings.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()

    rotated = current = unreadable = 0
    for row in rows:
        token = row.llm_key_ciphertext
        if crypto.is_current(token):
            current += 1
            continue
        try:
            fresh = crypto.rotate(token)
            # MultiFernet re-encrypts whatever any key decrypts. The user binding is
            # checked here, so a row copied from another user is not given a fresh token.
            crypto.decrypt(fresh, user_id=row.user_id)
        except crypto.Unreadable:
            row.llm_key_status = "unreadable"
            unreadable += 1
            continue
        row.llm_key_ciphertext = fresh
        rotated += 1
    db.flush()
    return RotationCounts(rotated=rotated, current=current, unreadable=unreadable)


def _row(db: Session, user: User) -> UserSettings | None:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one_or_none()


def _summary_of(row: UserSettings | None) -> KeySummary:
    available = crypto.available()
    if row is None or row.llm_key_ciphertext is None:
        return KeySummary(available=available, provider=None, model=None, hint=None, status="none")
    return KeySummary(
        available=available,
        provider=row.llm_provider,
        model=row.llm_model,
        hint=row.llm_key_hint,
        status=row.llm_key_status,
    )
```

Why the non-obvious parts are the way they are:
- **The upsert is loaded with `populate_existing`.** The upsert is one statement, so two saves at once cannot both insert. `populate_existing` guards a `UserSettings` object that is already in the session's identity map when the upsert runs, because something earlier in the same session loaded the row and still holds it. Without the option, the ORM hands back that object with its old attributes, and the summary built after the upsert shows the old hint, model and status. No `PUT` reads the row before its upsert today, so in production the case needs a later caller that reads first within one request. The tests meet it already: their session is shared across requests and never expires on commit. `test_a_new_key_replaces_the_old_one` holds the row across the second save, and fails without `populate_existing`: it answers `WXYZ` and `rejected`. Plan 8's `save_subscription` handles its upsert the same way.
- **`delete_key` works through the ORM.** It sets the six columns on the loaded row, so the session's copy and the database's never disagree. The six go out in one `UPDATE`, which the all-or-nothing CHECK needs.
- **`key_for` raises `NotConfigured` before it reads the row.** On a server with no keyring, Task 5's polish then answers 503 "not set up". Otherwise a user with no row would be told to add a key, which that server cannot save.
- **`key_for`'s `unreadable` mark is flushed, not committed.** A router that answers an error after `key_for` returned `None` must `db.commit()` first, or the mark is rolled back with the request.
- **`rotate_all` locks its rows.** Without `with_for_update`, a user who saves a new key while the script runs could have it overwritten by the rotated copy of the key it had just replaced.
- **`rotate_all` checks the user binding after rotating.** `MultiFernet.rotate` re-encrypts whatever any key decrypts. Checking the rotated token against the row's user stops a row copied from another user from being given a fresh token.

- [ ] **Step 4: Write the router, mount it, and parse the keyring at boot**

Create `app/llm/router.py`:

```python
"""The user's own Anthropic API key, for AI descriptions: GET, PUT and DELETE /settings/llm.

The key is write-only. PUT takes it in the JSON body -- never in a path or a query string,
which the access log records -- checks it with Anthropic and stores it encrypted. No
response carries it back: GET shows only its last four characters. A stolen session cookie
can therefore replace or remove a key, but never read one.

Every answer and refusal from these handlers says `Cache-Control: no-store`, so no browser
or proxy keeps a copy of it. The 401 for a missing session comes from the shared
`get_current_user` before any of this runs, and carries no key. No profile is needed: the
key belongs to the user.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.llm import crypto, service
from app.llm.providers import (
    DEFAULT_MODEL,
    MODEL_LABELS,
    MODELS,
    KeyRejected,
    ModelUnavailable,
    Provider,
    ProviderError,
    get_provider,
)
from app.models.user import User

router = APIRouter(prefix="/settings/llm", tags=["settings"])

NOT_SET_UP = "AI descriptions are not set up on this server"
UNREACHABLE = "Couldn't reach Anthropic to check the key. Nothing was saved."
REFUSED = "Anthropic refused this key"
MODEL_MESSAGE = "Your Anthropic account can't use {label}"
UNKNOWN_MODEL = "Choose one of the listed models"
# A body that failed validation before a handler here ran. app.main answers it with this,
# because FastAPI's own 422 would quote the input that failed, and that input is the key.
NOT_UNDERSTOOD = "The request was not understood"

# On every answer and refusal from these handlers: what this screen shows is nobody's to
# keep a copy of.
NO_STORE = "no-store"


class LlmKeyIn(BaseModel):
    # No Field constraints, deliberately: pydantic puts a failing value in its 422 body, and
    # this value is the key. The handler checks it instead, with fixed messages.
    api_key: SecretStr
    model: str = DEFAULT_MODEL


class LlmSettingsOut(BaseModel):
    # False when this server has no keyring: the feature is off here.
    available: bool
    provider: Literal["anthropic"] | None
    model: str | None
    # The key's last four characters, never the key.
    key_hint: str | None
    status: Literal["none", "ok", "rejected", "unreadable"]
    # The models this server offers, the default first.
    models: list[str]


def _out(summary: service.KeySummary) -> LlmSettingsOut:
    return LlmSettingsOut(
        available=summary.available,
        provider=summary.provider,
        model=summary.model,
        key_hint=summary.hint,
        status=summary.status,
        models=list(MODELS),
    )


def _refuse(status_code: int, detail: str) -> HTTPException:
    """An error answer, uncached like every other answer here."""
    return HTTPException(status_code, detail, headers={"Cache-Control": NO_STORE})


@router.get("", response_model=LlmSettingsOut)
def read_llm_settings(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmSettingsOut:
    response.headers["Cache-Control"] = NO_STORE
    return _out(service.summary(db, user))


@router.put("", response_model=LlmSettingsOut)
def save_llm_key(
    payload: LlmKeyIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: Provider = Depends(get_provider),
) -> LlmSettingsOut:
    if payload.model not in MODELS:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_MODEL)
    try:
        # The one place the secret is unwrapped: it goes from here to the service.
        api_key = service.normalise_key(payload.api_key.get_secret_value())
    except service.InvalidKeyFormat:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, service.FORMAT_MESSAGE) from None
    if not crypto.available():
        # Checked before Anthropic is asked: a key this server cannot store is not sent.
        raise _refuse(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)

    try:
        summary = service.save_key(
            db, user, api_key=api_key, model=payload.model, provider=provider
        )
    except KeyRejected:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, REFUSED) from None
    except ModelUnavailable:
        label = MODEL_LABELS[payload.model]
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_CONTENT, MODEL_MESSAGE.format(label=label)
        ) from None
    except ProviderError:
        # Unreachable, rate-limited or failing on Anthropic's side. NoCredit lands here too,
        # although a model lookup costs nothing and should never meet it.
        raise _refuse(status.HTTP_503_SERVICE_UNAVAILABLE, UNREACHABLE) from None
    db.commit()
    response.headers["Cache-Control"] = NO_STORE
    return _out(summary)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_key(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Works with the feature off too: a user can always take their key back.
    service.delete_key(db, user)
    db.commit()
    response.headers["Cache-Control"] = NO_STORE
```

The handler checks, in order: the model, the key's format, then whether this server can store a key at all. Only then does it ask Anthropic. A malformed key or a server with no keyring therefore never sends anything to Anthropic. Every error answer the handler gives is built by `_refuse`, so it carries `no-store` too, and its message is one of the fixed strings above, never the submitted value.

`api_key` is a `SecretStr` with no pydantic constraints. A failing constraint puts the value in FastAPI's 422 body, and the frontend's `ApiError` keeps that body as its message. `SecretStr` also keeps the key out of any log line that prints the payload, because its repr is `SecretStr('**********')`.

Some bodies fail before any of this runs: a misspelt or missing `api_key` (FastAPI's 422 quotes the whole body), an `api_key` that is not a string (it quotes the value), or a body that is not JSON at all (it quotes the raw body). None of those reaches the handler, so `_refuse` cannot answer them. The app-level handler added to `app/main.py` below does: on `/settings/llm` it answers 422 `NOT_UNDERSTOOD` with `no-store` and nothing of the input, and on every other path it hands over to FastAPI's own handler unchanged.

In `app/main.py`, which plan 8's Tasks 5, 10 and 11 have already changed:

1. Replace `from fastapi import FastAPI` with:

```python
from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
```

   Directly after `from fastapi.middleware.cors import CORSMiddleware`, add:

```python
from fastapi.responses import JSONResponse
```

   Directly after `from app.households.router import router as households_router`, add:

```python
from app.llm import crypto
from app.llm.router import NO_STORE, NOT_UNDERSTOOD
from app.llm.router import router as llm_router
```

2. In `lifespan`, directly above the line `    task = None`, add:

```python
    # Parse the LLM keyring now, so a malformed LLM_KEY_ENCRYPTION_KEYS stops the app at
    # boot instead of failing the first user who saves a key. An empty one only turns AI
    # descriptions off.
    crypto.keyring()

```

3. Directly after `app.include_router(push_router)`, the last `include_router` line, add:

```python
app.include_router(llm_router)
```

4. Directly after that line, and above `@app.get("/health")`, add:

```python


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's own 422, except on /settings/llm, where it would quote the key.

    A body that fails validation before the route runs -- `api_key` misspelt, missing or
    not a string, or a body that is not JSON -- comes back in FastAPI's 422 with the input
    that failed, and on /settings/llm that input is the key. There the answer is one fixed
    sentence instead, uncached like the answers of the handlers there.
    """
    if request.url.path.startswith("/settings/llm"):
        return JSONResponse(
            {"detail": NOT_UNDERSTOOD},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            headers={"Cache-Control": NO_STORE},
        )
    return await request_validation_exception_handler(request, exc)
```

The handler is registered on `app` itself: a `RequestValidationError` is raised before the route function runs, and an `APIRouter` takes no exception handlers of its own. Every other path still gets FastAPI's handler, so no other route's 422 changes.

`app/main.py` then reads:

```python
import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.config import settings
from app.cycle.router import router as cycle_router
from app.diary.router import router as diary_router
from app.foods.router import router as foods_router
from app.households.router import router as households_router
from app.llm import crypto
from app.llm.router import NO_STORE, NOT_UNDERSTOOD
from app.llm.router import router as llm_router
from app.planner.router import router as planner_router
from app.profiles.router import router as profile_router
from app.reminders.router import push_router, settings_router
from app.reminders.runner import run_forever
from app.reports.router import router as reports_router
from app.targets.router import router as targets_router
from app.weight.router import router as weight_router

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the reminder loop beside the API, on the instance configured to send them.

    Off unless SCHEDULER_ENABLED is set. Every TestClient runs this lifespan, and
    the loop opens its own sessions on the development database's engine, not the
    test's. The loop signs pushes with the VAPID private key, so without one it
    would only record every reminder as failed.
    """
    # Parse the LLM keyring now, so a malformed LLM_KEY_ENCRYPTION_KEYS stops the app at
    # boot instead of failing the first user who saves a key. An empty one only turns AI
    # descriptions off.
    crypto.keyring()

    task = None
    if settings.scheduler_enabled and settings.vapid_private_key:
        task = asyncio.create_task(run_forever())
    elif settings.scheduler_enabled:
        logger.warning("SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="healthMonitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(households_router)
app.include_router(foods_router)
app.include_router(profile_router)
app.include_router(targets_router)
app.include_router(diary_router)
app.include_router(planner_router)
app.include_router(weight_router)
app.include_router(cycle_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(push_router)
app.include_router(llm_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's own 422, except on /settings/llm, where it would quote the key.

    A body that fails validation before the route runs -- `api_key` misspelt, missing or
    not a string, or a body that is not JSON -- comes back in FastAPI's 422 with the input
    that failed, and on /settings/llm that input is the key. There the answer is one fixed
    sentence instead, uncached like the answers of the handlers there.
    """
    if request.url.path.startswith("/settings/llm"):
        return JSONResponse(
            {"detail": NOT_UNDERSTOOD},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            headers={"Cache-Control": NO_STORE},
        )
    return await request_validation_exception_handler(request, exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Write the rotation script**

Create `scripts/rotate_llm_keys.py`:

```python
"""Re-encrypt every stored API key under the first key of LLM_KEY_ENCRYPTION_KEYS, and exit.

Rotating the keyring:

1. Generate a key and put it first: LLM_KEY_ENCRYPTION_KEYS=<new>,<old>. Deploy. New saves
   are encrypted under the new key, and every stored key still decrypts under the old one.
2. Run this script. It re-encrypts each key still under an older key, in one transaction,
   and is safe to re-run.
3. Once a run reports "rotated 0", remove the old key from LLM_KEY_ENCRYPTION_KEYS.

A key that no key in the keyring can read is marked unreadable and left in place. Its
owner is asked to enter it again on the AI descriptions screen.

Rotation protects against a keyring that leaks on its own. If the keyring and a copy of
the database leak together, it is too late: users must revoke their keys at Anthropic.

Usage:
    uv run python -m scripts.rotate_llm_keys
"""

import sys

from app.db import SessionLocal
from app.llm import crypto
from app.llm.service import rotate_all


def main() -> int:
    if not crypto.available():
        print(
            "LLM_KEY_ENCRYPTION_KEYS is not set, so there is no key to rotate to.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as db:
        counts = rotate_all(db)
        db.commit()
    print(f"rotated {counts.rotated}, current {counts.current}, unreadable {counts.unreadable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

The whole run is one transaction. A run that fails part-way changes nothing and can simply be run again. A deployment has a handful of users, so there is no reason to commit in batches.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_llm_settings_api.py tests/test_rotate_llm_keys.py -q`

Expected: `43 passed` (37 and 6).

Then run the suites whose path this task touched: every `TestClient` runs the lifespan, every request that fails validation now passes through the new handler, and every test loads `conftest.py`.

Run: `uv run pytest tests/test_health.py tests/test_auth_api.py tests/test_tracking_api.py tests/test_reminders_api.py tests/test_llm_crypto.py tests/test_llm_models.py tests/test_anthropic_provider.py -q && uv run ruff check .`

Expected: all PASS, and ruff clean.

If `test_a_malformed_keyring_stops_the_app_at_boot` fails with Fernet's own message (`Fernet key must be 32 url-safe base64-encoded bytes.`) or any other, `crypto.keyring()` is letting an underlying error through. Task 1 replaces every malformed-key error with its one fixed message, `LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key`, which quotes no part of the keyring. Fix that in `app/llm/crypto.py`, not in this test.

- [ ] **Step 7: Check both entry points by hand**

These two commands touch no database.

The script, without a keyring. An empty variable overrides `.env`:

Run: `LLM_KEY_ENCRYPTION_KEYS= uv run python -m scripts.rotate_llm_keys; echo "exit $?"`

Expected: `LLM_KEY_ENCRYPTION_KEYS is not set, so there is no key to rotate to.` then `exit 1`.

The API, with a malformed keyring. The port is not the dev server's, so a running `uvicorn` on 8000 is unaffected:

Run: `LLM_KEY_ENCRYPTION_KEYS=not-a-fernet-key uv run uvicorn app.main:app --port 8765 > /tmp/boot.log 2>&1; echo "exit $?"; grep -E "^ValueError: LLM_KEY_ENCRYPTION_KEYS|startup failed" /tmp/boot.log; grep -c "not-a-fernet-key" /tmp/boot.log; rm /tmp/boot.log`

The first `grep` is anchored at the start of the line. It picks out the traceback's exception line, and not the indented source lines above it. One of those is the `raise` in `app/llm/crypto.py`, which also contains `ValueError`.

Expected, four lines:
- `exit 3`, uvicorn's exit code for a failed startup;
- then `ValueError: LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key` and `ERROR:    Application startup failed. Exiting.`;
- then `0`, because the traceback shows source lines, never the keyring's value.

If the second line is missing, the boot failed for another reason, or with another message. Read `/tmp/boot.log` before the `rm`, by running the command again without it.

- [ ] **Step 8: Commit**

```bash
git add app/llm/service.py app/llm/router.py app/main.py scripts/rotate_llm_keys.py \
  tests/conftest.py tests/test_llm_settings_api.py tests/test_rotate_llm_keys.py
git commit -m "feat(backend): save, check and remove a user's Anthropic API key

PUT /settings/llm checks the key with Anthropic's zero-token model lookup
and only then stores it, encrypted and bound to its user, with one upsert.
A refused key, a model the account cannot use, or an Anthropic that cannot
be reached leaves any earlier key exactly as it was. So does a malformed
key, and so does a server with no keyring, where Anthropic is never asked.
The key field is a SecretStr with no pydantic constraints, because a
failing constraint would echo the key in the 422 body. Every refusal is a
fixed message. A body that fails validation before the handler runs gets
one too: an app-level RequestValidationError handler answers it on
/settings/llm without the submitted input, because FastAPI's own 422
would quote the key, and leaves every other route's 422 as it was.

GET never decrypts. It shows the provider, the model, the last four
characters and a status, so a stolen session can replace or remove a key
but never read one. DELETE nulls the key columns and works even with the
feature off. Every answer and refusal the three handlers give is marked
no-store, and so is the validation 422.

A second save's upsert is loaded with populate_existing, so a row the
session already holds shows what was written, not what it remembered. A
test holds the row across the save to prove it.

key_for is the one place a key is decrypted, for Task 5's polish. A key
that no longer decrypts is marked unreadable rather than raising, so the
screen can ask for it again. scripts.rotate_llm_keys moves every key onto
the keyring's first key under a row lock, so an old encryption key can be
retired, and marks what no key can read. The lifespan parses the keyring,
so a malformed LLM_KEY_ENCRYPTION_KEYS stops the app at boot, with the
keyring's fixed message and no part of its value.

conftest gains FakeProvider and the fake_provider and llm_keyring
fixtures, so no test reaches Anthropic or encrypts under a developer's
keyring.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

---

## Task 5: Polish in the planner

This task makes `POST /plan/week/polish` describe the dishes in a week's plan, on the user's own key, and shows the text on the plan. The spec's promise is that polish "never changes a dish, a portion, or a nutrient number". This task keeps that promise in the code, and the tests hold it there.

- **What is written.** Two new strings per dish, `description` and `cooking_note`, arrive on every plan item as two new fields. `dish_name`, `portion`, `rationale` and the day's `vegetarian_reason` are built exactly as before, and nothing here writes `meal_plans` or `meal_plan_items`. A test watches the SQL of a polish request to prove it.
- **What the model sees.** `polish.py` sends each dish's name and its ingredients' names, and nothing else. It never sends a portion, a gram figure, a nutrient, the rationale (which can name levothyroxine and a percentage), a favourite or anything else from the profile. `DishBrief` has no field that could carry them.
- **What is kept.** Only text that passes `clean`: stripped, non-empty, at most 280 characters, with no digit or other numeric character, no `%`, and none of `BANNED_WORDS` as a whole word. That list holds numbers, multipliers ("double", "halve"), units and household measures ("katori", "tumbler", "ladle") in words, and a list of nutrient words. It is a word list, so it keeps amounts off the plan but does not catch every nutrition or health claim: "Rich in iron" passes. A dish whose description fails gets no row, and a cooking note that fails is stored as null. An answer for a reference that was not sent is dropped.
- **Where it lives.** `dish_polish`, one row per user and dish, keyed by `brief_hash`, a fingerprint of exactly what was sent. `describe_week` reads the text by dish, so a swap, a lock, a regenerate or an off-plan re-plan needs no invalidation: a dish shows its own text, or none. A row whose fingerprint no longer matches (a re-seed renamed an ingredient, or `PROMPT_VERSION` moved) is ignored, and the next polish replaces it.
- **When it runs.** Only when asked. Generating, reading, swapping, locking and re-planning after a log never call a model, and a test proves that too.
- **When it fails.** A provider error rolls back every `dish_polish` row the request wrote, and the plan is untouched either way. A refused key is marked `rejected` and committed. A refusal or a response cut off at `max_tokens` is not an error: the adapter returns no text for that batch, those dishes stay undescribed, and the call answers 200.
- **What the answer says.** The body is the week, as every plan route answers it. Beside it, the header `X-Dishes-Described` gives the number of dishes this request stored new text for. So a refusal, a cut-off answer, or an answer the guard refused entirely comes back as `0` instead of a 200 that looks like success. `app/main.py`'s CORS setup exposes the header, so the Plan screen can read it from its own origin.

Nothing on the household path changes: `cooking_view` still selects the slot, the dish name and the member names only, and never reads `user_settings` or `dish_polish`.

Run every backend command from `backend/`.

**Files:**
- Create: `backend/app/planner/polish.py`
- Modify:
  - `backend/app/planner/service.py`: `ItemView` gains two fields; a new `_item_view`; `describe_week` reads the cached text
  - `backend/app/planner/router.py`: `PlanItemOut` gains two fields; `PolishIn`; the `POST /plan/week/polish` route, its messages and its `X-Dishes-Described` header
  - `backend/app/main.py`: the CORS middleware exposes `X-Dishes-Described`
  - `backend/tests/test_planner_api.py`: the `planner_pool` fixture's body moves into a plain `build_planner_pool(db)`, so the new test module can build the same pool
- Test: `backend/tests/test_polish_guard.py` (create, pure), `backend/tests/test_plan_polish_api.py` (create)

**Interfaces:**
- Consumes:
  - Task 1, `app/llm/crypto.py`: `NotConfigured`, which the route answers with 503.
  - Task 2, `app/models/llm.py`: `DishPolish(user_id, dish_id, brief_hash: String(64), description: Text, cooking_note: Text | None, model: String(40))` and its named constraint `uq_dish_polish_user_dish`, which the upsert targets.
  - Task 3, `app/llm/providers.py`: `PROMPT_VERSION`, `MODEL_LABELS`, `DishBrief(ref, name, ingredients)`, `DishText(description, cooking_note)`, `Provider`, `ProviderError`, `KeyRejected`, `ModelUnavailable`, `NoCredit`, `ProviderUnavailable` (each constructible with no arguments), `get_provider`.
  - Task 4:
    - `app/llm/service.py`: `key_for(db, user) -> tuple[str, str] | None`. It raises `NotConfigured` before it reads anything, and marks an undecryptable key `unreadable` and flushes without committing ("the caller commits that mark"). Also `mark_status(db, user, status)` and `summary(db, user) -> KeySummary` (its `.model`).
    - `app/llm/router.py`: `NOT_SET_UP`; `PUT /settings/llm {api_key, model}` and `GET /settings/llm` (its `status`), in the tests.
    - `app/main.py`, as Task 4 leaves it: the line `from app.planner.router import router as planner_router` and the `app.add_middleware(CORSMiddleware, ...)` call, which Task 4 does not change.
    - `tests/conftest.py`: `FakeProvider`, `fake_provider` and `llm_keyring`. The tests rely on four behaviours of `FakeProvider`:
      - `polish` appends `(api_key, model, tuple(dishes))` to `polished` before it raises `error`;
      - with `texts` set, it returns `dict(texts)` verbatim, so refs that were never sent come back too;
      - with `texts` unset, it answers each brief with `DishText(f"A home-style {brief.name}.", None)`;
      - it is a plain class, so a test can replace one instance's `polish`.
  - Plan 8 Task 3: `MealPlan.emphasis`, which the "nothing moves" snapshot includes. Plan 8 Task 6 edits `service.py`'s imports, `DayContext`, `build_context`, `_day_input`, `generate_week`, `replan_after_log` and `swap_item`; none of the lines this task edits.
  - Existing: `tests.test_planner_api`'s `week`, `item_in`, `log`, `WEEK`, `MONDAY`, `NON_VEG_PROFILE`; `tests.test_tracking_api.PROFILE`; the `db`, `reference_data`, `api_client` and `signed_in` fixtures; `settings.frontend_origin`, the one origin the CORS middleware allows.
- Produces:
```python
# app/planner/polish.py -- services flush, never commit
MAX_TEXT = 280
MAX_DISHES_PER_CALL = 40
BANNED_WORDS: frozenset[str]      # the skeleton's list minus "gram", plus thirteen..nineteen,
                                  # sixty..ninety, multipliers and household measures (see Notes)
class NoKey(LookupError)
def clean(text: str | None) -> str | None
    # strip; None when empty, > MAX_TEXT, any numeric character (str.isnumeric: \d and also
    # "½", "²"), "%", or a BANNED_WORDS word among the [A-Za-z]+ tokens, case-insensitive
def brief_hash(name: str, ingredients: Sequence[str]) -> str
    # sha256 hex of "\n".join([f"v{PROMPT_VERSION}", name, *ingredients])
def dish_briefs(db, dish_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, tuple[str, tuple[str, ...]]]
    # dish id -> (Dish.name, sorted distinct ingredient names); one outer-join query; () for none
def current_polish(db, user, dish_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, DishText]
    # this user's rows whose brief_hash still matches; read as columns, not ORM objects
def polish_week(db, user, plan: MealPlan, provider: Provider) -> int
    # key_for (NotConfigured first) -> None -> NoKey; the plan's distinct dish ids minus
    # current_polish, sorted by (name, id), MAX_DISHES_PER_CALL a call, refs "d1".."dN" per
    # call; sent refs only; clean both; upsert on uq_dish_polish_user_dish; flush; returns
    # how many dishes got text. ProviderError propagates.

# app/planner/service.py
@dataclass(frozen=True)
class ItemView:
    ...                                   # the seven existing fields, unchanged, then:
    description: str | None = None
    cooking_note: str | None = None
# describe_week fills both from ONE polish.current_polish call per week; cooking_view is unchanged.

# app/planner/router.py
class PlanItemOut(BaseModel):
    ...                                   # the seven existing fields, then:
    description: str | None
    cooking_note: str | None
class PolishIn(BaseModel):
    start: datetime.date
NO_PLAN = "There is no plan for that week yet"
NO_KEY = "Add your Anthropic API key under AI descriptions first"
KEY_REFUSED = "Anthropic refused your saved key. Replace it under AI descriptions."
MODEL_REFUSED = "Your Anthropic account can't use {label}. Choose another model under AI descriptions."
NO_CREDIT = "Your Anthropic account has no credit left."
PROVIDER_DOWN = "Couldn't reach Anthropic. Your plan is unchanged."
DESCRIBED_HEADER = "X-Dishes-Described"
@router.post("/week/polish", response_model=WeekPlanOut)
def polish_week(payload: PolishIn, response: Response, user, db,
                provider: Provider = Depends(get_provider)) -> WeekPlanOut
    # on a 200 only: response.headers[DESCRIBED_HEADER] = str(polish.polish_week(...))

# app/main.py
app.add_middleware(CORSMiddleware, ..., expose_headers=[DESCRIBED_HEADER])
```
- The HTTP contract, which Task 7 builds the Plan screen's button on. Every plan route's items now carry `description` and `cooking_note`, both `null` until the user asks.

| Method and path | Body | Answer |
|---|---|---|
| `POST /plan/week/polish` | `{start}` | 200 `WeekPlanOut`, the week with its text, and the header `X-Dishes-Described: <n>`, the number of dishes this request stored new text for (CORS exposes it to `settings.frontend_origin`). `0` is still a 200. With every item described, there was nothing left to send. With items still `null`, the model gave nothing the guard kept (a refusal, an answer cut off at `max_tokens`, or only refused text), and asking again sends those dishes again. Otherwise, in the order checked: 401 without a session; 422 "The plan week starts on a Sunday"; 404 `NO_PLAN`; 503 `NOT_SET_UP`; 409 `NO_KEY` (no key, or one marked rejected or unreadable); 409 `KEY_REFUSED` (the key is then marked `rejected`); 409 `MODEL_REFUSED` with the saved model's label; 409 `NO_CREDIT`; 502 `PROVIDER_DOWN`. No failure leaves a `dish_polish` row from that request. |

- [ ] **Step 1: Let another test module build the planner's test pool**

The new API tests need the seven-dish pool from `test_planner_api.py`. Importing its `planner_pool` fixture into another module does not pass ruff: the import is flagged F401 (unused), and every test parameter named after it F811 (a redefinition). So the fixture's body becomes a plain function that both modules call.

In `backend/tests/test_planner_api.py`, replace these three lines:

```python
@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """Seven dishes across every slot, one egg, one meat, one calcium-heavy drink."""
```

with:

```python
def build_planner_pool(db) -> dict[str, Dish]:
    """Seven dishes across every slot, one egg, one meat, one calcium-heavy drink.

    A plain function so other test modules can build the same pool: a fixture
    imported into another module trips ruff's F401 and F811. Needs
    `reference_data` first, for the nutrients and the `test:rice` ingredient.
    """
```

The body below it is unchanged. It still ends:

```python
        dishes[code] = dish
    db.flush()
    return dishes
```

Directly after that `return dishes`, and before `NON_VEG_PROFILE = {**PROFILE, "diet_type": "non-vegetarian"}`, add the fixture back as a thin wrapper, with two blank lines on each side:

```python
@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """Seven dishes across every slot, one egg, one meat, one calcium-heavy drink."""
    return build_planner_pool(db)
```

Run: `uv run pytest tests/test_planner_api.py -q`

Expected: `38 passed`, which is the 29 tests at HEAD plus plan 8 Task 6's nine. On a Sunday it is `37 passed, 1 skipped`, because `test_logging_into_a_day_that_has_ended_does_not_replan_it` skips when the week has no past day. Only the fixture moved, so nothing may fail.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_polish_guard.py`. It is pure: no database, no provider.

```python
"""The guard on AI text, and the fingerprint of what a cached text was written from.

Pure: no database and no provider. The guard is the only thing standing between
a model's answer and the Plan screen, beside the planner's portion and rationale,
so every class of word it refuses is pinned here, along with what it must let
through.
"""

import hashlib

import pytest

from app.llm.providers import PROMPT_VERSION
from app.planner import polish
from app.planner.polish import BANNED_WORDS, MAX_TEXT, brief_hash, clean

# --- what is kept ------------------------------------------------------------------------


def test_clean_prose_is_kept_stripped():
    assert clean("  Soft, steamed rice cakes with a gentle tang.\n") == (
        "Soft, steamed rice cakes with a gentle tang."
    )


@pytest.mark.parametrize("text", [None, "", "   ", "\n\t  "])
def test_nothing_is_not_text(text):
    assert clean(text) is None


def test_the_limit_is_280_characters_after_stripping():
    assert MAX_TEXT == 280
    at_limit = "x" * 280

    assert clean(at_limit) == at_limit
    assert clean(f"   {at_limit}   ") == at_limit
    assert clean("x" * 281) is None


# --- numbers, in digits or in words -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Use 500 g of rice",
        "Ready in 5 minutes",
        "Covers 90% of your calcium",
        "Best eaten on day 2",
        # Any numeric character, not only 0-9: an Arabic-Indic five, a half, a square.
        "Ready in ٥ minutes",
        "Squeeze ½ a lemon over it",
        "Serve warm²",
    ],
)
def test_a_digit_or_any_numeric_character_is_refused(text):
    assert clean(text) is None


def test_a_percent_sign_is_refused_on_its_own():
    assert clean("A high % of it is rice") is None


@pytest.mark.parametrize(
    "text",
    [
        "Serves two happily",
        "Ready in ten minutes",
        "Simmer for fifteen minutes",
        "Ninety seconds in hot oil is enough",
        "Half a lemon over the top lifts it",
        "A dozen curry leaves make it",
        "A hundred percent comfort",
    ],
)
def test_a_number_in_words_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Double the dal for a heartier bowl",
        "Twice the rice keeps it mild",
        "Halve the rice and add more greens",
    ],
)
def test_a_multiplier_is_refused(text):
    # No number in it, and still a change to the planner's portion.
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "A cup of rice to start",
        "A teaspoon of ghee on top",
        "Measure out the grams carefully",
        "A generous serving with chutney",
        "Keep the portion small",
        "Low in calories",
        # The household measures the planner's own portions are written in.
        "A katori of curd on the side",
        "A tumbler of buttermilk after",
        "A ladle of sambar over the rice",
    ],
)
def test_a_unit_or_a_measure_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Packed with protein",
        "A good source of calcium",
        "Rich in vitamins",
        "High in fibre and filling",
        "Very nutritious",
        "Light on carbs",
    ],
)
def test_a_nutrient_claim_is_refused(text):
    assert clean(text) is None


@pytest.mark.parametrize("word", sorted(BANNED_WORDS))
def test_every_banned_word_is_refused_in_any_case(word):
    for form in (word, word.upper(), word.capitalize()):
        assert clean(f"Made with {form} in mind") is None, form


# --- whole words only ---------------------------------------------------------------------
#
# A word is a run of ASCII letters. So a banned word inside a longer word is
# not that word ("someone", "stone", "honey", "soften"), while a banned word
# joined by a hyphen is still a word of its own ("one-pot").


@pytest.mark.parametrize(
    "text",
    [
        "Cook it in a cast-iron pan.",
        "Someone always asks for more.",
        "A stone-ground batter makes it lighter.",
        "Finish with a little honey.",
        "Soften the onions first.",
        "Often served at breakfast.",
    ],
)
def test_a_banned_word_inside_a_longer_word_does_not_count(text):
    assert clean(text) == text


def test_a_hyphenated_number_word_still_counts():
    assert clean("A one-pot dinner.") is None


def test_the_pulses_called_gram_are_ingredients_not_units():
    # IFCT names the pulses in most seeded recipes "Bengal gram", "Black gram",
    # "Green gram" and "Red gram", and the model is shown those names.
    assert "gram" not in BANNED_WORDS
    assert clean("Soaked Bengal gram tossed with grated coconut.") == (
        "Soaked Bengal gram tossed with grated coconut."
    )


def test_iron_is_left_for_the_pan():
    assert "iron" not in BANNED_WORDS


# --- the fingerprint ----------------------------------------------------------------------


def test_the_fingerprint_is_a_sha256_of_exactly_what_was_sent():
    expected = hashlib.sha256(
        f"v{PROMPT_VERSION}\nIdli\nBlack gram, dal\nRice, parboiled, milled".encode()
    ).hexdigest()

    assert brief_hash("Idli", ("Black gram, dal", "Rice, parboiled, milled")) == expected


def test_the_fingerprint_is_stable():
    ingredients = ("Black gram, dal", "Rice, parboiled, milled")

    assert brief_hash("Idli", ingredients) == brief_hash("Idli", list(ingredients))
    assert len(brief_hash("Idli", ingredients)) == 64


@pytest.mark.parametrize(
    ("name", "ingredients"),
    [
        ("Rava idli", ("Black gram, dal", "Rice, parboiled, milled")),
        ("Idli", ("Black gram, whole", "Rice, parboiled, milled")),
        ("Idli", ("Black gram, dal",)),
        ("Idli", ("Black gram, dal", "Fenugreek seeds", "Rice, parboiled, milled")),
    ],
)
def test_the_fingerprint_changes_with_the_name_or_any_ingredient(name, ingredients):
    original = brief_hash("Idli", ("Black gram, dal", "Rice, parboiled, milled"))

    assert brief_hash(name, ingredients) != original


def test_a_new_prompt_version_changes_every_fingerprint(monkeypatch):
    before = brief_hash("Idli", ("Black gram, dal",))

    monkeypatch.setattr(polish, "PROMPT_VERSION", PROMPT_VERSION + 1)

    assert brief_hash("Idli", ("Black gram, dal",)) != before
```

Where a word ends matters, and the tests pin both directions:
- A word is a run of ASCII letters (`[A-Za-z]+`), matched whole and case-insensitively.
- So "someone", "stone", "honey", "soften" and "often" are each one word and pass, although each contains a banned word.
- "one-pot" is the two words "one" and "pot", so it is refused. The guard would rather lose a tip than show a number.
- "cast-iron" passes because "iron" is not banned.

What counts as an amount goes past digits and number words. "Double the dal" and "a ladle of sambar" each restate the planner's portion without a number, so the multipliers and the household measures that the planner's own portions use ("1 katori", "1 tumbler", "1 ladle") are banned too. The guard is still a word list, not a reader. "Rich in iron" passes, and so does a health claim made in words the list does not hold.

Create `backend/tests/test_plan_polish_api.py`:

```python
"""AI descriptions on the plan, end to end: what is sent, what is kept, what never moves.

`POST /plan/week/polish` is the only route that calls a model, and all it may
add is two strings per dish. These tests hold it to that. The plan's rows and
every planner field are snapshotted around it, the SQL it runs is watched, and
the fake provider's inputs are read back to prove the model is shown dish and
ingredient names and nothing else.

The provider is conftest's `FakeProvider`, which records every call as
`(api_key, model, briefs)`. Unless a test sets `texts`, it answers every dish
with "A home-style <name>.", which passes the guard.
"""

import contextlib
import dataclasses
import datetime
import re
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, event, select

from app.config import settings
from app.llm.providers import (
    DishBrief,
    DishText,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    ProviderUnavailable,
)
from app.models.food import Dish, DishIngredient, Ingredient
from app.models.household import HouseholdMember
from app.models.llm import DishPolish
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.planner import polish
from tests.test_planner_api import (
    MONDAY,
    NON_VEG_PROFILE,
    WEEK,
    build_planner_pool,
    item_in,
    log,
    week,
)
from tests.test_tracking_api import PROFILE

# Obviously fake, and never printed: see `save_key` and the privacy test.
KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
POLISH_FIELDS = ("description", "cooking_note")
NO_KEY = "Add your Anthropic API key under AI descriptions first"
# Beside a polish's 200: how many dishes that request stored new text for.
DESCRIBED = "X-Dishes-Described"
# An INSERT, UPDATE or DELETE that names either of the plan's tables.
PLAN_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE)\b.*\bmeal_plan(s|_items)\b", re.IGNORECASE | re.DOTALL
)


@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """test_planner_api's seven dishes across every slot, one egg, one meat."""
    return build_planner_pool(db)


# --- helpers -----------------------------------------------------------------------------


def me(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


def save_key(api, model: str = "claude-opus-5") -> None:
    saved = api.put("/settings/llm", json={"api_key": KEY, "model": model})
    # The detail only: whatever went wrong, the key stays out of the failure output.
    assert saved.status_code == 200, saved.json().get("detail")


def planned(api, profile: dict = NON_VEG_PROFILE, model: str = "claude-opus-5") -> dict:
    """A saved profile and key, and the coming week's plan, generated."""
    assert api.put("/profile", json=profile).status_code == 200
    save_key(api, model)
    return week(api)


def polish_week(api, start: datetime.date = WEEK):
    return api.post("/plan/week/polish", json={"start": str(start)})


def described(api, start: datetime.date = WEEK) -> dict:
    response = polish_week(api, start)
    assert response.status_code == 200, response.json().get("detail")
    return response.json()


def calls_made(fake) -> int:
    """How many polish calls the fake saw. Counted in a helper, so a failing assert
    prints a number, never the recorded calls, whose first element is the key."""
    return len(fake.polished)


def items(plan: dict) -> list[dict]:
    return [item for day in plan["days"] for item in day["items"]]


def without_polish(plan: dict) -> dict:
    """The plan as the planner made it: every field but the two AI ones."""
    return {
        **plan,
        "days": [
            {
                **day,
                "items": [
                    {key: value for key, value in item.items() if key not in POLISH_FIELDS}
                    for item in day["items"]
                ],
            }
            for day in plan["days"]
        ],
    }


def home_style(name: str) -> str:
    """FakeProvider's answer for a dish when a test sets no `texts`."""
    return f"A home-style {name}."


def stored_plan(db) -> tuple[list, list]:
    """Every stored column polish could conceivably move, read from the tables."""
    user_id = me(db).id
    plans = db.execute(
        select(MealPlan.id, MealPlan.week_start, MealPlan.seed, MealPlan.emphasis)
        .where(MealPlan.user_id == user_id)
        .order_by(MealPlan.week_start)
    ).all()
    rows = db.execute(
        select(
            MealPlanItem.id,
            MealPlanItem.plan_id,
            MealPlanItem.plan_date,
            MealPlanItem.slot,
            MealPlanItem.dish_id,
            MealPlanItem.grams,
            MealPlanItem.measure_name,
            MealPlanItem.quantity,
            MealPlanItem.locked,
            MealPlanItem.rationale,
        )
        .join(MealPlan, MealPlan.id == MealPlanItem.plan_id)
        .where(MealPlan.user_id == user_id)
        .order_by(MealPlanItem.id)
    ).all()
    return plans, rows


def polish_rows(db) -> dict[uuid.UUID, tuple[str, str | None, str]]:
    """This user's stored descriptions: dish id -> (description, cooking note, model)."""
    rows = db.execute(
        select(
            DishPolish.dish_id, DishPolish.description, DishPolish.cooking_note, DishPolish.model
        ).where(DishPolish.user_id == me(db).id)
    ).all()
    return {row.dish_id: (row.description, row.cooking_note, row.model) for row in rows}


def ingredient_names(db, dish_id: uuid.UUID) -> tuple[str, ...]:
    return tuple(
        sorted(
            db.scalars(
                select(Ingredient.name)
                .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
                .where(DishIngredient.dish_id == dish_id)
            )
        )
    )


@contextlib.contextmanager
def statements(db):
    """Every SQL statement the test session's connection runs inside the block.

    The API runs on the same session, and so on the same connection, so this
    sees everything a request does.
    """
    seen: list[str] = []
    connection = db.connection()

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(connection, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(connection, "before_cursor_execute", record)


def fail_on_second_call(fake, error: type[Exception]) -> list[int]:
    """Answer the first call as usual, then raise `error`. Returns each call's size.

    So a failure always lands after rows were written, and the test can see
    that they went too.
    """
    sizes: list[int] = []
    answer = fake.polish

    def polish_then_fail(api_key, model, dishes):
        sizes.append(len(dishes))
        if len(sizes) > 1:
            raise error
        return answer(api_key, model, dishes)

    fake.polish = polish_then_fail
    return sizes


# --- the fields ----------------------------------------------------------------------------


def test_a_plan_shows_no_descriptions_until_asked(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    plan = planned(signed_in)

    assert items(plan)
    for item in items(plan):
        # Present and null. A field on ItemView but not on PlanItemOut would be
        # dropped without an error, so the JSON itself is checked.
        assert item["description"] is None
        assert item["cooking_note"] is None


def test_descriptions_arrive_on_the_week_and_stay_there(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)

    polished = described(signed_in)

    for item in items(polished):
        assert item["description"] == home_style(item["dish_name"])
        assert item["cooking_note"] is None
    with statements(db) as seen:
        assert week(signed_in) == polished
    # Reading the week shows cached text; it never looks at the key.
    assert not [statement for statement in seen if "user_settings" in statement]


def test_generating_reading_and_editing_the_plan_never_call_a_model(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in)
    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})
    assert regenerated.status_code == 200
    lunch = item_in(regenerated.json(), MONDAY, "lunch")
    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 200
    swapped = item_in(week(signed_in), MONDAY, "lunch")
    assert signed_in.patch(f"/plan/items/{swapped['id']}", json={"locked": True}).status_code == 200
    off_plan = next(
        dish for dish in planner_pool.values()
        if str(dish.id) != swapped["dish_id"] and "lunch" in dish.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")
    week(signed_in)

    assert calls_made(fake_provider) == 0


# --- nothing in the plan moves ---------------------------------------------------------------

HOSTILE = (
    DishText("Use 500 g of rice", "Double the dal for more protein."),
    DishText("Swap it for pongal", "Skip the rice and serve it with pongal instead."),
    DishText("Covers 90% of your calcium", None),
    DishText("A soft, comforting everyday dish.", "Serve it hot."),
)


def test_polish_moves_nothing_in_the_plan(signed_in, planner_pool, llm_keyring, fake_provider, db):
    """The spec: polish never changes a dish, a portion, a rationale or a number."""
    before = planned(signed_in)
    assert len({item["dish_id"] for item in items(before)}) >= len(HOSTILE)
    stored = stored_plan(db)
    fake_provider.texts = {
        f"d{number}": HOSTILE[(number - 1) % len(HOSTILE)]
        for number in range(1, polish.MAX_DISHES_PER_CALL + 1)
    }

    with statements(db) as seen:
        response = polish_week(signed_in)

    assert response.status_code == 200
    # Every field the planner owns reads as it did, in the answer and afterwards.
    assert without_polish(response.json()) == without_polish(before)
    assert without_polish(week(signed_in)) == without_polish(before)
    # So does every stored column, row for row, and the plan's seed.
    assert stored_plan(db) == stored
    # No write was even attempted against the plan's tables...
    assert [statement for statement in seen if PLAN_WRITE.match(statement)] == []
    # ...while the listener was live: the descriptions themselves were written.
    assert any(
        statement.lstrip().upper().startswith("INSERT INTO DISH_POLISH") for statement in seen
    )
    # ...and nothing else was written at all: the text is the only thing stored, so no
    # dish, recipe, measure or nutrient row can move either.
    writes = [s for s in seen if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", s, re.IGNORECASE)]
    assert writes
    assert [s for s in writes if not s.lstrip().upper().startswith("INSERT INTO DISH_POLISH")] == []
    # Text that passes the guard is shown however it is worded, and only as text.
    polished = items(response.json())
    assert "Swap it for pongal" in {item["description"] for item in polished}
    assert {item["description"] for item in polished} <= {
        None, "Swap it for pongal", "A soft, comforting everyday dish.",
    }
    assert {item["cooking_note"] for item in polished} <= {
        None, "Skip the rice and serve it with pongal instead.", "Serve it hot.",
    }


# --- the guard -------------------------------------------------------------------------------


def test_only_text_that_passes_the_guard_is_kept(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    plan = planned(signed_in)
    assert len({item["dish_id"] for item in items(plan)}) >= 5
    fake_provider.texts = {
        "d1": DishText("Use 500 g of rice", "Serve it hot."),
        "d2": DishText("Covers 90% of your calcium", None),
        "d3": DishText("Rich in protein and fibre", "Serve it hot."),
        "d4": DishText("  A soft steamed rice cake.  ", "Rest the batter overnight."),
        "d5": DishText("A tangy lentil stew.", "Add two cups of water."),
    }

    polished = described(signed_in)

    sent = {brief.ref: brief.name for brief in fake_provider.polished[0][2]}
    shown = {
        item["dish_name"]: (item["description"], item["cooking_note"])
        for item in items(polished)
    }
    # A failing description leaves the dish undescribed, whatever its note said.
    for ref in ("d1", "d2", "d3"):
        assert shown[sent[ref]] == (None, None), ref
    assert shown[sent["d4"]] == ("A soft steamed rice cake.", "Rest the batter overnight.")
    # A failing note goes on its own; the description stands.
    assert shown[sent["d5"]] == ("A tangy lentil stew.", None)
    # A dish the answer left out stays undescribed.
    for ref, name in sent.items():
        if ref not in fake_provider.texts:
            assert shown[name] == (None, None), ref
    # Only the two kept dishes have rows, each naming the model that wrote it.
    rows = polish_rows(db)
    assert {db.get(Dish, dish_id).name for dish_id in rows} == {sent["d4"], sent["d5"]}
    assert {model for _, _, model in rows.values()} == {"claude-opus-5"}


def test_an_answer_for_a_reference_that_was_not_sent_is_dropped(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    stray = DishText("A dish nobody asked about.", None)
    fake_provider.texts = {
        "d1": DishText("A soft steamed rice cake.", None),
        "d99": stray,
        "D2": stray,
        " d3": stray,
    }

    polished = described(signed_in)

    sent = {brief.ref: brief.name for brief in fake_provider.polished[0][2]}
    assert "d99" not in sent
    shown = {item["dish_name"]: item["description"] for item in items(polished)}
    assert shown == {
        name: ("A soft steamed rice cake." if ref == "d1" else None) for ref, name in sent.items()
    }
    assert [db.get(Dish, dish_id).name for dish_id in polish_rows(db)] == [sent["d1"]]


def test_an_empty_answer_leaves_the_week_undescribed_and_is_not_an_error(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    """What the service sees when the model refused, or ran out of tokens."""
    plan = planned(signed_in)
    fake_provider.texts = {}

    response = polish_week(signed_in)

    assert response.status_code == 200
    assert response.json() == plan
    # A 200 all the same. The count is how a client tells it from success.
    assert response.headers[DESCRIBED] == "0"
    assert polish_rows(db) == {}
    # Nothing was stored, so asking again sends the same dishes again.
    described(signed_in)
    assert calls_made(fake_provider) == 2
    assert fake_provider.polished[1][2] == fake_provider.polished[0][2]


# --- what the model is shown -----------------------------------------------------------------


def test_the_model_is_shown_dish_and_ingredient_names_and_nothing_else(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    urad = db.scalar(select(Ingredient).where(Ingredient.code == "test:urad"))
    breakfast_soon_after_the_dose = [
        {**slot, "time": "07:30"} if slot["slot"] == "breakfast" else slot
        for slot in PROFILE["meal_times"]
    ]
    plan = planned(
        signed_in,
        profile={
            **NON_VEG_PROFILE,
            "meal_times": breakfast_soon_after_the_dose,
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
            # Named the way the user would, not the way IFCT does.
            "favourites": [
                {"label": "Ulundu", "food_id": str(urad.id), "food_kind": "ingredient"}
            ],
        },
    )
    # The rationale carries what must stay here: the medication and its timing,
    # the favourite in the user's own word, and usually a percentage.
    rationales = [item["rationale"] for item in items(plan) if item["rationale"]]
    assert "levothyroxine" in item_in(plan, MONDAY, "breakfast")["rationale"]
    assert any("Ulundu" in text for text in rationales)

    described(signed_in)

    # A brief has room for nothing but a reference and two kinds of name.
    assert [field.name for field in dataclasses.fields(DishBrief)] == [
        "ref", "name", "ingredients",
    ]
    [(api_key, model, briefs)] = fake_provider.polished
    # Compared outside the assert, so a failure cannot print the key.
    sent_the_saved_key = api_key == KEY
    assert sent_the_saved_key
    assert model == "claude-opus-5"
    # Every dish in the plan, once: its name and its ingredients' names, sorted.
    dishes = {item["dish_id"]: item["dish_name"] for item in items(plan)}
    assert len(briefs) == len(dishes)
    assert {brief.name: brief.ingredients for brief in briefs} == {
        name: ingredient_names(db, uuid.UUID(dish_id)) for dish_id, name in dishes.items()
    }
    words = "\n".join(text for brief in briefs for text in (brief.name, *brief.ingredients))
    assert "levothyroxine" not in words.lower()
    assert "Ulundu" not in words
    assert not re.search(r"[\d%]", words)
    for text in rationales:
        assert text not in words


def test_dishes_go_out_in_name_order_a_batch_at_a_time(
    signed_in, planner_pool, llm_keyring, fake_provider, monkeypatch
):
    plan = planned(signed_in, model="claude-sonnet-5")
    monkeypatch.setattr(polish, "MAX_DISHES_PER_CALL", 3)

    polished = described(signed_in)

    calls = fake_provider.polished
    names = sorted({item["dish_name"] for item in items(plan)})
    assert [brief.name for _, _, briefs in calls for brief in briefs] == names
    assert [len(briefs) for _, _, briefs in calls] == [
        min(3, len(names) - start) for start in range(0, len(names), 3)
    ]
    # References start again in every call, and mean nothing outside it.
    for _, _, briefs in calls:
        assert [brief.ref for brief in briefs] == [f"d{n}" for n in range(1, len(briefs) + 1)]
    # The model is the one the user chose.
    assert {model for _, model, _ in calls} == {"claude-sonnet-5"}
    assert all(item["description"] for item in items(polished))


# --- the cache -------------------------------------------------------------------------------


def test_a_described_dish_is_not_sent_again(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)
    first = described(signed_in)

    second = described(signed_in)

    assert calls_made(fake_provider) == 1
    assert second == first


def test_the_answer_says_how_many_dishes_got_text(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    plan = planned(signed_in)
    dishes = len({item["dish_id"] for item in items(plan)})
    assert dishes > 0

    first = polish_week(signed_in)
    second = polish_week(signed_in)

    assert first.status_code == 200
    assert second.status_code == 200
    # The body is the week, as every plan route answers it; the count rides beside it.
    assert first.headers[DESCRIBED] == str(dishes)
    # Everything is cached now: nothing was sent, and nothing is new.
    assert second.headers[DESCRIBED] == "0"
    assert calls_made(fake_provider) == 1


def test_a_page_on_the_frontend_origin_can_read_the_count(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in)

    response = signed_in.post(
        "/plan/week/polish",
        json={"start": str(WEEK)},
        headers={"Origin": settings.frontend_origin},
    )

    assert response.status_code == 200
    # The Plan screen is served from another origin, and fetch hands a script only
    # the response headers that CORS lists as exposed.
    exposed = response.headers["access-control-expose-headers"]
    assert DESCRIBED.lower() in {name.strip().lower() for name in exposed.split(",")}


def test_renaming_an_ingredient_makes_its_dishes_stale_and_they_go_out_again(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    first = described(signed_in)
    lunch = item_in(first, MONDAY, "lunch")
    ingredient = db.scalars(
        select(Ingredient)
        .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
        .where(DishIngredient.dish_id == uuid.UUID(lunch["dish_id"]))
        .order_by(Ingredient.name)
    ).first()
    uses = set(
        db.scalars(
            select(DishIngredient.dish_id).where(DishIngredient.ingredient_id == ingredient.id)
        )
    )
    stale = {uuid.UUID(item["dish_id"]) for item in items(first)} & uses
    assert uuid.UUID(lunch["dish_id"]) in stale

    # What a re-seed that renames an IFCT food looks like to the cache.
    ingredient.name = "Renamed by a re-seed"
    db.flush()

    # The model was shown the old name, so those dishes' text stops showing...
    for item in items(week(signed_in)):
        stale_dish = uuid.UUID(item["dish_id"]) in stale
        assert item["description"] == (None if stale_dish else home_style(item["dish_name"]))
    fake_provider.texts = {
        f"d{number}": DishText("Described again.", None)
        for number in range(1, polish.MAX_DISHES_PER_CALL + 1)
    }

    again = described(signed_in)

    # ...and only they go out again, under the new name, and their new text shows.
    assert calls_made(fake_provider) == 2
    resent = fake_provider.polished[1][2]
    assert {brief.name for brief in resent} == {db.get(Dish, dish_id).name for dish_id in stale}
    assert all("Renamed by a re-seed" in brief.ingredients for brief in resent)
    for item in items(again):
        stale_dish = uuid.UUID(item["dish_id"]) in stale
        expected = "Described again." if stale_dish else home_style(item["dish_name"])
        assert item["description"] == expected


def test_a_swapped_in_dish_shows_its_own_text_never_the_old_ones(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    lunch = item_in(described(signed_in), MONDAY, "lunch")
    assert lunch["description"] == home_style(lunch["dish_name"])
    # Keep only the outgoing dish's text, so the incoming dish has none of its own.
    db.execute(
        delete(DishPolish).where(
            DishPolish.user_id == me(db).id,
            DishPolish.dish_id != uuid.UUID(lunch["dish_id"]),
        )
    )
    db.flush()

    swapped = signed_in.post(f"/plan/items/{lunch['id']}/swap", json={})

    assert swapped.status_code == 200, swapped.text
    new_lunch = item_in(swapped.json(), MONDAY, "lunch")
    # The same plan item, updated in place, now holding another dish. The text
    # follows the dish, so the item has none.
    assert new_lunch["id"] == lunch["id"]
    assert new_lunch["dish_id"] != lunch["dish_id"]
    assert new_lunch["description"] is None
    assert new_lunch["cooking_note"] is None
    # The outgoing dish keeps its text wherever else it appears.
    for item in items(swapped.json()):
        if item["dish_id"] == lunch["dish_id"]:
            assert item["description"] == home_style(lunch["dish_name"])

    # Described now, the incoming dish gets its own.
    again = item_in(described(signed_in), MONDAY, "lunch")
    assert again["description"] == home_style(new_lunch["dish_name"])


def test_regenerating_keeps_each_dishs_text(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)
    polished = described(signed_in)
    lunch = item_in(polished, MONDAY, "lunch")
    assert signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True}).status_code == 200
    described_dishes = {item["dish_id"] for item in items(polished)}

    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})

    assert regenerated.status_code == 200
    after = items(regenerated.json())
    # New rows for every unlocked slot...
    unlocked_before = {item["id"] for item in items(polished)} - {lunch["id"]}
    unlocked_after = {item["id"] for item in after} - {lunch["id"]}
    assert unlocked_before.isdisjoint(unlocked_after)
    # ...and still the text, because it belongs to the dish, not the row.
    for item in after:
        expected = home_style(item["dish_name"]) if item["dish_id"] in described_dishes else None
        assert item["description"] == expected
    assert any(item["id"] != lunch["id"] and item["description"] for item in after)
    kept = item_in(regenerated.json(), MONDAY, "lunch")
    assert kept["id"] == lunch["id"]
    assert kept["description"] == lunch["description"]
    # Regenerating asked the model nothing.
    assert calls_made(fake_provider) == 1


# --- the service, directly -------------------------------------------------------------------


def test_polish_week_counts_the_dishes_it_described(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    plan_json = planned(signed_in)
    user = me(db)
    plan = db.scalar(
        select(MealPlan).where(MealPlan.user_id == user.id, MealPlan.week_start == WEEK)
    )

    assert polish.polish_week(db, user, plan, fake_provider) == len(
        {item["dish_id"] for item in items(plan_json)}
    )
    # Everything is described now, so a second run has nothing to send.
    assert polish.polish_week(db, user, plan, fake_provider) == 0
    assert calls_made(fake_provider) == 1


def test_a_brief_is_the_dish_name_and_its_ingredient_names_sorted(db, planner_pool):
    idli = planner_pool["test:idli"]
    urad = db.scalar(select(Ingredient).where(Ingredient.code == "test:urad"))
    # The same ingredient twice in a recipe is still one name.
    db.add(DishIngredient(dish_id=idli.id, ingredient_id=urad.id, grams=10.0))
    bare = Dish(
        code="test:buttermilk", name="Buttermilk", source="authored",
        is_editable=True, yield_factor=1.0,
    )
    db.add(bare)
    db.flush()

    briefs = polish.dish_briefs(db, [idli.id, bare.id, idli.id])

    assert briefs == {
        idli.id: ("Idli", ("Rice, cooked", "Urad dal")),
        bare.id: ("Buttermilk", ()),
    }
    assert polish.dish_briefs(db, []) == {}


def test_cached_text_counts_only_for_its_owner_and_while_it_matches(
    signed_in, planner_pool, db
):
    user = me(db)
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    idli, coffee, sundal = (
        planner_pool[code] for code in ("test:idli", "test:coffee", "test:sundal")
    )
    db.add_all([
        DishPolish(
            user_id=user.id, dish_id=idli.id,
            brief_hash=polish.brief_hash("Idli", ("Rice, cooked", "Urad dal")),
            description="Soft steamed rice cakes.", cooking_note="Rest the batter overnight.",
            model="claude-opus-5",
        ),
        # Written from a brief that no longer matches the dish.
        DishPolish(
            user_id=user.id, dish_id=coffee.id, brief_hash="0" * 64,
            description="Strong and milky.", cooking_note=None, model="claude-opus-5",
        ),
        # Someone else's text, current, for a dish this user has none for.
        DishPolish(
            user_id=other.id, dish_id=sundal.id,
            brief_hash=polish.brief_hash("Chana sundal", ("Bengal gram, whole",)),
            description="Their sundal.", cooking_note=None, model="claude-opus-5",
        ),
    ])
    db.flush()

    assert polish.current_polish(db, user, [idli.id, coffee.id, sundal.id]) == {
        idli.id: DishText("Soft steamed rice cakes.", "Rest the batter overnight."),
    }
    assert polish.current_polish(db, user, []) == {}


# --- when it cannot run ----------------------------------------------------------------------


def test_without_a_saved_key_polish_answers_409_and_calls_nothing(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    assert signed_in.put("/profile", json=NON_VEG_PROFILE).status_code == 200
    plan = week(signed_in)

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == 0
    assert week(signed_in) == plan


def test_a_server_without_a_keyring_answers_503(
    signed_in, planner_pool, fake_provider, monkeypatch
):
    # Explicit, so a keyring in a developer's .env cannot turn the feature on here.
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")
    assert signed_in.put("/profile", json=NON_VEG_PROFILE).status_code == 200
    week(signed_in)

    response = polish_week(signed_in)

    assert response.status_code == 503
    assert response.json()["detail"] == "AI descriptions are not set up on this server"
    assert calls_made(fake_provider) == 0


def test_a_saved_key_is_not_used_once_the_keyring_is_gone(
    signed_in, planner_pool, llm_keyring, fake_provider, monkeypatch
):
    planned(signed_in)
    monkeypatch.setattr(settings, "llm_key_encryption_keys", "")

    response = polish_week(signed_in)

    assert response.status_code == 503
    assert calls_made(fake_provider) == 0


def test_a_key_this_server_can_no_longer_read_is_marked_and_refused(
    signed_in, planner_pool, llm_keyring, fake_provider, db, monkeypatch
):
    planned(signed_in)
    # Another keyring altogether: the stored token no longer decrypts.
    monkeypatch.setattr(settings, "llm_key_encryption_keys", Fernet.generate_key().decode())

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == 0
    # The handler committed the mark. The shared test session would show a merely
    # flushed one too, but in production an uncommitted mark is rolled back when the
    # request's session closes; only a commit leaves no transaction open here.
    assert not db.in_transaction()
    assert signed_in.get("/settings/llm").json()["status"] == "unreadable"


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        pytest.param(
            KeyRejected, 409,
            "Anthropic refused your saved key. Replace it under AI descriptions.",
            id="key-rejected",
        ),
        pytest.param(
            ModelUnavailable, 409,
            "Your Anthropic account can't use Claude Opus 5. "
            "Choose another model under AI descriptions.",
            id="model-unavailable",
        ),
        pytest.param(
            NoCredit, 409, "Your Anthropic account has no credit left.", id="no-credit"
        ),
        pytest.param(
            ProviderUnavailable, 502, "Couldn't reach Anthropic. Your plan is unchanged.",
            id="unreachable",
        ),
    ],
)
def test_a_provider_failure_keeps_nothing_and_leaves_the_plan(
    error, code, detail, signed_in, planner_pool, llm_keyring, fake_provider, db, monkeypatch
):
    plan = planned(signed_in)
    stored = stored_plan(db)
    # Two dishes a call, and the second call fails: the first call's rows must go too.
    monkeypatch.setattr(polish, "MAX_DISHES_PER_CALL", 2)
    calls = fail_on_second_call(fake_provider, error)

    response = polish_week(signed_in)

    assert response.status_code == code
    assert response.json()["detail"] == detail
    assert calls == [2, 2]
    assert polish_rows(db) == {}
    assert stored_plan(db) == stored
    assert week(signed_in) == plan


def test_a_refused_key_is_marked_and_not_tried_again(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    fake_provider.error = KeyRejected()

    refused = polish_week(signed_in)

    assert refused.status_code == 409
    # Committed, as above: a 401 from Anthropic should not be met again next time.
    assert not db.in_transaction()
    assert signed_in.get("/settings/llm").json()["status"] == "rejected"
    calls = calls_made(fake_provider)
    again = polish_week(signed_in)
    assert again.status_code == 409
    assert again.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == calls


def test_the_model_message_names_the_users_own_model(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in, model="claude-haiku-4-5")
    fake_provider.error = ModelUnavailable()

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Your Anthropic account can't use Claude Haiku 4.5. "
        "Choose another model under AI descriptions."
    )


def test_polish_needs_a_sunday(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)

    response = polish_week(signed_in, MONDAY)

    assert response.status_code == 422
    assert response.json()["detail"] == "The plan week starts on a Sunday"


def test_polish_needs_a_plan_for_that_week(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)

    response = polish_week(signed_in, WEEK + datetime.timedelta(days=7))

    assert response.status_code == 404
    assert response.json()["detail"] == "There is no plan for that week yet"
    assert calls_made(fake_provider) == 0
    # Asking to describe a week never plans it.
    plans, _ = stored_plan(db)
    assert [row.week_start for row in plans] == [WEEK]


def test_polish_needs_a_session(api_client):
    assert api_client.post("/plan/week/polish", json={"start": str(WEEK)}).status_code == 401


# --- the household ---------------------------------------------------------------------------


def test_the_household_cooking_view_carries_no_ai_text(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    household = signed_in.post("/households", json={"name": "Home"}).json()
    mine = item_in(described(signed_in), MONDAY, "lunch")
    assert mine["description"]
    amma = User(google_sub="sub-amma", email="amma@example.com", name="Amma")
    db.add(amma)
    db.flush()
    db.add(HouseholdMember(household_id=uuid.UUID(household["id"]), user_id=amma.id))
    plan = MealPlan(user_id=amma.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    db.add(MealPlanItem(
        plan_id=plan.id, plan_date=MONDAY, slot="lunch",
        dish_id=uuid.UUID(mine["dish_id"]), grams=200.0, measure_name="cup", quantity=1.0,
    ))
    db.flush()

    with statements(db) as seen:
        response = signed_in.get(f"/plan/cooking?date={MONDAY}")

    # The three shared fields and nothing else: no description crosses over.
    assert response.json()["overlaps"] == [
        {"slot": "lunch", "dish_name": mine["dish_name"], "members": ["Amma", "Tracker"]},
    ]
    # Nor does that path read anyone's key or anyone's cached text.
    assert seen
    assert not [s for s in seen if re.search(r"\b(dish_polish|user_settings)\b", s)]
```

Why the tests are built the way they are:
- **The "nothing moves" test checks three layers.**
  - Every planner field in the JSON, before and after.
  - Every stored column of both plan tables, the seed and plan 8's `emphasis` included, read as columns so the session's identity map cannot hide a change.
  - The SQL itself. A `before_cursor_execute` listener on the test connection records every statement of the request. None may be an `INSERT`, `UPDATE` or `DELETE` naming `meal_plans` or `meal_plan_items`, and the `INSERT INTO dish_polish` must show up, which proves the listener was live. No statement other than `INSERT INTO dish_polish` may write at all, so recipes, portion measures and nutrient values are covered too, and with them the spec's 'or a nutrient number'.

  "Swap it for pongal" passes the guard on purpose. Text is only ever text: it is shown, and still nothing moves.
- **Which dish got which text.** The service numbers refs in name order, and the tests do not re-derive that order. They read it back from what the fake recorded, `{brief.ref: brief.name for brief in fake_provider.polished[0][2]}`.
- **Failures land after a write.** `fail_on_second_call` lets the first batch through, with `MAX_DISHES_PER_CALL` patched to 2, and then raises. "No rows" therefore proves the rollback, not merely that nothing was attempted.
- **`assert not db.in_transaction()` proves a commit.** The test session shares one identity map across requests and never rolls back between them, so a status that was merely flushed would read back as saved. In production, the request's session closes and rolls back anything uncommitted. Right after a request, only a handler that committed leaves no transaction open.
- **The key stays out of failure output.** It is compared outside an `assert`, the helpers print only `detail`, and the recorded calls are only counted through `calls_made` or indexed down to their briefs, so a failing assert never prints the list that holds the key.
- **The 503 test sets the keyring to empty explicitly,** so a keyring in a developer's `.env` cannot switch the feature on.
- **The count is checked where a client would read it.** `X-Dishes-Described` is read off the HTTP answer: the number of dishes on a first polish, `0` on a second one with everything cached, and `0` when the fake answers `{}`. The CORS test sends `Origin: settings.frontend_origin` and checks that the header is listed in `Access-Control-Expose-Headers`. Without that entry, a script on the frontend's origin could not read the header, although the header would still be sent.

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_polish_guard.py tests/test_plan_polish_api.py -q`

Expected: both files fail to collect, with `Interrupted: 2 errors during collection`. Each reports `ImportError: cannot import name 'polish' from 'app.planner' (.../backend/app/planner/__init__.py)`.

- [ ] **Step 4: Write the guard, the cache and the call**

Create `backend/app/planner/polish.py`:

```python
"""AI descriptions for the dishes in a plan: what is sent, what is kept, where it lives.

Nothing the planner decides passes through here. The model is shown each dish's
name and its ingredients' names, and nothing else: no portion, gram, nutrient,
rationale (which can name a medication and a percentage) or anything from the
profile. What comes back is kept only when `clean` finds no amount in it (no
digit, no "%", and no number, multiplier, unit or household measure in words)
and none of the nutrient words it lists. That is a word list, not a reader: it
does not catch every nutrition or health claim, and "rich in iron" passes. The
text reaches the plan as two new fields beside the planner's own, never in
place of them.

The text is cached per user and dish, keyed by a hash of exactly what was sent.
Nothing is keyed to a plan item, so a swap, a lock, a regenerate or a re-plan
needs no invalidation: a dish shows its own text, or none.
"""

import hashlib
import re
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.llm import service as llm
from app.llm.providers import PROMPT_VERSION, DishBrief, DishText, Provider
from app.models.food import Dish, DishIngredient, Ingredient
from app.models.llm import DishPolish
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User

# Well past the prompt's 25-word sentence and 30-word tip, so only a runaway
# answer is refused. Refused, not cut: half a sentence is worse than none.
MAX_TEXT = 280
# One structured-output call per this many dishes. A week holds 15 to 25
# distinct dishes, so one call is the usual case; the cap keeps a very varied
# week's answer well inside the call's max_tokens.
MAX_DISHES_PER_CALL = 40

# Words that state an amount, change a portion or name a nutrient. Matched as
# whole words, case-insensitively, where a word is a run of ASCII letters.
BANNED_WORDS: frozenset[str] = frozenset({
    # numbers in words
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand", "half", "quarter", "dozen", "percent",
    # multipliers: "double the dal" changes the planner's portion without a number
    "twice", "double", "triple", "halve", "halved",
    # units ("gram" is left out: Bengal, black, green and red gram are the pulses in
    # most of the seeded recipes, and a number in front of it is refused anyway)
    "grams", "kg", "mg", "mcg", "ml", "litre", "litres", "liter", "liters",
    "kcal", "calorie", "calories", "cup", "cups", "tablespoon", "tablespoons",
    "teaspoon", "teaspoons", "tbsp", "tsp", "serving", "servings", "portion", "portions",
    # household measures: the planner writes portions in these ("1 katori")
    "katori", "katoris", "tumbler", "tumblers", "ladle", "ladles", "ladleful",
    # nutrient words ("iron" is left out: "a cast-iron pan" is a cooking tip)
    "protein", "proteins", "calcium", "vitamin", "vitamins", "fibre", "fiber",
    "carbohydrate", "carbohydrates", "carbs", "sodium", "potassium", "cholesterol",
    "nutrient", "nutrients", "nutritious",
})

_WORD = re.compile(r"[A-Za-z]+")


class NoKey(LookupError):
    """The user has no usable key: none saved, or one marked rejected or unreadable."""


def clean(text: str | None) -> str | None:
    """The text, stripped, when it is fit to show beside a plan; None when it is not.

    Fit means non-empty, at most MAX_TEXT characters, with no digit or other
    numeric character ("½" included), no "%", and no word from BANNED_WORDS:
    numbers, multipliers, units and household measures in words, and a list of
    nutrient words. Words are runs of letters, so "cast-iron" is two words and
    passes, "someone" is one word and passes, and "one-pot" contains the word
    "one" and is refused. The guard errs toward losing a tip rather than showing
    an amount beside the planner's portion. It matches words, not meaning, so it
    does not catch every nutrition or health claim.
    """
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_TEXT:
        return None
    if "%" in stripped or any(char.isnumeric() for char in stripped):
        return None
    if any(word.lower() in BANNED_WORDS for word in _WORD.findall(stripped)):
        return None
    return stripped


def brief_hash(name: str, ingredients: Sequence[str]) -> str:
    """A fingerprint of what the model was shown for one dish, and under which prompt.

    A cached text whose fingerprint no longer matches -- the dish or one of its
    ingredients renamed by a re-seed, or a new PROMPT_VERSION -- is ignored, and
    the next polish replaces it.
    """
    payload = "\n".join([f"v{PROMPT_VERSION}", name, *ingredients])
    return hashlib.sha256(payload.encode()).hexdigest()


def dish_briefs(
    db: Session, dish_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, tuple[str, ...]]]:
    """Each dish's name and its ingredients' names, sorted and without repeats.

    This is everything the model is ever shown about a dish. One query; a dish
    with no ingredient rows (a fixed-nutrient reference dish) gets ().
    """
    ids = set(dish_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Dish.id, Dish.name, Ingredient.name)
        .outerjoin(DishIngredient, DishIngredient.dish_id == Dish.id)
        .outerjoin(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
        .where(Dish.id.in_(ids))
    ).all()

    names: dict[uuid.UUID, str] = {}
    ingredients: dict[uuid.UUID, set[str]] = {}
    for dish_id, dish_name, ingredient_name in rows:
        names[dish_id] = dish_name
        found = ingredients.setdefault(dish_id, set())
        if ingredient_name is not None:
            found.add(ingredient_name)
    return {
        dish_id: (name, tuple(sorted(ingredients[dish_id]))) for dish_id, name in names.items()
    }


def current_polish(
    db: Session, user: User, dish_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, DishText]:
    """This user's cached text for these dishes, where it still matches the dish.

    Read by dish, never by plan item, and only ever for the signed-in user's own
    plan: nothing on the household path calls this.
    """
    ids = set(dish_ids)
    if not ids:
        return {}
    # Columns rather than DishPolish objects. `_keep` writes with a Core upsert,
    # which never refreshes an ORM object, and a column read cannot go stale.
    rows = db.execute(
        select(
            DishPolish.dish_id,
            DishPolish.brief_hash,
            DishPolish.description,
            DishPolish.cooking_note,
        ).where(DishPolish.user_id == user.id, DishPolish.dish_id.in_(ids))
    ).all()
    if not rows:
        return {}

    briefs = dish_briefs(db, (row.dish_id for row in rows))
    return {
        row.dish_id: DishText(row.description, row.cooking_note)
        for row in rows
        if row.dish_id in briefs and row.brief_hash == brief_hash(*briefs[row.dish_id])
    }


def polish_week(db: Session, user: User, plan: MealPlan, provider: Provider) -> int:
    """Describe the plan's dishes that have no current text; return how many got some.

    One provider call per MAX_DISHES_PER_CALL dishes, in name order. Each dish
    goes under an opaque reference ("d1", "d2", ...) that means something only
    within its call, and only a reference that was sent is read back. A dish
    whose description fails `clean` gets no row; a cooking note that fails is
    kept as null.

    Of the plan, this reads only which dishes it holds. It never writes a plan
    or a plan item.

    Raises crypto.NotConfigured when the server has no keyring (key_for checks
    that before it reads anything, so the answer does not depend on whether this
    user ever saved a key), NoKey when the user has no usable key, and lets a
    ProviderError through for the router to answer and roll back. Flushes; the
    router commits.
    """
    key = llm.key_for(db, user)
    if key is None:
        raise NoKey
    api_key, model = key

    dish_ids = set(
        db.scalars(select(MealPlanItem.dish_id).where(MealPlanItem.plan_id == plan.id))
    )
    described = current_polish(db, user, dish_ids)
    briefs = dish_briefs(db, dish_ids - set(described))
    # By name, then id, so the calls do not depend on the query plan.
    pending = sorted(briefs.items(), key=lambda entry: (entry[1][0], str(entry[0])))

    kept = 0
    for start in range(0, len(pending), MAX_DISHES_PER_CALL):
        batch = pending[start : start + MAX_DISHES_PER_CALL]
        sent = {f"d{number}": entry for number, entry in enumerate(batch, start=1)}
        answers = provider.polish(
            api_key,
            model,
            [
                DishBrief(ref=ref, name=name, ingredients=ingredients)
                for ref, (_, (name, ingredients)) in sent.items()
            ],
        )
        for ref, text in answers.items():
            if ref not in sent:
                continue
            description = clean(text.description)
            if description is None:
                continue
            dish_id, (name, ingredients) = sent[ref]
            _keep(
                db,
                user,
                dish_id,
                digest=brief_hash(name, ingredients),
                description=description,
                cooking_note=clean(text.cooking_note),
                model=model,
            )
            kept += 1
    db.flush()
    return kept


def _keep(
    db: Session,
    user: User,
    dish_id: uuid.UUID,
    *,
    digest: str,
    description: str,
    cooking_note: str | None,
    model: str,
) -> None:
    """Insert or replace this user's text for one dish, in one statement."""
    values = {
        "user_id": user.id,
        "dish_id": dish_id,
        "brief_hash": digest,
        "description": description,
        "cooking_note": cooking_note,
        "model": model,
    }
    statement = insert(DishPolish).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_dish_polish_user_dish",
            set_={
                name: statement.excluded[name]
                for name in values
                if name not in ("user_id", "dish_id")
            },
        )
    )
```

Why the non-obvious parts are the way they are:
- **`current_polish` selects columns, not `DishPolish` objects.**
  - `_keep` upserts with one Core statement, so two polishes at once cannot both insert.
  - A Core statement never refreshes an ORM object, while a column read returns the row as it is now and cannot go stale. That is the whole reason. No test pins it, so keep the column read when you edit this function.
- **Ingredient names are de-duplicated.** A recipe that lists one ingredient twice sends it once, and its fingerprint does not depend on that.
- **Sorting is by `(name, id)`,** so two dishes with the same name, such as a user's own "Idli" beside the seeded one, still go out in a fixed order.
- **Refs restart at `d1` in every call.** They are opaque and mean nothing outside the call that used them. A dish id never reaches the model.

Run: `uv run pytest tests/test_polish_guard.py -q`

Expected: `140 passed`. `test_plan_polish_api.py` still fails: its plan items have no `description` yet, and there is no route to call.

- [ ] **Step 5: Put the text on the week**

In `backend/app/planner/service.py`:

1. Directly below `from app.households import service as households`, add:

```python
from app.llm.providers import DishText
```

2. Replace `from app.planner import engine, rules` with:

```python
from app.planner import engine, polish, rules
```

Plan 8 Task 6 changes the `app.models.profile` and `app.nutrition_core.conditions` import lines. It does not touch these two, so the edits land the same either way.

3. In `ItemView`, directly after `    rationale: str | None`, add:

```python
    # The user's own AI text for this dish (plan 9). Beside the planner's fields,
    # never in place of them; null until they ask for descriptions, and for a
    # dish whose cached text no longer matches what the dish is.
    description: str | None = None
    cooking_note: str | None = None
```

They go last, with defaults, so every existing keyword construction still works.

4. Directly below the `# --- reading ---...` banner, and above `def describe_week(`, add:

```python
def _item_view(item: MealPlanItem, dish: Dish, text: DishText | None) -> ItemView:
    return ItemView(
        id=item.id,
        slot=item.slot,
        dish_id=dish.id,
        dish_name=dish.name,
        portion=portion_label(item.measure_name, item.quantity, item.grams),
        locked=item.locked,
        rationale=item.rationale,
        description=text.description if text is not None else None,
        cooking_note=text.cooking_note if text is not None else None,
    )


```

5. In `describe_week`, directly after the line `    order = {slot: index for index, slot in enumerate(SLOTS)}` (`cooking_view` has the same line further down; leave that one alone), add:

```python
    # By dish, not by plan item: a swapped-in or regenerated dish shows its own
    # text or none, so nothing has to be cleared when an item changes.
    texts = polish.current_polish(db, user, {dish.id for _, dish in rows})
```

Then replace the `ItemView(...)` construction inside the `sorted(...)` generator, from `                ItemView(` down to its closing `                )`, with the single line:

```python
                _item_view(item, dish, texts.get(dish.id))
```

The generator then reads:

```python
        items = sorted(
            (
                _item_view(item, dish, texts.get(dish.id))
                for item, dish in rows
                if item.plan_date == day
            ),
            key=lambda view: order[view.slot],
        )
```

`describe_week` is only ever called for the signed-in user's own plan, from `_week_out`. `cooking_view` is left exactly as it is, so the household path reads neither `dish_polish` nor `user_settings`.

- [ ] **Step 6: The route**

In `backend/app/planner/router.py`:

1. Replace the line `from fastapi import APIRouter, Depends, HTTPException, Query, status` with:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
```

Then replace the imports from `from app.auth.deps import get_current_user` through `router = APIRouter(prefix="/plan", tags=["plan"])` with:

```python
from app.auth.deps import get_current_user
from app.db import get_db
from app.llm import crypto
from app.llm import service as llm
from app.llm.providers import (
    MODEL_LABELS,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    Provider,
    ProviderError,
    get_provider,
)
from app.llm.router import NOT_SET_UP
from app.models.user import User
from app.planner import polish, rules, service

router = APIRouter(prefix="/plan", tags=["plan"])

NO_PLAN = "There is no plan for that week yet"
NO_KEY = "Add your Anthropic API key under AI descriptions first"
KEY_REFUSED = "Anthropic refused your saved key. Replace it under AI descriptions."
MODEL_REFUSED = (
    "Your Anthropic account can't use {label}. Choose another model under AI descriptions."
)
NO_CREDIT = "Your Anthropic account has no credit left."
PROVIDER_DOWN = "Couldn't reach Anthropic. Your plan is unchanged."
# On a polish's 200: how many dishes that request stored new text for. main.py's
# CORS exposes it, so the Plan screen, on its own origin, can read it.
DESCRIBED_HEADER = "X-Dishes-Described"
```

2. In `PlanItemOut`, directly after `    rationale: str | None`, add:

```python
    # AI text for the dish, on the user's own key (plan 9): null until asked for.
    # Two separate fields, so a description can never stand in for the dish's
    # name, its portion or the planner's rationale.
    description: str | None
    cooking_note: str | None
```

`_week_out` builds each item with `PlanItemOut(**vars(item))`. Pydantic ignores keyword arguments a model does not declare, so without these two lines the fields would disappear from the JSON with no error. The first API test checks the JSON for exactly that reason.

3. Directly after the `RegenerateIn` class, add:

```python


class PolishIn(BaseModel):
    start: datetime.date
```

4. Directly after the `regenerate_week` route, which ends with `    return _week_out(db, user, plan)`, and before `@router.patch("/items/{item_id}", response_model=WeekPlanOut)`, add:

```python


def _model_label(db: Session, user: User) -> str:
    """The saved model's name as the AI descriptions screen shows it."""
    model = llm.summary(db, user).model
    return MODEL_LABELS.get(model, model) if model else "this model"


@router.post("/week/polish", response_model=WeekPlanOut)
def polish_week(
    payload: PolishIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: Provider = Depends(get_provider),
) -> WeekPlanOut:
    """Add AI descriptions to the week's dishes, on the user's own Anthropic key.

    The only route that calls a model; generating, reading and re-planning never
    wait on one. It writes `dish_polish` rows and nothing else: a failure rolls
    back every row this request wrote, and the plan is as it was either way.

    The answer is the week, as every plan route answers it, and DESCRIBED_HEADER
    says how many dishes got new text. 0 is still a 200: every dish already had
    text, or the model gave none the guard kept (a refusal, an answer cut off at
    max_tokens, or only refused text), and those dishes stay undescribed.
    """
    _require_sunday(payload.start)
    plan = service.get_plan(db, user, payload.start)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PLAN)
    try:
        described = polish.polish_week(db, user, plan, provider)
    except crypto.NotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP) from exc
    except polish.NoKey as exc:
        # Looking the key up may have just marked it unreadable. Keep that, so
        # the AI descriptions screen can say so; nothing else has been written.
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, NO_KEY) from exc
    except KeyRejected as exc:
        db.rollback()
        llm.mark_status(db, user, "rejected")
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, KEY_REFUSED) from exc
    except ModelUnavailable as exc:
        db.rollback()
        detail = MODEL_REFUSED.format(label=_model_label(db, user))
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc
    except NoCredit as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, NO_CREDIT) from exc
    except ProviderError as exc:
        # ProviderUnavailable, and anything else the adapter raises in future.
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, PROVIDER_DOWN) from exc
    db.commit()
    response.headers[DESCRIBED_HEADER] = str(described)
    return _week_out(db, user, plan)
```

5. In `backend/app/main.py`, directly above Task 4's line `from app.planner.router import router as planner_router`, add:

```python
from app.planner.router import DESCRIBED_HEADER
```

Then, in the `app.add_middleware(CORSMiddleware, ...)` call, directly after `    allow_headers=["*"],` and before its closing `)`, add:

```python
    # A cross-origin fetch shows a script only the response headers listed here.
    expose_headers=[DESCRIBED_HEADER],
```

The call then reads:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # A cross-origin fetch shows a script only the response headers listed here.
    expose_headers=[DESCRIBED_HEADER],
)
```

The two `app.planner.router` imports stay on separate lines, in that order, as Task 4's two `app.llm.router` imports do; ruff's import sorting wants the `as` import on a line of its own.

Why the handler is shaped this way:
- **The order is fixed.** A malformed week, then a missing plan, then the server's keyring, then the user's key.
  - Asking about a week with no plan never generates one. Only `GET /plan/week` does that.
  - `key_for` raises `NotConfigured` before it reads the user's row. A server with no keyring therefore answers 503 whether or not this user ever saved a key.
- **`NoKey` commits.**
  - `key_for` marks a key it can no longer decrypt `unreadable` and flushes it; Task 4 leaves the commit to its caller.
  - Nothing else has been written at that point, so the commit keeps only the mark.
  - Without it, the mark would be rolled back when the request's session closed, and the settings screen would go on showing "ok".
- **`KeyRejected` rolls back first, then marks.** Rows from an earlier batch in the same request go, and the `rejected` mark is committed on its own. The next polish then answers `NO_KEY` without calling Anthropic again.
- **The model's label is read after the rollback.** It comes from `summary`, which never decrypts. The exception carries nothing from the provider.
- **`ProviderError` is caught last.** That covers `ProviderUnavailable` and any subclass added later, and all of them answer 502 with the rollback. The adapter has already logged the exception's type and status code. The route logs nothing and never puts `str(exc)` in a response.
- **The count goes in a header, not in the body.**
  - `WeekPlanOut` stays what every plan route answers, so the Plan screen can still put the answer straight into its cached week.
  - Without the count, a refusal, a cut-off answer or an answer the guard refused entirely would be a 200 that looks like success. `X-Dishes-Described: 0` tells the client that nothing new was stored.
  - Only a 200 carries it. An `HTTPException` builds its own response, so the header is never set on a failure. It is set after the commit, from `polish_week`'s return value.
  - The Plan screen is served from another origin (Vite's port in development, Cloudflare Pages in production), and a cross-origin `fetch` hands a script only the headers listed in `Access-Control-Expose-Headers`. That is why `main.py` lists it.

- [ ] **Step 7: Run the tests and the checks**

Run: `uv run pytest tests/test_polish_guard.py tests/test_plan_polish_api.py tests/test_planner_api.py tests/test_weight_api.py -q && uv run ruff check .`

Expected: all PASS, and ruff reports `All checks passed!`:
- `test_polish_guard.py`: 140 passed.
- `test_plan_polish_api.py`: 32 passed. That is 29 tests, one of them parametrized over four provider failures.
- `test_planner_api.py` passes unchanged. Its whole-dict comparisons now include `description` and `cooking_note`, both null on both sides, so they still hold:
  - `test_swapping_replaces_only_that_dish` compares a whole item;
  - `test_logging_something_off_plan_replans_only_the_rest_of_that_day` compares items and whole days;
  - `test_logging_the_planned_dish_changes_nothing` and `test_logging_into_a_day_that_has_ended_does_not_replan_it` compare whole weeks.

  The two cooking-view tests compare `/plan/cooking` answers, whose shape this task does not change.
- `test_weight_api.py` calls `GET /plan/week`, which now also reads `dish_polish`.
- `app/main.py`'s change adds one header to answers for a request that carries an `Origin`, and nothing else. Every test module imports `app.main` through conftest, so an import mistake there fails collection in all four files.

The full suite runs in the last task.

- [ ] **Step 8: Commit**

From the repository root:

```bash
git add backend/app/planner/polish.py backend/app/planner/service.py \
  backend/app/planner/router.py backend/app/main.py backend/tests/test_polish_guard.py \
  backend/tests/test_plan_polish_api.py backend/tests/test_planner_api.py
git commit -m "feat(backend): describe a week's dishes on the user's own Anthropic key

POST /plan/week/polish asks the user's chosen Claude model for a
one-sentence description and a cooking tip for each dish in the week, and
the plan shows them as two new fields beside the planner's own. The spec's
promise is that polish never changes a dish, a portion or a number, so it
never writes meal_plans or meal_plan_items, or any table but dish_polish.
A test watches the request's SQL to prove it, and snapshots every stored
plan column around it.

The model is shown each dish's name and its ingredients' names and nothing
else. The rationale can name levothyroxine and a percentage, so it stays
here, as do portions, nutrients and the profile. What comes back is kept
only when it carries no digit or other numeric character, no %, and no
number, multiplier, unit, household measure or listed nutrient word.
\"gram\" is allowed, because Bengal, black, green and red gram are the
pulses in most of the seeded recipes. The guard is a word list: it keeps
amounts off the plan, and it does not catch every nutrition or health
claim.

The answer is the week, as every plan route answers it, with an
X-Dishes-Described header giving how many dishes got new text. So a
refusal, an answer cut off at max_tokens, or text the guard refused
comes back as 0 instead of a 200 that looks like success. CORS exposes
the header to the frontend's origin.

The text is cached per user and dish, keyed by a hash of exactly what was
sent. A swap, a lock, a regenerate or a re-plan therefore needs no
invalidation, a dish is paid for once rather than every week, and a
re-seed that renames an ingredient makes its dishes go out again. A
provider error rolls back every row the request wrote. A refused key is
marked rejected, and a key this server can no longer read is marked
unreadable, and both marks are committed.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

---

## Task 6: The AI descriptions screen

This task gives the user a place to bring their own Anthropic API key: a new "AI descriptions" screen at `/ai-descriptions`, listed under More after Reminders, on Task 4's `/settings/llm` endpoints. It adds nothing to the Plan screen yet; Task 7 does that.

What the screen shows follows from `GET /settings/llm`:
- **Not set up on this server** (`available: false`, no encryption keyring): a note saying so, and no form. A new key could not be stored there. A key saved before the server lost its keyring (`status` not `none`) is still summarized under the note, with "Remove key" and nothing else: no form and no "Replace key". Task 4's `DELETE` needs no keyring, so a user can always take their key back.
- **No key** (`status: "none"`): what is sent and who pays, then a form with the key and a model.
- **A saved key** (`status: "ok"`): the key's last four characters, as `sk-ant-…WXYZ`, and the model's name, with "Replace key" and "Remove key". The key itself is never shown, because the server never sends it back.
- **A key that needs entering again** (`rejected`, `unreadable`): why, and the form again, with the model it was saved with already chosen.

The key is a secret, and the screen treats it as one:
- The field is `type="password"` with `autoComplete="new-password"`, never pre-filled, and emptied the moment the form is sent, not once the answer arrives. Browsers ignore `autocomplete="off"` on a password field and fill in a password saved for the site anyway; `new-password` is the value that stops that.
- A key pasted but not sent is dropped whenever the form opens or closes: on "Replace key", on "Cancel", and when the settings change underneath to a saved key, such as a refetch that finds a key saved from another tab. So the form never comes back still holding it.
- A TanStack mutation remembers the variables it was called with, and here that is the key. The save mutation has `gcTime: 0`, and the screen calls `reset()` on it as soon as it settles. So the key leaves the page's memory once the answer is in, rather than five minutes later. Two tests prove the mutation cache is empty afterwards: one after a failed save, one after a successful one.
- A failed save shows the server's own sentence from the 422 or 503 `detail`, which Task 4 writes as fixed messages that never echo the key. A new helper, `errorDetail` in `src/lib/api.ts`, reads that sentence out of `ApiError.message`, which holds the raw response body. It falls back to the screen's own words for anything that is not a string `detail`. That covers FastAPI's own validation 422, whose `detail` is a list that can quote the input, and a proxy's HTML error page. Task 7 uses the same helper for a failed polish.

Changing the model means entering the key again, because Task 4 checks a key against the model it is saved with. So the saved state shows the model but offers no model picker; "Replace key" brings the form back.

The fallback sentence is shown whenever the feature is available. Claude Opus 5 is the default model, and it is the one model sent with Anthropic's server-side fallback, which can bill a declined request at another model's rate.

`src/shell/TopBar.tsx` needs no change: it titles the phone header from the navigation arrays, so `/ai-descriptions` reads "AI descriptions" there as soon as `MORE_NAV` has the entry. Plan 8 does not change `navigation.ts` or `App.tsx`, so the edits below are against their current text.

**Files:**
- Create:
  - `frontend/src/settings/useLlmSettings.ts`
  - `frontend/src/settings/AiDescriptionsScreen.tsx`
- Modify:
  - `frontend/src/settings/types.ts` (append, after plan 8's `PushUnsubscribe`)
  - `frontend/src/lib/api.ts` (append `errorDetail`)
  - `frontend/src/shell/navigation.ts` (`MORE_NAV` gains the entry)
  - `frontend/src/shell/Sidebar.tsx` (its doc comment lists the destinations)
  - `frontend/src/App.tsx` (the route)
- Test:
  - `frontend/src/settings/AiDescriptionsScreen.test.tsx` (create)
  - `frontend/src/lib/api.test.ts` (append)
  - `frontend/src/shell/navigation.test.tsx` (the label list, and a More screen test)

**Interfaces:**
- Consumes Task 4's HTTP contract. Each route answers 401 without a session, and all three carry `Cache-Control: no-store`.

| Method and path | Body | Answer |
|---|---|---|
| `GET /settings/llm` | — | 200 `{available, provider, model, key_hint, status, models}` |
| `PUT /settings/llm` | `{api_key, model}` | 200, the same shape; 422 `{"detail": "Choose one of the listed models"}`, `"That doesn't look like an Anthropic API key"`, `"Anthropic refused this key"` or `"Your Anthropic account can't use {label}"`; 503 `"AI descriptions are not set up on this server"` or `"Couldn't reach Anthropic to check the key. Nothing was saved."` |
| `DELETE /settings/llm` | — | 204 |

- Produces:
```ts
// src/settings/types.ts
export type LlmKeyStatus = 'none' | 'ok' | 'rejected' | 'unreadable'
export interface LlmSettings {
  available: boolean
  provider: 'anthropic' | null
  model: string | null
  key_hint: string | null
  status: LlmKeyStatus
  models: string[]
}
export interface LlmKeyIn { api_key: string; model: string }
export const MODEL_LABELS: Record<string, string>

// src/settings/useLlmSettings.ts
export const LLM_SETTINGS_KEY = ['settings', 'llm'] as const
export function useLlmSettings()     // GET /settings/llm, retry: false
export function useSaveLlmKey()      // PUT; the answer replaces LLM_SETTINGS_KEY's data; gcTime 0
export function useDeleteLlmKey()    // DELETE; invalidates LLM_SETTINGS_KEY

// src/lib/api.ts
export function errorDetail(error: unknown, fallback: string): string
    // an ApiError whose body is JSON with a non-empty string `detail` -> that string;
    // anything else -> fallback

// src/settings/AiDescriptionsScreen.tsx
export function AiDescriptionsScreen()   // routed at /ai-descriptions

// src/shell/navigation.ts, MORE_NAV, after Reminders:
//   { path: '/ai-descriptions', label: 'AI descriptions', icon: Sparkles }
```
- Task 7 reads `useLlmSettings()` and `LLM_SETTINGS_KEY`, and uses `errorDetail`. Task 13's end-to-end walk finds the not-set-up message by its text, "AI descriptions are not set up on this server."

- [ ] **Step 1: Write the contract**

Append to the end of `frontend/src/settings/types.ts`, after plan 8's `PushUnsubscribe` interface. It needs no new import.

```ts

/**
 * `GET`, `PUT` and `DELETE /settings/llm` — plan 9.
 *
 * The key itself is write-only: it goes up once, in a `PUT` body, and nothing
 * sends it back. What comes back is its last four characters and whether
 * Anthropic accepted it.
 */
export type LlmKeyStatus = 'none' | 'ok' | 'rejected' | 'unreadable'

export interface LlmSettings {
  /** False when the server has no encryption keyring: the feature is off there. */
  available: boolean
  provider: 'anthropic' | null
  model: string | null
  /** The key's last four characters, never the key. */
  key_hint: string | null
  /**
   * `ok` once Anthropic accepted the key. `rejected` when it later refused it,
   * and `unreadable` when the server can no longer decrypt it: both need the key
   * entered again.
   */
  status: LlmKeyStatus
  /** The models this server offers, default first. */
  models: string[]
}

/**
 * `PUT /settings/llm` body. It answers `LlmSettings`, or 422 with a sentence in
 * `detail` when the key is malformed or Anthropic refuses it, or 503 when the
 * server cannot check it.
 */
export interface LlmKeyIn {
  api_key: string
  model: string
}

/** What each model is called on screen. Mirrors the backend's `providers.MODEL_LABELS`. */
export const MODEL_LABELS: Record<string, string> = {
  'claude-opus-5': 'Claude Opus 5',
  'claude-sonnet-5': 'Claude Sonnet 5',
  'claude-haiku-4-5': 'Claude Haiku 4.5',
}
```

`MODEL_LABELS` mirrors the backend's `providers.MODEL_LABELS` (Task 3). The server sends model ids only, and a label is display copy.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/settings/AiDescriptionsScreen.test.tsx`. The key is fake and has the right shape, so a failure that prints it prints nothing useful:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { AiDescriptionsScreen } from './AiDescriptionsScreen'
import type { LlmSettings } from './types'
import { LLM_SETTINGS_KEY } from './useLlmSettings'

// Obviously fake: the right shape for the form, and useless anywhere else.
const KEY = 'sk-ant-api03-' + 'x'.repeat(40) + 'WXYZ'

const MODELS = ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5']

const NO_KEY: LlmSettings = {
  available: true,
  provider: null,
  model: null,
  key_hint: null,
  status: 'none',
  models: MODELS,
}

function savedWith(model: string): LlmSettings {
  return { ...NO_KEY, provider: 'anthropic', model, key_hint: 'WXYZ', status: 'ok' }
}

beforeEach(() => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(NO_KEY)))
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AiDescriptionsScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

/** Paste, as people do with a key, rather than type it. */
async function enterKey(field: HTMLElement) {
  await userEvent.click(field)
  await userEvent.paste(KEY)
}

// --- what the screen says -----------------------------------------------------------------

test('a server with no keyring says so, and asks for no key', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () =>
      HttpResponse.json<LlmSettings>({ ...NO_KEY, available: false }),
    ),
  )
  renderScreen()

  expect(await screen.findByRole('note')).toHaveTextContent(
    'AI descriptions are not set up on this server.',
  )
  expect(screen.getByRole('heading', { name: 'AI descriptions' })).toBeInTheDocument()
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
})

// Removing a key needs no keyring (Task 4), so a key saved before the server lost
// its keyring can always be taken back, whatever its status.
test.each(['ok', 'rejected', 'unreadable'] as const)(
  'a server with no keyring still lets a stored key be removed (%s)',
  async (status) => {
    let current: LlmSettings = { ...savedWith('claude-sonnet-5'), status, available: false }
    let deletes = 0
    server.use(
      http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)),
      http.delete(apiUrl('/settings/llm'), () => {
        deletes += 1
        current = { ...NO_KEY, available: false }
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderScreen()

    expect(await screen.findByRole('note')).toHaveTextContent(
      'AI descriptions are not set up on this server.',
    )
    expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
    expect(screen.getByText('Model: Claude Sonnet 5')).toBeInTheDocument()
    // Nothing on this server can check a key, so there is none to enter.
    expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Replace key' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Remove key' }))

    await waitFor(() => expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument())
    expect(deletes).toBe(1)
    expect(screen.getByRole('note')).toHaveTextContent(
      'AI descriptions are not set up on this server.',
    )
    expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
  },
)

test('says what is sent, who pays, and what happens when Claude Opus 5 declines', async () => {
  renderScreen()

  expect(
    await screen.findByText(
      'Only dish names and ingredient names are sent — never your health details, portions ' +
        'or any numbers. Anthropic bills your account for each request.',
    ),
  ).toBeInTheDocument()
  expect(
    screen.getByText(
      'If Claude Opus 5 declines a request, Anthropic re-runs it on another Claude model and ' +
        "bills that model's rate.",
    ),
  ).toBeInTheDocument()
})

// A key on screen is a key in a screenshot. A browser ignores `autocomplete="off"`
// on a password field; `new-password` is what stops it filling in a saved one.
test('the key field hides what is typed, starts empty, and is marked new-password', async () => {
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  expect(field).toHaveAttribute('type', 'password')
  expect(field).toHaveAttribute('autocomplete', 'new-password')
  expect(field).toHaveValue('')
})

test('offers the server’s models by name, the default first', async () => {
  renderScreen()

  const model = await screen.findByLabelText('Model')
  expect(model).toHaveValue('claude-opus-5')
  expect(
    Array.from(model.querySelectorAll('option'), (option) => option.textContent),
  ).toStrictEqual(['Claude Opus 5', 'Claude Sonnet 5', 'Claude Haiku 4.5'])
})

// --- saving a key -------------------------------------------------------------------------

test('a key goes up with the chosen model, and only its last four come back', async () => {
  let sent: unknown = null
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.put(apiUrl('/settings/llm'), async ({ request }) => {
      sent = await request.json()
      await held
      return HttpResponse.json(savedWith('claude-sonnet-5'))
    }),
  )
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  await enterKey(field)
  await userEvent.selectOptions(screen.getByLabelText('Model'), 'claude-sonnet-5')
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  // Emptied as it is sent, not once it is saved.
  expect(field).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
  expect(await screen.findByRole('status')).toHaveTextContent('Checking the key with Anthropic…')
  release()

  expect(await screen.findByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
  expect(screen.getByText('Model: Claude Sonnet 5')).toBeInTheDocument()
  expect(sent).toStrictEqual({ api_key: KEY, model: 'claude-sonnet-5' })
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(document.body.innerHTML.includes(KEY)).toBe(false)
})

test('a saved key shows its last four characters and its model', async () => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))))
  renderScreen()

  expect(await screen.findByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
  expect(screen.getByText('Model: Claude Opus 5')).toBeInTheDocument()
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open this week’s plan' })).toHaveAttribute(
    'href',
    '/plan',
  )
})

test('a key the server turns down says why, and is not kept in the field', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () =>
      HttpResponse.json({ detail: 'Anthropic refused this key' }, { status: 422 }),
    ),
  )
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  await enterKey(field)
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/^Anthropic refused this key$/)
  expect(field).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
})

// A mutation remembers what it was sent. Once the answer is in, nothing needs the key.
test('the page lets go of the key once the answer is in', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () =>
      HttpResponse.json({ detail: 'Anthropic refused this key' }, { status: 422 }),
    ),
  )
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  await screen.findByRole('alert')
  await waitFor(() => expect(queryClient.getMutationCache().getAll().length).toBe(0))
})

// The common path: a saved key must not linger in the mutation cache either.
test('the page lets go of the key once it is saved, too', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))),
  )
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  await screen.findByText('Key saved: sk-ant-…WXYZ')
  await waitFor(() => expect(queryClient.getMutationCache().getAll().length).toBe(0))
})

// A proxy's error page is not a sentence written for the user, and neither is
// FastAPI's own 422 list; errorDetail's tests cover both.
test('a failure with no sentence to show says so in its own words', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () => new HttpResponse('Bad gateway', { status: 502 })),
  )
  renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The key could not be saved. Please try again.',
  )
})

test.each([
  ['rejected', 'Anthropic refused this key. Enter a new one.'],
  ['unreadable', 'This key can no longer be read on this server. Enter it again.'],
] as const)('asks for the key again when it is %s', async (status, message) => {
  server.use(
    http.get(apiUrl('/settings/llm'), () =>
      HttpResponse.json<LlmSettings>({ ...savedWith('claude-haiku-4-5'), status }),
    ),
  )
  renderScreen()

  expect(await screen.findByText(message)).toBeInTheDocument()
  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
  // The model it was saved with, so entering the key again is all it takes.
  expect(screen.getByLabelText('Model')).toHaveValue('claude-haiku-4-5')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Remove key' })).toBeInTheDocument()
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
})

// --- replacing and removing ---------------------------------------------------------------

test('replacing a key starts from an empty field, and can be called off', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-sonnet-5'))),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Replace key' }))

  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
  expect(screen.getByLabelText('Model')).toHaveValue('claude-sonnet-5')
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
})

// A key pasted and never sent must not come back. Here the saved view takes the
// form's place with no click: a refetch finds a key saved from another tab.
test('a key pasted but not sent is gone when "Replace key" opens the form', async () => {
  let current = NO_KEY
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)))
  const queryClient = renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  await enterKey(field)
  expect(field).toHaveValue(KEY)
  current = savedWith('claude-opus-5')
  await act(() => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }))

  await userEvent.click(await screen.findByRole('button', { name: 'Replace key' }))

  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
})

// The same, when the form comes back by itself: the key saved from another tab
// has since been refused.
test('a key pasted but not sent is gone when the form comes back by itself', async () => {
  let current = NO_KEY
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)))
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  current = savedWith('claude-opus-5')
  await act(() => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }))
  await screen.findByText('Key saved: sk-ant-…WXYZ')
  current = { ...current, status: 'rejected' }
  await act(() => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }))

  expect(
    await screen.findByText('Anthropic refused this key. Enter a new one.'),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
})

test('removing the key sends a DELETE and goes back to the form', async () => {
  let current = savedWith('claude-opus-5')
  let deletes = 0
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)),
    http.delete(apiUrl('/settings/llm'), () => {
      deletes += 1
      current = NO_KEY
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove key' }))

  expect(await screen.findByLabelText('Anthropic API key')).toHaveValue('')
  expect(deletes).toBe(1)
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
})

test('a key that could not be removed says so, and stays', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))),
    http.delete(apiUrl('/settings/llm'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The key could not be removed. Please try again.',
  )
  await waitFor(() => expect(screen.getByRole('button', { name: 'Remove key' })).toBeEnabled())
  expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
})
```

In `frontend/src/lib/api.test.ts`, replace the import line `import { ApiError, api } from './api'` with:

```ts
import { ApiError, api, errorDetail } from './api'
```

Then append to the end of the file:

```ts

// A route's HTTPException carries a sentence written for the user; anything else
// is not, and the screen says something of its own instead.
const SENTENCE = JSON.stringify({ detail: 'Anthropic refused this key' })
const VALIDATION_LIST = JSON.stringify({
  detail: [{ loc: ['body', 'model'], msg: 'Field required', type: 'missing' }],
})

test.each([
  ['a route’s sentence', SENTENCE, 'Anthropic refused this key'],
  ['a validation list', VALIDATION_LIST, 'fallback'],
  ['an empty sentence', '{"detail": "  "}', 'fallback'],
  ['a body with no detail', '{"error": "nope"}', 'fallback'],
  ['a body that is not JSON', '<html>Bad gateway</html>', 'fallback'],
])('errorDetail reads %s', (_case, body, expected) => {
  expect(errorDetail(new ApiError(422, body), 'fallback')).toBe(expected)
})

test('errorDetail falls back for an error that did not come from the API', () => {
  expect(errorDetail(new TypeError('Failed to fetch'), 'fallback')).toBe('fallback')
})
```

In `frontend/src/shell/navigation.test.tsx`:

1. Replace `import { BottomTabs } from './BottomTabs'` with:

```ts
import { BottomTabs } from './BottomTabs'
import { MoreScreen } from './MoreScreen'
```

2. Directly above `function renderAt(`, add:

```ts
/** Behind the More tab on a phone, inline in the sidebar, in this order. */
const MORE_LABELS = ['Weight', 'Cycle', 'Household', 'Reminders', 'AI descriptions', 'Profile']

```

3. In the comment above the sidebar test, replace `burying five destinations` with `burying six destinations`. In that test, replace the line `  for (const label of ['Weight', 'Cycle', 'Household', 'Reminders', 'Profile']) {` with:

```ts
  for (const label of MORE_LABELS) {
```

4. Append to the end of the file:

```tsx

test('the phone’s More screen lists the same destinations, in the same order', () => {
  renderAt(<MoreScreen />, '/more')

  expect(screen.getAllByRole('link').map((link) => link.textContent)).toStrictEqual(MORE_LABELS)
  expect(screen.getByRole('link', { name: 'AI descriptions' })).toHaveAttribute(
    'href',
    '/ai-descriptions',
  )
})
```

- [ ] **Step 3: Run them to verify they fail**

From `frontend/`, run: `npx vitest run src/settings/AiDescriptionsScreen.test.tsx src/lib/api.test.ts src/shell/navigation.test.tsx`

Expected: FAIL, `Test Files  3 failed (3)` and `Tests  8 failed | 7 passed (15)`.
- `AiDescriptionsScreen.test.tsx` does not load: `Error: Failed to resolve import "./AiDescriptionsScreen" from "src/settings/AiDescriptionsScreen.test.tsx". Does the file exist?`. Its 20 tests are not counted.
- In `api.test.ts`, the six `errorDetail` tests fail with `TypeError: errorDetail is not a function`. The three existing tests pass.
- In `navigation.test.tsx`, two fail. The sidebar test fails with `Unable to find an accessible element with the role "link" and name "AI descriptions"`, and the More screen test with `expected [ Array(5) ] to strictly equal [ Array(6) ]`. The other four pass.

- [ ] **Step 4: Implement**

Append to the end of `frontend/src/lib/api.ts`, after the `api` object:

```ts

/**
 * The sentence FastAPI sent with a failed request, or `fallback` when there is none.
 *
 * `ApiError.message` is the raw response body. A route that raises
 * `HTTPException` answers `{"detail": "..."}`, and those sentences are written
 * for the user to read. A request-validation 422 carries a list in `detail`
 * instead, a proxy's error page is not JSON at all, and neither is written for
 * anyone, so both get the fallback.
 */
export function errorDetail(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  let body: unknown
  try {
    body = JSON.parse(error.message)
  } catch {
    return fallback
  }
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string' && detail.trim() !== '') return detail
  }
  return fallback
}
```

Create `frontend/src/settings/useLlmSettings.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { LlmKeyIn, LlmSettings } from './types'

/** The Plan screen reads it too: it offers descriptions only with a key Anthropic accepted. */
export const LLM_SETTINGS_KEY = ['settings', 'llm'] as const

export function useLlmSettings() {
  return useQuery({
    queryKey: LLM_SETTINGS_KEY,
    queryFn: () => api.get<LlmSettings>('/settings/llm'),
    retry: false,
  })
}

export function useSaveLlmKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LlmKeyIn) => api.put<LlmSettings>('/settings/llm', body),
    // A mutation remembers what it was called with, and here that is the key.
    // The screen resets the mutation once it settles, and with no cache time
    // the mutation cache lets go of it straight after, rather than five minutes on.
    gcTime: 0,
    // The answer is the whole screen's state, so there is nothing to refetch.
    onSuccess: (settings) => queryClient.setQueryData(LLM_SETTINGS_KEY, settings),
  })
}

export function useDeleteLlmKey() {
  const queryClient = useQueryClient()
  return useMutation({
    // 204, with nothing to show, so the settings are read again.
    mutationFn: () => api.del<null>('/settings/llm'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }),
  })
}
```

Create `frontend/src/settings/AiDescriptionsScreen.tsx`:

```tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorDetail } from '../lib/api'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Field, Select, TextInput } from '../ui/fields'
import { Skeleton } from '../ui/feedback'
import { MODEL_LABELS } from './types'
import type { LlmKeyStatus, LlmSettings } from './types'
import { useDeleteLlmKey, useLlmSettings, useSaveLlmKey } from './useLlmSettings'

const INTRO =
  'Add a one-line description and a cooking tip to each dish in your plan, written by ' +
  'Claude using your own Anthropic API key.'

const PRIVACY =
  'Only dish names and ingredient names are sent — never your health details, portions ' +
  'or any numbers. Anthropic bills your account for each request.'

// Only Claude Opus 5 is sent with the server-side fallback (backend providers.FALLBACK_MODELS).
const FALLBACK =
  'If Claude Opus 5 declines a request, Anthropic re-runs it on another Claude model and ' +
  "bills that model's rate."

const NOT_AVAILABLE = 'AI descriptions are not set up on this server.'

const STORED_WHILE_OFF =
  'Your key is still stored here, encrypted, but nothing can use it until AI descriptions ' +
  'are set up again. You can remove it.'

/** Why a stored key has to be entered again. */
const NEEDS_NEW_KEY: Partial<Record<LlmKeyStatus, string>> = {
  rejected: 'Anthropic refused this key. Enter a new one.',
  unreadable: 'This key can no longer be read on this server. Enter it again.',
}

const KEY_HINT =
  'It starts with sk-ant-. Anthropic checks it before it is saved. It is stored encrypted, ' +
  'and never shown again.'

const SAVE_FAILED = 'The key could not be saved. Please try again.'
const REMOVE_FAILED = 'The key could not be removed. Please try again.'

function modelLabel(model: string | null): string {
  if (model === null) return ''
  return MODEL_LABELS[model] ?? model
}

/** The stored model while the server still offers it, else the server's default. */
function initialModel(settings: LlmSettings): string {
  if (settings.model !== null && settings.models.includes(settings.model)) return settings.model
  return settings.models[0] ?? ''
}

/** All the server says about a stored key: its last four characters and its model. */
function SavedKey({ settings }: { settings: LlmSettings }) {
  return (
    <>
      <p className="mt-2 text-sm font-medium">
        {`Key saved: sk-ant-…${settings.key_hint ?? ''}`}
      </p>
      <p className="text-sm">{`Model: ${modelLabel(settings.model)}`}</p>
    </>
  )
}

/**
 * A key saved before this server lost its keyring. Nothing here can check or use
 * it, so there is no form and no "Replace key". But removing a key needs no
 * keyring, so the user can always take theirs back.
 */
function StoredKeyCard({ settings }: { settings: LlmSettings }) {
  const remove = useDeleteLlmKey()

  return (
    <Card>
      <CardTitle>Your Anthropic API key</CardTitle>
      <SavedKey settings={settings} />
      <p className="mt-2 text-sm text-text-muted">{STORED_WHILE_OFF}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove key
        </Button>
      </div>
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {REMOVE_FAILED}
        </p>
      )}
    </Card>
  )
}

function KeyCard({ settings }: { settings: LlmSettings }) {
  const save = useSaveLlmKey()
  const remove = useDeleteLlmKey()
  // Never pre-filled, since the server never sends the key back, and emptied the
  // moment it is sent: a typed key stays in this page no longer than the request.
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(() => initialModel(settings))
  const [replacing, setReplacing] = useState(false)
  // Kept here rather than read from `save.error`, because the mutation is reset
  // as soon as it settles: it holds the key it was sent.
  const [saveError, setSaveError] = useState<string | null>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const typed = apiKey.trim()
    if (typed === '') return
    setApiKey('')
    setSaveError(null)
    save.mutate(
      { api_key: typed, model },
      {
        onSuccess: () => setReplacing(false),
        onError: (failure) => setSaveError(errorDetail(failure, SAVE_FAILED)),
        onSettled: () => save.reset(),
      },
    )
  }

  function startReplacing() {
    setApiKey('')
    setSaveError(null)
    setModel(initialModel(settings))
    setReplacing(true)
  }

  function stopReplacing() {
    setApiKey('')
    setSaveError(null)
    setReplacing(false)
  }

  function removeKey() {
    setSaveError(null)
    remove.mutate(undefined, { onSuccess: () => setReplacing(false) })
  }

  const saved = settings.status === 'ok' && !replacing
  // Whatever was pasted and not sent goes whenever the form opens or closes. The
  // handlers above cover a click. This covers the form closing with no click: a
  // refetch that finds a key saved from another tab puts the saved view in its
  // place, and "Replace key", or the key later turning out refused, would
  // otherwise bring the form back still holding the pasted key.
  const formOpen = !saved
  const [formWasOpen, setFormWasOpen] = useState(formOpen)
  if (formOpen !== formWasOpen) {
    setFormWasOpen(formOpen)
    setApiKey('')
  }
  const needsNewKey = NEEDS_NEW_KEY[settings.status]
  // A key Anthropic refused, or one the server cannot read, can still be removed.
  const removeButton = settings.status !== 'none' && (
    <Button variant="danger" disabled={remove.isPending || save.isPending} onClick={removeKey}>
      Remove key
    </Button>
  )

  return (
    <Card>
      <CardTitle>Your Anthropic API key</CardTitle>

      {saved ? (
        <>
          <SavedKey settings={settings} />
          <p className="mt-2 text-sm text-text-muted">
            Anthropic checks the key against the model it is saved with, so to use another model,
            replace the key and pick it. Descriptions are only added when you ask, from the Plan
            screen.
          </p>
          <Link
            to="/plan"
            className="inline-flex min-h-11 items-center text-sm text-accent underline"
          >
            Open this week’s plan
          </Link>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={startReplacing}>Replace key</Button>
            {removeButton}
          </div>
        </>
      ) : (
        <form className="mt-2" onSubmit={submit}>
          {needsNewKey !== undefined && (
            <p className="mb-3 text-sm text-above-limit">{needsNewKey}</p>
          )}
          <Field label="Anthropic API key" hint={KEY_HINT}>
            {(fieldProps) => (
              <TextInput
                {...fieldProps}
                type="password"
                autoComplete="new-password"
                autoCapitalize="off"
                spellCheck={false}
                placeholder="sk-ant-…"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            )}
          </Field>
          <Field label="Model">
            {(fieldProps) => (
              <Select
                {...fieldProps}
                value={model}
                onChange={(event) => setModel(event.target.value)}
              >
                {settings.models.map((option) => (
                  <option key={option} value={option}>
                    {modelLabel(option)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={apiKey.trim() === '' || save.isPending}
            >
              Save key
            </Button>
            {replacing && (
              <Button variant="quiet" disabled={save.isPending} onClick={stopReplacing}>
                Cancel
              </Button>
            )}
            {removeButton}
          </div>
          {save.isPending && (
            <p role="status" className="mt-2 text-sm text-text-muted">
              Checking the key with Anthropic…
            </p>
          )}
        </form>
      )}

      {saveError !== null && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {saveError}
        </p>
      )}
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {REMOVE_FAILED}
        </p>
      )}
    </Card>
  )
}

export function AiDescriptionsScreen() {
  const settings = useLlmSettings()

  if (settings.isPending) return <Skeleton className="h-64 w-full" />
  if (settings.isError || settings.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your AI description settings could not be loaded. Please try again.
      </p>
    )
  }

  const data = settings.data

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">AI descriptions</h2>
        <p className="mt-1 max-w-prose text-sm text-text-muted">{INTRO}</p>
      </div>

      {data.available ? (
        <>
          <Card>
            <CardTitle>What is sent</CardTitle>
            <p className="mt-1 text-sm">{PRIVACY}</p>
            <p className="mt-2 text-sm text-text-muted">{FALLBACK}</p>
          </Card>
          <KeyCard settings={data} />
        </>
      ) : (
        <>
          <p
            role="note"
            className="rounded-card border border-border bg-surface px-4 py-3 text-sm text-text-muted"
          >
            {NOT_AVAILABLE}
          </p>
          {data.status !== 'none' && <StoredKeyCard settings={data} />}
        </>
      )}
    </section>
  )
}
```

Why it is built this way:
- The save mutation, the error and the "replacing" flag live in `KeyCard`, which stays mounted while the saved state and the form swap places. A per-call `onSuccess` passed to `mutate` only runs while its component is still mounted, and `setReplacing(false)` must run after a replacement is saved.
- The error is copied into state in `onError`, because `onSettled` then resets the mutation, and `save.error` goes with it.
- "Remove key" is offered for `rejected` and `unreadable` too. A key that no longer works is still stored, and removing it is a reasonable thing to want.
- On a server with no keyring, `StoredKeyCard` stands in for `KeyCard` whenever a key is still stored, whatever its status. It shares `SavedKey` with the saved view, and offers only "Remove key": nothing there can check a new key, so there is no form, no "Replace key", and no link to the plan. The note stays the page's only `role="note"` element, which this task's tests rely on.
- `apiKey` lives in `KeyCard`, which stays mounted while the form and the saved view swap places, so closing the form does not empty it. `startReplacing` and `stopReplacing` empty it for a click. The `formWasOpen` check empties it when the form closes or opens with no click, for instance when a refetch finds a key saved from another tab. It sets state during render, React's pattern for adjusting state when what a component is given changes, so the form is never rendered again with the old key in it. An effect would run only after the form had been committed to the page still holding it.
- "Cancel" appears only while replacing a working key. Before there is one, there is nothing to go back to.

In `frontend/src/shell/navigation.ts`, add `Sparkles` to the `lucide-react` import, between `Settings,` and `Users,`:

```ts
  Settings,
  Sparkles,
  Users,
```

Then, in `MORE_NAV`, directly after the line `  { path: '/reminders', label: 'Reminders', icon: ClipboardList },`, add:

```ts
  { path: '/ai-descriptions', label: 'AI descriptions', icon: Sparkles },
```

In `frontend/src/shell/Sidebar.tsx`, the doc comment above `export function Sidebar()` names the destinations behind More. Replace its four lines of text, from ` * The wide-screen navigation.` down to the line that ends `different affordance.`, with:

```ts
 * The wide-screen navigation. A phone has room for five tabs, so Weight, Cycle,
 * Household, Reminders, AI descriptions and Profile hide behind More there — but
 * a 1440px window has room for all of them, and importing the phone's constraint
 * would be gratuitous. Same `navigation.ts` source, different affordance.
```

In `frontend/src/App.tsx`:
- Directly after `import { PlanScreen } from './plan/PlanScreen'`, add:

```tsx
import { AiDescriptionsScreen } from './settings/AiDescriptionsScreen'
```

- Directly after `          <Route path="/reminders" element={<RemindersScreen />} />`, add:

```tsx
          <Route path="/ai-descriptions" element={<AiDescriptionsScreen />} />
```

- [ ] **Step 5: Run the tests and the checks**

From `frontend/`, run: `npx vitest run && npx tsc -b && npm run lint && npm run build`

Expected: all PASS and clean.
- The three files pass in full: 20 tests in `AiDescriptionsScreen.test.tsx`, 9 in `api.test.ts` and 6 in `navigation.test.tsx`.
- No other test renders the new screen or calls `/settings/llm`, so nothing else needs a stub.
- oxlint prints nothing. `MODEL_LABELS` is a constant in `types.ts`, not in a component file, so `react/only-export-components` does not apply to it.

- [ ] **Step 6: Commit**

From the repository root:

```bash
git add frontend/src/settings/types.ts frontend/src/settings/useLlmSettings.ts \
  frontend/src/settings/AiDescriptionsScreen.tsx frontend/src/settings/AiDescriptionsScreen.test.tsx \
  frontend/src/lib/api.ts frontend/src/lib/api.test.ts \
  frontend/src/shell/navigation.ts frontend/src/shell/navigation.test.tsx \
  frontend/src/shell/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add the AI descriptions screen, for the user's own key

A user who wants dish descriptions brings their own Anthropic API key. The new
screen, under More after Reminders, saves it through PUT /settings/llm with a
chosen model, and afterwards shows only what the server sends back: the key's
last four characters and the model's name. A key Anthropic refused, or one the
server can no longer read, asks to be entered again. A server with no
encryption keyring says the feature is not set up there and offers no form,
but a key saved before it lost the keyring can still be removed there.

The key is handled as a secret. The field is a password field that is never
pre-filled, and it is marked new-password, because browsers ignore
autocomplete=off on a password field and fill in a saved password anyway.
It is emptied the moment the form is sent, and a key pasted but not sent is
dropped whenever the form opens or closes. The save mutation is reset once
it settles, after a failed save or a successful one, and kept for no time
after, so the mutation cache does not hold the key for five minutes. A
failed save shows the server's own sentence. errorDetail reads it from the
error body, and falls back to the screen's words for anything that is not a
string detail, such as FastAPI's validation list, which can quote the input.

The screen says what is sent (dish and ingredient names, never health details,
portions or numbers), that Anthropic bills the user's account, and that a
request Claude Opus 5 declines is re-run on another model at that model's
rate.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Descriptions on the Plan screen

This task puts Task 5's descriptions on the Plan screen. It makes two changes.

**The dish rows show the new text.**
- Each plan item now carries `description` and `cooking_note`, null until the user asks for them.
- A description renders as its own line under the dish's name and portion. A cooking tip renders behind a "Cooking tip" disclosure, so a week of tips does not swamp the plan.
- Neither replaces anything. The dish name, the portion and the rationale are the planner's, and they render exactly as they did: the same elements, with the same text. A test compares their HTML with and without descriptions. That is the spec's promise, that polish "never changes a dish, a portion, or a nutrient number", as the screen can check it.

**An "Add descriptions" button sits next to "Regenerate week".**
- It is there only when `GET /settings/llm` says the feature is available and the saved key is `ok`. With no key, a refused key, an unreadable one or a server with no keyring, there is no button. The fix for each of those lives on the AI descriptions screen (Task 6), not here.
- It posts `{start}` to `POST /plan/week/polish`. The answer is the whole week with the descriptions attached, so it replaces the cached week directly and nothing is refetched.
- A polish can succeed and describe nothing. A refusal, an answer cut off at its length limit, and text that fails the server's check all answer 200 with the week as it was. Task 5 puts the number of dishes that got text in the `X-Dishes-Described` header. When it is `0`, a quiet status line (`role="status"`) says "Claude added no new descriptions this time." Without that line the click looks like it did nothing, and a second click sends the same dishes, and bills them, again.
  - `api.post` returns only the body. So `src/lib/api.ts` gains `postWithHeaders`, which returns the headers as well. The fetch moves out of `request` into a shared `send`, so `postWithHeaders` sends exactly as `api.post` does and fails with the same `ApiError`.
  - A missing header, or one that is not a whole number, counts as unknown, and the screen says nothing. That is also what happens if CORS does not expose the header.
- While it runs, which can take a while on a first polish, its label reads "Adding descriptions…". It is disabled while the week regenerates, and "Regenerate week" is disabled while it runs. Each answer replaces the whole cached week, so whichever lands last wins. A polish answered before a regenerate committed would put the old dishes back. The screen reads both from the query client's mutation cache (`useIsMutating` on each mutation's `mutationKey`), not from its own `isPending`. Leaving `/plan` unmounts the screen, and a remounted screen's own mutation observers start idle. The lockout must still hold if the user comes back while a polish, which can take minutes, is still running. Otherwise a second polish would send the same dishes to Anthropic again, on the user's own account.
- A failure shows the server's own sentence in an alert, read with Task 6's `errorDetail`. Task 5's messages are written for the user, for example "Couldn't reach Anthropic. Your plan is unchanged." A failure also refreshes the key's settings, because a key Anthropic refused is marked `rejected` on the server. The button then goes, and the alert, which sits outside the button's condition, stays to say why.

Swap and Lock are left enabled during a polish. Polish writes no plan rows (a backend test watches the SQL to prove it), so a swap or lock sent meanwhile targets a row that still exists. The polish answer is read after its own commit, so it already carries a swap that committed first.

The Plan screen now reads `/settings/llm` on every visit, so every Plan screen test stubs it in `beforeEach`, as "no key saved".

**Files:**
- Modify:
  - `frontend/src/lib/api.ts` (`request`'s fetch moves into a shared `send`, and `postWithHeaders` is appended)
  - `frontend/src/plan/types.ts` (`PlanItem` gains two fields; the header comment says the contract is built)
  - `frontend/src/plan/usePlan.ts` (`PolishResult` and `usePolishWeek`, and a `mutationKey` on `useRegenerateWeek`)
  - `frontend/src/plan/PlanScreen.tsx`
  - `frontend/src/mocks/fixtures/plan.ts` (the two new fields on every item, and a polished week)
- Test: `frontend/src/plan/PlanScreen.test.tsx` (the settings stub in `beforeEach`, `renderScreen` takes an optional client and returns it, and 13 tests appended)

**Interfaces:**
- Consumes:
  - Task 5's endpoint. `POST /plan/week/polish {start: "YYYY-MM-DD"}` answers 200 with the whole `WeekPlan`, like the other plan routes. It answers 409 with a `detail` sentence when there is no key, when the key or model was refused, or when the account has no credit, 502 when Anthropic cannot be reached, 503 when the server has no keyring, and 404 when there is no plan for that week.
  - The same 200 also carries `X-Dishes-Described`: a whole number, how many dishes got text on this request, and `0` when none did. The app calls the API from another origin, and a browser hides from script any response header that CORS does not expose. So `backend/app/main.py`'s `CORSMiddleware` has to list the header in `expose_headers`. If the header does not reach the page, the screen shows no status line and otherwise works as described here.
  - Task 5's `PlanItemOut`, which carries `description: str | None` and `cooking_note: str | None` on every plan route's answer, polish or not.
  - Task 6: `useLlmSettings()` and `LLM_SETTINGS_KEY` from `src/settings/useLlmSettings.ts`, `errorDetail` from `src/lib/api.ts`, and `LlmSettings` from `src/settings/types.ts`.
- Produces:
```ts
// src/lib/api.ts
export async function postWithHeaders<T>(
  path: string,
  body: unknown,
): Promise<{ data: T; headers: Headers }>
    // sends through the same send() as api.post, so it fails with the same ApiError;
    // api's own methods keep their signatures

// src/plan/types.ts
export interface PlanItem {
  // ...plan 6's fields, unchanged...
  description: string | null
  cooking_note: string | null
}

// src/plan/usePlan.ts
export interface PolishResult {
  week: WeekPlan
  described: number | null   // X-Dishes-Described; null when it is missing or not a whole number
}
export function usePolishWeek()
    // mutation (start: string) => POST /plan/week/polish {start} -> PolishResult;
    // mutationKey: ['plan', 'polish'];
    // on success setQueryData(['plan', 'week', start], result.week);
    // on error invalidates LLM_SETTINGS_KEY
export function useRegenerateWeek()
    // unchanged, except it now carries mutationKey: ['plan', 'regenerate']

// src/mocks/fixtures/plan.ts
export const PONGAL_TEXT: { description: string; cooking_note: string }
export const SAMBAR_RICE_TEXT: { description: string; cooking_note: null }
export const POLISHED_PLAN_FIXTURE: WeekPlan   // PLAN_FIXTURE with those two dishes described
```
- The screen's names, for Task 13's end-to-end walk: the button is `Add descriptions` (`Adding descriptions…` while it runs), and it is absent when the server has no keyring. A polish that described nothing shows `Claude added no new descriptions this time.` with `role="status"`.

- [ ] **Step 1: Write the contract as built**

In `frontend/src/plan/types.ts`, replace the header comment

```ts
/**
 * PROPOSED CONTRACT for `GET /plan/week?start=` and the swap/lock/regenerate
 * endpoints — implemented by plan 6.
 */
```

with:

```ts
/**
 * CONTRACT for `GET /plan/week?start=` and the swap, lock and regenerate
 * endpoints, built in plan 6, and for `POST /plan/week/polish`, built in plan 9.
 * Each of them answers the whole `WeekPlan`.
 */
```

Then, in `PlanItem`, directly after the line `  rationale: string | null`, add:

```ts
  /**
   * One sentence on what the dish is, written by Claude once the user asks for
   * descriptions with their own Anthropic key (plan 9). Null until then, and for
   * a dish the model declined or whose text failed the server's check. It sits
   * beside the planner's fields and never replaces one: a description changes no
   * dish, portion, rationale or number.
   */
  description: string | null
  /** A tip for cooking the same dish at home, or null. Only ever set with a description. */
  cooking_note: string | null
```

In `frontend/src/mocks/fixtures/plan.ts`:
1. Replace the import line with:

```ts
import type { CookingView, PlanDay, PlanItem, WeekPlan } from '../../plan/types'
```

2. In `day()`, directly after the line `      rationale: rationale === '' ? null : rationale,`, add:

```ts
      description: null,
      cooking_note: null,
```

3. Directly above `export const COOKING_FIXTURE: CookingView = {`, add:

```ts
/**
 * What `POST /plan/week/polish` attaches (plan 9). The text belongs to the dish,
 * so a dish on two days carries the same words on both. Rice with sambar has no
 * cooking tip: a tip is optional, and one that fails the server's check is dropped.
 */
export const PONGAL_TEXT = {
  description: 'A soft, peppery porridge of rice and moong dal, finished with ghee and cumin.',
  cooking_note: 'Roast the moong dal until it smells nutty before it goes in with the rice.',
}
export const SAMBAR_RICE_TEXT = {
  description: 'Steamed rice under a tangy tamarind and lentil stew full of vegetables.',
  cooking_note: null,
}

const POLISH_TEXT: Record<string, Pick<PlanItem, 'description' | 'cooking_note'>> = {
  'Ven pongal': PONGAL_TEXT,
  'Rice with sambar': SAMBAR_RICE_TEXT,
}

/**
 * PLAN_FIXTURE as the polish endpoint answers it. Every other field is
 * PLAN_FIXTURE's own, because a description never changes a dish, a portion or a
 * rationale.
 */
export const POLISHED_PLAN_FIXTURE: WeekPlan = {
  ...PLAN_FIXTURE,
  days: PLAN_FIXTURE.days.map((planDay) => ({
    ...planDay,
    items: planDay.items.map((item) => ({ ...item, ...POLISH_TEXT[item.dish_name] })),
  })),
}

```

The texts pass Task 5's guard: no digit, no `%`, and none of `polish.BANNED_WORDS`. Both dishes appear on Sunday only, so a test scoped to Sunday finds each once.

- [ ] **Step 2: Write the failing tests**

In `frontend/src/plan/PlanScreen.test.tsx`:

1. Replace the three imports from `import { COOKING_FIXTURE, PLAN_FIXTURE } from '../mocks/fixtures/plan'` down to and including `import { PlanScreen } from './PlanScreen'` with:

```tsx
import {
  COOKING_FIXTURE,
  PLAN_FIXTURE,
  POLISHED_PLAN_FIXTURE,
  PONGAL_TEXT,
  SAMBAR_RICE_TEXT,
} from '../mocks/fixtures/plan'
import { server } from '../mocks/server'
import type { LlmSettings } from '../settings/types'
import { PlanScreen } from './PlanScreen'
import type { WeekPlan } from './types'
import { weekStartIso } from './usePlan'

/** No key saved: the screen offers no descriptions. */
const NO_KEY: LlmSettings = {
  available: true,
  provider: null,
  model: null,
  key_hint: null,
  status: 'none',
  models: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
}
const KEY_SAVED: LlmSettings = {
  ...NO_KEY,
  provider: 'anthropic',
  model: 'claude-opus-5',
  key_hint: 'WXYZ',
  status: 'ok',
}
```

2. In `beforeEach`, directly after the line `    http.get(apiUrl('/households/me'), () => new HttpResponse('no household', { status: 404 })),`, add:

```tsx
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(NO_KEY)),
```

3. Replace `renderScreen` with this version. It returns the client, so a test can wait for the settings query. It also takes an optional client, so a test can mount the screen again on the same cache, the way leaving `/plan` and coming back does in the app:

```tsx
function renderScreen(
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...rendered, queryClient }
}
```

4. Append to the end of the file. The file already imports `waitFor`, `within` and `userEvent`.

```tsx

// --- descriptions (plan 9) ----------------------------------------------------------------

function stubWeek(week: WeekPlan) {
  server.use(http.get(apiUrl('/plan/week'), () => HttpResponse.json(week)))
}

/** A POST that answers only once the returned function is called. */
function holdPost(path: string, answer: WeekPlan): () => void {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.post(apiUrl(path), async () => {
      await held
      return HttpResponse.json(answer)
    }),
  )
  return () => release()
}

test('shows a dish’s description, and its cooking tip behind a disclosure', async () => {
  stubWeek(POLISHED_PLAN_FIXTURE)
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(PONGAL_TEXT.description)).toBeInTheDocument()
  const tip = sunday.getByText(PONGAL_TEXT.cooking_note)
  expect(tip.closest('details')).toContainElement(sunday.getByText('Cooking tip'))
  // A description with no tip shows no empty disclosure.
  const lunch = sunday.getByText('Rice with sambar').closest('li')!
  expect(within(lunch).getByText(SAMBAR_RICE_TEXT.description)).toBeInTheDocument()
  expect(within(lunch).queryByText('Cooking tip')).not.toBeInTheDocument()
})

test('a dish with no description shows neither a description nor a tip', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.queryByText('Cooking tip')).not.toBeInTheDocument()
  expect(sunday.queryByText(PONGAL_TEXT.description)).not.toBeInTheDocument()
})

// The spec's promise: polish never changes a dish, a portion or a rationale. On
// screen, that means the planner's own text renders exactly as it did without it.
test('the dish, its portion and the rationale render the same with a description', async () => {
  async function plannerText(week: WeekPlan): Promise<string[]> {
    stubWeek(week)
    const { unmount } = renderScreen()
    const sunday = await day('Sunday')
    const html = ['Ven pongal', '1.5 cup', 'Closes the morning protein gap with moong dal'].map(
      (text) => sunday.getByText(text).outerHTML,
    )
    unmount()
    return html
  }

  const plain = await plannerText(PLAN_FIXTURE)
  const polished = await plannerText(POLISHED_PLAN_FIXTURE)

  expect(polished).toStrictEqual(plain)
})

test.each([
  ['no key is saved', NO_KEY],
  ['the server has no keyring', { ...NO_KEY, available: false }],
  ['the saved key was refused', { ...KEY_SAVED, status: 'rejected' }],
] as const)('offers no descriptions when %s', async (_case, settings) => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(settings)))
  const { queryClient } = renderScreen()

  await day('Sunday')
  await waitFor(() =>
    expect(queryClient.getQueryState(['settings', 'llm'])?.status).toBe('success'),
  )
  expect(screen.queryByRole('button', { name: /add descriptions/i })).not.toBeInTheDocument()
})

test('adding descriptions sends the week and shows what came back', async () => {
  let posted: unknown = null
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json(POLISHED_PLAN_FIXTURE, {
        headers: { 'X-Dishes-Described': '2' },
      })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  const sunday = await day('Sunday')
  expect(await sunday.findByText(PONGAL_TEXT.description)).toBeInTheDocument()
  expect(posted).toStrictEqual({ start: weekStartIso() })
  // Two dishes got text, so there is nothing to explain.
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

// A refusal, an answer cut short, and text the server's check turned down all
// answer 200 with the week as it was. Only the count tells them from success.
test('a polish that described nothing says so, quietly', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), () =>
      HttpResponse.json(PLAN_FIXTURE, { headers: { 'X-Dishes-Described': '0' } }),
    ),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    /^Claude added no new descriptions this time\.$/,
  )
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled()
})

// Each answer replaces the whole week, so the one landing last would win.
test('descriptions wait while the week regenerates', async () => {
  const release = holdPost('/plan/week/regenerate', PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  renderScreen()

  const describe = await screen.findByRole('button', { name: 'Add descriptions' })
  expect(describe).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: /regenerate week/i }))

  expect(describe).toBeDisabled()
  release()
  await waitFor(() => expect(describe).toBeEnabled())
})

test('the week waits while descriptions are added', async () => {
  const release = holdPost('/plan/week/polish', POLISHED_PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(screen.getByRole('button', { name: 'Adding descriptions…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /regenerate week/i })).toBeDisabled()
  release()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /regenerate week/i })).toBeEnabled(),
  )
  expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled()
  // holdPost's answer has no X-Dishes-Described header. An unknown count says nothing.
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

// The lockout reads the mutation cache, not this screen's own observer, so it
// holds when the user leaves the Plan screen mid-polish and comes back.
test('the lockout holds when the screen is left and opened again mid-polish', async () => {
  const release = holdPost('/plan/week/polish', POLISHED_PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  const { unmount, queryClient } = renderScreen()
  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))
  unmount()

  renderScreen(queryClient)

  expect(await screen.findByRole('button', { name: 'Adding descriptions…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /regenerate week/i })).toBeDisabled()
  release()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled(),
  )
})

test('a failed polish says why in the server’s words, and leaves the plan alone', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), () =>
      HttpResponse.json(
        { detail: "Couldn't reach Anthropic. Your plan is unchanged." },
        { status: 502 },
      ),
    ),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /^Couldn't reach Anthropic\. Your plan is unchanged\.$/,
  )
  expect((await day('Sunday')).getByText('Ven pongal')).toBeInTheDocument()
})

// The server marks a refused key, so the button goes, and the reason stays.
test('a key Anthropic refused takes the button away, and says where to fix it', async () => {
  let status: LlmSettings['status'] = 'ok'
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json({ ...KEY_SAVED, status })),
    http.post(apiUrl('/plan/week/polish'), () => {
      status = 'rejected'
      return HttpResponse.json(
        { detail: 'Anthropic refused your saved key. Replace it under AI descriptions.' },
        { status: 409 },
      )
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Anthropic refused your saved key. Replace it under AI descriptions.',
  )
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: /add descriptions/i })).not.toBeInTheDocument(),
  )
  expect(screen.getByRole('alert')).toBeInTheDocument()
})
```

The tests that expect no button wait until the settings query has succeeded, rather than asserting straight after the plan renders, when the button would be absent anyway.

- [ ] **Step 3: Run them to verify they fail**

From `frontend/`, run: `npx vitest run src/plan/PlanScreen.test.tsx`

Expected: FAIL, `Tests  11 failed | 16 passed (27)`.
- `shows a dish’s description, and its cooking tip behind a disclosure` fails with `Unable to find an element with the text: A soft, peppery porridge of rice and moong dal, finished with ghee and cumin.`
- The three `offers no descriptions when …` tests fail with `expected undefined to be 'success'`, because the screen never reads `/settings/llm` yet.
- The seven tests that click the button fail with `Unable to find role="button" and name "Add descriptions"`.
- The 14 existing tests pass. So do two new ones, which guard the change rather than drive it. `a dish with no description shows neither a description nor a tip` holds because nothing renders the new fields yet. `the dish, its portion and the rationale render the same with a description` holds because the polished fixture's extra fields are not drawn. Once Step 4 draws them, it is what proves they sit beside the planner's text and change none of it.

- [ ] **Step 4: Implement**

In `frontend/src/lib/api.ts`, make two edits. Line 1, `API_BASE`, stays as it is.

1. Replace the whole `request` function, from `async function request<T>(method: string, path: string, body?: unknown): Promise<T> {` down to the `}` that closes it, directly above `export const api = {`, with:

```ts
/** Sends one request. An answer that is not 2xx throws an `ApiError` holding its body. */
async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }
  return response
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await send(method, path, body)
  if (response.status === 204) {
    return null as T
  }
  return (await response.json()) as T
}
```

2. Append to the end of the file, after Task 6's `errorDetail`:

```ts

/**
 * `api.post` for a route whose answer says something in a header as well as in
 * its body. Plan 9's `POST /plan/week/polish` puts how many dishes it described
 * in `X-Dishes-Described`. It sends through the same `send`, so it fails with
 * the same `ApiError`, which `errorDetail` reads as it reads any other.
 */
export async function postWithHeaders<T>(
  path: string,
  body: unknown,
): Promise<{ data: T; headers: Headers }> {
  const response = await send('POST', path, body)
  return { data: (await response.json()) as T, headers: response.headers }
}
```

`api`'s methods keep their signatures and their behaviour: they still call `request`, which now sends through `send`. The three tests in `src/lib/api.test.ts` (credentials, `ApiError` with its status, `null` for a 204) guard that. They pass unchanged in Step 5.

In `frontend/src/plan/usePlan.ts`, replace `import { api } from '../lib/api'` with:

```ts
import { api, postWithHeaders } from '../lib/api'
import { LLM_SETTINGS_KEY } from '../settings/useLlmSettings'
```

In `useRegenerateWeek`, replace

```ts
  return useMutation({
    mutationFn: (start: string) => api.post('/plan/week/regenerate', { start }),
```

with:

```ts
  return useMutation({
    // The Plan screen reads this key from the mutation cache, so its lockout
    // holds across leaving the screen and coming back.
    mutationKey: ['plan', 'regenerate'],
    mutationFn: (start: string) => api.post('/plan/week/regenerate', { start }),
```

Then append to the end of the file:

```ts

/** What a polish answers: the whole week, and how many dishes got text this time. */
export interface PolishResult {
  week: WeekPlan
  /**
   * The `X-Dishes-Described` header. 0 when Claude added nothing: a refusal, an
   * answer cut short and text the server's check turned down all answer 200 with
   * the week as it was. Null when the header is missing or is not a whole
   * number, for example when CORS does not expose it. That counts as unknown,
   * and the screen says nothing.
   */
  described: number | null
}

/**
 * Ask Claude for descriptions of this week's dishes, with the user's own key
 * (plan 9). The server sends only the dishes with no current text, so asking
 * again costs nothing for the ones already described.
 */
export function usePolishWeek() {
  const queryClient = useQueryClient()
  return useMutation({
    // Read by the Plan screen from the mutation cache, like ['plan', 'regenerate'].
    mutationKey: ['plan', 'polish'],
    mutationFn: async (start: string): Promise<PolishResult> => {
      const { data, headers } = await postWithHeaders<WeekPlan>('/plan/week/polish', { start })
      const count = headers.get('X-Dishes-Described')
      const described = count !== null && /^\d+$/.test(count) ? Number(count) : null
      return { week: data, described }
    },
    // The answer is the whole week, descriptions attached, so there is nothing to
    // refetch.
    onSuccess: ({ week }, start) => queryClient.setQueryData(['plan', 'week', start], week),
    // A key Anthropic refused is marked on the server, and the button goes with it.
    onError: () => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }),
  })
}
```

`setQueryData` uses the `start` the mutation was called with, which is the key `useWeekPlan(start)` reads. Every other mutation in this file invalidates `['plan']`. Here the answer is the week, so a refetch would only fetch it again.

The count is read with `/^\d+$/` rather than `Number` alone because `Number('')` is `0`. An empty header would otherwise say that nothing was added.

In `frontend/src/plan/PlanScreen.tsx`, make six edits.

1. Replace the imports from `import { Leaf, Lock, LockOpen, RefreshCw, Shuffle } from 'lucide-react'` down to and including `import { Badge } from '../ui/Badge'` with:

```tsx
import { useIsMutating } from '@tanstack/react-query'
import { Leaf, Lock, LockOpen, RefreshCw, Shuffle, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, errorDetail } from '../lib/api'
import { cx } from '../lib/cx'
import { SLOT_LABELS } from '../log/types'
import { useLlmSettings } from '../settings/useLlmSettings'
import { Badge } from '../ui/Badge'
```

2. Replace the line `import { useRegenerateWeek, useSwapItem, useToggleLock, useWeekPlan, weekStartIso } from './usePlan'` with:

```tsx
import {
  usePolishWeek,
  useRegenerateWeek,
  useSwapItem,
  useToggleLock,
  useWeekPlan,
  weekStartIso,
} from './usePlan'

const POLISH_FAILED = 'The descriptions could not be added. Please try again.'
```

3. In `ItemRow`, replace

```tsx
      <p className="mt-0.5 text-sm font-medium">{item.dish_name}</p>
      <p className="text-xs text-text-muted">{item.portion}</p>

      {item.rationale !== null && (
        <p className="mt-1 text-xs text-text-muted italic">{item.rationale}</p>
      )}
```

with:

```tsx
      <p className="mt-0.5 text-sm font-medium">{item.dish_name}</p>
      <p className="text-xs text-text-muted">{item.portion}</p>

      {/*
        Claude's words sit beside the planner's and replace none of them: the dish
        and portion above, and the rationale below, render exactly as they do
        without a description.
      */}
      {item.description !== null && <p className="mt-1 text-xs">{item.description}</p>}

      {item.rationale !== null && (
        <p className="mt-1 text-xs text-text-muted italic">{item.rationale}</p>
      )}

      {item.cooking_note !== null && (
        <details className="mt-1 text-xs">
          <summary className="cursor-pointer py-1 text-text-muted">Cooking tip</summary>
          <p>{item.cooking_note}</p>
        </details>
      )}
```

4. In `PlanScreen`, directly after `  const regenerate = useRegenerateWeek()`, add:

```tsx
  const polish = usePolishWeek()
  const llm = useLlmSettings()
  // From the mutation cache, not this screen's own observer, so the lockout
  // holds when the user leaves the Plan screen mid-polish and comes back.
  const polishing = useIsMutating({ mutationKey: ['plan', 'polish'] }) > 0
  const regenerating = useIsMutating({ mutationKey: ['plan', 'regenerate'] }) > 0
```

These are hooks, so they go here with the others, before the early returns (`if (plan.isPending) return ...`), not in edit 5.

5. Directly after `  const active = days.find((day) => day.date === selectedDate) ?? days[0]`, add:

```tsx
  // Offered only with a key Anthropic accepted. A missing, refused or unreadable
  // key is put right on the AI descriptions screen, not here.
  const canPolish = llm.data?.available === true && llm.data.status === 'ok'
  // Each answer replaces the whole cached week, so whichever lands last wins: a
  // polish answered before a regenerate committed would put the old dishes back.
  const busy = regenerating || polishing
```

6. Replace the "Regenerate week" button and the `</div>` that closes the toolbar after it:

```tsx
        <Button
          className="ml-auto"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate(start)}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Regenerate week
        </Button>
      </div>
```

with:

```tsx
        <div className="ml-auto flex flex-wrap justify-end gap-2">
          {canPolish && (
            <Button disabled={busy} onClick={() => polish.mutate(start)}>
              <Sparkles className="size-4" aria-hidden="true" />
              {polishing ? 'Adding descriptions…' : 'Add descriptions'}
            </Button>
          )}
          <Button disabled={busy} onClick={() => regenerate.mutate(start)}>
            <RefreshCw className="size-4" aria-hidden="true" />
            Regenerate week
          </Button>
        </div>
      </div>

      {/*
        Outside the button's condition: a key Anthropic refused takes the button
        away, and the reason must stay on screen.
      */}
      {polish.isError && (
        <p role="alert" className="mb-4 text-sm text-above-limit">
          {errorDetail(polish.error, POLISH_FAILED)}
        </p>
      )}

      {/*
        A polish can succeed and describe nothing, and the week comes back as it
        was. Said quietly, so the click does not look as if nothing happened.
      */}
      {polish.isSuccess && polish.data.described === 0 && (
        <p role="status" className="mb-4 text-sm text-text-muted">
          Claude added no new descriptions this time.
        </p>
      )}
```

The status line reads this screen's own `polish` result, as the alert does, so it belongs to the click the user just made. A new polish sets the mutation back to pending, which clears it.

`DayPanel` still receives `regenerating={regenerate.isPending}`, not `busy`, which keeps Swap and Lock enabled during a polish (see the introduction). Leave that line as it is.

- [ ] **Step 5: Run the tests and the checks**

From `frontend/`, run: `npx vitest run && npx tsc -b && npm run lint && npm run build`

Expected: all PASS and clean.
- `PlanScreen.test.tsx` passes in full, 27 tests: the 14 that were there and 13 new.
- `src/lib/api.test.ts` passes unchanged. Its tests go through `request`, which now sends with `send`.
- `tsc -b` finds no other `PlanItem` literal to fix. The fixture's `day()` is the only code that builds one.
- No other test renders the Plan screen, so no other file needs the `/settings/llm` stub.

- [ ] **Step 6: Commit**

From the repository root:

```bash
git add frontend/src/lib/api.ts frontend/src/plan/types.ts frontend/src/plan/usePlan.ts \
  frontend/src/plan/PlanScreen.tsx frontend/src/plan/PlanScreen.test.tsx \
  frontend/src/mocks/fixtures/plan.ts
git commit -m "feat(frontend): show dish descriptions on the Plan screen, on request

Each plan item now carries the description and cooking tip that polish
attaches. A description is a line of its own under the dish and its portion,
and a tip sits behind a Cooking tip disclosure. Neither replaces anything: the
dish name, the portion and the rationale are the planner's and render exactly
as before, which a test checks by comparing their HTML with and without
descriptions.

An Add descriptions button sits next to Regenerate week, shown only when the
server has the feature and the saved key is one Anthropic accepted. It posts
the week to /plan/week/polish, and the answer, the whole week, replaces the
cached one. The two buttons wait for each other, even when the screen is left
and opened again, because each answer replaces the whole week and the one
landing last would win. A failure shows the
server's own sentence, and refreshes the key's settings, so a key Anthropic
refused takes the button with it while the reason stays on screen.

A polish can also succeed and describe nothing, when the model refused or
its text failed the server's check. The route counts the described dishes in
X-Dishes-Described, and at 0 a quiet status line says so, rather than the
click seeming to do nothing. api.post returns only the body, so api.ts gains
postWithHeaders. It sends through the same send() as api.post and fails with
the same ApiError.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Production settings

A first deploy that forgets a secret should stop at boot and say what is wrong. Today it starts, and runs on the development defaults. `Settings` reads everything from the environment, and every setting has a development default. A server that forgets `SESSION_SECRET` signs sessions with a string that is public in this repository, so anyone can forge a session for any user. Nothing refuses it.

This task adds `APP_ENV`, which is `development` unless set. Under `production`, `Settings` refuses to load while any of five settings still has an unsafe value. It names every problem in one error, so a first deploy is fixed in one pass rather than one failed boot per setting. The optional features are not required, because without their keys they switch themselves off: plan 8's VAPID keys, and Task 1's keyring.

Five smaller fixes ride along:
- `DATABASE_URL` accepts the `postgres://` and `postgresql://` forms that Neon and Supabase hand out.
- Alembic escapes `%` in the URL, so a URL-encoded password works.
- Logout deletes the cookie with the same attributes sign-in set it with.
- The lifespan gives the `app.*` loggers a stderr handler at INFO.
- `backend/.python-version` pins the Python the image runs.

**Files:**
- Modify:
  - `backend/app/config.py` (`APP_ENV`, `DEV_SESSION_SECRET`, the URL normaliser, the production refusal)
  - `backend/alembic/env.py` (the `%%` escape)
  - `backend/app/auth/router.py` (`logout`)
  - `backend/app/main.py` (`_configure_logging`, called first in the lifespan)
  - `backend/.env.example` (the production block)
- Create: `backend/.python-version`
- Test: `backend/tests/test_config.py` (create), `backend/tests/test_app_logging.py` (create), `backend/tests/test_auth_api.py` (append)

**Interfaces:**
- Consumes:
  - Plan 8 Task 10's `Settings` fields (`vapid_public_key`, `vapid_private_key`, `vapid_subject`, `scheduler_enabled`) and its `backend/.env.example`.
  - Plan 8 Task 11's `app/main.py`: `import logging`, `logger = logging.getLogger(__name__)`, and `lifespan`.
  - Task 1's last field, `llm_key_encryption_keys: str = ""`.
  - Task 4's keyring check in `lifespan`, which this task leaves where it is.
- Produces:
```python
# app/config.py
DEV_SESSION_SECRET = "dev-only-insecure-secret-change-me"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "production"] = "development"
    session_secret: str = DEV_SESSION_SECRET
    # ...every other field unchanged...

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_psycopg(cls, value: object) -> object
        # "postgres://..." and "postgresql://..." -> "postgresql+psycopg://...";
        # anything else is returned as given

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self
        # app_env == "production" and any problem ->
        # ValueError("Refusing to start in production: " + "; ".join(problems)),
        # with the problems in this order:
        #   "SESSION_SECRET is the development default or shorter than 32 characters"
        #   "GOOGLE_CLIENT_ID is empty"
        #   "COOKIE_SECURE must be true"
        #   "FRONTEND_ORIGIN must be an https:// origin with no trailing slash"
        #   "DATABASE_URL points at localhost"        (localhost, 127.0.0.1 or ::1)

# app/main.py
def _configure_logging() -> None
    # one StreamHandler (stderr, format "%(levelname)s [%(name)s] %(message)s") on
    # logging.getLogger("app"), which is set to INFO; nothing at all when that logger
    # already has a handler
```
- Pydantic wraps the refusal: `Settings()` raises `pydantic.ValidationError`, and `str()` of that error contains the whole `Refusing to start in production: …` line. Because of `hide_input_in_errors`, it never contains a setting's value. Task 9's image check and Task 12's CI step match on `Refusing to start in production`.
- `POST /auth/logout` answers 204 with `Set-Cookie: <name>=""; expires=…; HttpOnly; Max-Age=0; Path=/; SameSite=lax`, plus `; Secure` when `COOKIE_SECURE` is true.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_config.py`:

```python
"""Settings: what production refuses, and the database URL forms hosts hand out.

Every Settings here is built with `_env_file=None`, and the fixture below takes
every setting out of the process environment, so neither a developer's
backend/.env nor CI's exported DATABASE_URL can decide an outcome.
"""

import pytest
from pydantic import ValidationError

from app.config import DEV_SESSION_SECRET, Settings

# Production-shaped and safe. Each refusal below changes one of these.
CLEAN_PRODUCTION = {
    "app_env": "production",
    "session_secret": "s" * 48,
    "google_client_id": "1234567890-abcdef.apps.googleusercontent.com",
    "cookie_secure": True,
    "frontend_origin": "https://app.example.com",
    "database_url": "postgresql+psycopg://hm:db-password@db.example.com:5432/hm?sslmode=require",
}

# The wording is pinned here, not imported: the image check in CI and the
# deploy runbook quote it.
SECRET = "SESSION_SECRET is the development default or shorter than 32 characters"
CLIENT_ID = "GOOGLE_CLIENT_ID is empty"
COOKIE = "COOKIE_SECURE must be true"
ORIGIN = "FRONTEND_ORIGIN must be an https:// origin with no trailing slash"
DATABASE = "DATABASE_URL points at localhost"


@pytest.fixture(autouse=True)
def bare_environment(monkeypatch):
    """Only what a test passes reaches Settings."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def refusal(**unsafe: object) -> str:
    """The one error Settings refuses CLEAN_PRODUCTION with, once `unsafe` is applied."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **{**CLEAN_PRODUCTION, **unsafe})
    [error] = excinfo.value.errors()
    return str(error["ctx"]["error"])


# --- production --------------------------------------------------------------------------


def test_a_clean_production_config_loads():
    configured = Settings(_env_file=None, **CLEAN_PRODUCTION)

    assert configured.app_env == "production"
    assert configured.database_url == CLEAN_PRODUCTION["database_url"]


@pytest.mark.parametrize(
    ("unsafe", "problem"),
    [
        pytest.param({"session_secret": DEV_SESSION_SECRET}, SECRET, id="development-secret"),
        pytest.param({"session_secret": "s" * 31}, SECRET, id="short-secret"),
        pytest.param({"google_client_id": ""}, CLIENT_ID, id="no-client-id"),
        pytest.param({"google_client_id": "   "}, CLIENT_ID, id="blank-client-id"),
        pytest.param({"cookie_secure": False}, COOKIE, id="insecure-cookie"),
        pytest.param({"frontend_origin": "http://app.example.com"}, ORIGIN, id="http-origin"),
        pytest.param({"frontend_origin": "https://app.example.com/"}, ORIGIN, id="trailing-slash"),
        pytest.param({"frontend_origin": "https://app.example.com/app"}, ORIGIN, id="origin-path"),
        pytest.param(
            {"database_url": "postgresql+psycopg://hm:pw@localhost:5432/hm"},
            DATABASE,
            id="localhost-database",
        ),
        pytest.param(
            {"database_url": "postgresql+psycopg://hm:pw@127.0.0.1/hm"},
            DATABASE,
            id="loopback-database",
        ),
        # Normalised first, then checked.
        pytest.param(
            {"database_url": "postgres://hm:pw@localhost/hm"}, DATABASE, id="libpq-localhost"
        ),
    ],
)
def test_each_unsafe_setting_is_refused_on_its_own(unsafe, problem):
    assert refusal(**unsafe) == f"Refusing to start in production: {problem}"


def test_every_problem_is_named_at_once():
    """The development defaults, as a first deploy that forgot every secret has them."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, app_env="production")

    [error] = excinfo.value.errors()
    assert str(error["ctx"]["error"]) == (
        f"Refusing to start in production: {SECRET}; {CLIENT_ID}; {COOKIE}; {ORIGIN}; {DATABASE}"
    )


def test_a_32_character_secret_is_long_enough():
    configured = Settings(_env_file=None, **{**CLEAN_PRODUCTION, "session_secret": "s" * 32})
    assert len(configured.session_secret) == 32


def test_a_port_on_the_origin_is_fine():
    origin = "https://app.example.com:8443"
    configured = Settings(_env_file=None, **{**CLEAN_PRODUCTION, "frontend_origin": origin})
    assert configured.frontend_origin == origin


def test_the_refusal_never_repeats_a_value():
    """Pydantic's message would otherwise end with its input: on a platform's log
    stream, the tail of DATABASE_URL or the session secret."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            app_env="production",
            session_secret="short-secret",
            database_url="postgresql+psycopg://hm:s3cret-pw@localhost/hm",
        )

    message = str(excinfo.value)
    assert "Refusing to start in production" in message
    assert "short-secret" not in message
    assert "s3cret-pw" not in message


def test_app_env_is_read_from_the_environment(monkeypatch):
    """As fly.toml's [env] sets it."""
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ValidationError, match="Refusing to start in production"):
        Settings(_env_file=None)


def test_a_misspelt_app_env_is_refused_rather_than_read_as_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValidationError, match="app_env"):
        Settings(_env_file=None)


# --- development -------------------------------------------------------------------------


def test_development_accepts_the_defaults():
    configured = Settings(_env_file=None)

    assert configured.app_env == "development"
    assert configured.session_secret == DEV_SESSION_SECRET
    assert configured.google_client_id == ""
    assert configured.cookie_secure is False
    assert configured.frontend_origin == "http://localhost:5173"
    assert "@localhost:5433/" in configured.database_url


# --- database URLs -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "used"),
    [
        pytest.param(
            "postgres://hm:pw@db.example.com/hm",
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            id="postgres",
        ),
        pytest.param(
            "postgresql://hm:pw@db.example.com/hm?sslmode=require",
            "postgresql+psycopg://hm:pw@db.example.com/hm?sslmode=require",
            id="postgresql",
        ),
        pytest.param(
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            id="already-psycopg",
        ),
        pytest.param(
            "postgres://hm:p%40ss@db.example.com/hm",
            "postgresql+psycopg://hm:p%40ss@db.example.com/hm",
            id="encoded-password-kept",
        ),
        pytest.param("sqlite:///scratch.db", "sqlite:///scratch.db", id="not-postgres"),
    ],
)
def test_database_urls_are_pointed_at_psycopg(given, used):
    configured = Settings(_env_file=None, database_url=given, test_database_url=given)

    assert (configured.database_url, configured.test_database_url) == (used, used)


def test_a_database_url_from_the_environment_is_normalised_too(monkeypatch):
    """The way a platform secret arrives."""
    monkeypatch.setenv("DATABASE_URL", "postgres://hm:pw@db.example.com/hm")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://hm:pw@db.example.com/hm"
```

None of these tests uses the `db` fixture, so the file runs without the test database. The fake secrets are obviously fake, and the password check in `test_the_refusal_never_repeats_a_value` is what guards `hide_input_in_errors`. Without that setting, pydantic ends the message with `input_value={'app_env': 'production',...secret': 'short-secret'}`.

Create `backend/tests/test_app_logging.py`:

```python
"""The app's own log lines reach stderr, where a platform's log stream reads them.

Uvicorn configures only its own loggers, so the lifespan gives the `app` logger
a handler. These tests start from a bare `app` logger and put back whatever an
earlier test's lifespan left there, because a handler added here would write to
this test's captured stderr after the test is over.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def app_logger():
    """The `app` logger as a new process has it: no handler, no level of its own."""
    logger = logging.getLogger("app")
    saved_handlers, saved_level = logger.handlers[:], logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    yield logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.setLevel(saved_level)


def test_the_lifespan_sends_the_apps_info_lines_to_stderr(app_logger, capsys):
    with TestClient(app):
        logging.getLogger("app.reminders.runner").info("reminders sent: 3")

    assert "INFO [app.reminders.runner] reminders sent: 3" in capsys.readouterr().err


def test_a_second_lifespan_adds_no_second_handler(app_logger):
    with TestClient(app):
        pass
    with TestClient(app):
        pass

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.INFO


def test_a_handler_configured_elsewhere_is_left_alone(app_logger):
    """As a uvicorn --log-config that names the `app` logger would leave it."""
    theirs = logging.NullHandler()
    app_logger.addHandler(theirs)
    app_logger.setLevel(logging.WARNING)

    with TestClient(app):
        pass

    assert app_logger.handlers == [theirs]
    assert app_logger.level == logging.WARNING
```

These tests enter the app's lifespan without the `db` fixture. Plan 8's session-wide `scheduler_off` fixture keeps the reminder loop out, and nothing in the lifespan opens a connection.

In `backend/tests/test_auth_api.py`, add this import directly after `from app.auth import google as google_auth`:

```python
from app.config import settings
```

Then append to the end of the file:

```python


# --- logout deletes the cookie it set ------------------------------------------------
#
# A browser replaces a cookie only with a Set-Cookie it accepts. Under a __Host-
# or __Secure- name, one without Secure is rejected outright, so a bare deletion
# would leave the session in place. The deletion carries what the sign-in set.


def _flags(response) -> set[str]:
    """The attributes of the response's one Set-Cookie, less its value and lifetime."""
    _, *attributes = (part.strip() for part in response.headers["set-cookie"].split(";"))
    return {
        attribute
        for attribute in attributes
        if not attribute.lower().startswith(("expires=", "max-age="))
    }


def test_logout_deletes_the_cookie_with_the_attributes_it_was_set_with(api, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    _accept_google_token(monkeypatch)
    sign_in = api.post("/auth/google", json={"credential": "t"})

    logout = api.post("/auth/logout")

    assert logout.status_code == 204
    header = logout.headers["set-cookie"]
    assert header.startswith(f"{settings.session_cookie_name}=")
    assert "Max-Age=0" in header
    assert {"HttpOnly", "SameSite=lax", "Secure"} <= _flags(logout)
    assert _flags(logout) == _flags(sign_in)


def test_a_development_logout_matches_a_development_sign_in(api, monkeypatch):
    # Set explicitly: a developer's backend/.env may turn COOKIE_SECURE on.
    monkeypatch.setattr(settings, "cookie_secure", False)
    _accept_google_token(monkeypatch)
    sign_in = api.post("/auth/google", json={"credential": "t"})

    logout = api.post("/auth/logout")

    assert "Secure" not in _flags(logout)
    assert _flags(logout) == _flags(sign_in)
```

- [ ] **Step 2: Run them to verify they fail**

From `backend/`, run: `uv run pytest tests/test_config.py -q`

Expected: FAIL at collection, with `ImportError: cannot import name 'DEV_SESSION_SECRET' from 'app.config'`.

Run: `uv run pytest tests/test_app_logging.py tests/test_auth_api.py -q`

Expected: 4 failed, 7 passed.
- `test_the_lifespan_sends_the_apps_info_lines_to_stderr` fails with `assert 'INFO [app.reminders.runner] reminders sent: 3' in ''`. With no handler on `app`, the root logger's WARNING level drops an INFO line.
- `test_a_second_lifespan_adds_no_second_handler` fails with `assert 0 == 1`.
- `test_logout_deletes_the_cookie_with_the_attributes_it_was_set_with` fails on the subset assertion, because the deletion carries only `Path=/` and `SameSite=lax`.
- `test_a_development_logout_matches_a_development_sign_in` fails with `{'Path=/', 'SameSite=lax'} == {'HttpOnly', 'Path=/', 'SameSite=lax'}`.
- `test_a_handler_configured_elsewhere_is_left_alone` already passes, because nothing adds a handler yet. It guards the implementation, which must not replace one.
- The six existing auth tests pass.

- [ ] **Step 3: The production settings**

In `backend/app/config.py`, make five edits.

1. Replace the first line, `from pydantic_settings import BaseSettings, SettingsConfigDict`, with:

```python
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The session secret's development default. It is public -- it is written right
# here -- so a server that signs sessions with it lets anyone sign one for any
# user. Production refuses it, and any secret shorter than 32 characters.
DEV_SESSION_SECRET = "dev-only-insecure-secret-change-me"
_MIN_SECRET_LENGTH = 32

# The URL forms Neon and Supabase hand out. SQLAlchemy no longer accepts
# postgres:// at all, and reads postgresql:// as psycopg2, which is not installed.
_LIBPQ_SCHEMES = ("postgres://", "postgresql://")
_PSYCOPG_SCHEME = "postgresql+psycopg://"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_https_origin(value: str) -> bool:
    """`https://host[:port]` and nothing after it.

    CORS compares FRONTEND_ORIGIN with the browser's Origin header character for
    character, and that header never carries a path or a trailing slash.
    """
    parts = urlsplit(value)
    return (
        value.startswith("https://")
        and bool(parts.hostname)
        and not parts.path
        and not parts.query
        and not parts.fragment
    )
```

2. Replace `    model_config = SettingsConfigDict(env_file=".env", extra="ignore")` with:

```python
    # hide_input_in_errors: pydantic ends a validation message with the input it
    # was given. On a platform's log stream, a refusal would print the tail of
    # DATABASE_URL or a secret.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # "production" makes _refuse_unsafe_production below check the settings that
    # must never keep their development default. fly.toml sets it.
    app_env: Literal["development", "production"] = "development"
```

3. Replace `    session_secret: str = "dev-only-insecure-secret-change-me"` with:

```python
    session_secret: str = DEV_SESSION_SECRET
```

4. Directly after Task 1's field `    llm_key_encryption_keys: str = ""`, the last field of the class, add:

```python

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_psycopg(cls, value: object) -> object:
        """Point a libpq-style URL at psycopg 3, the driver this project installs."""
        if isinstance(value, str):
            for scheme in _LIBPQ_SCHEMES:
                if value.startswith(scheme):
                    return _PSYCOPG_SCHEME + value.removeprefix(scheme)
        return value

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self:
        """In production, refuse every development default that is unsafe there.

        Every problem is named in one error, so a first deploy is fixed in one
        pass rather than one failed boot per setting. Reminders and AI
        descriptions are not required: without their keys they switch themselves
        off.
        """
        if self.app_env != "production":
            return self
        problems = []
        if (
            self.session_secret == DEV_SESSION_SECRET
            or len(self.session_secret) < _MIN_SECRET_LENGTH
        ):
            problems.append(
                "SESSION_SECRET is the development default or shorter than 32 characters"
            )
        if not self.google_client_id.strip():
            problems.append("GOOGLE_CLIENT_ID is empty")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if not _is_https_origin(self.frontend_origin):
            problems.append("FRONTEND_ORIGIN must be an https:// origin with no trailing slash")
        if urlsplit(self.database_url).hostname in _LOCAL_HOSTS:
            problems.append("DATABASE_URL points at localhost")
        if problems:
            raise ValueError("Refusing to start in production: " + "; ".join(problems))
        return self
```

5. Leave `settings = Settings()` at the bottom as it is. A production misconfiguration therefore fails at the first `import app.config`: uvicorn's app import, alembic's `env.py`, and every script. That is where it should fail.

Notes on these choices:
- The field validator runs in `before` mode, so it sees the raw string from the environment or `.env`. It does not run on the defaults, which are already `+psycopg`.
- `urlsplit().hostname` is lower-cased, and it drops the brackets from `[::1]`, so `LOCALHOST` and IPv6 loopback are caught too.
- The origin check is stricter than "starts with https:// and has no trailing slash". It also refuses a path, a query or a fragment, which CORS would never match either. The message covers all of them.

- [ ] **Step 4: Logout mirrors the cookie's attributes**

In `backend/app/auth/router.py`, replace the body of `logout`, `    response.delete_cookie(settings.session_cookie_name)`, with:

```python
    # The attributes sign-in set it with. From https a bare deletion clears the
    # cookie today, but under a __Host- or __Secure- name a Set-Cookie without
    # Secure is rejected outright, and logout would quietly leave the session.
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
```

Starlette's `delete_cookie` defaults are `secure=False, httponly=False, samesite="lax"`, and its `path` default of `/` already matches the sign-in. Sign-in sets no `domain`, so the deletion sets none either.

- [ ] **Step 5: The app's loggers reach stderr**

In `backend/app/main.py`, directly below plan 8's `logger = logging.getLogger(__name__)`, add:

```python


def _configure_logging() -> None:
    """Send the app's own loggers to stderr at INFO, where the platform's log stream reads.

    Uvicorn configures only its own loggers. Without this an `app.*` INFO line is
    dropped, and a warning reaches stderr only through logging's last-resort
    handler, with no level or logger name on it. Records still propagate to the
    root logger, which has no handler under uvicorn, and which pytest's caplog
    reads. A handler already on `app` -- from a --log-config, or an earlier
    lifespan in the same process -- means this has been done, and it is left alone.
    """
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
```

Then, in `lifespan`, make `_configure_logging()` the first statement of the body, directly below the docstring and above everything plan 8 and Task 4 put there. Leave the docstring and the rest of the body as they are. The top of the function then reads:

```python
@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """…the docstring, unchanged…"""
    _configure_logging()
    # …then the body as it was: Task 4's keyring check, and plan 8's `task = None` onwards.
```

It goes first so that anything the rest of the lifespan logs is already formatted and on stderr. That includes plan 8's warning, "SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders".

The handler goes on the `app` logger, not the root logger. Under uvicorn the root logger has no handler, so nothing is printed twice. A library's own INFO chatter (`httpx`, `anthropic`) also stays out of the stream: Task 3's provider logs are the app's, not the SDK's.

- [ ] **Step 6: Run the tests to verify they pass**

From `backend/`, run: `uv run pytest tests/test_config.py tests/test_app_logging.py tests/test_auth_api.py tests/test_health.py -q`

Expected: all PASS: 25 in `test_config.py`, 3 in `test_app_logging.py`, 8 in `test_auth_api.py` and 1 in `test_health.py`, so 37 passed.

- [ ] **Step 7: Alembic reads a URL-encoded password**

`alembic/env.py` hands the URL to `config.set_main_option`, which is a ConfigParser `set`. ConfigParser reads `%` as the start of an interpolation, so a password with a URL-encoded character fails before alembic connects. Neon generates passwords that may need encoding, and so does any password manager.

First, show the failure. `%68` is a URL-encoded `h`, so this URL carries the real development password:

From `backend/`, run: `DATABASE_URL='postgresql+psycopg://healthmonitor:%68ealthmonitor@localhost:5433/healthmonitor' uv run alembic current`

Expected: FAIL. The traceback ends with `ValueError: invalid interpolation syntax in 'postgresql+psycopg://healthmonitor:%68ealthmonitor@localhost:5433/healthmonitor' at position 35`.

In `backend/alembic/env.py`, replace `config.set_main_option("sqlalchemy.url", settings.database_url)` with:

```python
# set_main_option is a ConfigParser set, which reads "%" as the start of an
# interpolation: a URL-encoded password ("p%40ss") would fail before connecting.
# "%%" is ConfigParser's escape, and alembic reads the URL back unescaped.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
```

Run the same command again.

Expected: PASS. It prints `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.`, then `INFO  [alembic.runtime.migration] Will assume transactional DDL.`, then `a3b4c5d6e7f8 (head)`. `alembic current` only reads `alembic_version`. SQLAlchemy decodes `%68` back to `h` before psycopg connects.

- [ ] **Step 8: Document it, and pin the Python version**

In `backend/.env.example` (plan 8), directly after the line `# FRONTEND_ORIGIN=http://localhost:5173` and the blank line below it, and before the line `# --- Meal reminders, by web push ---------------------------------------------`, add:

```
# --- Production --------------------------------------------------------------
# APP_ENV=production (fly.toml sets it) makes the API refuse to start, naming
# every problem at once, while any of these holds:
#   SESSION_SECRET is the development default or shorter than 32 characters,
#   GOOGLE_CLIENT_ID is empty, COOKIE_SECURE is not true,
#   FRONTEND_ORIGIN is not an https:// origin without a trailing slash,
#   DATABASE_URL points at localhost.
# Reminders and AI descriptions are optional there. A postgres:// or
# postgresql:// DATABASE_URL, as Neon and Supabase hand it out, is read as
# postgresql+psycopg://, and a URL-encoded password (%40 for @) works as it is.
# APP_ENV=development

```

Like every other line in the file, `APP_ENV` stays commented out, so copying the file to `.env` changes nothing.

Create `backend/.python-version` containing exactly one line:

```
3.13
```

uv reads this file for every `uv run` and `uv sync` in `backend/`. It is the Python the image runs (Task 9), and CI reads it too (Task 12), so tests stop running on the CI runner's system 3.12. The development virtualenv is already 3.13, so nothing is rebuilt.

From `backend/`, run: `uv run python --version`

Expected: `Python 3.13.9` (any 3.13.x). If uv recreates the virtualenv first, the old one was on another minor version, and the next `uv run` is back to normal.

- [ ] **Step 9: Lint, and the files around these changes**

From `backend/`, run: `uv run ruff check . && uv run pytest tests/test_config.py tests/test_app_logging.py tests/test_auth_api.py tests/test_health.py tests/test_reminders_api.py tests/test_llm_settings_api.py -q`

Expected: ruff reports `All checks passed!`, and every test passes. The reminders and LLM settings suites run the lifespan through every API test, so they show that the logging change breaks no lifespan. They also show that the development `.env` still loads under the new validators.

Then check that no `Settings` in the suite trips the refusal by accident:

Run: `grep -rn --include='*.py' "app_env" app tests scripts`

Expected: the only matches are in `app/config.py` and `tests/test_config.py`. The `--include='*.py'` filter keeps grep out of `__pycache__`. Without it, after the test run above, grep also prints `Binary file app/__pycache__/config.cpython-313.pyc matches` and a matching line for the test module's `.pyc`.

- [ ] **Step 10: Commit**

From the repository root:

```bash
git add backend/app/config.py backend/alembic/env.py backend/app/auth/router.py \
  backend/app/main.py backend/.env.example backend/.python-version \
  backend/tests/test_config.py backend/tests/test_app_logging.py backend/tests/test_auth_api.py
git commit -m "feat(backend): refuse to start in production on development settings

APP_ENV=production makes Settings refuse the development defaults that are
unsafe on a real server, and name every problem in one error so a first
deploy is fixed in one pass: the public session secret or any secret under
32 characters, an empty Google client id, insecure cookies, an origin that
is not bare https, and a localhost database. The error hides its input,
because pydantic would otherwise end it with the tail of DATABASE_URL, and
that lands on the platform's log stream. Reminders and AI descriptions stay
optional; without their keys they switch themselves off.

DATABASE_URL accepts the postgres:// and postgresql:// forms Neon and
Supabase hand out, rewritten to psycopg 3, since SQLAlchemy would reach for
psycopg2. Alembic escapes % before ConfigParser sees the URL, so a
URL-encoded password works.

Logout deletes the session cookie with the attributes sign-in set it with.
Under a __Host- name a deletion without Secure is rejected, and the user
would stay signed in.

The lifespan gives the app.* loggers a stderr handler at INFO, so the
reminder loop's and the provider's lines reach the platform's log stream.
backend/.python-version pins 3.13, the Python the image runs.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

---

## Task 9: The backend image and Fly config

The API has never run anywhere but `uv run uvicorn` on a laptop. This task writes the three files a Fly.io deploy needs and rehearses them against the compose Postgres: the image build, the release step, a production-mode boot and the refusal. Nothing is deployed: no `flyctl`, no registry and no account.

What matters for this app is:
- **Exactly one always-on process.** Plan 8's lifespan starts a reminder loop in every uvicorn worker, and a stopped machine sends no reminders.
- **Migrations run as the release step, never in the `CMD`.** Two machines starting together would race on the same migration.
- **Nothing local reaches the image.** `Settings` reads `.env` from the working directory, so a developer's `.env` baked in would quietly override the platform's secrets. The ETL's downloads carry IFCT data, which has no open licence.

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`, `backend/fly.toml`
- Test: none in pytest. Step 4 to Step 8 are the checks, run against the built image. Task 12 turns the same checks into a CI job.

**Interfaces:**
- Consumes:
  - Task 8: `backend/.python-version` (the Dockerfile copies it, so the build fails without it). Also Task 8's `APP_ENV` refusal, whose text contains `Refusing to start in production`, the `%%` escape in `alembic/env.py`, the `postgres://` normaliser and the `app` log handler.
  - Plan 8's lifespan warning, `SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders`, logged by `app.main`.
  - Task 4's `scripts/rotate_llm_keys.py`. Step 5 imports it from `/`, to prove `PYTHONPATH`.
  - `etl/common.py`'s `CACHE_DIR = Path(__file__).parent / ".cache"`, which is `/app/etl/.cache` in the image. Task 11's `.part` files land in the same directory.
  - `alembic.ini`'s `script_location = %(here)s/alembic` and `prepend_sys_path = .`, so alembic runs from `WORKDIR /app`.
- Produces, for Task 12 (CI) and Task 13 (`DEPLOY.md`):
  - Build: `docker build -t <tag> backend` from the repository root. The context is `backend/`.
  - The image runs as uid:gid `10001:10001`, with `WORKDIR /app`, `/app/.venv/bin` first on `PATH`, and `PYTHONPATH=/app`.
    - `alembic`, `uvicorn` and `python` resolve to the virtualenv.
    - `python -m scripts.<name>` and `python -m etl.run_all` work from any working directory, so a `fly ssh console` session need not start in `/app`. `alembic` still reads `alembic.ini` from the working directory, so it runs from `/app`.
    - The code is root-owned and read-only. `/app/etl/.cache` is the one writable directory.
  - It has no `/app/.env`, `/app/tests`, `/app/scripts/e2e_*.py` or `/app/seed-snapshot`.
  - `EXPOSE 8000`. `ENV PORT=8000 FORWARDED_ALLOW_IPS="*" PYTHONPATH=/app`.
  - The builder stage carries `LABEL healthmonitor.stage=builder`, and the runtime image does not. After a local build, `docker rmi <tag>` and then `docker image prune -f --filter label=healthmonitor.stage=builder` remove what the build left behind. No other dangling image is touched.
  - `CMD`: `sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --no-server-header'`.
  - The release step is `alembic upgrade head`, run in the image with the app's environment.
  - `fly.toml`: app `healthmonitor-api`, region `bom`, `[env] APP_ENV = "production"`, `internal_port = 8000`, `auto_stop_machines = "off"`, `min_machines_running = 1`, a `GET /health` check, and no secrets.

- [ ] **Step 1: Write the Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
# The API image. From the repository root:
#   docker build -t healthmonitor-api backend
#
# Two stages on the same base image, so the virtualenv built in the first finds
# its interpreter at the same path in the second. The runtime stage holds the
# virtualenv and the code, both owned by root, and runs as an unprivileged user
# that can write only the ETL's download cache.
#
# No BuildKit-only syntax (RUN --mount, COPY --link): CI builds with BuildKit,
# and colima's docker without the buildx plugin falls back to the classic
# builder, which rejects both.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# The classic builder keeps this stage as an untagged image, virtualenv and uv
# included. The label lets a cleanup remove it without touching any other
# dangling image:
#   docker image prune -f --filter label=healthmonitor.stage=builder
LABEL healthmonitor.stage=builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

# UV_COMPILE_BYTECODE: compile the dependencies here, because the runtime user
# cannot write __pycache__. UV_PYTHON_DOWNLOADS=0: use this image's Python, never
# a downloaded one, so the virtualenv's interpreter exists in the runtime stage.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Only what decides the dependencies, so a code change does not reinstall them.
# --locked fails the build when uv.lock is out of step with pyproject.toml.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . /app

# The one directory the app writes to: etl/common.py's CACHE_DIR, used when the
# ETL is run inside the container.
RUN mkdir -p /app/etl/.cache && chown app:app /app/etl/.cache

# PYTHONPATH: app, scripts and etl import from any working directory, so
# `python -m scripts.<name>` also works in a `fly ssh console` session that does
# not start in WORKDIR.
# FORWARDED_ALLOW_IPS: trust X-Forwarded-Proto from the platform's proxy, the only
# way in, so a redirect FastAPI builds says https. Uvicorn reads it from here.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FORWARDED_ALLOW_IPS="*"

USER 10001:10001
EXPOSE 8000

# One worker: plan 8's lifespan starts a reminder loop in every worker process,
# and --workers stops a WEB_CONCURRENCY set by a platform from multiplying it.
# exec, so uvicorn is PID 1 and gets the platform's SIGTERM. Migrations are not
# run here: they are the platform's release step (fly.toml).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --no-server-header"]
```

Why it is shaped this way:
- **No `RUN --mount` cache for uv.** On this repo's colima setup, `docker buildx` is not installed, so `docker build` is the classic builder, and that answers `the --mount option requires BuildKit`. The dependency layer is keyed on `pyproject.toml`, `uv.lock` and `.python-version` instead, so a code change reuses it. `UV_NO_CACHE=1` keeps uv's download cache out of that layer.
- **The project installs nothing of its own.** `pyproject.toml` has no `[build-system]`, so uv treats it as a virtual project, and `--no-install-project` only states that.
- **`PYTHONPATH=/app` puts the code on `sys.path` from any working directory.**
  - `python -m scripts.<name>` and `python -m etl.run_all` then work in a `fly ssh console` session, which need not start in `WORKDIR`.
  - Without it, `import app.main` run from `/` fails with `No module named 'app.main'`. The only `app` Python finds there is the `/app` directory itself, as a namespace package.
  - `alembic` still reads `alembic.ini` from the working directory, so it runs from `/app`. `/app/alembic` has no `__init__.py`, so it cannot shadow the installed `alembic` package.
- **`LABEL healthmonitor.stage=builder`.**
  - The classic builder keeps the builder stage as an untagged image holding the whole virtualenv and uv. `docker rmi` of the tag does not remove it.
  - The label lets Step 9 prune that image with a filter that matches no other dangling image on the machine.
  - The runtime stage starts again from the base image, so it does not inherit the label.
- **No extra system packages.** `psycopg[binary]` bundles libpq, and `cryptography`, `uvloop` and `httptools` ship manylinux wheels.
- **`useradd` without `--system`.** With `--system`, a uid above 999 makes `useradd` print a warning on every build.
- **`--proxy-headers` is uvicorn's default,** and is written out because `FORWARDED_ALLOW_IPS="*"` depends on it. Trusting every forwarder is safe only because the platform's proxy is the only way in.
- **`--no-server-header`** stops announcing `uvicorn` on every response.

- [ ] **Step 2: Write the .dockerignore**

Create `backend/.dockerignore`:

```
# What the image must never carry. The build context is backend/.

# Local settings and secrets. Settings reads .env from the working directory,
# so one baked in would quietly override the platform's environment.
.env
.env.*

# Local tooling and caches.
.venv
.pytest_cache
.ruff_cache
**/__pycache__
**/*.py[cod]
**/.DS_Store

# The tests, and the development-only scripts: e2e_session.py signs a real
# session for any user it is pointed at.
tests
scripts/e2e_*.py

# Downloaded ETL sources and the seed snapshot. Both are large, and IFCT has no
# open licence, so neither may ship in an image that could be pulled.
etl/.cache
seed-snapshot

# The deploy files themselves, so editing them does not rebuild the code layer.
Dockerfile
.dockerignore
fly.toml
```

Notes on the patterns:
- A pattern without `**/` matches at the context root only. That is right for `.env`, `tests` and `etl/.cache`. The caches that appear in every package need `**/`.
- `.env.*` also drops `.env.example`, which the image has no use for.
- Everything else under `scripts/` ships, because production runs it:
  - `send_reminders.py` (plan 8);
  - `rotate_llm_keys.py` (Task 4);
  - `seed_snapshot.py` (Task 11), which runs against the database, not from inside the image.
- `seed-snapshot/` does not exist until Task 11. The rule is here now, so the first snapshot can never be baked into an image.

- [ ] **Step 3: Write fly.toml, and check it**

Create `backend/fly.toml`:

```toml
# Fly.io config for the API: `fly deploy` from backend/ builds ./Dockerfile.
#
# Nothing in this file is secret, and no secret belongs here. DATABASE_URL,
# SESSION_SECRET, GOOGLE_CLIENT_ID, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and
# LLM_KEY_ENCRYPTION_KEYS go in with `fly secrets set`; DEPLOY.md lists them.
# Before a first deploy, replace the app name, both example.com values and the
# VAPID contact below.

app = "healthmonitor-api"
# Mumbai, beside Neon's aws-ap-south-1. Check both are still offered.
primary_region = "bom"
kill_signal = "SIGTERM"
# Time for the lifespan to cancel the reminder loop and for requests to finish.
kill_timeout = "30s"

[build]
  dockerfile = "Dockerfile"

[deploy]
  # Runs once per deploy, on a temporary machine with the app's secrets, before
  # the new version starts. A failure stops the deploy. Never in the image's CMD,
  # where two machines starting at once would race on the same migration.
  release_command = "alembic upgrade head"
  strategy = "rolling"

[env]
  # Settings refuses to start unless the secrets above are set and safe.
  APP_ENV = "production"
  FRONTEND_ORIGIN = "https://app.example.com"
  COOKIE_SECURE = "true"
  # Plan 8's reminder loop runs in the API process. It warns and stays idle
  # until both VAPID keys are set.
  SCHEDULER_ENABLED = "true"
  VAPID_SUBJECT = "mailto:owner@example.com"

[http_service]
  internal_port = 8000
  force_https = true
  # Exactly one machine, always running: a stopped machine sends no reminders,
  # and every extra one runs its own reminder loop. `fly deploy --ha=false`
  # keeps a first deploy from creating a second machine.
  auto_stop_machines = "off"
  auto_start_machines = true
  min_machines_running = 1

  [[http_service.checks]]
    # /health answers without touching the database.
    method = "GET"
    path = "/health"
    interval = "15s"
    timeout = "5s"
    grace_period = "10s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

Notes:
- `FORWARDED_ALLOW_IPS` is set in the Dockerfile, not here, so every platform gets it.
- `PORT` is not set here either: the image defaults it to 8000, which matches `internal_port`.
- `strategy = "rolling"` with one machine means a deploy has a gap of a few seconds. `bluegreen` would avoid the gap and would also be safe: two reminder loops overlap for a moment, and each reminder is claimed before it is sent. The default is kept.
- 512 MB rather than 256 MB leaves room for the planner, and for the ETL if it is ever run inside the machine.

`flyctl` is not run: `fly config validate` needs an account. The file is checked as TOML instead, and for what this app depends on. From `backend/`, run:

```bash
uv run python -c "
import tomllib
with open('fly.toml', 'rb') as f:
    config = tomllib.load(f)
secrets = {'DATABASE_URL', 'SESSION_SECRET', 'GOOGLE_CLIENT_ID', 'VAPID_PUBLIC_KEY',
           'VAPID_PRIVATE_KEY', 'LLM_KEY_ENCRYPTION_KEYS'}
assert not secrets & set(config['env']), secrets & set(config['env'])
assert config['env']['APP_ENV'] == 'production'
assert config['deploy']['release_command'] == 'alembic upgrade head'
service = config['http_service']
assert (service['auto_stop_machines'], service['min_machines_running']) == ('off', 1)
assert service['internal_port'] == 8000
assert service['checks'][0]['path'] == '/health'
print('fly.toml: ok')
"
```

Expected: `fly.toml: ok`.

- [ ] **Step 4: Build the image**

Colima has died on this machine when the disk was nearly full. From the repository root, run `df -h /System/Volumes/Data` first. Expected: several GB available. The build needs about 1 GB for layers, beyond the base images.

Then run: `docker build -t healthmonitor-api:local backend`

Expected:
- **On the classic builder** (colima without buildx), the output starts with `DEPRECATED: The legacy builder is deprecated…` and `Sending build context to Docker daemon  …kB`.
  - The context must be under a few MB. The real `backend/.venv` (about 120 MB) and `etl/.cache` (about 30 MB) are excluded.
  - A context of hundreds of MB means `.dockerignore` is not being read.
  - It ends with `Successfully tagged healthmonitor-api:local`.
- **With BuildKit** it ends with `naming to docker.io/library/healthmonitor-api:local done`.
- If the build fails at `uv sync --locked`, `uv.lock` is out of step with `pyproject.toml`. Run `uv lock` in `backend/` and commit the lock, not a Dockerfile change.
- If a build fails, or you stop before Step 9, still run `docker image prune -f --filter label=healthmonitor.stage=builder`. The classic builder keeps each builder step it finished as an untagged image.

The colima VM here is x86_64 under emulation. The first build pulls `python:3.13-slim-bookworm` and `ghcr.io/astral-sh/uv:0.12.5` and runs `uv sync`, which takes 5 to 20 minutes. A rebuild after a code-only change reuses the dependency layer, and takes about 3 minutes.

- [ ] **Step 5: Check what the image holds**

Run each of these from the repository root.

```bash
docker run --rm healthmonitor-api:local id
```
Expected: `uid=10001(app) gid=10001(app) groups=10001(app)`.

```bash
docker run --rm healthmonitor-api:local sh -c '
  test ! -e /app/.env && test ! -e /app/.env.example && test ! -e /app/tests &&
  test ! -e /app/scripts/e2e_session.py && test ! -e /app/scripts/e2e_seed.py &&
  test ! -e /app/seed-snapshot && test ! -e /app/fly.toml && test ! -e /app/Dockerfile &&
  test -z "$(ls -A /app/etl/.cache)" &&
  test -z "$(find /app -path /app/.venv -prune -o \( -name __pycache__ -o -name .DS_Store \) -print)" &&
  echo clean'
```
Expected: `clean`. Your `backend/` does have a `.env`, `tests/`, an `etl/.cache` full of downloads and `__pycache__` directories, so each test here checks a real exclusion.

```bash
docker run --rm healthmonitor-api:local sh -c '
  readlink -f /app/.venv/bin/python; python --version; command -v uv || echo "no uv"
  touch /app/etl/.cache/probe && echo "cache writable"
  touch /app/app/probe 2>/dev/null && echo "code WRITABLE" || echo "code read-only"'
```
Expected:
```
/usr/local/bin/python3.13
Python 3.13.x
no uv
cache writable
code read-only
```
- The first line proves the virtualenv is the builder's. A copy of the macOS `.venv` would point into `/Library/Frameworks`, and would not run.
- `no uv` shows the build tool stayed in the builder stage.

```bash
docker run --rm healthmonitor-api:local python -c 'import app.main; print("import ok")'
```
Expected: `import ok`. With no environment set, the app loads on the development defaults. Importing it opens no database connection.

```bash
docker run --rm -w / healthmonitor-api:local \
  python -c 'import app.main, scripts.rotate_llm_keys, etl.run_all' && echo "imports from / ok"
```
Expected: `imports from / ok`, and exit 0.
- `-w /` runs the command from the root, as a `fly ssh console` command may be run. `PYTHONPATH=/app` is what makes it pass.
- Without `PYTHONPATH`, it fails with `ModuleNotFoundError: No module named 'app.main'`.
- The check imports the two entry points rather than running them. Both keep their work behind `if __name__ == "__main__"`, and `python -m etl.run_all` takes no arguments: run, it would start the ETL.

- [ ] **Step 6: The image refuses a production config with development settings**

```bash
docker run --rm -e APP_ENV=production healthmonitor-api:local python -c 'import app.config'; echo "exit $?"
```

Expected: a traceback whose last lines are:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, Refusing to start in production: SESSION_SECRET is the development default or shorter than 32 characters; GOOGLE_CLIENT_ID is empty; COOKIE_SECURE must be true; FRONTEND_ORIGIN must be an https:// origin with no trailing slash; DATABASE_URL points at localhost [type=value_error]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
exit 1
```

It ends `[type=value_error]`, with no `input_value=`: Task 8's `hide_input_in_errors` keeps every value out of the platform's log.

The same happens to the real start command, which is what Fly would run:

```bash
docker run --rm -e APP_ENV=production healthmonitor-api:local; echo "exit $?"
```

Expected: the same `Refusing to start in production: …` lines, raised from uvicorn's import of `app.main`, then `exit 1`.

- [ ] **Step 7: Run the release step against a scratch database**

This runs the image's `alembic upgrade head` and `alembic check` with a production environment, as Fly's release machine would.
- The database is a scratch one, `healthmonitor_image`, in the compose Postgres, reached over the compose network by its service name `db`. The production refusal rejects a `localhost` URL, so `--network host` is no use here.
- The URL uses the `postgres://` form and a URL-encoded password: `%68` is `h`, so it is the real `healthmonitor` password. That exercises Task 8's normaliser and its `%%` escape in `env.py` in the shipped image.
- Never point this at `healthmonitor` or `healthmonitor_test`.

Write the rehearsal environment to a temporary file. It holds a random secret, and Step 9 deletes it.

```bash
cat > "${TMPDIR:-/tmp}/hm-image-rehearsal.env" <<EOF
APP_ENV=production
DATABASE_URL=postgres://healthmonitor:%68ealthmonitor@db:5432/healthmonitor_image
SESSION_SECRET=$(openssl rand -hex 32)
GOOGLE_CLIENT_ID=rehearsal-only.apps.googleusercontent.com
COOKIE_SECURE=true
FRONTEND_ORIGIN=https://app.example.com
EOF
```

Create the scratch database. The container is found by its published port, so this works whatever the compose project is called:

```bash
docker exec "$(docker ps -q --filter publish=5433)" createdb -U healthmonitor healthmonitor_image && echo created
```

Expected: `created`.

Run the release step, then the check:

```bash
NET=$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}' \
  "$(docker ps -q --filter publish=5433)")
docker run --rm --network "$NET" --env-file "${TMPDIR:-/tmp}/hm-image-rehearsal.env" \
  healthmonitor-api:local alembic upgrade head
docker run --rm --network "$NET" --env-file "${TMPDIR:-/tmp}/hm-image-rehearsal.env" \
  healthmonitor-api:local alembic check
```

Expected:
- `NET` is `healthmonitor_default` for a checkout named `healthMonitor`.
- The upgrade prints `Context impl PostgresqlImpl.`, then one `Running upgrade` line per migration, 14 in all:
  - it starts with `Running upgrade  -> a2f31782db5d, create users table`;
  - it continues through `e1f2a3b4c5d6 -> f2a3b4c5d6e7, reports and reminders`;
  - it ends with `f2a3b4c5d6e7 -> a3b4c5d6e7f8, …`, where the text after the comma is the first line of Task 2's migration docstring.
- The check ends with `No new upgrade operations detected.`
- Both commands exit 0.
- A `ValueError: invalid interpolation syntax` here means `env.py` lost Task 8's escape.

- [ ] **Step 8: Boot it, and hit /health**

```bash
NET=$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}' \
  "$(docker ps -q --filter publish=5433)")
docker run -d --name hm-image-rehearsal --network "$NET" \
  --env-file "${TMPDIR:-/tmp}/hm-image-rehearsal.env" -e SCHEDULER_ENABLED=true \
  -p 127.0.0.1:18000:8000 healthmonitor-api:local
for _ in $(seq 1 90); do
  curl -fsS http://127.0.0.1:18000/health 2>/dev/null && break
  sleep 1
done; echo
docker logs hm-image-rehearsal
```

Expected: `{"status":"ok"}`. Under emulation the first answer can take about 30 seconds, and until then curl sees an empty reply from colima's port forwarder. The logs read:

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
WARNING [app.main] SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.18.0.1:<port> - "GET /health HTTP/1.1" 200 OK
```

- `Started server process [1]` means `exec` made uvicorn PID 1, so it gets the platform's SIGTERM.
- The `WARNING [app.main] …` line has Task 8's format. Without Task 8's handler it would appear without its level and logger name, through logging's last-resort handler.
- A clean production config booted, with a `postgres://` URL, so the refusal passes what it should.

Then check the rest:

```bash
curl -sS -D - -o /dev/null http://127.0.0.1:18000/health
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/auth/me
docker exec hm-image-rehearsal sh -c 'tr "\0" " " < /proc/1/cmdline; echo'
docker stop -t 30 hm-image-rehearsal >/dev/null
docker logs hm-image-rehearsal 2>&1 | tail -4
docker inspect -f '{{.State.ExitCode}}' hm-image-rehearsal
```

Expected:
- The headers are `HTTP/1.1 200 OK`, `date`, `content-length: 15` and `content-type: application/json`. There is no `server:` line.
- `/auth/me` answers `401`: the routers are mounted, and it needs no session to say so.
- PID 1 is `/app/.venv/bin/python /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --no-server-header`.
- The stop is graceful. The logs end `Shutting down`, `Waiting for application shutdown.`, `Application shutdown complete.` and `Finished server process [1]`, and the exit code is `0`.

- [ ] **Step 9: Clean up**

```bash
docker rm hm-image-rehearsal
docker exec "$(docker ps -q --filter publish=5433)" dropdb -U healthmonitor healthmonitor_image && echo dropped
rm "${TMPDIR:-/tmp}/hm-image-rehearsal.env"
docker rmi healthmonitor-api:local
docker image prune -f --filter label=healthmonitor.stage=builder
test -z "$(docker images -aq --filter label=healthmonitor.stage=builder)" && echo "no builder image left"
docker exec "$(docker ps -q --filter publish=5433)" psql -U healthmonitor -Atc \
  "select datname from pg_database where datname like 'healthmonitor%' order by 1"
```

Expected:
- `dropped`.
- The prune prints `Deleted Images:`, then `untagged:` and `deleted:` lines for the builder stage's images, and ends with `Total reclaimed space: …`.
  - `docker rmi` removes only the runtime image and its layers. On the classic builder, the builder stage is a separate untagged image holding the whole virtualenv and uv. It stays behind after `docker rmi`, and each dependency change adds another.
  - The label filter removes those images and no other. This machine already holds other projects' dangling images, and an unfiltered `docker image prune` would delete them too.
  - With BuildKit, the prune prints only `Total reclaimed space: 0B`. BuildKit keeps no builder image, only its build cache.
- `no builder image left`.
- The final listing shows `healthmonitor` and `healthmonitor_test`, and no `healthmonitor_image`. Other plan 9 tasks' scratch databases may also appear while they run.
- What stays in docker is what was there before Step 4, including the two base images (`python:3.13-slim-bookworm` and `ghcr.io/astral-sh/uv:0.12.5`) if Step 4 pulled them. Keep them: they make the next build fast, and removing them frees about 260 MB.
- The prune also removed the cached dependency layer. The next local build (Task 12's local check, Task 13's final build) runs `uv sync` again: Step 4's first-build time, without the pulls.

- [ ] **Step 10: Commit**

From the repository root:

```bash
git add backend/Dockerfile backend/.dockerignore backend/fly.toml
git commit -m "build(backend): add the API image and its Fly.io config

A two-stage uv image on python:3.13-slim-bookworm, matching
backend/.python-version. The builder installs the locked dependencies and
fails when uv.lock is stale. The runtime stage holds the virtualenv and the
code, both root-owned, and runs as uid 10001, which can write only the
ETL's download cache. It uses no BuildKit-only syntax, because the classic
builder that colima falls back to without buildx rejects RUN --mount.

PYTHONPATH=/app makes python -m scripts.<name> and python -m etl.run_all
work from any working directory, since a fly ssh console session need
not start in WORKDIR. The builder stage is labelled
healthmonitor.stage=builder. A local cleanup can then prune the untagged
image the classic builder leaves of it, virtualenv and uv included,
without touching any other dangling image.

.dockerignore keeps out .env, which Settings would read from the working
directory over the platform's secrets, the tests, the e2e session minter,
the ETL downloads and the seed snapshot, which carry IFCT data that has no
open licence.

uvicorn runs with --workers 1, because plan 8's lifespan starts a reminder
loop per worker, and it trusts the platform proxy's forwarded headers.
fly.toml keeps one machine always on, so reminders keep ticking, runs the
migration as the release step rather than in the CMD, sets
APP_ENV=production and holds no secret.

Rehearsed against the compose Postgres: the release step and alembic check
run under a production config with a postgres:// URL and an encoded
password, the image boots and answers /health, app, scripts and etl
import from /, and with development settings it refuses to start.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

---

## Task 10: The SPA host config

The SPA goes on Cloudflare Pages at the root of its own host, `app.<domain>`, and talks to the API on `api.<domain>`. This task makes the build and its output fit that host. Four things change.

**The build refuses to bake in localhost.** `src/lib/api.ts:1` is `import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'`. A build that forgets the variable succeeds today and ships a bundle that sends every request to the visitor's own machine. `vite build` in production mode now stops with a message naming the variable, unless `VITE_USE_MOCKS=true`.
- The check reads the environment with `loadEnv`, exactly as Vite fills `import.meta.env`: `.env`, `.env.local`, `.env.production` and `.env.production.local`, with the shell's environment winning over all four.
- It mirrors `??`: only a missing variable is refused. An empty `VITE_API_BASE=` counts as set, because `??` keeps it (it gives relative URLs). So to watch the check fire you must remove the variable, not blank it.
- `.env.local` is read in every mode, and the development checkout's `frontend/.env.local` (gitignored) sets `VITE_API_BASE`. So no build run in `frontend/` can show the refusal. Steps 1 and 5 build a throwaway copy of the frontend that has no env files.

**The workbox navigation denylist goes.** `navigateFallbackDenylist: [/^\/auth/, /^\/households/, /^\/foods/]` was meant to keep API paths away from the service worker's `index.html` fallback. With the API on its own origin, the worker never sees a navigation to it. And `/^\/foods/` matches the SPA's own `/foods` route (`src/App.tsx`), so an offline reload of the Foods screen failed.

**`public/_headers`.** Pages reads this from the build output.
- It marks the service worker, the push handlers the worker imports, `registerSW.js`, the manifest and the app shell `no-cache`.
- It marks the content-hashed files immutable.
- It has no catch-all rule, because Pages joins the values of every matching rule with a comma.

**`public/_redirects` holds no rules, on purpose.** As the Decisions record: the usual way to write an SPA fallback on Pages is wrong here.
- Pages already serves `/index.html` with a 200 for any path that is not a file, as long as the build has no top-level `404.html`.
- Pages applies `_redirects` rules *before* it looks for a file. So a catch-all 200 rule such as `/* / 200` answers `/sw.js` and every script under `/assets/` with `index.html`, and the app never loads.
- The usual `/* /index.html 200` is dropped outright, with the warning "Infinite loop detected in this rule and has been ignored".

The file stays, with no rules and a comment saying all of this, so that the next person who goes to add a rule reads why not. Step 6 shows all of it on a local Pages server.

**`frontend/.env.example`** lists the four build variables. Vite never reads `.env.example`, and git does not ignore it: the root `.gitignore` names `.env` and `.env.local` exactly, and `frontend/.gitignore` has `*.local`.

A second SKELETON DEVIATION: the config is `defineConfig(({ command, mode }) => …)`, not `({ mode })`. `vite preview` also loads the config in mode `production`, so a check on `mode` alone would stop `npm run preview` whenever `VITE_API_BASE` is unset, although preview only serves a finished build. The check therefore runs only when `command === 'build'`. Vitest loads this file in mode `test` and `vite` dev in `development`, so neither reaches it. The Playwright walk runs `npm run dev`, so it needs no `VITE_API_BASE` either.

Run every command from `frontend/` unless a step says otherwise.

**Files:**
- Create: `frontend/public/_headers`, `frontend/public/_redirects`, `frontend/.env.example`
- Modify: `frontend/vite.config.ts`, which is HEAD plus plan 8 Task 12's `workbox.importScripts: ['push-handlers.js']`
- Test: no test file. The checks are builds, in Steps 1, 5 and 6. The `frontend` CI job (Task 12) repeats Step 5's output checks on every pull request.

**Interfaces:**
- Consumes:
  - Plan 8 Task 12:
    - `frontend/public/push-handlers.js`;
    - in `vite.config.ts`, the four comment lines and the `importScripts: ['push-handlers.js'],` line directly after `navigateFallbackDenylist: [/^\/auth/, /^\/households/, /^\/foods/],` (lines 51 and 56);
    - `src/mocks/handlers/index.ts`, which holds only the opt-in demo-auth handlers (`VITE_DEMO_AUTH=true`). So a `VITE_USE_MOCKS=true` build fakes the sign-in and nothing else.
  - `src/lib/api.ts:1` and `src/mocks/apiUrl.ts:5`: the `?? 'http://localhost:8000'` fallback.
  - `src/main.tsx`: `VITE_USE_MOCKS` turns the MSW worker on only when it is exactly `'true'` in a build.
- Produces:
```ts
// frontend/vite.config.ts (private to the file)
const API_BASE_MISSING =
  'VITE_API_BASE is not set. A production build would call http://localhost:8000. ' +
  'Set it (for example in frontend/.env.local) or set VITE_USE_MOCKS=true.'
function refuseLocalhostBuild(command: 'build' | 'serve', mode: string): void
  // throws new Error(API_BASE_MISSING) when command === 'build' && mode === 'production'
  // && loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE === undefined
  // && VITE_USE_MOCKS !== 'true'
export default defineConfig(({ command, mode }) => { refuseLocalhostBuild(command, mode); return {...} })
```
  - The build output `dist/`:
    - `_headers` with 8 rules and `_redirects` with none;
    - no `404.html`;
    - `sw.js` registers `NavigationRoute(createHandlerBoundToURL("index.html"))` with no `denylist`, and still `importScripts("push-handlers.js")`.
  - For Task 12: `npm run build` in CI needs `VITE_API_BASE` (CI sets `https://api.example.invalid`, and `VITE_GOOGLE_CLIENT_ID: ci-placeholder`).
  - For Task 13, which writes `DEPLOY.md` and the READMEs:
    - Pages' SPA fallback is automatic, and `_redirects` must never get a `/*` rule.
    - The Pages build needs `NODE_VERSION=22`, `VITE_API_BASE` and `VITE_GOOGLE_CLIENT_ID`.
    - `npm run build` now needs `VITE_API_BASE`, from `frontend/.env.local` (see `frontend/.env.example`).

- [ ] **Step 1: Show what a build does today**

This build runs in a throwaway copy of the frontend. The copy holds only what `vite build` reads, so it has no env files, and it shares this `node_modules` through a symlink. `env -u` removes both variables from the build's environment.

Run:

```bash
CHECK="$(mktemp -d)"
cp -R index.html package.json tsconfig.json tsconfig.app.json tsconfig.node.json \
  tsconfig.e2e.json vite.config.ts src public "$CHECK/"
ln -s "$PWD/node_modules" "$CHECK/node_modules"
(cd "$CHECK" && env -u VITE_API_BASE -u VITE_USE_MOCKS npx vite build > build.log 2>&1)
echo "build exit: $?"
grep -rl 'localhost:8000' "$CHECK/dist/assets"
grep -o 'denylist:[^}]*' "$CHECK/dist/sw.js"
ls "$CHECK/dist/_headers" "$CHECK/dist/_redirects"
rm -rf "$CHECK"
```

Expected, where `<tmp>` is the `mktemp` directory:

```
build exit: 0
<tmp>/dist/assets/index-<hash>.js
denylist:[/^\/auth/,/^\/households/,/^\/foods/]
ls: <tmp>/dist/_headers: No such file or directory
ls: <tmp>/dist/_redirects: No such file or directory
```

This shows all three problems:
- A build with no API base succeeds, and its main chunk calls `http://localhost:8000`.
- The worker still carries the denylist that catches `/foods`.
- There is no Pages config.

- [ ] **Step 2: Refuse the localhost build, and drop the denylist**

First confirm the file is in plan 8's shape. Run: `grep -n "importScripts\|navigateFallbackDenylist" vite.config.ts`

Expected:

```
51:        navigateFallbackDenylist: [/^\/auth/, /^\/households/, /^\/foods/],
56:        importScripts: ['push-handlers.js'],
```

If anything else in the file differs from HEAD plus those plan 8 lines, carry it into the version below.

The config becomes a function, so its body moves in one indentation level. Replace the whole of `frontend/vite.config.ts` with:

```ts
import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

/*
 * `src/lib/api.ts` falls back to http://localhost:8000 when VITE_API_BASE is unset.
 * That is right for `npm run dev` and wrong for anything deployed: the bundle would
 * send every request to the visitor's own machine, and the build would not say so.
 * So a production build stops instead.
 *
 * - It mirrors the `??` in api.ts: only a missing variable falls back to localhost,
 *   so only a missing variable is refused. `??` keeps an empty one, and so does this.
 * - A mock build (`VITE_USE_MOCKS=true`) is exempt. Its MSW worker holds only the
 *   opt-in demo-auth handlers (`VITE_DEMO_AUTH=true`), so it is a local demo of the
 *   sign-in alone. Every other request still goes to VITE_API_BASE, or to localhost
 *   when that is unset. Such a build is never deployed.
 * - It checks `vite build` only. `vite preview` loads this file in production mode
 *   too, but it serves a finished build and bakes nothing in. Vitest runs in mode
 *   "test" and `vite` in "development", so neither reaches it.
 */
const API_BASE_MISSING =
  'VITE_API_BASE is not set. A production build would call http://localhost:8000. ' +
  'Set it (for example in frontend/.env.local) or set VITE_USE_MOCKS=true.'

function refuseLocalhostBuild(command: 'build' | 'serve', mode: string): void {
  if (command !== 'build' || mode !== 'production') return
  // What Vite itself puts in import.meta.env: .env, .env.local, .env.production and
  // .env.production.local from its root (the working directory, since this config
  // sets none), with the shell's environment winning over all four.
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  if (env.VITE_API_BASE === undefined && env.VITE_USE_MOCKS !== 'true') {
    throw new Error(API_BASE_MISSING)
  }
}

export default defineConfig(({ command, mode }) => {
  refuseLocalhostBuild(command, mode)
  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['apple-touch-icon.png'],
        /*
         * Deliberately off in dev. MSW's worker and this one both claim the root
         * scope, and only one service worker can control a page -- so the mocks own
         * dev, and the PWA worker owns the production build.
         */
        devOptions: { enabled: false },
        manifest: {
          name: 'Nutrient Tracker',
          short_name: 'Nutrients',
          description:
            'Track macros and micronutrients on a South Indian diet, against ICMR-NIN targets.',
          start_url: '/',
          display: 'standalone',
          orientation: 'portrait',
          background_color: '#ffffff',
          theme_color: '#0f766e',
          icons: [
            { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
            {
              src: '/icon-maskable-512.png',
              sizes: '512x512',
              type: 'image/png',
              // Android crops icons to the launcher's shape; the maskable variant
              // keeps its glyph inside the centre 80% so nothing important is cut.
              purpose: 'maskable',
            },
          ],
        },
        workbox: {
          // The app shell is precached so a cold, offline launch still renders.
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          // Vite copies all of public/ into dist, which sweeps up MSW's dev worker.
          // It is never registered in production, but precaching it would ship and
          // cache 8KB of dev tooling to every user.
          globIgnores: ['mockServiceWorker.js'],
          // No navigateFallbackDenylist. The API has its own origin (api.<domain>),
          // so this worker never sees a navigation to it, and every navigation it
          // does see is an SPA route that index.html answers. The old list (/auth,
          // /households, /foods) caught the real /foods screen, so an offline reload
          // there failed. API responses are still never precached: globPatterns
          // matches only this build's own files.
          //
          // The meal reminders' push and notification-click handlers: plain JS in
          // public/, loaded into the generated worker, which stays generateSW. The
          // file is precached too, so an edit to it changes sw.js and updates the
          // worker.
          importScripts: ['push-handlers.js'],
        },
      }),
    ],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.ts',
      /*
       * The Playwright specs live in e2e/ and drive a real browser against a real
       * backend. Vitest's default glob would otherwise collect them and run them
       * under jsdom, where `@playwright/test` has no runner to attach to.
       */
      exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
    },
  }
})
```

Notes on the code:
- `loadEnv` comes from `vite`, not `vitest/config`.
- `process.cwd()` is typed because `tsconfig.node.json`, which covers this file, has `"types": ["node"]`.
- If a proxied deploy ever serves the API under `/api` on the SPA's own origin, it would need a denylist again, `[/^\/api\//]`. Only then does the worker see API navigations.

- [ ] **Step 3: Add the Pages config**

Create `frontend/public/_headers`:

```
# Cloudflare Pages response headers. Vite copies this file from public/ into dist/,
# where Pages reads it. Pages never serves it, and the service worker never precaches it.
#
# Every rule whose path matches a request applies, and a header that two rules set is
# joined with a comma. So there is deliberately no catch-all /* rule: its value would
# be added to the immutable one below.

# The service worker and what it is installed from. A browser fetches sw.js past its
# HTTP cache when it checks for an update, but by default lets the scripts sw.js
# imports come from that cache, so a cached push-handlers.js could outlive the sw.js
# that expects it.
/sw.js
  Cache-Control: no-cache
/push-handlers.js
  Cache-Control: no-cache
/registerSW.js
  Cache-Control: no-cache
/manifest.webmanifest
  Cache-Control: no-cache

# The app shell. Pages answers "/" and every SPA route with index.html, and redirects
# /index.html itself to "/". The routes (/plan, /foods, ...) keep Pages' default,
# "public, max-age=0, must-revalidate", which also checks on every load.
/
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache

# Content-hashed files: a new build gives them new names, so a cached copy is never
# stale.
/assets/*
  Cache-Control: public, max-age=31536000, immutable
/workbox-*.js
  Cache-Control: public, max-age=31536000, immutable
```

About these rules:
- The `/` rule is in the Decisions' list for this reason: The app shell is served at `/`, and a request for `/index.html` is redirected there (308). So a rule on `/index.html` alone never reaches a page a browser renders.
- `workbox-<hash>.js` is named after its content. It keeps the same name across builds until the workbox runtime changes.
- Neither file matches the precache glob `**/*.{js,css,html,svg,png,woff2}`, so neither is precached.

Create `frontend/public/_redirects`:

```
# Cloudflare Pages redirects. This file has no rules, on purpose.
#
# The SPA needs none. While the build has no top-level 404.html, Pages answers every
# path that is not a file (/plan, /foods, /profile/goals, ...) with /index.html and a
# 200.
#
# Do not add the usual "/*  /index.html  200". Pages drops that exact rule as an
# infinite loop. Any other catch-all 200 is worse: Pages applies these rules before it
# looks for a file, so "/*  /  200" answers /sw.js and every script under /assets/
# with index.html, and the app never loads.
```

- [ ] **Step 4: Document the build variables**

Create `frontend/.env.example`:

```
# Copy to .env.local, which git ignores, and fill in. Vite reads .env.local in every
# mode, and a variable set in the shell wins over the file.

# The FastAPI backend's origin, with no trailing slash. `npm run dev` falls back to
# http://localhost:8000 without it, but `npm run build` stops without it
# (vite.config.ts), so a deployed bundle can never call localhost by accident. A deploy
# sets it in the host's build settings to the API's https:// origin (see DEPLOY.md).
VITE_API_BASE=http://localhost:8000

# The Google OAuth client id, the same value as the backend's GOOGLE_CLIENT_ID. It is
# baked into the bundle, so it is public.
VITE_GOOGLE_CLIENT_ID=

# The MSW mock worker: on in dev, off in a build. It serves only the opt-in demo auth
# below; every other request goes to the real API. false turns it off in dev; true
# turns it on in a build. That build is a local demo of the sign-in alone and is never
# deployed, so it may leave VITE_API_BASE unset, and it then calls
# http://localhost:8000 for everything else, as dev does.
# VITE_USE_MOCKS=

# Fakes /auth/* in the browser, so dev opens the app without Google; every other
# request still needs a real session. Never set it for a deployed build: it hands a
# session to anyone who asks.
# VITE_DEMO_AUTH=
```

About this file:
- "No trailing slash" matters because `api.ts` joins `${API_BASE}${path}`, and every path starts with `/`.
- `DEPLOY.md` arrives with Task 13.

Run: `git check-ignore -v .env.example public/_headers public/_redirects; echo "ignored: $?"`

Expected: `ignored: 1`, with nothing printed before it. None of the three is ignored, so all three will be committed.

- [ ] **Step 5: Run the build checks**

First, the refusal, in a throwaway copy like Step 1's. The same copy also shows that a mock build is exempt, and that `vite preview` still starts without the variable. Run:

```bash
CHECK="$(mktemp -d)"
cp -R index.html package.json tsconfig.json tsconfig.app.json tsconfig.node.json \
  tsconfig.e2e.json vite.config.ts src public "$CHECK/"
ln -s "$PWD/node_modules" "$CHECK/node_modules"
(cd "$CHECK" && env -u VITE_API_BASE -u VITE_USE_MOCKS npx vite build > unset.log 2>&1)
echo "unset: exit $?"
grep -m1 '^Error:' "$CHECK/unset.log"
ls "$CHECK/dist"
(cd "$CHECK" && env -u VITE_API_BASE VITE_USE_MOCKS=true npx vite build > mocks.log 2>&1)
echo "mocks: exit $?"
(cd "$CHECK" && env -u VITE_API_BASE -u VITE_USE_MOCKS npx vite preview --port 4179 --strictPort \
  > preview.log 2>&1 &)
for _ in $(seq 1 20); do curl --noproxy '*' -s -o /dev/null http://localhost:4179/ && break; sleep 1; done
curl --noproxy '*' -s -o /dev/null -w 'preview: %{http_code}\n' http://localhost:4179/foods
pkill -f 'vite preview --port 4179'
rm -rf "$CHECK"
```

Expected:

```
unset: exit 1
Error: VITE_API_BASE is not set. A production build would call http://localhost:8000. Set it (for example in frontend/.env.local) or set VITE_USE_MOCKS=true.
ls: <tmp>/dist: No such file or directory
mocks: exit 0
preview: 200
```

What this shows:
- The refused build stops while loading its config, before it writes anything. Its full log starts `failed to load config from <tmp>/vite.config.ts` and `error during build:`.
- The preview serves the mock build.
- `--noproxy '*'` keeps a corporate `http_proxy` out of local requests, which it would otherwise answer with a 503.
- If port 4179 is taken, pick another one in all three places.

Then build in place, the way CI and Pages build: with the variables in the shell environment, which wins over `.env.local`. Then check the output. Run:

```bash
rm -rf dist
VITE_API_BASE=https://api.example.invalid VITE_GOOGLE_CLIENT_ID=ci-placeholder npm run build > /dev/null
grep -rl 'localhost:8000' dist/assets; echo "localhost matches: $?"
grep -rl 'https://api.example.invalid' dist/assets
ls dist/_headers dist/_redirects
ls dist/404.html
grep -Ev '^[[:space:]]*(#|$)' dist/_redirects; echo "redirect rules: $?"
grep -o 'importScripts("push-handlers.js")' dist/sw.js
grep -o 'denylist:[^}]*' dist/sw.js; echo "denylist matches: $?"
grep -o 'NavigationRoute([^;]*' dist/sw.js
```

Expected:

```
localhost matches: 1
dist/assets/index-<hash>.js
dist/_headers
dist/_redirects
ls: dist/404.html: No such file or directory
redirect rules: 1
importScripts("push-handlers.js")
denylist matches: 1
NavigationRoute(e.createHandlerBoundToURL("index.html")))})
```

What each line shows:
- No `localhost:8000` anywhere in the bundle. The minifier folds `"https://api.example.invalid" ?? 'http://localhost:8000'` down to the first operand.
- The API base is in the main chunk.
- Both Pages files are in `dist/`, and there is no `404.html` to switch off the SPA fallback.
- `_redirects` has no rule line.
- The worker still imports the push handlers.
- The navigation route has no denylist. The minified variable name (`e.`) can differ.

- [ ] **Step 6: Rehearse on a local Pages server**

`wrangler pages dev` runs Cloudflare's own Pages asset server on this machine, reading `_headers` and `_redirects` exactly as a deploy would. It touches no account. `npx` fetches wrangler into its cache; nothing is added to `package.json`. Wrangler writes a `.wrangler/` state directory into its working directory, so it runs from a temporary one.

Using the `dist/` that Step 5 built, run:

```bash
DIST="$PWD/dist"
PAGES="$(mktemp -d)"
(cd "$PAGES" && WRANGLER_SEND_METRICS=false npx --yes wrangler@4.138.0 pages dev "$DIST" \
  --port 8788 --ip 127.0.0.1 > wrangler.log 2>&1) &
for _ in $(seq 1 90); do curl --noproxy '*' -s -o /dev/null http://127.0.0.1:8788/ && break; sleep 1; done
grep -E 'valid (redirect|header) rule|invalid' "$PAGES/wrangler.log"
for url_path in / /foods /sw.js /push-handlers.js /registerSW.js /manifest.webmanifest \
  "/assets/$(ls dist/assets | grep -m1 '^index-.*\.js$')" "/$(ls dist | grep -m1 '^workbox-')"; do
  printf '%-28s' "$url_path"
  curl --noproxy '*' -s -o /dev/null -D - "http://127.0.0.1:8788$url_path" | tr -d '\r' \
    | grep -i -E '^(content-type|cache-control):' | sort | tr '\n' ' '
  echo
done
pkill -f 'wrangler.*pages dev.*--port 8788'
rm -rf "$PAGES"
```

The loop variable is `url_path`, not `path`, on purpose. In zsh, `path` is tied to `PATH`, and assigning it breaks every command after it.

Expected (hashes vary):

```
✨ Parsed 0 valid redirect rules.
✨ Parsed 8 valid header rules.
/                           Cache-Control: no-cache Content-Type: text/html; charset=utf-8
/foods                      Cache-Control: public, max-age=0, must-revalidate Content-Type: text/html; charset=utf-8
/sw.js                      Cache-Control: no-cache Content-Type: application/javascript
/push-handlers.js           Cache-Control: no-cache Content-Type: application/javascript
/registerSW.js              Cache-Control: no-cache Content-Type: application/javascript
/manifest.webmanifest       Cache-Control: no-cache Content-Type: application/manifest+json
/assets/index-<hash>.js     Cache-Control: public, max-age=31536000, immutable Content-Type: application/javascript
/workbox-<hash>.js          Cache-Control: public, max-age=31536000, immutable Content-Type: application/javascript
```

What this shows:
- No line mentions `invalid`.
- `/foods`, a path with no file behind it, gets `index.html` from the automatic fallback.
- Every real file gets itself, with its rule's `Cache-Control`.

Then confirm that no wrangler process is left: `pgrep -f 'wrangler.*pages dev' || echo none` prints `none`.

If you want to see why `_redirects` stays empty, append `/*  /  200` to `dist/_redirects` (not `public/`) and rerun the block. `/sw.js` then comes back as `text/html`. Rebuild afterwards.

- [ ] **Step 7: Run the frontend checks**

Run: `npx tsc -b && npx vitest run && npm run lint && npm run build`

Expected:
- `tsc` prints nothing.
- Every vitest file passes. Vitest loads the config in mode `test`, so the check never runs.
- oxlint exits 0 with no diagnostics.
- The build succeeds, taking `VITE_API_BASE` from `.env.local`. This also replaces Step 5's placeholder `dist/` with a local build again.

If you have no `frontend/.env.local`, the build stops with the Step 5 message. Run `cp .env.example .env.local`, fill in `VITE_GOOGLE_CLIENT_ID`, and build again.

From the repository root, run: `git status --short`

Expected, besides any files plan 8 left uncommitted:

```
 M frontend/vite.config.ts
?? frontend/.env.example
?? frontend/public/_headers
?? frontend/public/_redirects
```

`dist/` is ignored, and no `.wrangler/` directory appears, since wrangler ran in a temporary directory.

- [ ] **Step 8: Commit**

From the repository root:

```bash
git add frontend/vite.config.ts frontend/public/_headers frontend/public/_redirects \
  frontend/.env.example
git commit -m "feat(frontend): refuse a build without VITE_API_BASE, and add the Pages config

src/lib/api.ts falls back to http://localhost:8000 when VITE_API_BASE is
unset, so a build that forgot it succeeded and shipped a bundle that sent
every request to the visitor's own machine. vite build in production mode
now stops with a message naming the variable, unless VITE_USE_MOCKS=true.
The check reads the environment as Vite does, so .env.local and the shell
both count. It runs for builds only, because vite preview also loads the
config in production mode and bakes nothing in.

The service worker's navigation denylist goes. With the API on its own
origin the worker never sees a navigation to it, and /^\/foods/ caught
the SPA's own /foods screen, so an offline reload there failed.

public/_headers makes the service worker, the push handlers it imports,
registerSW.js, the manifest and the app shell revalidate on every load,
and marks the content-hashed files immutable. It has no catch-all rule,
because Pages joins the values of every matching rule.

public/_redirects has no rules, on purpose. Pages already answers an
unknown path with index.html while the build has no 404.html, and it
applies _redirects before it looks for a file. It drops the usual
'/* /index.html 200' as a loop, and '/* / 200' answers /sw.js and every
script with index.html. The file says so, where the next person would
add a rule. frontend/.env.example lists the four build variables.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: The seed snapshot

A new production database needs the nine reference tables before anyone can use the app: nutrients, the ICMR reference values, IFCT ingredients, the authored and INDB dishes, and their rows. Today the only way to fill them is `python -m etl.run_all`, which downloads from three third-party hosts at run time (one a mutable `master` branch on GitHub, one a WordPress upload path), needs a writable cache, and takes about two minutes locally. This task adds a snapshot of the ETL's output instead, which a first deploy loads in one transaction.

`scripts/seed_snapshot.py` has three commands:
- **`export --out DIR`** writes one CSV per table with COPY and a `manifest.json`.
  - The column lists come from the SQLAlchemy models, so the files never depend on a table's physical column order.
  - The source's UUIDs are kept.
  - Every user-created dish is left out (`created_by_user_id IS NOT NULL`), together with its ingredients, nutrients and measures. Nothing writes user dishes today, but the column exists and the planner already reads it.
  - The manifest records, per table, the row count, the file's SHA-256 and a fingerprint (a row count and an md5 over the rows as natural keys). It also records the alembic revision, the git commit and the time.
- **`import --from DIR`** refuses, before writing anything, when:
  - the target's alembic revision is not the snapshot's;
  - any of the nine tables in the target already holds a row;
  - a file's SHA-256 is not the manifest's.

  It then loads the tables parents first, runs `ANALYZE`, and compares every table's fingerprint with the manifest. The load runs under a savepoint, so a mismatch takes every loaded row back out. Every refusal is a `SnapshotError` with a plain message, and the command exits 1.
- **`fingerprint`** prints each table's fingerprint as JSON, so two databases can be compared.

Three choices are deliberate:
- **Our own script, not `pg_dump`.** `pg_dump` needs client binaries matching the server's major version, cannot filter rows, and cannot be exercised by the test suite. COPY runs through the psycopg connection the app already has, and every refusal here has a test.
- **Fingerprints over natural keys, not ids.** A fingerprint names each row by codes (`'ifct:A001'|'energy'|…`) and reads every reference through its join. So a row pointing at the wrong parent changes it, and the same fingerprint compares a snapshot-loaded database with one the ETL built. Values go through `quote_nullable`, which keeps NULL apart from an empty string. Rows are sorted by their own text under the `"C"` collation, so the order does not depend on the server's locale, or on the identical duplicate rows `portion_measures` can hold (it has no unique constraint).
- **Only into an empty database.** A database that already has users is refreshed by `etl.run_all`, which updates rows in place by code. That keeps the ids that `meal_logs` and `meal_plan_items` point at, and the ids in the `food_id` columns that have no foreign key. The import's refusal message says so.

The snapshot is derived from IFCT, which has no open licence (spec, "Food data sources"). The root `.gitignore` gains `backend/seed-snapshot/`, and Task 9's `.dockerignore` already leaves `seed-snapshot/` out of the image.

This task also fixes two places where the ETL's cache trusted a half-written result. The ETL run that a snapshot is exported from reads that cache too, so either defect would reach production through the snapshot.
- `etl.common.cached_download` streamed straight into the final path and trusted any file already there. So a download cut off halfway left a truncated file that every later run loaded, and a short IFCT CSV loads without an error, only with fewer foods. It now writes to a `.part` file and renames it into place once the last byte has arrived.
- `etl.run_all._usda_csv_paths` has the same defect one step later. It unzips the USDA release only when the release directory is missing. So an extraction cut off halfway (a full disk, a damaged archive) left a directory that every later run loaded, and an empty or cut-off `food_nutrient.csv` loads without an error, only with fewer B12 and iodine values. It now extracts into a `.part` directory and renames the release directory into place once every file is out.

The tests run COPY on the test transaction's own connection, `db.connection()`, so everything they export, delete and load is rolled back with the test. They never touch the development database: `main()` reaches a database only through `_connection()`, which the command-line tests replace.

All commands run from `backend/` unless a step says otherwise, and the commit runs from the repository root.

**Files:**
- Create: `backend/scripts/seed_snapshot.py`
- Modify:
  - `backend/etl/common.py`: `cached_download` writes through a `.part` file
  - `backend/etl/run_all.py`: `_usda_csv_paths` extracts through a `.part` directory
  - `.gitignore` (repository root): `backend/seed-snapshot/`
- Test (create):
  - `backend/tests/test_cached_download.py` (no test covers `cached_download` itself today)
  - `backend/tests/test_usda_extract.py` (no test covers the extraction today; `tests/test_dish_coverage.py` only calls `_usda_csv_paths` on the real cache)
  - `backend/tests/test_seed_snapshot.py`

**Interfaces:**
- Consumes:
  - The nine reference models: `Nutrient` (`app/models/nutrient.py`), `Ingredient`, `IngredientNutrient`, `Dish`, `DishIngredient`, `DishNutrient`, `PortionMeasure` (`app/models/food.py`), `RdaReference`, `UpperLimit` (`app/models/reference.py`). None of their columns changes in plans 8 or 9.
  - `app.db.engine`, which reads `DATABASE_URL`. Task 8 normalises a `postgres://` URL, so a URL copied from Neon's console works here too.
  - The `alembic_version` table. Plan 9's head is `a3b4c5d6e7f8` (Task 2).
  - The `db` fixture in `tests/conftest.py`: a session on one connection inside a transaction that is rolled back after each test. `db.connection()` is that connection.
  - Task 9's `backend/.dockerignore`, which already lists `seed-snapshot/`.
  - `etl/run_all.py` as it is today: `USDA_CSV_DIRNAME = "FoodData_Central_foundation_food_csv_2025-04-24"`, the only top-level directory in the USDA zip; `from etl.common import cached_download`, a module-level name the extraction tests replace; and `_usda_csv_paths`, which `tests/test_dish_coverage.py` imports and calls on the real cache.
- Produces:
```python
# scripts/seed_snapshot.py
SNAPSHOT_FORMAT = 1
MANIFEST = "manifest.json"

@dataclass(frozen=True)
class SeedTable:
    name: str
    model: type[Base]      # columns come from model.__table__.columns, in table order
    where: str | None      # SQL filter on the export, None for every row
    fingerprint_sql: str   # SELECT count(*) AS rows, md5(string_agg(... ORDER BY line COLLATE "C"))

SEED_TABLES: tuple[SeedTable, ...]   # load order: nutrients, ingredients, dishes,
                                     # ingredient_nutrients, rda_reference, upper_limits,
                                     # dish_ingredients, dish_nutrients, portion_measures
class SnapshotError(RuntimeError)    # every refusal, with a plain message

def fingerprints(conn: Connection) -> dict[str, dict[str, object]]   # {table: {"rows": n, "md5": hex}}
def export_snapshot(conn: Connection, out_dir: Path, *, git_commit: str) -> dict   # the manifest
def import_snapshot(conn: Connection, src: Path) -> None   # checks, COPY FROM, ANALYZE, re-fingerprint
def main(argv: Sequence[str] | None = None) -> int
    # export --out DIR | import --from DIR | fingerprint; 0 on success, 1 on SnapshotError,
    # argparse's exit 2 on bad arguments
# The seams main() goes through, which tests replace:
@contextlib.contextmanager
def _connection(*, repeatable_read: bool = False) -> Iterator[Connection]   # one transaction
def _git_commit() -> str             # `git rev-parse HEAD`, or "unknown"

# etl/common.py -- signature unchanged
def cached_download(url: str, filename: str) -> Path
    # writes <filename>.part, renames it to <filename> once complete; on any error the
    # .part file is removed and nothing exists at <filename>

# etl/run_all.py -- signature unchanged
def _usda_csv_paths() -> tuple[Path, Path, Path]   # food.csv, nutrient.csv, food_nutrient.csv
    # extracts into .cache/usda_foundation_food.part/, renames its release directory to
    # .cache/usda_foundation_food/<USDA_CSV_DIRNAME> once complete; on any error the
    # .part directory is removed and no release directory exists
```
- The manifest, `manifest.json`:
```json
{
  "format": 1,
  "alembic_revision": "a3b4c5d6e7f8",
  "git_commit": "<40 hex characters, or unknown>",
  "created_at": "2026-09-24T13:25:12+00:00",
  "tables": {
    "nutrients": {
      "rows": 32,
      "sha256": "<64 hex characters>",
      "file": "nutrients.csv",
      "fingerprint": {"rows": 32, "md5": "<32 hex characters>"}
    }
  }
}
```
  All nine tables are listed, in load order. Each file is `<table>.csv`, written with `COPY … WITH (FORMAT csv, HEADER true)` and read back with `HEADER MATCH`, which refuses a file whose header is not the model's column list.
- Task 13's `DEPLOY.md` runs exactly these commands.

- [ ] **Step 1: Write the failing download tests**

Create `backend/tests/test_cached_download.py`:

```python
"""The ETL's download cache never keeps a partial file.

`cached_download` trusts any file already at its path, so a download cut off
halfway used to leave a truncated source that every later run loaded. A short
IFCT CSV loads without complaint, just with fewer foods. No network here: the
stream is a fake.
"""

import contextlib

import httpx
import pytest

from etl import common

URL = "https://example.invalid/ifct_compositions.csv"
WHOLE = b"code,name\nA001,Amaranth seed\nA002,Bajra\n"


class _Response:
    def __init__(self, chunks: list[bytes], *, fail_after: int | None = None) -> None:
        self._chunks = chunks
        self._fail_after = fail_after

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self):
        for n, chunk in enumerate(self._chunks):
            if n == self._fail_after:
                raise httpx.ReadError("the connection dropped")
            yield chunk


def _serve(monkeypatch, response: _Response) -> list[str]:
    """Answer every download with `response`; returns the URLs requested."""
    requested: list[str] = []

    @contextlib.contextmanager
    def stream(method, url, **kwargs):
        requested.append(url)
        yield response

    monkeypatch.setattr(common.httpx, "stream", stream)
    return requested


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "CACHE_DIR", tmp_path)
    return tmp_path


def test_a_download_cut_off_midway_leaves_nothing_behind(cache, monkeypatch):
    _serve(monkeypatch, _Response([b"code,name\n", b"A001,Amaranth seed\n"], fail_after=1))

    with pytest.raises(httpx.ReadError):
        common.cached_download(URL, "ifct_compositions.csv")

    assert not (cache / "ifct_compositions.csv").exists()
    assert list(cache.iterdir()) == []


def test_the_next_run_downloads_again_instead_of_trusting_a_fragment(cache, monkeypatch):
    _serve(monkeypatch, _Response([b"code,name\n", b"A001,Amaranth seed\n"], fail_after=1))
    with pytest.raises(httpx.ReadError):
        common.cached_download(URL, "ifct_compositions.csv")

    requested = _serve(monkeypatch, _Response([WHOLE]))
    path = common.cached_download(URL, "ifct_compositions.csv")

    assert requested == [URL]
    assert path == cache / "ifct_compositions.csv"
    assert path.read_bytes() == WHOLE


def test_a_part_file_left_by_a_killed_run_is_replaced(cache, monkeypatch):
    """A process killed mid-download never reaches its cleanup, so the next run
    finds the .part file. It is never trusted, and a finished download replaces it."""
    (cache / "ifct_compositions.csv.part").write_bytes(b"code,na")
    _serve(monkeypatch, _Response([WHOLE]))

    path = common.cached_download(URL, "ifct_compositions.csv")

    assert path.read_bytes() == WHOLE
    assert sorted(entry.name for entry in cache.iterdir()) == ["ifct_compositions.csv"]


def test_a_finished_download_is_reused_without_the_network(cache, monkeypatch):
    (cache / "ifct_compositions.csv").write_bytes(WHOLE)
    requested = _serve(monkeypatch, _Response([b"something else"]))

    path = common.cached_download(URL, "ifct_compositions.csv")

    assert requested == []
    assert path.read_bytes() == WHOLE
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cached_download.py -q`

Expected: `3 failed, 1 passed`. No database is touched.
- `test_a_download_cut_off_midway_leaves_nothing_behind` fails on `assert not True`: the fragment sits at the final path.
- `test_the_next_run_downloads_again_instead_of_trusting_a_fragment` fails on `assert [] == ['https://exa...ositions.csv']`: the second call trusted the fragment and never downloaded.
- `test_a_part_file_left_by_a_killed_run_is_replaced` fails on `Left contains one more item: 'ifct_compositions.csv.part'`.
- `test_a_finished_download_is_reused_without_the_network` passes already. It guards the behaviour the fix must keep.

- [ ] **Step 3: Write through a `.part` file**

In `backend/etl/common.py`, replace the whole of `cached_download` (from `def cached_download(url: str, filename: str) -> Path:` to its `return target`) with:

```python
def cached_download(url: str, filename: str) -> Path:
    """Download once into etl/.cache and reuse it on later runs.

    Any file at the final path is trusted as complete, so the download is written
    to a `.part` file beside it and renamed into place only once the last byte
    has arrived. An interrupted download leaves no file for a later run to load:
    a truncated IFCT CSV would otherwise load without error, just with fewer
    foods. A `.part` file left by a killed process is overwritten, never read.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / filename

    if not target.exists():
        partial = target.with_name(f"{target.name}.part")
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

    return target
```

`Path.replace` is an atomic rename on the same filesystem, and the `.part` file sits beside the target, so a reader sees either no file or the whole file. After a successful rename there is no `.part` left for the `finally` to remove, so `missing_ok=True` makes that a no-op.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/test_cached_download.py -q`

Expected: `4 passed`.

- [ ] **Step 5: Write the failing extraction tests**

Create `backend/tests/test_usda_extract.py`:

```python
"""The USDA archive is extracted whole or not at all.

`_usda_csv_paths` skips extraction once the release directory exists, so an
extraction cut off halfway used to leave a directory of missing and empty CSVs
that every later run loaded as the release. No network here: `cached_download`
is replaced, and the archive is a small zip built in the test's own directory.
"""

import zipfile

import pytest

from etl import run_all

RELEASE = run_all.USDA_CSV_DIRNAME
# In the order `_usda_csv_paths` returns them, and the order they are zipped.
FILES = {
    "food.csv": b'"fdc_id","description"\n"321358","Hummus, commercial"\n',
    "nutrient.csv": b'"id","name","unit_name"\n"1178","Vitamin B-12","UG"\n',
    "food_nutrient.csv": b'"id","fdc_id","nutrient_id","amount"\n"1","321358","1178","0.25"\n',
}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """`_usda_csv_paths` extracts beside the zip `cached_download` hands it, so a
    zip in tmp_path keeps the whole extraction there."""
    monkeypatch.setattr(run_all, "cached_download", lambda url, filename: tmp_path / filename)
    return tmp_path


def _archive(cache, *, damaged: bool = False) -> None:
    """Write the release as usda_foundation_food.zip, stored uncompressed.

    `damaged` changes a byte of food_nutrient.csv, the last member, after its
    checksum was recorded. Extraction then writes the first two files and fails
    on the third, as it would on a full disk or a corrupt download.
    """
    path = cache / "usda_foundation_food.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name, data in FILES.items():
            archive.writestr(f"{RELEASE}/{name}", data)
    if damaged:
        raw = path.read_bytes()
        assert raw.count(b'"0.25"') == 1
        path.write_bytes(raw.replace(b'"0.25"', b'"9.25"'))


def test_an_extraction_cut_off_midway_leaves_no_release_directory(cache):
    _archive(cache, damaged=True)

    with pytest.raises(zipfile.BadZipFile):
        run_all._usda_csv_paths()

    assert not (cache / "usda_foundation_food" / RELEASE).exists()
    assert sorted(entry.name for entry in cache.iterdir()) == ["usda_foundation_food.zip"]


def test_the_next_run_extracts_again_instead_of_trusting_a_fragment(cache):
    _archive(cache, damaged=True)
    with pytest.raises(zipfile.BadZipFile):
        run_all._usda_csv_paths()

    _archive(cache)
    paths = run_all._usda_csv_paths()

    assert paths == tuple(cache / "usda_foundation_food" / RELEASE / name for name in FILES)
    assert [path.read_bytes() for path in paths] == list(FILES.values())


def test_a_part_directory_left_by_a_killed_run_is_replaced(cache):
    """A process killed mid-extraction never reaches its cleanup, so the next run
    finds the .part directory. It is never trusted, and a finished extraction
    replaces it."""
    fragment = cache / "usda_foundation_food.part" / RELEASE
    fragment.mkdir(parents=True)
    (fragment / "food.csv").write_bytes(b'"fdc_id","descr')
    _archive(cache)

    paths = run_all._usda_csv_paths()

    assert [path.read_bytes() for path in paths] == list(FILES.values())
    assert sorted(entry.name for entry in cache.iterdir()) == [
        "usda_foundation_food",
        "usda_foundation_food.zip",
    ]


def test_a_finished_extraction_is_reused_without_opening_the_archive(cache):
    _archive(cache)
    run_all._usda_csv_paths()
    (cache / "usda_foundation_food.zip").write_bytes(b"not a zip")

    paths = run_all._usda_csv_paths()

    assert [path.read_bytes() for path in paths] == list(FILES.values())
```

The damaged archive is how the test makes `extractall` fail midway without patching `zipfile`'s internals. Each member is stored uncompressed, so its bytes sit verbatim in the zip, and changing one after the CRC was recorded makes `zipfile` raise `BadZipFile` when it reaches the end of that member. The first two files are already written by then. The `assert raw.count(...) == 1` makes sure the bytes changed are the member's data and nothing in the zip's headers.

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/test_usda_extract.py -q`

Expected: `3 failed, 1 passed`. No database is touched.
- `test_an_extraction_cut_off_midway_leaves_no_release_directory` fails on `assert not True`: the release directory is there, holding `food.csv`, `nutrient.csv` and an empty `food_nutrient.csv`.
- `test_the_next_run_extracts_again_instead_of_trusting_a_fragment` fails on `At index 2 diff: b'' != b'"id","fdc_id","nutrient_id","amount"\n"1","321358","1178","0.25"\n'`: the second call trusted the fragment and returned its empty `food_nutrient.csv`.
- `test_a_part_directory_left_by_a_killed_run_is_replaced` fails on `At index 1 diff: 'usda_foundation_food.part' != 'usda_foundation_food.zip'`: nothing removes the `.part` directory yet.
- `test_a_finished_extraction_is_reused_without_opening_the_archive` passes already. It guards the behaviour the fix must keep.

- [ ] **Step 7: Extract through a `.part` directory**

In `backend/etl/run_all.py`, add `import shutil` directly above `import zipfile`, so the imports begin:

```python
import shutil
import zipfile
from pathlib import Path
```

Then replace the whole of `_usda_csv_paths` (from `def _usda_csv_paths() -> tuple[Path, Path, Path]:` to its `return csv_dir / "food.csv", ...`) with:

```python
def _usda_csv_paths() -> tuple[Path, Path, Path]:
    """Download (if needed) and extract (if needed) the USDA Foundation Foods
    release, returning the three CSVs load_usda_gapfill reads.

    Extraction is skipped once the release directory exists, so a second run
    doesn't re-unzip a ~50 MB archive it already expanded. That makes the
    directory's existence the proof that extraction finished, so the archive is
    extracted into a `.part` directory beside it, and the release directory is
    renamed into place only once every file is out. An extraction cut off
    halfway (a full disk, a damaged archive) leaves nothing for a later run to
    load: an empty or cut-off food_nutrient.csv would otherwise load without
    error, just with fewer B12 and iodine values. A `.part` directory left by a
    killed process is deleted, never read.
    """
    zip_path = cached_download(USDA_URL, "usda_foundation_food.zip")
    extract_root = zip_path.parent / "usda_foundation_food"
    csv_dir = extract_root / USDA_CSV_DIRNAME

    if not csv_dir.exists():
        staging = extract_root.with_name(f"{extract_root.name}.part")
        shutil.rmtree(staging, ignore_errors=True)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(staging)
            extract_root.mkdir(exist_ok=True)
            (staging / USDA_CSV_DIRNAME).rename(csv_dir)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    return csv_dir / "food.csv", csv_dir / "nutrient.csv", csv_dir / "food_nutrient.csv"
```

Notes on the code:
- **The rename is the commit point.** `Path.rename` is an atomic rename on the same filesystem, and `usda_foundation_food.part/` sits beside `usda_foundation_food/` in `etl/.cache`. So a reader sees either no release directory or the whole one.
- **Only the release directory moves**, not `usda_foundation_food/` itself. The zip holds nothing else at its top level, and `csv_dir` is the directory the existence check reads, so it does not matter whether `usda_foundation_food/` is already there.
- **Both `rmtree` calls pass `ignore_errors=True`.** The first finds no `.part` directory on a normal run. The second finds one emptied by the rename, or none at all when the zip could not be opened.
- **A release directory extracted before this fix is still trusted.** Nothing can tell an old partial extraction from a whole one. `USDA gap-fill rows: 335` in Step 14's rehearsal is the check on an existing cache: a lower count means deleting `etl/.cache/usda_foundation_food` and running the ETL again.

- [ ] **Step 8: Run them to verify they pass**

Run: `uv run pytest tests/test_usda_extract.py -q`

Expected: `4 passed`.

- [ ] **Step 9: Write the failing snapshot tests**

Create `backend/tests/test_seed_snapshot.py`:

```python
"""The seed snapshot: export the reference tables, and load them into an empty database.

Everything runs on the test transaction's own connection (`db.connection()`), so
COPY reads and writes rows that the fixture's rollback takes away again. The
round trip empties the nine tables inside that transaction, children first, and
loads the snapshot back into them.
"""

import contextlib
import datetime
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.food import (
    Dish,
    DishIngredient,
    DishNutrient,
    Ingredient,
    IngredientNutrient,
    PortionMeasure,
)
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User
from scripts import seed_snapshot
from scripts.seed_snapshot import (
    SEED_TABLES,
    SNAPSHOT_FORMAT,
    SnapshotError,
    export_snapshot,
    fingerprints,
    import_snapshot,
)

# What the fixture exports: every seed row, and none of the cook's own dish.
EXPORTED = {
    "nutrients": 2,
    "ingredients": 2,
    "dishes": 2,
    "ingredient_nutrients": 3,
    "rda_reference": 2,
    "upper_limits": 1,
    "dish_ingredients": 1,
    "dish_nutrients": 1,
    "portion_measures": 3,
}
EMPTY = dict.fromkeys(EXPORTED, 0)


@pytest.fixture
def seeded(db) -> dict[str, uuid.UUID]:
    """A few rows in each of the nine tables, and one user's own dish with its rows.

    The values probe the CSV round trip: a comma, a quote and a newline inside a
    value, NULL beside an empty string, a float with no short decimal form, a
    NULL activity level, and two identical portion rows (the table has no
    unique constraint, and the ETL has written such pairs before).
    """
    energy = Nutrient(
        code="snap:energy",
        display_name="Energy",
        unit="kcal",
        category="macro",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=True,
    )
    calcium = Nutrient(
        code="snap:calcium",
        display_name='Calcium, "total"',
        unit="mg",
        category="mineral",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=False,
    )
    rice = Ingredient(
        code="snap:rice",
        name="Rice, parboiled, milled",
        source="IFCT",
        food_group="Cereals and Millets",
        diet_tags="vegetarian veg",
        search_aliases="arisi\nakki | chawal",
    )
    curd = Ingredient(code="snap:curd", name="Curd", source="USDA", food_group=None, diet_tags="")
    cook = User(google_sub="snap-cook", email="cook@example.com", name="Cook")
    db.add_all([energy, calcium, rice, curd, cook])
    db.flush()

    idli = Dish(
        code="snap:idli",
        name="Idli",
        source="authored",
        is_editable=True,
        slot_tags="breakfast dinner",
        diet_tags="vegetarian",
        yield_factor=1.4,
    )
    payasam = Dish(code="snap:indb-payasam", name="Payasam", source="INDB", yield_factor=1.0)
    own = Dish(
        code="snap:user-rasam",
        name="Amma's rasam",
        source="user",
        is_editable=True,
        yield_factor=1.0,
        created_by_user_id=cook.id,
    )
    db.add_all([idli, payasam, own])
    db.flush()

    db.add_all(
        [
            IngredientNutrient(
                ingredient_id=rice.id, nutrient_id=energy.id, per_100g=346.0, source="IFCT"
            ),
            IngredientNutrient(
                ingredient_id=rice.id, nutrient_id=calcium.id, per_100g=0.1 + 0.2, source="IFCT"
            ),
            IngredientNutrient(
                ingredient_id=curd.id, nutrient_id=calcium.id, per_100g=121.0, source=None
            ),
            RdaReference(
                nutrient_id=calcium.id,
                sex="female",
                age_band="18-59",
                activity_level=None,
                ear=800.0,
                rda=1000.0,
                ai=None,
                source="ICMR-NIN-2020",
            ),
            RdaReference(
                nutrient_id=energy.id,
                sex="male",
                age_band="60+",
                activity_level="sedentary",
                ear=None,
                rda=None,
                ai=1800.0,
                source="ICMR-NIN-2020",
            ),
            UpperLimit(
                nutrient_id=calcium.id, value=2500.0, supplemental_only=False, source="ICMR-TUL"
            ),
            DishIngredient(dish_id=idli.id, ingredient_id=rice.id, grams=60.0),
            DishNutrient(dish_id=payasam.id, nutrient_id=energy.id, per_100g=133.3),
            PortionMeasure(dish_id=idli.id, measure_name="1 idli", grams=40.0, is_default=True),
            PortionMeasure(dish_id=idli.id, measure_name="1 idli", grams=40.0, is_default=True),
            PortionMeasure(ingredient_id=curd.id, measure_name="1 katori", grams=100.0),
            # The cook's own dish, and every row hanging off it: none of these is exported.
            DishIngredient(dish_id=own.id, ingredient_id=curd.id, grams=50.0),
            DishNutrient(dish_id=own.id, nutrient_id=energy.id, per_100g=40.0),
            PortionMeasure(dish_id=own.id, measure_name="1 bowl", grams=150.0),
        ]
    )
    db.flush()
    return {"idli": idli.id, "own": own.id, "cook": cook.id}


def wipe(conn) -> None:
    """Empty the nine tables inside the test's transaction, children first."""
    for table in reversed(SEED_TABLES):
        conn.execute(text(f"DELETE FROM {table.name}"))


def row_counts(conn) -> dict[str, int]:
    return {name: fingerprint["rows"] for name, fingerprint in fingerprints(conn).items()}


def edit_manifest(snapshot: Path, change) -> None:
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the round trip ---------------------------------------------------------------------


def test_a_snapshot_loads_back_exactly_into_an_empty_database(db, seeded, tmp_path):
    conn = db.connection()
    before = fingerprints(conn)
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    assert row_counts(conn) == EMPTY

    import_snapshot(conn, tmp_path)

    assert fingerprints(conn) == before
    # The source's ids come across, so anything that points at a dish still finds it.
    idli = conn.execute(text("SELECT id FROM dishes WHERE code = 'snap:idli'")).scalar_one()
    assert idli == seeded["idli"]


def test_the_manifest_records_each_file_and_where_it_came_from(db, seeded, tmp_path):
    conn = db.connection()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    manifest = export_snapshot(conn, tmp_path, git_commit="abc123")

    assert manifest == json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == SNAPSHOT_FORMAT
    assert manifest["alembic_revision"] == revision
    assert manifest["git_commit"] == "abc123"
    created = datetime.datetime.fromisoformat(manifest["created_at"])
    assert created.utcoffset() == datetime.timedelta(0)
    # Load order, parents first.
    assert list(manifest["tables"]) == [table.name for table in SEED_TABLES]
    source = fingerprints(conn)
    for name, entry in manifest["tables"].items():
        assert entry["file"] == f"{name}.csv"
        assert entry["sha256"] == sha256_of(tmp_path / entry["file"])
        assert entry["fingerprint"] == source[name]
        assert entry["rows"] == source[name]["rows"]


def test_user_dishes_and_their_rows_stay_out_of_the_snapshot(db, seeded, tmp_path):
    manifest = export_snapshot(db.connection(), tmp_path, git_commit="abc123")

    assert {name: entry["rows"] for name, entry in manifest["tables"].items()} == EXPORTED
    exported = "".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.csv"))
    assert str(seeded["own"]) not in exported
    assert str(seeded["cook"]) not in exported
    assert "snap:user-rasam" not in exported


def test_an_export_never_writes_over_an_earlier_snapshot(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")

    with pytest.raises(SnapshotError, match="already holds a snapshot"):
        export_snapshot(conn, tmp_path, git_commit="def456")


# --- what the import refuses, leaving nothing loaded ----------------------------------


def test_the_import_refuses_a_database_that_already_holds_reference_data(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    before = fingerprints(conn)

    with pytest.raises(SnapshotError, match="already holds reference data"):
        import_snapshot(conn, tmp_path)

    assert fingerprints(conn) == before


def test_the_import_refuses_a_snapshot_taken_at_another_revision(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    edit_manifest(tmp_path, lambda manifest: manifest.update(alembic_revision="0123456789ab"))

    with pytest.raises(SnapshotError, match="alembic revision 0123456789ab"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_refuses_a_file_edited_after_the_export(db, seeded, tmp_path):
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    path = tmp_path / "ingredient_nutrients.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("346", "364"), encoding="utf-8")

    with pytest.raises(SnapshotError, match=r"ingredient_nutrients\.csv does not match"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_undoes_every_table_when_a_fingerprint_does_not_match(db, seeded, tmp_path):
    """A file edited and re-hashed passes the hash check. The fingerprints are
    compared after all nine tables are loaded, and the whole load goes back out."""
    conn = db.connection()
    export_snapshot(conn, tmp_path, git_commit="abc123")
    wipe(conn)
    path = tmp_path / "dishes.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("Idli", "Dosa"), encoding="utf-8")
    edit_manifest(
        tmp_path, lambda manifest: manifest["tables"]["dishes"].update(sha256=sha256_of(path))
    )

    with pytest.raises(SnapshotError, match=r"fingerprints \(dishes: the rows differ\)"):
        import_snapshot(conn, tmp_path)

    assert row_counts(conn) == EMPTY


def test_the_import_refuses_a_directory_with_no_manifest(db, tmp_path):
    with pytest.raises(SnapshotError, match="holds no manifest.json"):
        import_snapshot(db.connection(), tmp_path)


# --- the command line ---------------------------------------------------------------------


@pytest.fixture
def cli(db, monkeypatch):
    """main() on the test's connection. `_connection` is main's only way to a database,
    so nothing here can commit to one."""

    @contextlib.contextmanager
    def test_connection(**_options):
        yield db.connection()

    monkeypatch.setattr(seed_snapshot, "_connection", test_connection)
    monkeypatch.setattr(seed_snapshot, "_git_commit", lambda: "cli-commit")
    return db.connection()


def test_the_command_line_exports_imports_and_fingerprints(cli, seeded, tmp_path, capsys):
    before = fingerprints(cli)
    out = tmp_path / "seed-snapshot"

    assert seed_snapshot.main(["export", "--out", str(out)]) == 0
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["git_commit"] == (
        "cli-commit"
    )
    assert "dishes: 2 rows" in capsys.readouterr().out

    wipe(cli)
    assert seed_snapshot.main(["import", "--from", str(out)]) == 0
    assert "every table matches its fingerprint" in capsys.readouterr().out

    assert seed_snapshot.main(["fingerprint"]) == 0
    assert json.loads(capsys.readouterr().out) == before


def test_a_refused_import_exits_1_with_the_reason(cli, seeded, tmp_path, capsys):
    seed_snapshot.main(["export", "--out", str(tmp_path)])
    capsys.readouterr()

    assert seed_snapshot.main(["import", "--from", str(tmp_path)]) == 1
    assert "already holds reference data" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [[], ["export"], ["import"], ["import", "--out", "x"], ["restore", "--from", "x"]],
)
def test_the_command_line_rejects_incomplete_arguments(cli, argv, capsys):
    with pytest.raises(SystemExit) as exited:
        seed_snapshot.main(argv)

    assert exited.value.code == 2
    assert "usage:" in capsys.readouterr().err
```

The fixture's rows live only in the test's transaction, and the test database carries no seed data of its own (see `tests/conftest.py`). So the exact counts in `EXPORTED` hold, and `wipe` empties tables that held nothing else. The user dish is deleted by `wipe` too. It is not reloaded, and that is the point: the fingerprints ignore user dishes, so `before` and the reloaded database still match.

- [ ] **Step 10: Run them to verify they fail**

Run: `uv run pytest tests/test_seed_snapshot.py -q`

Expected: a collection error, `ImportError: cannot import name 'seed_snapshot' from 'scripts'`, then `1 error`.

- [ ] **Step 11: Write the script**

Create `backend/scripts/seed_snapshot.py`:

```python
"""Export the reference data to a snapshot, and load a snapshot into an empty database.

The ETL (`python -m etl.run_all`) builds the nine reference tables from three
downloads. A first deploy should not depend on those hosts being up, so the
snapshot carries the ETL's output instead: one CSV per table and a manifest.

Take it from a scratch database built fresh at HEAD (`alembic upgrade head`, then
`python -m etl.run_all`), never from the development database, which holds e2e
users and possibly rows from before the ETL's advisory lock.

    uv run python -m scripts.seed_snapshot export --out seed-snapshot
    uv run python -m scripts.seed_snapshot import --from seed-snapshot
    uv run python -m scripts.seed_snapshot fingerprint

DATABASE_URL picks the database, as it does for the app.

- The export keeps the source's UUIDs and leaves out every user-created dish and
  the rows hanging off one.
- The manifest records each file's row count and SHA-256, a fingerprint of each
  table over its natural keys, the alembic revision and the git commit.
- The import runs in one transaction. It refuses a database at another alembic
  revision, or one whose reference tables are not empty, and a file whose hash
  has changed. It then loads parents first, runs ANALYZE, and compares every
  table's fingerprint with the manifest before anything is committed.
- It is a one-time load. Refreshing a database that already has users goes
  through `etl.run_all`, which updates rows in place by code, so the ids that
  meal logs and plans point at are kept.

The snapshot is derived from IFCT, which has no open licence: keep it out of git
and out of any public release.
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy import Connection, text

from app.db import engine
from app.models.base import Base
from app.models.food import (
    Dish,
    DishIngredient,
    DishNutrient,
    Ingredient,
    IngredientNutrient,
    PortionMeasure,
)
from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit

SNAPSHOT_FORMAT = 1
MANIFEST = "manifest.json"

# A dish some user created is theirs, not reference data.
_SEED_DISH_IDS = "SELECT id FROM dishes WHERE created_by_user_id IS NULL"


def _fingerprint(fields: Sequence[str], rows: str) -> str:
    """A table's row count, and an md5 over its rows as natural keys and values.

    It names each row by codes rather than ids, so it compares across any two
    loads of the same data, and it reads references through their joins, so a
    row pointing at the wrong parent changes it. `quote_nullable` keeps NULL
    apart from '' and a '|' inside a value apart from the separator. The rows are
    sorted by their own text under the "C" collation, so the order does not
    depend on the server's locale or on duplicate rows.
    """
    line = "concat_ws('|', " + ", ".join(f"quote_nullable({field})" for field in fields) + ")"
    return (
        "SELECT count(*) AS rows,"
        " md5(coalesce(string_agg(line, E'\\n' ORDER BY line COLLATE \"C\"), '')) AS md5"
        f" FROM (SELECT {line} AS line FROM {rows}) AS lines"
    )


@dataclass(frozen=True)
class SeedTable:
    name: str
    model: type[Base]  # columns come from model.__table__.columns, in table order
    where: str | None  # SQL filter on the export, None for every row
    fingerprint_sql: str  # SELECT count(*), md5(string_agg(... ORDER BY natural key)) ...


# Load order: every table after the tables it points at.
SEED_TABLES: tuple[SeedTable, ...] = (
    SeedTable(
        "nutrients",
        Nutrient,
        None,
        _fingerprint(
            [
                "n.code",
                "n.display_name",
                "n.unit",
                "n.category",
                "n.is_compensable",
                "n.compensation_days",
                "n.is_excess_sensitive",
            ],
            "nutrients AS n",
        ),
    ),
    SeedTable(
        "ingredients",
        Ingredient,
        None,
        _fingerprint(
            [
                "i.code",
                "i.name",
                "i.source",
                "i.food_group",
                "i.diet_tags",
                "i.oxalate_class",
                "i.search_aliases",
            ],
            "ingredients AS i",
        ),
    ),
    SeedTable(
        "dishes",
        Dish,
        "created_by_user_id IS NULL",
        _fingerprint(
            [
                "d.code",
                "d.name",
                "d.source",
                "d.is_editable",
                "d.slot_tags",
                "d.diet_tags",
                "d.yield_factor",
            ],
            "dishes AS d WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "ingredient_nutrients",
        IngredientNutrient,
        None,
        _fingerprint(
            ["i.code", "n.code", "x.per_100g", "x.source"],
            "ingredient_nutrients AS x"
            " JOIN ingredients AS i ON i.id = x.ingredient_id"
            " JOIN nutrients AS n ON n.id = x.nutrient_id",
        ),
    ),
    SeedTable(
        "rda_reference",
        RdaReference,
        None,
        _fingerprint(
            [
                "n.code",
                "r.sex",
                "r.age_band",
                "r.activity_level",
                "r.ear",
                "r.rda",
                "r.ai",
                "r.source",
            ],
            "rda_reference AS r JOIN nutrients AS n ON n.id = r.nutrient_id",
        ),
    ),
    SeedTable(
        "upper_limits",
        UpperLimit,
        None,
        _fingerprint(
            ["n.code", "u.value", "u.supplemental_only", "u.source"],
            "upper_limits AS u JOIN nutrients AS n ON n.id = u.nutrient_id",
        ),
    ),
    SeedTable(
        "dish_ingredients",
        DishIngredient,
        f"dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "i.code", "x.grams"],
            "dish_ingredients AS x"
            " JOIN dishes AS d ON d.id = x.dish_id"
            " JOIN ingredients AS i ON i.id = x.ingredient_id"
            " WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "dish_nutrients",
        DishNutrient,
        f"dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "n.code", "x.per_100g"],
            "dish_nutrients AS x"
            " JOIN dishes AS d ON d.id = x.dish_id"
            " JOIN nutrients AS n ON n.id = x.nutrient_id"
            " WHERE d.created_by_user_id IS NULL",
        ),
    ),
    SeedTable(
        "portion_measures",
        PortionMeasure,
        f"dish_id IS NULL OR dish_id IN ({_SEED_DISH_IDS})",
        _fingerprint(
            ["d.code", "i.code", "p.measure_name", "p.grams", "p.is_default"],
            "portion_measures AS p"
            " LEFT JOIN dishes AS d ON d.id = p.dish_id"
            " LEFT JOIN ingredients AS i ON i.id = p.ingredient_id"
            " WHERE p.dish_id IS NULL OR d.created_by_user_id IS NULL",
        ),
    ),
)


class SnapshotError(RuntimeError):
    """A snapshot that cannot be written or loaded, and why, in plain words."""


def fingerprints(conn: Connection) -> dict[str, dict[str, object]]:
    """Every seed table's row count and md5, keyed by table name, in load order."""
    result: dict[str, dict[str, object]] = {}
    for table in SEED_TABLES:
        row = conn.execute(text(table.fingerprint_sql)).one()
        result[table.name] = {"rows": row.rows, "md5": row.md5}
    return result


def export_snapshot(conn: Connection, out_dir: Path, *, git_commit: str) -> dict:
    """Write one CSV per seed table and a manifest into `out_dir`. Returns the manifest.

    The manifest is written last, so an export that fails partway leaves a
    directory that the import refuses.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / MANIFEST).exists():
        raise SnapshotError(f"{out_dir} already holds a snapshot; export into a new directory")

    expected = fingerprints(conn)
    tables: dict[str, dict[str, object]] = {}
    for table in SEED_TABLES:
        path = out_dir / f"{table.name}.csv"
        rows, sha256 = _copy_out(conn, table, path)
        if rows != expected[table.name]["rows"]:
            raise SnapshotError(
                f"{table.name}: the export wrote {rows} rows but the fingerprint counts "
                f"{expected[table.name]['rows']}; the export filter and the fingerprint disagree"
            )
        tables[table.name] = {
            "rows": rows,
            "sha256": sha256,
            "file": path.name,
            "fingerprint": expected[table.name],
        }

    manifest = {
        "format": SNAPSHOT_FORMAT,
        "alembic_revision": _revision(conn),
        "git_commit": git_commit,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "tables": tables,
    }
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def import_snapshot(conn: Connection, src: Path) -> None:
    """Load a snapshot into a database whose reference tables are empty.

    Every check that needs no write runs first. The load itself runs under a
    savepoint, so a fingerprint that does not match takes every loaded row back
    out, whether the caller then commits or not.
    """
    manifest = _read_manifest(src)
    revision = _revision(conn)
    if manifest["alembic_revision"] != revision:
        raise SnapshotError(
            f"The snapshot was taken at alembic revision {manifest['alembic_revision']}, but "
            f"the target database is at {revision}. Migrate the target, or export a new "
            "snapshot from a database at the same revision."
        )
    occupied = [
        table.name
        for table in SEED_TABLES
        if conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {table.name})")).scalar_one()
    ]
    if occupied:
        raise SnapshotError(
            f"The target database already holds reference data ({', '.join(occupied)}). "
            "A snapshot loads only into empty tables; refresh a live database with "
            "`python -m etl.run_all` instead."
        )
    contents = {table.name: _verified_file(src, table, manifest) for table in SEED_TABLES}

    with conn.begin_nested():
        for table in SEED_TABLES:
            _copy_in(conn, table, contents[table.name])
        for table in SEED_TABLES:
            # Without statistics the planner's dish-nutrient join has been seen to
            # take 28 s per dish instead of 0.09 s (tests/test_dish_coverage.py).
            conn.execute(text(f"ANALYZE {table.name}"))
        _check_fingerprints(fingerprints(conn), manifest)


def _columns(table: SeedTable) -> str:
    return ", ".join(f'"{column.name}"' for column in table.model.__table__.columns)


def _copy_out(conn: Connection, table: SeedTable, path: Path) -> tuple[int, str]:
    """COPY one table's rows to `path`; returns (rows, sha256)."""
    where = f" WHERE {table.where}" if table.where else ""
    sql = (
        f"COPY (SELECT {_columns(table)} FROM {table.name}{where} ORDER BY id)"
        " TO STDOUT WITH (FORMAT csv, HEADER true)"
    )
    digest = hashlib.sha256()
    raw = conn.connection.driver_connection
    with path.open("wb") as handle, raw.cursor() as cursor:
        with cursor.copy(sql) as copy:
            for block in copy:
                handle.write(block)
                digest.update(block)
        rows = cursor.rowcount
    return rows, digest.hexdigest()


def _copy_in(conn: Connection, table: SeedTable, data: bytes) -> None:
    """COPY one CSV into its table. HEADER MATCH refuses a file whose columns differ."""
    sql = f"COPY {table.name} ({_columns(table)}) FROM STDIN WITH (FORMAT csv, HEADER MATCH)"
    raw = conn.connection.driver_connection
    try:
        with raw.cursor() as cursor, cursor.copy(sql) as copy:
            copy.write(data)
    except psycopg.Error as exc:
        raise SnapshotError(
            f"{table.name}.csv could not be loaded: {type(exc).__name__}: "
            f"{exc.diag.message_primary}"
        ) from exc


def _read_manifest(src: Path) -> dict:
    path = src / MANIFEST
    if not path.is_file():
        raise SnapshotError(f"{src} holds no {MANIFEST}, so it is not a finished snapshot")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        snapshot_format = manifest["format"]
        listed = set(manifest["tables"])
        entries_complete = isinstance(manifest["alembic_revision"], str) and all(
            {"sha256", "fingerprint"} <= set(entry) for entry in manifest["tables"].values()
        )
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise SnapshotError(f"{path} is not a snapshot manifest") from exc
    if not entries_complete:
        raise SnapshotError(f"{path} is not a snapshot manifest")
    if snapshot_format != SNAPSHOT_FORMAT:
        raise SnapshotError(
            f"{src} is snapshot format {snapshot_format}; this script reads format "
            f"{SNAPSHOT_FORMAT}"
        )
    expected = {table.name for table in SEED_TABLES}
    if listed != expected:
        raise SnapshotError(
            f"The manifest lists the tables {sorted(listed)}, not the seed tables "
            f"{sorted(expected)}"
        )
    return manifest


def _verified_file(src: Path, table: SeedTable, manifest: dict) -> bytes:
    """The table's CSV, read once, after its hash matched the manifest."""
    path = src / f"{table.name}.csv"
    if not path.is_file():
        raise SnapshotError(f"{path.name} is missing from {src}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["tables"][table.name]["sha256"]:
        raise SnapshotError(
            f"{path.name} does not match its manifest (its SHA-256 differs), so the "
            "snapshot is damaged or was edited after export"
        )
    return data


def _check_fingerprints(loaded: dict[str, dict[str, object]], manifest: dict) -> None:
    problems = []
    for table in SEED_TABLES:
        expected = manifest["tables"][table.name]["fingerprint"]
        got = loaded[table.name]
        if got["rows"] != expected["rows"]:
            problems.append(f"{table.name}: {got['rows']} rows loaded, {expected['rows']} expected")
        elif got["md5"] != expected["md5"]:
            problems.append(f"{table.name}: the rows differ")
    if problems:
        raise SnapshotError(
            "The loaded data does not match the manifest's fingerprints ("
            + "; ".join(problems)
            + "), so nothing was imported"
        )


def _revision(conn: Connection) -> str:
    """The database's one alembic revision."""
    if conn.execute(text("SELECT to_regclass('alembic_version')")).scalar() is None:
        raise SnapshotError(
            "The database has no alembic_version table. Run `alembic upgrade head` on it first."
        )
    revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(revisions) != 1:
        raise SnapshotError(f"The database's alembic_version holds {revisions}, not one revision")
    return revisions[0]


@contextlib.contextmanager
def _connection(*, repeatable_read: bool = False) -> Iterator[Connection]:
    """One connection in one transaction: committed if the block succeeds, else rolled back.

    The export reads under REPEATABLE READ, so every file and every fingerprint
    come from the same snapshot of the database.
    """
    options = {"isolation_level": "REPEATABLE READ"} if repeatable_read else {}
    with engine.connect().execution_options(**options) as conn, conn.begin():
        yield conn


def _git_commit() -> str:
    """The checkout's commit, so a snapshot can be traced to the ETL that built it."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_snapshot",
        description="Export the reference data to a snapshot, or load one into an empty database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write a snapshot of this database")
    export.add_argument("--out", type=Path, required=True, help="a new or empty directory")
    load = commands.add_parser("import", help="load a snapshot into this empty database")
    load.add_argument("--from", dest="source", type=Path, required=True, help="a snapshot")
    commands.add_parser("fingerprint", help="print each seed table's row count and md5")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "export":
            with _connection(repeatable_read=True) as conn:
                manifest = export_snapshot(conn, args.out, git_commit=_git_commit())
            for name, table in manifest["tables"].items():
                print(f"{name}: {table['rows']} rows")
            print(f"snapshot written to {args.out}")
        elif args.command == "import":
            with _connection() as conn:
                import_snapshot(conn, args.source)
            print(f"imported {args.source}: every table matches its fingerprint")
        else:
            with _connection() as conn:
                print(json.dumps(fingerprints(conn), indent=2))
    except SnapshotError as exc:
        print(f"seed snapshot: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Notes on the code:
- **The export double-checks its filter.** `export_snapshot` compares each file's COPY row count with that table's fingerprint count. The export's `where` and the fingerprint's `WHERE` are written separately, so an edit that changed one and not the other would fail here, at export, rather than as a fingerprint mismatch at import.
- **COPY runs on the driver connection.** `conn.connection.driver_connection` is the psycopg connection under the SQLAlchemy `Connection`, so COPY runs inside the caller's transaction: the command's own transaction, or the test's.
- **The savepoint.** `conn.begin_nested()` is a SAVEPOINT. The checks before it write nothing, and a failure inside it rolls back every COPY, including a psycopg error from a malformed file, which becomes a `SnapshotError` naming the file.
- **One read per file.** `_verified_file` reads each file once and hashes those bytes, and the same bytes are loaded. The whole snapshot is about 8.5 MB.
- **REPEATABLE READ on export**, so the fingerprints and all nine files come from one snapshot of the source.
- **Why `ANALYZE`.** Without statistics, the planner's dish-nutrient join has been measured at 28 s per dish instead of 0.09 s (`tests/test_dish_coverage.py`). `ANALYZE` may run inside a transaction; `VACUUM` may not.

- [ ] **Step 12: Run the snapshot tests to verify they pass**

Run: `uv run pytest tests/test_seed_snapshot.py -q`

Expected: `16 passed`, in about 10 seconds.

- [ ] **Step 13: Keep the snapshot out of git**

In the root `.gitignore`, directly after the line `backend/etl/.cache/`, add:

```
# The seed snapshot (backend/scripts/seed_snapshot.py). It is derived from IFCT, which
# has no open licence, so it never goes into git or a public release.
backend/seed-snapshot/
```

- [ ] **Step 14: Rehearse it on real data, in two scratch databases**

This is the path `DEPLOY.md` (Task 13) gives the owner: a database built fresh at HEAD by the ETL, exported, and imported into another empty database at HEAD. Both are scratch databases in the compose Postgres, created and dropped here. Never point these commands at `healthmonitor` or `healthmonitor_test`.

The ETL reads its three source files from `backend/etl/.cache` when they are there; otherwise it downloads about 5.6 MB. It also reuses the USDA release already extracted there. `USDA gap-fill rows: 335` below is the check on that directory (see Step 7's notes).

From the repository root, create both databases:

```bash
docker compose exec -T db createdb -U healthmonitor healthmonitor_seed
docker compose exec -T db createdb -U healthmonitor healthmonitor_seed_target
```

From `backend/`, migrate both and fill the source:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed_target uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run python -m etl.run_all
```

Expected: the ETL prints the following, in about two minutes on colima:

```
nutrients: 32
reference rows: 60 RDA, 16 upper limits
ingredients (IFCT): 542
ingredients (manual): 5
USDA gap-fill rows: 335
recipes (authored dishes): 72
reference dishes (INDB): 1014
```

Export:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run python -m scripts.seed_snapshot export --out seed-snapshot
```

Expected, in a few seconds:

```
nutrients: 32 rows
ingredients: 547 rows
dishes: 1086 rows
ingredient_nutrients: 16747 rows
rda_reference: 60 rows
upper_limits: 16 rows
dish_ingredients: 680 rows
dish_nutrients: 29406 rows
portion_measures: 1022 rows
snapshot written to seed-snapshot
```

Those are the counts a clean ETL at HEAD produces. `16747` is the same `ingredient_nutrients` figure that `tests/test_dish_coverage.py` records independently. `du -sh seed-snapshot` shows about 8.5M, and `grep alembic_revision seed-snapshot/manifest.json` shows `"a3b4c5d6e7f8"`.

Import, and compare both databases:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed_target uv run python -m scripts.seed_snapshot import --from seed-snapshot
diff <(DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed uv run python -m scripts.seed_snapshot fingerprint) \
     <(DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed_target uv run python -m scripts.seed_snapshot fingerprint) \
  && echo "fingerprints identical"
```

Expected:
- The import prints `imported seed-snapshot: every table matches its fingerprint`. It takes about 30 seconds on colima, most of it the per-row foreign-key checks on `dish_nutrients` and `ingredient_nutrients`.
- The diff prints `fingerprints identical`.

Run the import again, to see the refusal a second load gets:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_seed_target uv run python -m scripts.seed_snapshot import --from seed-snapshot; echo "exit $?"
```

Expected: `seed snapshot: The target database already holds reference data (nutrients, ingredients, dishes, ingredient_nutrients, rda_reference, upper_limits, dish_ingredients, dish_nutrients, portion_measures). A snapshot loads only into empty tables; refresh a live database with `python -m etl.run_all` instead.`, then `exit 1`.

Check that the planner has its dishes in the target, and that the load analysed the tables:

```bash
docker compose exec -T db psql -U healthmonitor -d healthmonitor_seed_target -Atc \
  "select count(*) from dishes where slot_tags is not null; select count(*) from pg_stat_user_tables where relname in ('dishes', 'dish_nutrients', 'ingredient_nutrients') and last_analyze is not null"
```

Expected: `72`, then `3`.

Check that git ignores the snapshot. From the repository root, run `git status --short --ignored backend/seed-snapshot`. Expected: `!! backend/seed-snapshot/`.

Then clean up. From `backend/`, delete the snapshot, since a deploy exports a fresh one at the commit it deploys (see `DEPLOY.md`):

```bash
rm -rf seed-snapshot
```

From the repository root, drop both databases:

```bash
docker compose exec -T db dropdb -U healthmonitor healthmonitor_seed
docker compose exec -T db dropdb -U healthmonitor healthmonitor_seed_target
docker compose exec -T db psql -U healthmonitor -Atc "select datname from pg_database where datname like 'healthmonitor%' order by 1"
```

Expected: the last command prints `healthmonitor` and `healthmonitor_test`, and nothing else from this task.

- [ ] **Step 15: Run the checks**

```bash
uv run pytest tests/test_cached_download.py tests/test_usda_extract.py tests/test_seed_snapshot.py tests/test_load_ifct.py tests/test_run_all.py -q
uv run ruff check .
uv run ruff format --check scripts/seed_snapshot.py etl/common.py etl/run_all.py tests/test_seed_snapshot.py tests/test_cached_download.py tests/test_usda_extract.py
```

Expected: `44 passed`, then ruff clean, and `6 files already formatted`. `test_load_ifct.py` calls `cached_download` on the real cache, which shows the fixed function still reuses a finished file without the network. Step 14's ETL run did the same for `_usda_csv_paths` and the extracted release.

- [ ] **Step 16: Commit**

From the repository root:

```bash
git add .gitignore backend/etl/common.py backend/etl/run_all.py backend/scripts/seed_snapshot.py \
  backend/tests/test_cached_download.py backend/tests/test_usda_extract.py \
  backend/tests/test_seed_snapshot.py
git commit -m "feat(backend): export and import a seed snapshot, and stop trusting a partial ETL cache

A first deploy needs the nine reference tables, and the ETL builds them
from three third-party downloads at run time. scripts.seed_snapshot takes
the ETL's output from a scratch database built fresh at HEAD instead. It
writes one CSV per table with COPY, keeping the source's ids and leaving
out user-created dishes and their rows, plus a manifest with each file's
SHA-256, a per-table fingerprint over natural keys, the alembic revision
and the git commit.

The import loads only into a database at the same revision whose
reference tables are empty, and refuses a file whose hash changed. It
loads parents first under one savepoint, runs ANALYZE, and compares
every table's fingerprint with the manifest, so a mismatch leaves
nothing loaded. A database that already has users is refreshed by
etl.run_all, which updates rows in place and keeps the ids that logs and
plans point at. Not pg_dump: that needs matching client binaries, cannot
filter rows and cannot run under the test suite.

The snapshot derives from IFCT, which has no open licence, so it is
gitignored (and dockerignored since the image task).

cached_download streamed into the final path and trusted any file there,
so an interrupted download left a truncated source that later runs
loaded, and a short IFCT CSV loads without error. It now writes a .part
file and renames it into place once complete.

_usda_csv_paths unzipped the USDA release only when its directory was
missing, so an extraction cut off halfway left a directory that later
runs loaded, and an empty food_nutrient.csv loads without error. It now
extracts into a .part directory and renames the release into place once
every file is out.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: CI

CI is `.github/workflows/ci.yml`. It has three jobs today: `backend`, `frontend` and `e2e`. Neither plan 8 nor Tasks 1 to 11 touch it (`git log --oneline -1 -- .github/workflows/ci.yml` still prints `ac051d0 test: add the Playwright smoke test, against the real backend`). This task rewrites it to check what a deploy ships, and still deploys nothing.

**When it runs, and with what.**
- `push` now runs on `main` only. Until now a push to a pull request's branch fired both `push` and `pull_request`, so every job ran twice.
- A top-level `permissions: contents: read` makes every job read-only. No job needs more: the Docker layer cache and the Playwright artifact go through the runner's own token, not `GITHUB_TOKEN`.

**`backend`.**
- `uv sync` becomes `uv sync --locked`, here and in `e2e`. A `uv.lock` that no longer matches `pyproject.toml` then fails the job, as the image build (Task 9) already does, instead of being quietly re-resolved.
- There is no Python setting to add. uv reads `backend/.python-version` (Task 8, `3.13`) for every `uv sync` and `uv run` in `backend/`, and downloads 3.13 when the runner has only its system 3.12. The tests therefore run on the image's Python.

**`frontend`.**
- It gains `npm run lint`. The plan's frontend checks have always been `tsc -b`, vitest, lint and build, but CI ran only three of them.
- The build step sets `VITE_API_BASE: https://api.example.invalid` and `VITE_GOOGLE_CLIENT_ID: ci-placeholder`, because Task 10's `vite.config.ts` stops a production build without an API base.
- A new step then checks the build output:
  - no `localhost:8000` in `dist/assets`, and the placeholder base present;
  - `dist/_headers` and `dist/_redirects` present;
  - no `dist/404.html`, which would switch off Cloudflare Pages' SPA fallback;
  - no rule in `_redirects`. Task 10 explains why a catch-all there answers `/sw.js` with `index.html`;
  - `importScripts("push-handlers.js")` in `dist/sw.js`, and `dist/push-handlers.js` present (plan 8 Task 12);
  - no navigation `denylist` left in `dist/sw.js`.

  Every check fails through a small `fail` function, never through a trailing `! grep`. GitHub runs `run:` scripts with `bash -e`, and bash does not exit on a failed command whose status is negated with `!`. So `! grep -q …` on any line but the last could never fail the step.

**A new `image` job.** It builds `backend/Dockerfile` (Task 9) with buildx into the runner's own Docker (`load: true`, `push: false`) and runs it the way Fly runs it:
1. It runs as a non-root user and ships no `.env`, no `tests/`, no `seed-snapshot/` and no `scripts/e2e_*.py`. The last matters most: `e2e_session.py` signs a real session for any user it is pointed at. A fresh checkout has neither a `.env` nor a snapshot, so the job first writes decoys into the build context. Without them, the check could never fail. With them, only `backend/.dockerignore` keeps them out. The checkout does have `scripts/e2e_seed.py` and `scripts/e2e_session.py`. A third decoy, `scripts/e2e_decoy.py`, stands for any e2e script added later, so the check still bites if those two are renamed.
2. The release step, `alembic upgrade head`, runs from the image against an empty Postgres 16 service, followed by `alembic check`. The containers use `--network host`, so `localhost:5433` inside them is the service's published port on the runner.
3. It boots the server and waits up to 30 seconds for `/health`, printing the container's log if it never answers.
4. `APP_ENV=production` with nothing else set must fail to start. The failure must name all five problems from Task 8's validator and must not contain `input_value`. Pydantic prints the settings' input there unless `hide_input_in_errors` is set, and in production that input holds the database password, the session secret and the LLM keyring. The step checks exit code 124 separately, so an image that serves instead of refusing fails the step after 60 seconds instead of hanging it.

The two new actions are at their current majors, `docker/setup-buildx-action@v4` and `docker/build-push-action@v7`, both on the Node 24 runtime. The existing pins (`actions/checkout@v4`, `actions/setup-node@v4`, `astral-sh/setup-uv@v5`, `actions/upload-artifact@v4`) stay as they are. Upgrading them is a separate change.

**`e2e`.** It still runs uvicorn from source, with `uv sync --locked`. Its Playwright web server is `npm run dev` (`frontend/playwright.config.ts`), so it never makes a production build and needs no `VITE_API_BASE`. A comment in the job says so.

Nothing here can be run on GitHub from this task, since nothing is pushed. It is checked locally instead:
- the YAML parses;
- `actionlint`, which includes shellcheck over every `run:` script, is clean;
- the frontend job's check script, cut straight out of the YAML, passes on a real build and fails on four broken copies of it;
- the image job's two database-free checks pass against a locally built image and fail against a stock one, and the exclusion check fails against a copy of the image that ships `scripts/e2e_session.py`.

The release step and the boot are left out of the local run. They need a database, and Task 9 already ran the same commands from the image against a scratch database. The only difference in CI is how the container reaches Postgres.

Run every command from the repository root unless a step says otherwise.

**Files:**
- Modify: `.github/workflows/ci.yml` (rewritten whole)
- Test: no test file. The workflow's own scripts are exercised in Steps 3 to 5.

**Interfaces:**
- Consumes:
  - Task 8:
    - `backend/.python-version` (`3.13`) and `APP_ENV`;
    - the refusal `Refusing to start in production: ` followed by the five problems, joined with `; `: `SESSION_SECRET is the development default or shorter than 32 characters`, `GOOGLE_CLIENT_ID is empty`, `COOKIE_SECURE must be true`, `FRONTEND_ORIGIN must be an https:// origin with no trailing slash`, `DATABASE_URL points at localhost`;
    - `hide_input_in_errors=True` on `Settings.model_config`, so the error line ends `[type=value_error]` with no `input_value`;
    - `settings = Settings()` at import, so `uvicorn app.main:app` exits non-zero on the refusal.
  - Task 9:
    - `backend/Dockerfile`, built from the context `backend/`. It has a `USER` that is not root (uid 10001), and a `CMD`, not an `ENTRYPOINT`, that `exec`s uvicorn on `${PORT}` (8000) with `--workers 1`. `docker run IMAGE id -u` and `docker run IMAGE alembic …` rely on that: an `ENTRYPOINT` would take them as its arguments.
    - `WORKDIR /app` holds `alembic.ini`, and `alembic` is on `PATH`.
    - The `builder` stage carries `LABEL healthmonitor.stage=builder`. The classic builder leaves that stage behind as untagged images, which removing the tag does not delete, so Step 5's cleanup prunes them by that label.
    - `backend/.dockerignore` excludes `.env`, `tests/`, `scripts/e2e_*.py` and `seed-snapshot/`.
  - Task 10:
    - the production-build guard;
    - `frontend/public/_headers`, and `frontend/public/_redirects` with no rules;
    - no `navigateFallbackDenylist`.
  - Task 11: the snapshot directory `backend/seed-snapshot/`.
  - Plan 8 Task 12: `frontend/public/push-handlers.js` and `workbox.importScripts`.
- Produces:
  - `.github/workflows/ci.yml`:
    - jobs `backend`, `frontend`, `image`, `e2e`;
    - `on: push: branches: [main]` and `pull_request`;
    - `permissions: contents: read`.
  - The step names Steps 4 and 5 cut out of the YAML: `Check the build output` (frontend), `It runs as a non-root user, and ships no .env, tests, snapshot or e2e scripts` and `It refuses to start in production with development settings` (image).
  - For Task 13's `DEPLOY.md`:
    - CI builds and boots the image and checks the SPA build, but never deploys: no registry push, no `flyctl`, no `wrangler`, no secrets.
    - The e2e walk still runs the API from source.

- [ ] **Step 1: Confirm the starting point**

Run: `git log --oneline -1 -- .github/workflows/ci.yml && grep -n 'uv sync\|^  [a-z0-9]*:$' .github/workflows/ci.yml`

Expected:

```
ac051d0 test: add the Playwright smoke test, against the real backend
4:  push:
8:  backend:
27:      - run: uv sync
42:  frontend:
60:  e2e:
86:      - run: uv sync
```

If the file has changed since, carry those changes into the version below.

- [ ] **Step 2: Rewrite the workflow**

Replace the whole of `.github/workflows/ci.yml` with:

```yaml
name: CI

# A pull request runs once, for its own event, and a push runs only on main, where it
# checks what was merged. Before, both events fired for every push to a pull request's
# branch. Nothing here deploys: no registry push, no flyctl or wrangler, no secrets.
on:
  push:
    branches: [main]
  pull_request:

# Every job only reads the repository.
permissions:
  contents: read

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: healthmonitor
          POSTGRES_PASSWORD: healthmonitor
          POSTGRES_DB: healthmonitor_test
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -U healthmonitor"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      # --locked fails when uv.lock no longer matches pyproject.toml, as the image
      # build does, instead of quietly re-resolving. uv reads the Python version
      # from backend/.python-version, the image's 3.13.
      - run: uv sync --locked
        working-directory: backend
      - run: uv run ruff check .
        working-directory: backend
      - run: uv run alembic upgrade head
        working-directory: backend
        env:
          DATABASE_URL: postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test
      - run: uv run alembic check
        working-directory: backend
        env:
          DATABASE_URL: postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test
      - run: uv run pytest -v
        working-directory: backend

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
        working-directory: frontend
      # `-b`, not `--noEmit`: the root tsconfig is `files: []` with project
      # references, so `tsc --noEmit` type-checks an empty program and always passes.
      - run: npx tsc -b
        working-directory: frontend
      - run: npx vitest run
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      # Built the way a deploy builds it, with placeholders for the two public values.
      # vite.config.ts refuses a production build without VITE_API_BASE, which would
      # otherwise call http://localhost:8000.
      - name: Build
        run: npm run build
        working-directory: frontend
        env:
          VITE_API_BASE: https://api.example.invalid
          VITE_GOOGLE_CLIENT_ID: ci-placeholder
      # Each check calls fail() rather than ending in `! grep`: bash -e ignores a
      # failure negated with `!`, so such a line could never fail the step.
      - name: Check the build output
        working-directory: frontend
        run: |
          fail() { echo "::error::$*"; exit 1; }

          # The API base went in, and the localhost fallback did not.
          grep -rq 'https://api.example.invalid' dist/assets \
            || fail "the bundle does not use VITE_API_BASE"
          if grep -rl 'localhost:8000' dist/assets; then
            fail "the files above call http://localhost:8000"
          fi

          # Cloudflare Pages reads both files from the build output.
          [ -f dist/_headers ] || fail "dist/_headers is missing"
          [ -f dist/_redirects ] || fail "dist/_redirects is missing"

          # Pages answers an unknown path with index.html only while the build has no
          # top-level 404.html. It applies _redirects before it looks for a file, so any
          # rule there could answer /sw.js with index.html (frontend/public/_redirects).
          [ ! -e dist/404.html ] || fail "dist/404.html turns off the Pages SPA fallback"
          if grep -Ev '^[[:space:]]*(#|$)' dist/_redirects; then
            fail "dist/_redirects has the rule above"
          fi

          # The generated worker loads the push handlers, and the file ships beside it.
          grep -q 'importScripts("push-handlers.js")' dist/sw.js \
            || fail "dist/sw.js does not import push-handlers.js"
          [ -f dist/push-handlers.js ] || fail "dist/push-handlers.js is missing"

          # No navigation denylist: the old one caught the SPA's own /foods route.
          if grep -o 'denylist:[^}]*' dist/sw.js; then
            fail "dist/sw.js still has the navigation denylist above"
          fi

  image:
    # The API image a deploy would ship, run the way Fly runs it: the release step
    # against a real Postgres, then the server. It is loaded into this runner's
    # Docker and never pushed anywhere.
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: healthmonitor
          POSTGRES_PASSWORD: healthmonitor
          POSTGRES_DB: healthmonitor
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -U healthmonitor"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      IMAGE: healthmonitor-api:ci
      # The service's port on the runner. Every `docker run` below that needs the
      # database uses --network host, so localhost in the container is the runner.
      DATABASE_URL: postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor
    steps:
      - uses: actions/checkout@v4

      # A checkout has no .env and no snapshot, so without decoys the check below
      # could never fail for them. It does have scripts/e2e_seed.py and
      # e2e_session.py, and the third decoy stands for any e2e script added later.
      # With the decoys in place, only backend/.dockerignore keeps them out.
      - name: Put decoys where .dockerignore must stop them
        run: |
          set -o noclobber   # never overwrite a real one
          printf 'SESSION_SECRET=decoy-that-must-not-reach-the-image\n' > backend/.env
          mkdir -p backend/seed-snapshot
          printf '{}\n' > backend/seed-snapshot/manifest.json
          printf 'raise SystemExit("a decoy that must not reach the image")\n' \
            > backend/scripts/e2e_decoy.py

      - uses: docker/setup-buildx-action@v4
      - name: Build the image
        uses: docker/build-push-action@v7
        with:
          context: backend
          load: true
          push: false
          tags: ${{ env.IMAGE }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: It runs as a non-root user, and ships no .env, tests, snapshot or e2e scripts
        run: |
          fail() { echo "::error::$*"; exit 1; }
          uid="$(docker run --rm "$IMAGE" id -u)"
          echo "the image runs as uid $uid"
          [ "$uid" != 0 ] || fail "the image runs as root"
          # The container's shell expands the glob, and ls prints only the paths that
          # exist. The glob covers e2e_session.py, which signs a real session for any
          # user it is pointed at, e2e_seed.py and the decoy. `; true` because ls
          # exits 2 for a missing path, and in a good image every path is missing.
          shipped="$(docker run --rm "$IMAGE" sh -c \
            'ls -d /app/.env /app/tests /app/seed-snapshot /app/scripts/e2e_*.py 2>/dev/null; true')"
          if [ -n "$shipped" ]; then
            echo "$shipped"
            fail "the image ships the files above"
          fi

      # Fly's release_command, `alembic upgrade head`, from the image against an empty
      # database. Then `alembic check`: the image's models match its migrations.
      - name: The release step migrates a fresh database
        run: |
          docker run --rm --network host -e DATABASE_URL="$DATABASE_URL" "$IMAGE" \
            alembic upgrade head
          docker run --rm --network host -e DATABASE_URL="$DATABASE_URL" "$IMAGE" \
            alembic check

      - name: Boot the API from the image
        run: docker run -d --name api --network host -e DATABASE_URL="$DATABASE_URL" "$IMAGE"
      - name: Wait for /health
        run: |
          for _ in $(seq 1 30); do
            curl -sf http://localhost:8000/health && exit 0
            sleep 1
          done
          echo "the image did not come up. Its log:" >&2
          docker logs api >&2
          exit 1

      # APP_ENV=production and nothing else: the development session secret, no
      # Google client id, insecure cookies, an http origin and a localhost database.
      # Settings must name all five and stop the import, so uvicorn exits before it
      # serves anything. `timeout` stops the step if the image ever serves instead.
      - name: It refuses to start in production with development settings
        run: |
          fail() { echo "::error::$*"; exit 1; }
          log="$RUNNER_TEMP/refusal.log"
          exit_code=0
          timeout 60 docker run --rm -e APP_ENV=production "$IMAGE" > "$log" 2>&1 || exit_code=$?
          cat "$log"
          [ "$exit_code" != 0 ] || fail "the image started in production with development settings"
          [ "$exit_code" != 124 ] || fail "the image was still running after 60 seconds"
          for problem in \
            'Refusing to start in production' \
            'SESSION_SECRET is the development default or shorter than 32 characters' \
            'GOOGLE_CLIENT_ID is empty' \
            'COOKIE_SECURE must be true' \
            'FRONTEND_ORIGIN must be an https:// origin with no trailing slash' \
            'DATABASE_URL points at localhost'; do
            grep -qF "$problem" "$log" || fail "the refusal does not say: $problem"
          done
          # Pydantic ends a validation message with the settings' input unless told
          # not to (hide_input_in_errors in app/config.py), and in production that
          # input holds the database password, the session secret and the LLM keyring.
          if grep -F 'input_value' "$log"; then
            fail "the refusal prints the settings' input"
          fi

  e2e:
    # The end-to-end walk goes through the real backend and a real Postgres, so
    # it needs both. Against mocks it would only assert that the mocks return
    # what they were told, which is why it is not folded into the frontend job.
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: healthmonitor
          POSTGRES_PASSWORD: healthmonitor
          POSTGRES_DB: healthmonitor
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -U healthmonitor"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - run: uv sync --locked
        working-directory: backend
      - run: uv run alembic upgrade head
        working-directory: backend

      # Only the loaders that need no downloads. The full ETL pulls IFCT, INDB
      # and USDA, which is far too slow and too network-dependent for CI; these
      # three are enough for targets to compute and for food search to return
      # something real to log.
      - run: uv run python -m scripts.e2e_seed
        working-directory: backend

      # nohup and a redirect, not a bare `&`: the step's shell exits as soon as
      # the command returns, and the log has to outlive it to be readable when
      # the API fails to start.
      - name: Start the API
        run: nohup uv run uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &
        working-directory: backend
      - name: Wait for the API
        run: |
          for _ in $(seq 1 30); do
            curl -sf http://localhost:8000/health && exit 0
            sleep 1
          done
          echo "the API did not come up. Its log:" >&2
          cat /tmp/api.log >&2
          exit 1

      # Playwright serves the SPA with `npm run dev`, so this job never makes a
      # production build and needs no VITE_API_BASE.
      - run: npm ci
        working-directory: frontend
      - run: npx playwright install --with-deps chromium
        working-directory: frontend
      - run: npm run test:e2e
        working-directory: frontend

      - name: The API log, if anything failed
        if: failure()
        run: cat /tmp/api.log

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: |
            frontend/playwright-report/
            frontend/test-results/
          retention-days: 7
```

Notes on the file:
- `DATABASE_URL` is set once, on the `image` job. Each `docker run` passes it on explicitly, with `-e DATABASE_URL="$DATABASE_URL"`. The refusal step deliberately does not pass it, so the image's own localhost default is one of the five problems.
- `set -o noclobber` in the decoy step makes it fail rather than overwrite a `backend/.env` or a `backend/scripts/e2e_decoy.py` that exists. A fresh checkout has neither. Never run that step on your own machine: your `backend/.env` holds real secrets.
- The exclusion check runs `ls` inside the container, through `sh -c` in single quotes, so the glob `/app/scripts/e2e_*.py` is expanded against the image, not against the runner's checkout. A shipped path is printed before the step fails, so the log names it.
- The refusal step keeps its exit status in `exit_code`, not `status`, which is read-only in zsh. It stays pasteable into a local shell.
- The two `DATABASE_URL` lines in `backend` are 106 columns, as they were before. YAML has no line limit.

- [ ] **Step 3: Parse and lint it**

Run:

```bash
uv run --no-project --quiet --with pyyaml python -c "
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml'))
print(sorted(d['jobs']), d[True], d['permissions'])
"
```

Expected:

```
['backend', 'e2e', 'frontend', 'image'] {'push': {'branches': ['main']}, 'pull_request': None} {'contents': 'read'}
```

PyYAML reads the key `on` as the boolean `True` (YAML 1.1), hence `d[True]`. GitHub reads it as `on`.

Then lint it with actionlint 1.7.12 in Docker. It checks the workflow's syntax and each action's inputs, and runs shellcheck over every `run:` script. `-` reads the workflow from stdin, so no volume mount is needed. It needs colima (or another Docker) running.

Run: `docker run --rm -i rhysd/actionlint:1.7.12 -color - < .github/workflows/ci.yml; echo "actionlint: exit $?"`

Expected: `actionlint: exit 0`, with nothing else printed. The first run also prints Docker's pull progress. An input actionlint does not know is reported like this, which is what to look for if it fails:

```
<stdin>:160:11: input "lod" is not defined in action "docker/build-push-action@v7". available inputs are ...
```

- [ ] **Step 4: Run the frontend job's checks on a real build, and on broken ones**

The script comes straight out of the YAML, so what runs here is exactly what CI runs.

From `frontend/`, run:

```bash
SCRIPT="$(mktemp)"
uv run --no-project --quiet --with pyyaml python -c '
import sys, yaml
jobs = yaml.safe_load(open(sys.argv[1]))["jobs"]
print(next(s["run"] for s in jobs[sys.argv[2]]["steps"] if s.get("name") == sys.argv[3]))
' ../.github/workflows/ci.yml frontend 'Check the build output' > "$SCRIPT"
rm -rf dist
VITE_API_BASE=https://api.example.invalid VITE_GOOGLE_CLIENT_ID=ci-placeholder npm run build > /dev/null
bash -e "$SCRIPT"; echo "good build: exit $?"
for broken in localhost rule 404 denylist; do
  T="$(mktemp -d)"; cp -R dist "$T/dist"
  case "$broken" in
    localhost) echo 'fetch("http://localhost:8000/auth/me")' > "$T/dist/assets/stray.js" ;;
    rule) printf '/*  /  200\n' >> "$T/dist/_redirects" ;;
    404) echo 'Not found' > "$T/dist/404.html" ;;
    denylist) sed -i.bak 's#createHandlerBoundToURL("index.html"))#createHandlerBoundToURL("index.html"),{denylist:[/^\\/foods/]})#' "$T/dist/sw.js" ;;
  esac
  (cd "$T" && bash -e "$SCRIPT"); echo "$broken: exit $?"
  rm -rf "$T"
done
rm -f "$SCRIPT"
```

Expected:

```
good build: exit 0
dist/assets/stray.js
::error::the files above call http://localhost:8000
localhost: exit 1
/*  /  200
::error::dist/_redirects has the rule above
rule: exit 1
::error::dist/404.html turns off the Pages SPA fallback
404: exit 1
denylist:[/^\/foods/]
::error::dist/sw.js still has the navigation denylist above
denylist: exit 1
```

Each broken copy is one of the regressions the step exists for:
- a bundle that calls localhost;
- a catch-all redirect that would serve `index.html` for `/sw.js`;
- a `404.html` that switches off the SPA fallback;
- the old denylist.

The build here takes its values from the shell, which wins over `.env.local`. Rebuild with a plain `npm run build` afterwards if you want a local `dist/` again.

- [ ] **Step 5: Run the image job's database-free checks on a local image**

This needs colima running (`colima status`). Check `df -h ~` first: colima's VM has stopped under low disk on this machine before, and the image and its build cache take about 1 GB.

It runs as three commands: the build, the checks and the cleanup. The checks and the cleanup share a fixed scratch directory, not a shell variable, because each command may run in a fresh shell.

**The build.** The colima VM here is x86_64 under emulation, so the build is slow. Task 9 measured 19 minutes for a cold build and about 3 minutes for a rebuild after a code-only change. Expect 5 to 20 minutes here: the base images are already there, but Task 9's cleanup pruned the builder stage, so `uv sync` runs again.

Run it as a command of its own:
- in the background (the Bash tool's `run_in_background: true`), and wait for it to exit before going on;
- or with a command timeout of at least 25 minutes.

The Bash tool's foreground limit is 10 minutes, which a cold build outlasts. There is no `-q`, so the output shows which step the build has reached.

Run:

```bash
docker build -t healthmonitor-api:ci backend; echo "build: exit $?"
```

Expected, on the classic builder (colima without buildx):

```
DEPRECATED: The legacy builder is deprecated and will be removed in a future release.
            Install the buildx component to build images with BuildKit:
            https://docs.docker.com/go/buildx/

Sending build context to Docker daemon  <size>kB
Step 1/<N> : ARG PYTHON_VERSION=3.13
Step 2/<N> : FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
 ---> <base image id>
Step 3/<N> : <the next instruction>
 ---> Running in <container id>
 ---> Removed intermediate container <container id>
 ---> <layer id>
…
Step <n>/<N> : RUN uv sync --locked --no-dev --no-install-project
 ---> Running in <container id>
<uv's log, with "Installed <count> packages in …" and one " + <package>==<version>" line per package>
 ---> Removed intermediate container <container id>
 ---> <layer id>
Step <n>/<N> : FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
 ---> <base image id>
…
Step <N>/<N> : CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --no-server-header"]
 ---> Running in <container id>
 ---> Removed intermediate container <container id>
 ---> <image id>
Successfully built <image id>
Successfully tagged healthmonitor-api:ci
build: exit 0
```

- The four `DEPRECATED` lines, the last one blank, go to stderr. The rest goes to stdout.
- `<N>` is the number of instructions in Task 9's Dockerfile, counting the `ARG` before the first `FROM`. Each one prints `Step <n>/<N> :` and its own text. A `COPY` then prints only ` ---> <layer id>`. A step whose layer is reused prints ` ---> Using cache` before its id.
- The context size is under a few MB. Hundreds of MB means `.dockerignore` is not being read (Task 9, Step 4).
- With BuildKit (buildx installed) there is no `DEPRECATED` notice, the progress looks different, and it ends with `naming to docker.io/library/healthmonitor-api:ci done`.
- A failure at `uv sync --locked` means `uv.lock` is out of step with `pyproject.toml`. Fix it as Task 9, Step 4 says.

**The checks.** They start seven short containers and build one small copy of the image, which takes a few minutes under emulation. Give the command a 10-minute timeout.

Run:

```bash
S="${TMPDIR:-/tmp}/hm-ci-image-check"
rm -rf "$S" && mkdir -p "$S"
extract() {
  uv run --no-project --quiet --with pyyaml python -c '
import sys, yaml
jobs = yaml.safe_load(open(".github/workflows/ci.yml"))["jobs"]
print(next(s["run"] for s in jobs["image"]["steps"] if s.get("name") == sys.argv[1]))
' "$1"
}
extract 'It runs as a non-root user, and ships no .env, tests, snapshot or e2e scripts' > "$S/nonroot.sh"
extract 'It refuses to start in production with development settings' > "$S/refusal.sh"
IMAGE=healthmonitor-api:ci bash -e "$S/nonroot.sh"; echo "non-root: exit $?"
IMAGE=healthmonitor-api:ci RUNNER_TEMP="$S" bash -e "$S/refusal.sh" > "$S/out.txt"
echo "refusal: exit $?"; tail -3 "$S/out.txt"
docker build -q -t healthmonitor-api:ci-leaky - <<'EOF'
FROM healthmonitor-api:ci
USER 0
RUN touch /app/scripts/e2e_session.py
USER 10001:10001
EOF
IMAGE=healthmonitor-api:ci-leaky bash -e "$S/nonroot.sh"; echo "leaky non-root: exit $?"
IMAGE=python:3.13-slim-bookworm bash -e "$S/nonroot.sh"; echo "stock non-root: exit $?"
IMAGE=python:3.13-slim-bookworm RUNNER_TEMP="$S" bash -e "$S/refusal.sh" > "$S/out.txt"
echo "stock refusal: exit $?"; tail -1 "$S/out.txt"
```

`healthmonitor-api:ci-leaky` is the local image plus an empty `/app/scripts/e2e_session.py`, which is what a `.dockerignore` without `scripts/e2e_*.py` would ship. The build reads its Dockerfile from stdin, so it has no context, and it takes about 30 seconds here.

Expected:

```
the image runs as uid 10001
non-root: exit 0
refusal: exit 0
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, Refusing to start in production: SESSION_SECRET is the development default or shorter than 32 characters; GOOGLE_CLIENT_ID is empty; COOKIE_SECURE must be true; FRONTEND_ORIGIN must be an https:// origin with no trailing slash; DATABASE_URL points at localhost [type=value_error]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
DEPRECATED: The legacy builder is deprecated and will be removed in a future release.
            Install the buildx component to build images with BuildKit:
            https://docs.docker.com/go/buildx/

sha256:<leaky image id>
the image runs as uid 10001
/app/scripts/e2e_session.py
::error::the image ships the files above
leaky non-root: exit 1
the image runs as uid 0
::error::the image runs as root
stock non-root: exit 1
stock refusal: exit 1
::error::the image started in production with development settings
```

With BuildKit, the leaky build prints only its `sha256:` line.

What this shows:
- The build context here is your own `backend/`, so the exclusion check is a real test of `.dockerignore`. `tests/`, `scripts/e2e_seed.py` and `scripts/e2e_session.py` are in every checkout, and `.env` is in yours if you have one.
- The refusal is Task 8's validator, reached through the image's own `CMD`.
- The leaky copy runs as uid 10001, like the real image, and differs only by the session minter. So the exclusion check alone fails it, and names the file it found.
- The stock `python:3.13-slim-bookworm` image, Task 9's base, is already on the machine. It runs as root, and its default command exits 0 at once. So it fails both checks, which proves they can fail.

If the refusal's last line ends `input_value={…}, input_type=dict]` instead of `[type=value_error]`, the step prints `::error::the refusal prints the settings' input`. That means Task 8's `hide_input_in_errors=True` is missing, which is a bug to fix there, not here.

**The cleanup.** Run it even if a check failed.

```bash
docker image rm -f healthmonitor-api:ci-leaky healthmonitor-api:ci > /dev/null
docker image prune -f --filter label=healthmonitor.stage=builder
echo "builder images left: $(docker image ls -aq --filter label=healthmonitor.stage=builder | wc -l | tr -d ' ')"
rm -rf "${TMPDIR:-/tmp}/hm-ci-image-check"
```

Expected:

```
Deleted Images:
untagged: sha256:<id>
deleted: sha256:<id>
…

Total reclaimed space: <size>
builder images left: 0
```

- `docker image rm` removes both tags, and with them the leaky layer and the runtime stage's layers.
- The classic builder also keeps the `builder` stage, which holds the whole virtualenv and uv, as untagged images that no tag leads to. Task 9's Dockerfile labels that stage `healthmonitor.stage=builder`, so the prune removes them and nothing else. There is one `untagged:` and one `deleted:` line per image.
- With BuildKit no builder image is kept, and the prune prints only `Total reclaimed space: 0B`.
- On the classic builder, `0B` means the stage is not labelled. Check that Task 9's `builder` stage has `LABEL healthmonitor.stage=builder`, and remove the untagged image this build left with `docker image rm <id>`. `docker image ls --filter dangling=true --format '{{.ID}} {{.CreatedSince}}'` lists it with its age.
- Keep the two base images, as Task 9 does. They make the next build faster.

- [ ] **Step 6: Commit**

Run: `git status --short`

Expected: only ` M .github/workflows/ci.yml` (besides anything plan 8 left uncommitted). No `backend/.env` or `backend/scripts/e2e_decoy.py` decoy was written and no `seed-snapshot/` was created, because the decoy step never runs locally.

```bash
git add .github/workflows/ci.yml
git commit -m "ci: build and boot the API image, check the SPA build, run each change once

Every job ran twice for a pull request, once for the push and once for
the pull request. A push now runs only on main, and every job only reads
the repository. Nothing deploys: there is no registry push, no flyctl or
wrangler, and no secret.

uv sync --locked fails when uv.lock no longer matches pyproject.toml, as
the image build does, instead of quietly re-resolving. uv takes Python
3.13 from backend/.python-version, so the tests run on the image's Python
rather than the runner's 3.12.

The frontend job now lints too, and builds as a deploy does, with
placeholders, since the build refuses to run without VITE_API_BASE. It
then checks the output: no http://localhost:8000 in the bundle, both
Cloudflare Pages files present, no 404.html to switch off the SPA
fallback, no rule in _redirects, the push handlers imported by the
worker, and no navigation denylist. Each check fails through a function
rather than a negated grep, which bash -e ignores.

The new image job builds backend/Dockerfile into the runner's Docker and
runs it the way Fly does. The image must run as a non-root user and ship
no .env, tests, seed snapshot or e2e scripts, one of which signs a real
session for any user. Decoys in the build context mean only .dockerignore
can keep them out. It runs the release step, alembic
upgrade head, and alembic check against an empty Postgres, boots the
server and waits for /health. APP_ENV=production with development
settings must stop the import, name all five problems, and print none of
the settings' values.

The e2e job keeps running uvicorn from source. Playwright serves the SPA
with npm run dev, so it never makes a production build.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: The runbook, the READMEs, the end-to-end walk and the plan record

This task writes down what plan 9 leaves for the owner, and closes the plan.
- **`DEPLOY.md`**, at the repository root, is the first-deploy runbook.
  - It opens by saying plainly that nothing has been deployed.
  - It lists, in order, what the owner does by hand: accounts, the domain and DNS, the database, the OAuth origin, the secrets, the placeholders, the deploy, the seed data, and the checks.
  - It says what each production setting refuses, that the server-side refusal fallback is on for Claude Opus 5, how to rotate the keyring, how to roll back, and what was and was not verified.
- **The end-to-end walk** gains one test: with no key saved, the AI descriptions screen shows what the server says, and the Plan screen offers no descriptions. It never enters a key, so the run cannot reach Anthropic.
- **The READMEs** gain AI descriptions, the build's `VITE_API_BASE` rule and a pointer to `DEPLOY.md`. The root `README.md` is two lines today, so it gains the quick start that `backend/` has no README of its own to hold.
- **The records.** The plans index gets row 9, the UI-foundation contract table gets the two new endpoints, and this plan gets its Status line.

The runbook describes files that Tasks 8 to 12 wrote. Step 5 checks each fact it relies on against those files. Where a file says something else, the file is right and the runbook changes.

All commands run from the repository root unless a step says otherwise.

**Files:**
- Create: `DEPLOY.md`
- Modify:
  - `frontend/e2e/smoke.spec.ts`: one walk appended, and one bullet in the header comment
  - `frontend/README.md`
  - `README.md` (repository root)
  - `docs/superpowers/plans/README.md`: row 9, and two paragraphs
  - `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`: the contract table
  - `docs/superpowers/plans/2026-09-24-ai-descriptions-and-deploy.md` (this plan): its Status line, and the Known gaps below if the final review changes them
- There is no `backend/README.md`, and this task does not create one. The root README carries the backend's quick start.

**Interfaces:**
- Consumes, as the tasks before this one built them:
  - **Task 6's AI descriptions screen** at `/ai-descriptions`:
    - the heading `AI descriptions`;
    - the note `AI descriptions are not set up on this server.`;
    - the field labelled `Anthropic API key`;
    - the button `Save key`.
  - **Task 7's Plan screen:** the `Add descriptions` button, rendered only when `GET /settings/llm` answers `available: true` and `status: 'ok'`, and the `Cooking tip` disclosure. After a polish whose `X-Dishes-Described` header is `0`, it also shows the status line `Claude added no new descriptions this time.` (`role="status"`). The walk never clicks the button, so it never sees that line; the frontend README and `DEPLOY.md` step 11 describe it.
  - **Task 4's `GET /settings/llm`:** `{available, provider, model, key_hint, status, models}`. For a user with no row, `status` is `'none'` and `key_hint` is `null`.
  - **Task 2's `scripts/e2e_session.py`,** whose `--reset` deletes the e2e user's `UserSettings` and `DishPolish` rows. So every run starts with no key.
  - **The deploy files:**
    - Task 8's refusal messages;
    - Task 9's `backend/Dockerfile`, with `PYTHONPATH=/app` and `LABEL healthmonitor.stage=builder` on its builder stage, and its `backend/.dockerignore` and `backend/fly.toml`;
    - Task 10's `frontend/public/_headers` (six `no-cache` rules and two `immutable` ones), `_redirects` and `.env.example`, and the build guard;
    - Task 11's `scripts/seed_snapshot.py` commands and output. Task 11 deletes `backend/seed-snapshot/` after its rehearsal;
    - Task 4's `scripts/rotate_llm_keys.py`, and its `rotated N, current N, unreadable N` output.
  - **Plan 8's final `frontend/README.md`, e2e walks and contract rows** (plan 8, Task 14), quoted below where this task edits next to them.
- Produces: documentation only. After this task, the e2e run is `10 passed`, or `9 passed, 1 skipped` against a database without the full ETL.

- [ ] **Step 1: Write the runbook**

Create `DEPLOY.md` at the repository root:

````markdown
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
- **Keys are write-only.** A saved key is encrypted with the keyring and bound to its user. The API never returns it, only its last four characters, and never logs it. A provider error is logged as its class name and status code only.
  - FastAPI's own 422 quotes the input that failed validation. On `/settings/llm` a validation handler answers a malformed body without quoting it, so even a misspelt or non-string `api_key` never comes back.
  - Every answer on `/settings/llm` except the 401 for a missing session, including the validation handler's 422, is sent `Cache-Control: no-store`.

**Rotating the keyring:**
1. Generate a new key and put it first: `LLM_KEY_ENCRYPTION_KEYS=<new>,<old>`. Store it with `fly secrets import`, as in step 7, which restarts the machine with the new value. New saves use the new key, and every stored key still opens with the old one.
2. Run `fly ssh console -C "python -m scripts.rotate_llm_keys"`. A session may start in `/` rather than the image's `/app`. The image sets `PYTHONPATH=/app` and puts its virtualenv first on `PATH`, so the command works from either. It re-encrypts every key still under an older key, in one transaction, and is safe to re-run. It prints `rotated N, current N, unreadable N`.
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
````

- [ ] **Step 2: Append the walk**

The walk goes at the end of `test.describe('the tracking loop', ...)` in `frontend/e2e/smoke.spec.ts`, after plan 8's last walk, `'a meal reminder can be switched off, and stays off'`. Every walk shares the one e2e user, whom `globalSetup` resets once per run: onboarding and the plan walk have run by the time this one does.

```ts
  test('AI descriptions stay off without a key, and the plan offers none', async ({ page }) => {
    // The server decides what the screen shows. CI starts the API with no
    // LLM_KEY_ENCRYPTION_KEYS, so the feature is off there; a developer's backend/.env
    // may set it. Either way globalSetup's reset left this user with no key, and this
    // walk never enters one, so nothing here can reach Anthropic.
    const api = 'http://localhost:8000'
    const llm = (await (await page.request.get(`${api}/settings/llm`)).json()) as {
      available: boolean
      status: string
      key_hint: string | null
    }
    expect(llm.status).toBe('none')
    expect(llm.key_hint).toBeNull()

    await page.goto('/ai-descriptions')
    await expect(page.getByRole('heading', { name: 'AI descriptions' })).toBeVisible()
    if (llm.available) {
      // A keyring but no key yet: the form, empty.
      await expect(page.getByLabel('Anthropic API key')).toHaveValue('')
      await expect(page.getByRole('button', { name: 'Save key' })).toBeVisible()
    } else {
      await expect(page.getByText('AI descriptions are not set up on this server')).toBeVisible()
      await expect(page.getByLabel('Anthropic API key')).toHaveCount(0)
    }
    await expect(page.getByRole('alert')).toHaveCount(0)

    // No saved key, so the Plan screen offers no descriptions and shows none. Wait for
    // the screen's own read of the settings: before it lands, a missing button proves
    // nothing.
    const settingsRead = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' && response.url().includes('/settings/llm'),
    )
    await page.goto('/plan')
    await settingsRead
    await expect(page.getByRole('region', { name: 'Saturday' })).toBeVisible()
    await expect(page.getByRole('button', { name: /regenerate week/i })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add descriptions' })).toHaveCount(0)
    await expect(page.getByText('Cooking tip')).toHaveCount(0)
  })
```

- **Why the walk branches.** It reads the server's answer and then checks that the screen matches it. The one fixed expectation, that a user with no key is offered nothing on the Plan screen, holds on either kind of server.
- **Why it reads the settings with `page.request`,** as the cycle walk reads the profile: `page.request` carries the browser context's session cookie.
- **Why the note is matched without its full stop.** `getByText` with a string matches a substring, so the check does not depend on the punctuation.
- **Check the labels against Task 6's `AiDescriptionsScreen.tsx`.** If the screen renders the heading, the note, the field or the button differently, change the walk to what the screen renders, not the screen to the walk.

In the header comment at the top of the file, add this bullet after plan 8's last one ("Meal reminders on the real settings endpoint: …"):

```ts
 *  - AI descriptions without a key: the screen shows what the real settings
 *    endpoint says (not set up on this server, or no key saved yet), and the Plan
 *    screen offers no descriptions. No walk enters a key, so no run reaches Anthropic.
```

- [ ] **Step 3: Run the walks against the real stack**

With Postgres up (`docker compose up -d db`) and the development database at the migration head (`cd backend && uv run alembic upgrade head`):

```bash
cd backend && uv run python -m scripts.e2e_seed
cd backend && (uv run uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &) && sleep 3 && curl -sf http://localhost:8000/health
cd frontend && npm run test:e2e
```

Expected: `10 passed`. Against a database without the full ETL, the swap-and-lock walk skips itself: `9 passed, 1 skipped`.

Stop the API afterwards: `pkill -f "uvicorn app.main:app --port 8000"`. The scheduler stays off, because `SCHEDULER_ENABLED` is unset.

- **If the new walk fails on the Plan screen's `waitForResponse`,** Task 7's Plan screen is not reading `/settings/llm`. Fix that screen: the button must follow the server's answer.
- **If it fails on `expect(llm.status).toBe('none')`,** the e2e user kept a key from an earlier run. `scripts/e2e_session.py`'s `OWNED_MODELS` must list `UserSettings` (Task 2).

- [ ] **Step 4: Update the READMEs, the plans index and the contract table**

**`frontend/README.md`.** The anchors quoted here are plan 8's final text (plan 8, Task 14).

1. In "## Running it", directly after the code block that ends with `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`, add:

   ```markdown
   The frontend's settings are build-time `VITE_*` variables, all listed in `.env.example`.
   Copy it to `.env.local`, which is git-ignored, and fill in `VITE_GOOGLE_CLIENT_ID` and
   `VITE_API_BASE`. Every `VITE_*` value is baked into the bundle, so none of them is a secret.
   ```

2. In "## Which screens are real", in the paragraph that begins `**Live against the real backend:** every screen.`, replace `the weekly report and reminders.` with `the weekly report, reminders and AI descriptions.`

3. Directly after the paragraph that begins `**Push reminders need a production build.**` and ends `See `backend/.env.example`.`, add:

   ```markdown
   **AI descriptions need a server keyring and the user's own key.** With
   `LLM_KEY_ENCRYPTION_KEYS` unset, which is the default, the AI descriptions screen says the
   feature is not set up on this server and the Plan screen offers nothing. With it set (see
   `backend/.env.example`), a user saves their own Anthropic API key, and "Add descriptions" on
   the Plan screen asks Claude for a one-line description and a cooking tip for each dish.
   Only dish and ingredient names are sent, and no dish, portion or number changes. When a
   polish stores no new text (every dish already had some, Claude declined, or it wrote
   nothing the server's check kept), the Plan screen says "Claude added no new descriptions
   this time." No test and no end-to-end walk ever reaches Anthropic.
   ```

4. In "## Checks", directly after the paragraph that begins `` `npm run build` is the authoritative typecheck``, add:

   ```markdown
   A production build refuses to run without `VITE_API_BASE`, because the bundle would
   otherwise call `http://localhost:8000`. Set it in `.env.local`. `VITE_USE_MOCKS=true` also
   lets the build through, for a local build that is never deployed.
   ```

5. Under "### End to end", replace the comment `# Playwright: onboarding -> log -> dashboard, then the plan, weight, cycle, report and reminders` with `# Playwright: onboarding -> log -> dashboard, then the plan, weight, cycle, report, reminders and AI descriptions`.

6. At the end of the file, add:

   ```markdown
   ## Deploying

   The web app is built for Cloudflare Pages: `npm run build` with `VITE_API_BASE` and
   `VITE_GOOGLE_CLIENT_ID` set, publishing `dist/`. `public/_headers` serves the service
   worker's files, the manifest and the app shell (`/` and `/index.html`) `no-cache`, and the
   content-hashed files (`/assets/*` and `/workbox-*.js`) as immutable. `public/_redirects`
   deliberately holds no rule. Pages itself answers every path that is not a file with
   `index.html`, as long as the build has no top-level `404.html`. Never add a `/*` rule there:
   Pages applies `_redirects` before it looks for a file, so a catch-all would answer `/sw.js`
   and every script under `/assets/` with HTML. Never add a `404.html` to `public/` either.

   The app must be served at the root of its own host, under the same registrable domain as the
   API, or the session cookie is never sent.

   `DEPLOY.md` at the repository root is the runbook. Nothing has been deployed.
   ```

**`README.md`** (repository root). Replace the whole file with:

````markdown
# Nutrition-and-Health-Tracking-

A nutrient-tracking app for Indian diets — Google sign-in, household sharing, and a South Indian food database (IFCT/USDA/INDB) scored against ICMR-NIN RDA targets

What it does:
- **Targets.** It computes each person's daily targets from ICMR-NIN 2020, adjusted for their health conditions and medications.
- **The ledger.** It carries a short day's shortfall forward where the body can make it up.
- **Planning and reports.** It plans a week of South Indian meals around the targets, and reports on how the week went.
- **Reminders** arrive at meal times by web push.
- **AI descriptions.** A user who brings their own Anthropic API key can add a one-line description and a cooking tip to each planned dish. The model never sees health details, and never changes a dish, a portion or a number.

**Nothing is deployed.** Everything here runs locally. [`DEPLOY.md`](DEPLOY.md) is the runbook for a first deploy, and lists what has to be done by hand.

## Layout

| Path | What is there |
|---|---|
| `backend/` | FastAPI, SQLAlchemy 2, Alembic and pytest. The food-data ETL is in `backend/etl/`, and the operational scripts are in `backend/scripts/`. |
| `frontend/` | React 19, TanStack Query and Vite, installable as a PWA. See [`frontend/README.md`](frontend/README.md). |
| `docs/superpowers/specs/` | The design spec and the UI foundation design |
| `docs/superpowers/plans/` | The implementation plans, one per subsystem, each with its decisions and known gaps |

## Running it locally

You need Docker (for Postgres), [`uv`](https://docs.astral.sh/uv/) and Node 22.

```bash
docker compose up -d db                  # Postgres 16 on localhost:5433
cd backend
uv sync
uv run alembic upgrade head
uv run python -m etl.run_all             # the food and reference data; downloads about 5.6 MB once
uv run uvicorn app.main:app --reload     # http://localhost:8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

- **Settings.** `backend/.env.example` and `frontend/.env.example` list every setting. Copy them to `backend/.env` and `frontend/.env.local`, which are both git-ignored.
- **Sign-in** needs a Google OAuth client. The spec's "Prerequisite: Google OAuth client" section says how to make one.
- **Reminders** also need VAPID keys, and **AI descriptions** an encryption keyring. Both are off until those are set, and `backend/.env.example` says how to generate them.

## Checks

The backend tests run against their own database, `healthmonitor_test`, at the migration head. Create it once, and migrate it whenever a migration is added:

```bash
docker compose exec -T db createdb -U healthmonitor healthmonitor_test
cd backend && DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head
```

Then:

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npx vitest run && npx tsc -b && npm run lint && npm run build
cd frontend && npm run test:e2e          # needs the API running: see frontend/README.md
```

No test that plan 9 added reaches the network: none calls Anthropic, Google or a push service. The ETL tests, which predate plan 9, still download their sources from GitHub, the INDB site and USDA whenever `backend/etl/.cache` is empty, as it is on a fresh checkout and on every CI run.

## Data sources and licences

- **IFCT 2017** (ICMR-NIN) has no formal open licence. It is fine for personal and family use; commercial distribution would need written permission from NIN. Anything derived from it stays out of git and out of any public release. That includes the seed snapshot that `backend/scripts/seed_snapshot.py` writes.
- **INDB** (Anuvaad Solutions) is open access.
- **USDA FoodData Central** is CC0.
````

**`docs/superpowers/plans/README.md`.**
- Replace row 9, `| 9 | LLM polish & deploy | BYO-key polish adapter, hosting, domain, seed migration | Not started |`, with:

  ```
  | 9 | LLM polish & deploy | BYO-key polish adapter, hosting, domain, seed migration | **Complete as configuration; nothing deployed** — `2026-09-24-ai-descriptions-and-deploy.md`. AI descriptions are asked for on demand with the user's own Anthropic key, cached per dish, and never change a dish or a number. The image, Fly and Cloudflare Pages config, production settings checks, the seed snapshot and CI's image checks are rehearsed locally, though CI has never run on GitHub; `DEPLOY.md` lists what the owner does by hand |
  ```

- Directly after the paragraph `Plan 8's decisions and the gaps it leaves are recorded at the top and bottom of `2026-09-24-report-and-reminders.md`.`, add:

  ```markdown
  Plan 9's decisions and the gaps it leaves are recorded at the top and bottom of
  `2026-09-24-ai-descriptions-and-deploy.md`. It stops short of going live: no account,
  domain, DNS record or pushed image exists. `DEPLOY.md` at the repository root is the runbook
  for that step, in the order the owner takes it.

  With plan 9, the spec's implementation sequence is built up to step 13, except the deploy
  itself. What remains is the owner's first deploy and phase 2: WhatsApp as a second reminder
  channel, and the prescription and meal-alteration work that plan 5's closeout moved there.
  ```

**`docs/superpowers/specs/2026-08-17-ui-foundation-design.md`.** In the contract table under "## Proposed endpoint contracts":
- Replace the row `` | `GET /plan/week?start=`, swap / lock / regenerate, `GET /plan/cooking` | `src/plan/types.ts` | Plan 6 | `` with:

  ```
  | `GET /plan/week?start=`, swap / lock / regenerate, `GET /plan/cooking` | `src/plan/types.ts` | Plan 6; plan 9 adds each item's `description` and `cooking_note` |
  ```

- Directly after plan 8's row `` | `GET/PATCH /settings/reminders`, `GET /push/public-key`, `POST/DELETE /push/subscriptions` | `src/settings/types.ts` | Plan 8 (built; contract amended) | ``, add:

  ```
  | `GET/PUT/DELETE /settings/llm` | `src/settings/types.ts` | Plan 9 (built; new) |
  | `POST /plan/week/polish`, answering the week and an `X-Dishes-Described` header | `src/plan/types.ts` | Plan 9 (built; new) |
  ```

- [ ] **Step 5: Check the runbook against the files it describes**

`DEPLOY.md` was written against the plan's skeleton, before Tasks 8 to 12 existed. Each command below must print at least one line. Where one prints nothing, read the file, correct `DEPLOY.md` to what the file says, and run the check again.

```bash
grep -n 'app = "healthmonitor-api"' backend/fly.toml
grep -n 'primary_region = "bom"' backend/fly.toml
grep -n 'release_command = "alembic upgrade head"' backend/fly.toml
grep -n 'APP_ENV = "production"' backend/fly.toml
grep -n 'COOKIE_SECURE = "true"' backend/fly.toml
grep -n 'SCHEDULER_ENABLED = "true"' backend/fly.toml
grep -n 'FRONTEND_ORIGIN = "https://app.example.com"' backend/fly.toml
grep -n 'VAPID_SUBJECT' backend/fly.toml
grep -n 'auto_stop_machines = "off"' backend/fly.toml
grep -n 'min_machines_running = 1' backend/fly.toml
grep -n 'shared-cpu-1x' backend/fly.toml
grep -n '512' backend/fly.toml
grep -n 'strategy = "rolling"' backend/fly.toml
grep -n 'FORWARDED_ALLOW_IPS' backend/Dockerfile
grep -n 'PYTHONPATH=/app' backend/Dockerfile
grep -n 'LABEL healthmonitor.stage=builder' backend/Dockerfile
grep -n -- '--workers 1' backend/Dockerfile
grep -n 'seed-snapshot' backend/.dockerignore
grep -n 'no-cache' frontend/public/_headers
grep -n 'immutable' frontend/public/_headers
grep -n 'no rules, on purpose' frontend/public/_redirects
test ! -e frontend/public/404.html && echo "no 404.html"
grep -n 'VITE_API_BASE is not set' frontend/vite.config.ts
grep -n 'Refusing to start in production' backend/app/config.py
grep -n 'rotated' backend/scripts/rotate_llm_keys.py
grep -n 'FALLBACK_BETA = "server-side-fallback-2026-07-01"' backend/app/llm/providers.py
```

Then check the runbook's facts in prose:
- **The rules in `_headers`** are the six `no-cache` and two `immutable` ones that step 10 of `DEPLOY.md` lists. Run:

  ```bash
  grep -B1 'Cache-Control: no-cache' frontend/public/_headers | grep '^/'
  grep -B1 'immutable$' frontend/public/_headers | grep '^/'
  ```

  The first must print exactly six paths, in this order: `/sw.js`, `/push-handlers.js`, `/registerSW.js`, `/manifest.webmanifest`, `/` and `/index.html`. The second must print exactly `/assets/*` and `/workbox-*.js`. The plain `grep -n 'immutable'` above also matches a comment line, so count from these two commands, not from that one.
- **`_redirects` holds no rule, only comments.** Run `grep -Ev '^[[:space:]]*(#|$)' frontend/public/_redirects; echo "redirect rules: $?"`. It must print exactly `redirect rules: 1`, meaning no line is a rule. If it prints a rule line, remove the rule (see Task 10); do not document it.
- **Neither document says `_redirects` sends paths to `index.html`.** Run `grep -n '_redirects' DEPLOY.md frontend/README.md`. Step 10 of `DEPLOY.md` and the frontend README's "## Deploying" must say the file holds no rule, and that Pages' own fallback serves `index.html` while the build has no `404.html`.
- **`backend/fly.toml`** must hold no secret: no `SESSION_SECRET`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `VAPID_PRIVATE_KEY` or `LLM_KEY_ENCRYPTION_KEYS`. Run `grep -nE 'SESSION_SECRET|DATABASE_URL|GOOGLE_CLIENT_ID|VAPID_PRIVATE_KEY|LLM_KEY_ENCRYPTION_KEYS' backend/fly.toml`. It should print nothing, unless those names appear only in a comment.
- **The refusal messages** in the "Production settings" table must be the five strings in `backend/app/config.py`, word for word.
- **The seed row counts** in step 8 must be Task 11's rehearsal output.

- [ ] **Step 6: Run everything**

The backend suite takes about fifteen minutes at this size, which is longer than a ten-minute command timeout, so run it in the background and wait for it. Never run it beside another pytest session on the same test database.

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npx vitest run && npx tsc -b && npm run lint && npm run build
```

Expected: every command clean.
- **The frontend build** reads `VITE_API_BASE` from `frontend/.env.local`. If yours does not set it, the build stops with Task 10's message; run it as `VITE_API_BASE=http://localhost:8000 npm run build`.
- **Record the counts:** pytest's `N passed` and Vitest's `Tests  N passed`.

The image, once more, since Task 11 changed backend files after Task 9 built it. This needs colima running. Colima has stopped on this machine when the disk was nearly full, so run `df -h /System/Volumes/Data` first and check that several GB are available. Task 9's and Task 12's cleanups both prune the labelled builder stage, which holds the cached dependency layer, so this build runs `uv sync` again: allow 5 to 20 minutes under colima's emulation, rather than the 3 of a code-only rebuild. The prune at the end removes this build's builder stage, and any that an earlier build left behind.

Task 11 deleted `backend/seed-snapshot/` after its rehearsal, so the build context has no snapshot, and a check that the image carries none could not fail. The first command writes a decoy there, so that only `backend/.dockerignore` can keep it out. It writes nothing if `backend/seed-snapshot/` already exists. The third removes the decoy and nothing else, right after the build.

```bash
test ! -e backend/seed-snapshot && mkdir backend/seed-snapshot && echo decoy > backend/seed-snapshot/decoy.csv && echo "decoy written"
docker build -t healthmonitor-api:final backend
rm backend/seed-snapshot/decoy.csv && rmdir backend/seed-snapshot && echo "decoy removed"
docker run --rm healthmonitor-api:final id -u
docker run --rm healthmonitor-api:final sh -c 'test ! -e /app/.env && test ! -d /app/tests && test ! -e /app/seed-snapshot && echo clean'
docker run --rm -w / healthmonitor-api:final python -c 'import scripts.rotate_llm_keys' && echo "imports from / ok"
docker run --rm -e APP_ENV=production healthmonitor-api:final; echo "exit $?"
docker image rm healthmonitor-api:final
docker image prune -f --filter label=healthmonitor.stage=builder
test -z "$(docker images -aq --filter label=healthmonitor.stage=builder)" && echo "no builder image left"
```

Expected:
- `decoy written`. If the first command prints nothing, a real snapshot is in `backend/seed-snapshot/`. Stop, move it out of the repository (it carries IFCT data), and start again. Never run the build with a real snapshot in its context.
- The build succeeds. On the classic builder it ends `Successfully tagged healthmonitor-api:final`, and with BuildKit it ends `naming to docker.io/library/healthmonitor-api:final done`. If it fails, still run the third command, then the last two.
- `decoy removed`.
- `10001`.
- `clean`. The decoy was in the build context, so `.dockerignore`'s `seed-snapshot` rule is what kept it out.
- `imports from / ok`. That is the `PYTHONPATH=/app` that the runbook's rotation command relies on.
- The refusal, from the image's own start command, as Fly would run it. A traceback whose last lines are:

  ```
  pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
    Value error, Refusing to start in production: SESSION_SECRET is the development default or shorter than 32 characters; GOOGLE_CLIENT_ID is empty; COOKIE_SECURE must be true; FRONTEND_ORIGIN must be an https:// origin with no trailing slash; DATABASE_URL points at localhost [type=value_error]
      For further information visit https://errors.pydantic.dev/2.13/v/value_error
  exit 1
  ```

  If it prints `Application startup complete.` instead, the image started in production with development settings. Stop it with Ctrl-C: that is a failure to fix in Task 8's validator, and the Status line in Step 7 cannot be written.
- The prune ends `Total reclaimed space: …` (`0B` with BuildKit), then `no builder image left`.

- [ ] **Step 7: Write this plan's Status line**

In this plan's file, `docs/superpowers/plans/2026-09-24-ai-descriptions-and-deploy.md`, add a paragraph directly after the Spec paragraph's last bullet (`- Implementation Sequence steps 12 and 13.`) and before `## Global Constraints`. Write it in the form plan 7 uses, with the counts from Steps 3 and 6 in place of `<backend>`, `<frontend>` and `<e2e>`:

```markdown
**Status:** Complete as configuration: nothing is deployed, and `DEPLOY.md` lists what the
owner does by hand. <backend> backend tests and <frontend> frontend tests passing, plus <e2e>
Playwright end-to-end tests; `ruff`, `alembic check`, `tsc -b`, `oxlint` and `vite build`
clean; the image builds, runs as a non-root user and refuses a production start with
development settings.
```

If Step 3 skipped the swap-and-lock walk, write `<e2e>` as, for example, `9 (one skipped without the full ETL)`.

Then read the "Known gaps to record in the closeout" section at the end of this plan against what was built:
- **Delete a gap that a task closed.** For example, the security-headers gap goes if `frontend/public/_headers` sets a `Content-Security-Policy`.
- **Add any gap the final review finds.**
- **Make "Carried from plan 8" match plan 8's own final Known gaps section** in `docs/superpowers/plans/2026-09-24-report-and-reminders.md`, if its closeout changed it.

- [ ] **Step 8: Commit**

```bash
git add DEPLOY.md README.md frontend/README.md frontend/e2e/smoke.spec.ts \
  docs/superpowers/plans/README.md docs/superpowers/plans/2026-09-24-ai-descriptions-and-deploy.md \
  docs/superpowers/specs/2026-08-17-ui-foundation-design.md
git commit -m "docs: write the deploy runbook, record plan 9, and walk AI descriptions end to end

DEPLOY.md is the first-deploy runbook for Fly, Neon and Cloudflare Pages.
It says plainly that nothing is deployed, and lists what the owner does
by hand, in order: accounts, domain and DNS, the direct database URL,
the OAuth origin, the secrets, the placeholders, the deploy with its
release-step migration, the seed snapshot import, the checks. It also
covers what each production refusal means, the refusal fallback that
Claude Opus 5 requests carry, keyring rotation, rollback, and what was
never verified: flyctl and every fly command, CI on GitHub, the regions,
Safari's 7-day cookie cap, and a real Anthropic request.

The end-to-end walk checks that without a key the AI descriptions screen
follows the server and the Plan screen offers nothing, and it never
enters a key. The READMEs gain AI descriptions, the build's VITE_API_BASE
rule and the deploy pointer; the root README gains the quick start.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Known gaps to record in the closeout

**AI descriptions**
- **The guard catches amounts and a fixed list of nutrient words, not every nutrition or health claim.**
  - It refuses digits, `%`, number words, multipliers ("double", "halve"), units, household measures ("katori", "ladle") and the nutrient words it lists.
  - A nutrition or health claim made in other words passes: "Rich in iron", "good for the bones", "wholesome", "helps digestion" and "light on the stomach" all pass `polish.BANNED_WORDS`.
  - "Iron" is left out on purpose, so that "a cast-iron pan" survives.
  - The system prompt forbids health advice, but nothing checks a claim made in other words.
- **The guard's word list has known holes beyond "rich in iron", and one deliberate over-reach.**
  - "Plate" and "helping" (not measures the planner uses), "thrice", "pinch", "handful", "spoonful", and non-ASCII look-alike letters all pass.
  - "Bowl", "glass" and "piece" (and their plurals) were added during execution, because the planner's own portions use them. So a description such as "a comforting bowl of rasam" is refused, and that dish goes undescribed.
- **A polish that yields nothing is still billed.**
  - A refusal, an answer cut off at its length limit, or text the guard refuses entirely stores nothing, and the dishes stay undescribed. Anthropic still bills the user's account for the request.
  - Nothing is cached for a dish that got no text, so another click sends the same dishes again, and bills them again.
  - The Plan screen now says so: `X-Dishes-Described: 0` shows "Claude added no new descriptions this time.", so the click no longer looks as if it did nothing. Nothing stops a repeat click.
- **Nothing checks that a description is right about its dish.** Text that passes the guard is shown as the model wrote it, and a regional dish can be described wrongly.
- **Polish holds a database connection through the model call.**
  - The request's session stays open for every batch: up to 120 s a call, with no retry.
  - The pool has 5 connections and 10 overflow per process, so a burst of concurrent polishes can starve other requests.
- **A long polish can outlast the hosting proxy.** The request is synchronous: one call per 15 dishes, one after another, each allowed 120 s. Fly's proxy is reported to cut an idle request at about 60 s, which is unverified. If it does, the user sees a generic failure while the request may still finish and be billed.
- **Polish can send a household member's dish name to this user's Anthropic account.** Polish sends every dish name in the plan, including a household member's user-created dish, which could reach this user's Anthropic account. Latent: no code creates user dishes yet. When dish creation lands, send only seed dishes and the user's own.
- **Polish feedback is lost after leaving the Plan screen mid-polish.**
  - If the user navigates away while "Add descriptions" runs and comes back, the buttons stay locked until it ends, and the new descriptions appear.
  - But the completion line ("Claude added no new descriptions this time.") and any failure alert do not show: they read the screen's own mutation observer, which starts idle after a remount.
  - A fix would read `useMutationState` over the `['plan', 'polish']` mutation key.
- **`rotate_all` counts already-unreadable rows again on every run.** A row no key opens stays in place, marked `unreadable`, so the `unreadable` count falls only as those users enter their keys again.
- **Changing the model means entering the key again**, because the key is checked against the model it will be used with.
- **The refusal fallback is on for `claude-opus-5` only.**
  - Whether Claude Sonnet 5 and Claude Haiku 4.5 accept `fallbacks="default"` is not verified, and a 400 there would break polish.
  - So on those two models a refusal leaves the batch's dishes undescribed.
- **The key check cannot see an account with no credit.** The zero-token model lookup succeeds, and the first polish answers 409 "Your Anthropic account has no credit left."
- **The key check accepts any 200.** `check_key` does not read the models lookup's answer, because a lookup by alias can answer with the model's canonical id. So a 200 with an unexpected body, an intercepting proxy's page say, saves the key as checked. Polish does read its answer, and turns a 200 that is not a message into 502 "Couldn't reach Anthropic. Your plan is unchanged."
- **No request has reached the real Anthropic API.** Every test uses `FakeProvider` or an `httpx2.MockTransport`. Each model's call shape is taken from Anthropic's documentation and the SDK's request encoding:
  - Claude Opus 5: structured outputs, `effort: low`, and the `server-side-fallback-2026-07-01` beta with `fallbacks="default"`.
  - Claude Sonnet 5: structured outputs and `effort: low`.
  - Claude Haiku 4.5: structured outputs, no effort.
  - The key check: `models.retrieve`.
  - If the API refuses a combination, every polish on that model answers 502 "Couldn't reach Anthropic. Your plan is unchanged.", and `fly logs` shows `anthropic call failed: BadRequestError (status 400)`.
- **The cooking view shows no descriptions.** `describe_week` attaches them, and `cooking_view`, the household's view of the week, does not.
- **Removing the key keeps the descriptions already written.** Each is shown until its dish's name or ingredients, or the prompt version, change. They are deleted only with the account.

**Deploy**
- **Nothing is deployed.** No account, domain, DNS record, pushed image or production secret exists. `DEPLOY.md` lists the steps, in order.
- **`backend/fly.toml` has never been validated by `flyctl`.** `fly config validate` needs the CLI and an account, and the runbook runs it before the first deploy.
- **A hostless `DATABASE_URL` passes the production localhost refusal.** `postgresql+psycopg:///hm`, a Unix-socket URL, has no host, so it is not refused. A hosted Postgres URL always carries a host.
- **The runtime image relies on its base image for CA certificates.** The Anthropic SDK's HTTP client (`httpx2`, through `truststore`) trusts the operating system's store. `python:3.13-slim-bookworm` ships `ca-certificates`, and Task 9's rehearsal found it there, but nothing in the Dockerfile installs or asserts it.
- **CI boots the image with development settings only.**
  - Its boot step sets no `APP_ENV`, so the server it waits on runs on the development defaults. In CI, the production path is exercised only by the refusal check.
  - So a change that made the production validator refuse a clean production configuration would still pass CI. The one production boot is Task 9's local rehearsal, against a scratch database on the compose network.
  - The workflow itself has never run on GitHub, since nothing has been pushed.
- **Safari may cap the `api.` cookie at 7 days.**
  - WebKit documents a 7-day cap on cookies that a first-party subdomain sets from a server whose IP address is unlike the page's.
  - `api.` on Fly and `app.` on Cloudflare have unlike addresses, so Safari users may have to sign in weekly despite the 30-day session.
  - Unverified; step 11 of the runbook says how to check.
  - The fix, a same-origin API behind a Pages Function or Worker, is not built.
- **Preview deployments cannot sign in.** `*.pages.dev` is a public suffix, so a preview is a different site from `api.<domain>`, and its `Lax` cookie is never sent. Its origin is not in the OAuth client either.
- **The seed snapshot loads only into an empty database.** A database that already has users is refreshed by `etl.run_all`, which needs the three downloads and a direct connection.
- **The regions are unchecked.** Fly's `bom` and Neon's `aws-ap-south-1` must be confirmed at sign-up.
- **The reminder loop keeps Neon awake.** A tick every minute means Neon's compute never scales to zero.
- **The web app sends no security headers.**
  - `_headers` sets caching only: there is no `Content-Security-Policy`, `frame-ancestors` or `Referrer-Policy`.
  - Headers added later must keep Google sign-in working: `Referrer-Policy` no stricter than `strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin-allow-popups`, and GSI's script, frame and style origins allowed.
- **The ETL's sources are unpinned.**
  - IFCT is read from a mutable `master` branch, and no download is checksummed, so two ETL runs months apart can differ.
  - The seed snapshot's `fingerprint` command shows whether they did.

**Carried from plan 8** (as plan 8's closeout records them)

*Recalibration*
- **A blip can still step as the oldest point of a fresh window** (carried from plan 7). That covers the onboarding weigh-in, a step's own date, and the first weigh-in after a goal change. A reading more than about 0.83 kg off can move a bounded step on the fourth weigh-in. A typed onboarding weight is the realistic case. Leaving the anchor weigh-in out of its own window's slope would close it.

*The ledger and the report*
- **Carries onto untracked days are not reported.** A shortfall carried onto a day with nothing logged is neither made up nor counted as uncompensated, because the walk never costs an untracked day.
- **A week's figures can differ slightly from what Today showed.** The report walks from a clean slate four days before Sunday, as Today does. Chains of unmet carries older than that are not followed.
- **An old week is re-costed against today's profile and food tables.** The report is derived, never stored.
- **EAR and TUL come from the week's first day.** The report loads its context at the Sunday, so the EAR of an energy-scaled B vitamin, and an overlay-touched energy-derived target, do not follow a mid-week recalibration.
- **A day logged only with foods that have no nutrient rows reads as untracked**, although the diary has an entry.
- **Only sodium's lowered ceiling is explained on Today.** Saturated fat, free sugar and cholesterol render as `StatTile`s, which show no carry, and so does a lowered energy target.
- **The "Lowered by" note can overstate the drop.** It prints the raw negative carry, while `effective_target` clamps at the EAR.
- **A salty day's lowering can chain past two days.** A surplus is measured against the already-lowered ceiling (the spec's delta = consumed - effective target, the same rule shortfalls follow), so a day under the base ceiling but over the lowered one counts as over the limit and carries a little further, bounded by the 30% cap per source day. Measuring a ceiling's surplus against its base ceiling would stop it.
- **The Report screen's Next stops at the browser's current week**, so a browser whose clock is behind the account's timezone cannot reach the server's week in progress; the household card mirrors this.

*The planner*
- **The planner's emphasis is invisible.** `WeekPlanOut` does not carry it, so the Plan screen cannot say it is leaning on calcium because of last week.
- **Suggestions ignore oxalate.** A calcium suggestion can name a dish whose calcium comes from high-oxalate greens. The ingredient's `oxalate_class` is not used yet.
- **Suggested dishes ignore what else they carry.**
  - On warfarin, a calcium or fibre suggestion can name a greens dish rich in vitamin K, and the next plan's calcium emphasis can lean the same way.
  - Vitamin K has no `rda_reference` row, so it has no target. That leaves nothing to filter a dish against, and it leaves the planner's hold-steady penalty inert in production: `_hold_steady_penalty` finds no vitamin K goal.
  - Seeding a sourced vitamin K reference would allow both a report filter and a working penalty. The filter would drop dishes whose default portion alone moves vitamin K by more than `HOLD_STEADY_TOLERANCE` of its goal.
  - Potassium needs no such filter: on a potassium-sparing drug it keeps its base AI, and the planner fills that AI itself.
- **Asking for next week's plan mid-week freezes a partial-week emphasis until a regenerate.** The emphasis is read from the week before the plan's, which has not finished yet; the screen only asks for the current week.

*Households*
- **Daily progress is not shared.**
  - The spec shares "daily and weekly nutrition progress — whether each member hit their targets". The household sees only the week's counts: days logged, and nutrient-days on track out of those measured.
  - The counts cover finished days only, so the card never shows whether anyone hit their targets on a particular day. Today reaches the household only once it is over, so on a Sunday the card reads zero for everyone.
  - The sharing switch still says "Share my daily progress with the household".

*Reminders*
- **Saturday-evening plan generation is not built.** A plan generated then misses Saturday's carries, and on-demand generation on Sunday gives the same plan with them.
- **Recalibration is still re-read only on a new weigh-in.**
- **Push targets are checked for https only.** There is no allowlist of the push services' hosts.
- **A session that ends without a sign-out leaves the device subscribed** to the previous account. That covers cookie expiry and cleared cookies. The screen reads it as "on" for whoever signs in next.
- **A subscription under an old VAPID key pair reads as on but is never reminded.** Turning it off and on again fixes it.
- **Push cannot be exercised by the e2e walks.** The dev server registers no service worker. Manual spec step 16 needs a production build and VAPID keys.
- **`pywebpush` brings `aiohttp` and six small packages into the lock file.**

*Pre-existing gaps*
- **Concurrent double submits can answer 500** on the unique constraints of check-then-insert upserts: weigh-ins, cycle settings and reminder rows.
- **The swap-during-regenerate backend race remains.** The Plan screen now disables Swap and Lock while a regenerate runs.
