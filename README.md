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
