# Wind Intelligence

A web app for a UK utility's day-ahead buying team. For any delivery day in the January 2026 purchasing window it shows
**the latest wind forecast that was actually available when the buyer had to decide**, set against what wind really delivered,
and it **quantifies how accurate that forecast has been**. Data: Elexon BMRS `FUELHH` (wind outturn) and `WINDFOR` (wind forecast) only.

**Live app: https://wind-intelligence.vercel.app** (API docs: https://wind-intelligence.vercel.app/api/docs)

React + TypeScript front end, Python (FastAPI) back end, Docker packaging, deployed on Vercel.

## What it tells the buyer

On the January 2026 data (09:20 UK cutoff, 768 delivery hours) the forecast was **systematically too high**: on average by
+1.8 GW (16% of mean outturn), too high in 85% of hours and on 28 of 32 days, and most of all when it predicted a lot of wind
(forecasts of 17.8 GW or more were too high in every hour). It still beats a naive "same as yesterday" guess by about half.
Removing the average bias alone would cut the typical miss by about a third. A buyer who takes the forecast at face value
under-procures; the app therefore also offers a data-driven P10-P90 band and a "wind to count on" figure (the band's lower edge).
Full numbers and the method are in [`docs/APP_DESIGN.md`](docs/APP_DESIGN.md) and on the app's *Method and limits* page.
The data cannot say *why* the forecast runs high.

## Quick start

### Docker (recommended)

```bash
docker compose up --build
# web: http://localhost:8080   (nginx serves the React build and proxies /api)
# api: http://localhost:8000   (OpenAPI at /api/docs)
```

### Local development

```bash
# back end (Python 3.12 or 3.13)
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# front end (Node 22+), in a second terminal
cd frontend
npm install
npm run dev            # http://localhost:5173, /api proxied to :8000
npm run build          # type-check and production build into frontend/dist
npm test               # unit tests (vitest)
```

### Tests

```bash
cd backend
python -m pytest tests -q                 # all 219 tests (about 1 minute)
python -m pytest tests -q -m "not data"   # fast suite (about 10 seconds)

# browser checks (19) against a running app; needs Playwright with Chromium, which is not a dependency of this repo
node frontend/e2e/interact.cjs http://localhost:8080      # or the live URL
```

### Refreshing the data

The app reads a committed snapshot (`data/elexon/wind_snapshot.json`), not the live Elexon API, because January 2026 is history.
`cd backend && python -m app.wind.ingest` rebuilds it from Elexon and fails loudly on gaps, conflicting duplicates, non-hourly runs
or any row it would drop. `GET /api/health` returns the snapshot's SHA-256 so a deployment can be checked against the committed file.

## Deployment

Deployed on Vercel as one project: the React build is served statically and `api/index.py` exposes the FastAPI app as a Python
serverless function (`vercel.json` rewrites `/api/*` to it and bundles the snapshot with it). The deployed API is pure Python with two
dependencies (`requirements.txt`: fastapi, tzdata).

The Vercel project is **not linked to this Git repository**, so a push to GitHub does **not** redeploy it. Redeploy from the repository root
with the Vercel CLI (`vercel deploy --prod`) or through the Vercel API with this repository as the Git source. See `DECISIONS.md` D-34.

## Files and directories

```
README.md                  this file
DECISIONS.md               every decision made without asking, with reasons (D-01 ...)
BUG_LOG.md                 defects found while building, and how each was fixed
TEST_REPORT.md             what was run, results, mutation checks, remaining risks
docker-compose.yml         api (:8000) + web (:8080)
vercel.json, .vercelignore Vercel build, /api rewrite, bundle contents
requirements.txt           deployed API dependencies (fastapi, tzdata)
api/index.py               Vercel entrypoint (exposes backend/app/main.py:app)
backend/
  Dockerfile               API image (python:3.12-slim, non-root, uvicorn)
  requirements.txt         + uvicorn
  requirements-data.txt    NESO pipeline only (pandas, pyarrow, holidays)
  requirements-dev.txt     everything + pytest, httpx
  app/main.py              FastAPI app (docs at /api/docs)
  app/wind/
    scope.py               the January 2026 window and decision-time presets (one place to change them)
    elexon.py, ingest.py   fetch and validate FUELHH/WINDFOR, build the snapshot
    dataset.py             load the snapshot; "latest forecast available at a cutoff" lookup
    analytics.py           decision view, accuracy view, error model (P10-P90 band), persistence benchmark
    schemas.py, routes.py  response models and the /api endpoints
  tests/
    test_wind_analytics.py   synthetic cases (including clock-change days), regressions, exact percentiles
    test_wind_api.py         every endpoint on the real snapshot, recomputed independently; band calibration
    test_wind_ingest.py, test_wind_dataset.py, test_vercel_config.py   ingest rules, loading, bundle completeness
  app/data/                the NESO demand pipeline (see below)
frontend/
  Dockerfile, nginx.conf   web image: node build, nginx serves it and proxies /api
  src/App.tsx, api.ts, format.ts, types.ts, theme.css
  src/views/               DecisionView, AccuracyView, MethodView
  src/charts/              hand-written SVG charts (line, bar, histogram, scatter), tooltip, legend, table twin
  e2e/interact.cjs         19 Playwright checks to run against any running instance
data/
  elexon/wind_snapshot.json   the Elexon snapshot the app serves (1,536 half-hours of outturn, 280 forecast runs)
  raw/, processed/            NESO demand data (see below; not used by the app)
demo/                      demo video: transcript, captions, YouTube description, build scripts (the MP4 is not in git)
docs/
  APP_DESIGN.md            findings, decision logic, architecture, limits
  DATA_DICTIONARY.md, DATA_CLEANING_REPORT.md   NESO pipeline documentation
```

## How the "available at decision time" forecast is chosen

Delivery day D, decision on D-1 at a UK local time the user picks (presets 09:20 EPEX and 09:50 N2EX GB day-ahead gate closures; editable).
For each hour of D the app takes the newest `WINDFOR` publication at or before that cutoff that has a value for the hour. Error = forecast
minus outturn, so positive means the forecast was too high (the costly side for a buyer). If an early cutoff leaves some hours without any
published forecast, they are shown as missing, never estimated.

## Scope and limits

- Elexon `FUELHH` (wind) and `WINDFOR` only, as the PRD requires. **No demand and no prices**, so the app cannot say how much to buy,
  only how much wind to count on.
- One winter month, one source: the bias may not transfer to other seasons. The P10-P90 band is in-sample for the window.
- `WINDFOR` is hourly and `FUELHH` half-hourly. The literal reading (same start time) is used; alternatives move the MAE by less than 2% (`DECISIONS.md` D-26).
- The decision cutoff is a modelling choice (the PRD says only "one day before"); it is editable.

## Supporting dataset: NESO historic demand (separate, not used by the app)

`backend/app/data/` holds a cleaning and validation pipeline for NESO "Historic Demand Data" (Great Britain, half-hourly, 2009-01-01 to
2024-12-05). It is **not** Elexon data, it is **not** wired into the app (the PRD allows no data beyond FUELHH/WINDFOR), and it ends in
December 2024, so it does not cover January 2026. `embedded_wind_generation` in it is NESO's estimate of distribution-connected wind only.

```bash
cd backend
python -m app.data.fetch_raw_data   # only if data/raw/ is empty; verifies SHA-256 before installing
python -m app.data.clean_demand     # about 30 s, idempotent: writes data/interim/ and data/processed/ only
python -m app.data.build_docs       # regenerates docs/DATA_DICTIONARY.md
```

It is built from the 16 yearly files (five schema eras), produces DST-correct unique UTC timestamps, drops nothing and imputes nothing, nulls
invalid zeros with a flag, and keeps suspect readings flagged. See `docs/DATA_CLEANING_REPORT.md`, `docs/DATA_DICTIONARY.md` and `data/README.md`.

## Not delivered

The PRD also asks for a recorded demo video, an anonymously named public repository and a submission form. Those are not code in this
repository and were not done; neither was a Heroku deployment (Vercel was chosen). This repository carries its owner's name, so it is not anonymous.

## AI-use disclosure

This project was built with an AI coding assistant, Claude Code by Anthropic, which wrote the code, tests and documentation and ran the
deployment. Outputs were checked by running the test suites, a browser-driven interaction suite (Playwright) against the local build, the Docker
stack and the live site, and mutation checks on the analytics (`TEST_REPORT.md`). The demo video's script was written by the assistant and its narration voice is computer generated (`demo/README.md`). Docker was verified in a sandbox using local shim base images
(`DECISIONS.md` D-35); the Dockerfiles themselves are unchanged and standard.

## Data licences and sources

Wind outturn and forecast data come from the Elexon BMRS API (https://data.elexon.co.uk/bmrs/api/v1, endpoints in `DECISIONS.md` D-02); check Elexon's
published terms of use before redistributing the snapshot, the licence was not reviewed here.
NESO Historic Demand Data: NESO Open Data Licence. The combined files `historic_demand_2009_2024*.csv` are "Electricity Consumption UK 2009-2024"
by albertovidalrod on Kaggle, ODbL 1.0 (see `data/README.md`).
