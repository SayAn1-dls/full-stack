# Wind Intelligence app: design

The product the PRD asks for: a web app for a UK utility's day-ahead buying team that (1) shows the latest wind
forecast available when they must decide, and (2) quantifies how accurate that forecast is. Elexon data only
(`FUELHH` wind outturn, `WINDFOR` wind forecast), decisions made in January 2026.

## What the data says (January 2026, 09:20 cutoff)

All figures from `GET /api/accuracy` on the committed snapshot; each is asserted by a test in `backend/tests/test_wind_api.py`.

| | |
|---|---|
| Hours compared | 768 (32 delivery days x 24) |
| Mean outturn / mean forecast | 11.4 GW / 13.2 GW |
| **Bias (forecast - outturn)** | **+1,823 MW (16% of mean outturn)** |
| MAE / RMSE | 2,091 MW / 2,572 MW |
| P90 of absolute error | 4,251 MW |
| Hours over-forecast / days over-forecast | 85% / 28 of 32 |
| MAE if the bias were removed | 1,416 MW: correcting the offset alone would cut the typical miss by about a third (2,091 to 1,416 MW); the rest is hour-to-hour variation that a constant correction cannot fix |
| Error P5 to P95 | -1,026 to +5,333 MW |
| Skill vs persistence | 51% (MAE 2,023 vs 4,097 MW on the 744 hours where a persistence value exists) |
| Bias by forecast size (quartiles) | +525, +1,701, +1,614, **+3,454 MW** (forecasts of 17.8 GW or more were over-forecast in every hour) |
| MAE by lead time | 1,738 MW (0-6 h) rising to 2,349 MW (48-67 h); bias stays 1.5-2.0 GW at every lead time |
| P10-P90 band coverage | 78.4% of outturns fall inside the band (nominal 80%) |

Reading: the forecast is far better than a naive guess, but it is consistently optimistic (the average error is almost as large as the typical error
because the misses are one-sided), most of all when it forecasts a lot of wind. A buyer who takes it at face value under-procures. The data cannot say *why*. Candidate explanations,
not tested here: WINDFOR covers wind farms "visible to the ESO and have operational metering" and may describe available
rather than delivered output (curtailment would then appear as over-forecast), or the two series cover slightly
different sets of plants.

Other findings that shaped the build:

- WINDFOR is **hourly**, FUELHH is **half-hourly**. Comparing the forecast for hour T with the outturn at T, T+30, the hour
  average, T-30..T, or a centred average changes the MAE only between 2,060 and 2,105 MW (<2%), so the literal PRD reading (same `startTime`) is used.
- Elexon publishes WINDFOR about 8 times a day (UTC: 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30, 22:30). One run on 15 January
  came at 12:25 instead of 11:30. Each run is 73 hourly values reaching 46.5 to 66.5 hours ahead.
- Consecutive runs are often identical for the next day (only 7 of 279 consecutive pairs are fully identical overall, but the
  02:30, 04:30 and 07:30 runs frequently carry the same D+1 values).
- A very early cutoff (for example 00:00) leaves the last two hours of the delivery day without any forecast; the app reports
  them as missing instead of hiding or estimating them.

## Decision logic

- Delivery day D, decision on D-1 at a user-chosen UK local time. Presets: **09:20** (EPEX GB day-ahead gate closure) and
  **09:50** (N2EX); both from [Nord Pool](https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-day-ahead-gb-auction) and EPEX
  (10:20 CET = 09:20 UK). One trade-press note puts N2EX at 09:40, so the cutoff is editable.
- For every hour of D the forecast "available at the decision" is the newest WINDFOR publication at or before the cutoff that has
  a value for that hour (`Dataset.latest_forecast`). A run published exactly at the cutoff counts.
- **Scope.** The PRD says "purchase decisions to be made in January 2026". Decisions on 1-31 January cover delivery days
  2 January - 1 February; delivery on 1 January (decided 31 December) is included as well so every January target time is covered,
  and the UI labels it. `backend/app/wind/scope.py` is the single place to change this.
- **Error** = forecast - outturn; positive = forecast too high = wind came in below it (the costly side for a buyer).
- **Planning band.** The P10-P90 of past error for forecasts of a similar size: forecast levels are split into data-driven quartiles, each
  quartile's error quantiles are taken, and they are interpolated linearly between quartile centres so the band has no steps.
  The day being viewed is excluded from its own band. "Wind to count on" is the lower edge (outturn was at or above it in about 9 of 10 similar hours).
  It uses information from later days, so it describes this window rather than guaranteeing the future.
- **What it deliberately does not do:** compute how much to buy. Demand and prices are out of scope (PRD: "no other data beyond this").

## Architecture

```
React (Vite, TypeScript, hand-written SVG charts)  --/api-->  FastAPI (pure Python analytics)  --reads-->  data/elexon/wind_snapshot.json
                                                                                                              ^
                                                              python -m app.wind.ingest  --fetches-->  Elexon BMRS API (FUELHH, WINDFOR)
```

- **Snapshot, not live calls.** January 2026 is history, so the app reads a committed 147 KB snapshot (1,536 half-hours of outturn,
  280 forecast runs, 20,440 hourly values). `ingest` rebuilds it from the live Elexon API and fails loudly on gaps, conflicting duplicates,
  non-hourly runs or any row it would drop. Cold starts need no network and the app cannot be taken down by an Elexon outage.
- **Pure Python, no pandas/numpy** in the API: the serverless bundle is just FastAPI plus the app (a few tens of KB).
- **Endpoints** (OpenAPI at `/api/docs`): `GET /api/meta`, `/api/decision?delivery_date=&decision_time=`, `/api/accuracy?start=&end=&decision_time=`, `/api/health`
  (returns the snapshot SHA-256, which is how a deployment is verified against the committed data).
- **Frontend**: no chart library. Charts follow a stated spec (2px lines, bars at most 24px with a 4px rounded data end and a 2px surface gap,
  surface-ringed markers, hairline grid, crosshair that snaps to data, 24px nearest-point reach on the scatter), every chart has a
  table twin, a legend whenever there are two or more series, light and dark themes with their own selected steps, URL state (`?tab=&date=&time=`) so views can be shared.
- **Colour** (validated with the dataviz `validate_palette.js`, all PASS in both modes): forecast = blue `#2a78d6` / `#3987e5`, outturn = orange `#eb6834` / `#d95926`
  (CVD distance 24.7 / 26.8, normal-vision 33.6 / 31.8); error polarity = blue vs red `#e34948` / `#e66767` (CVD 21.6 / 19.2, normal 32.3 / 29.0).
  Text never wears a data colour.

## Layout of the code

```
api/index.py                  Vercel entrypoint (exposes backend/app/main.py:app)
vercel.json                   build, rewrite /api/* to the function, files bundled with it
requirements.txt              serverless runtime dependencies (fastapi, tzdata)
backend/app/main.py           FastAPI app
backend/app/wind/             scope.py (window, cutoffs), elexon.py + ingest.py (fetch/validate/snapshot), dataset.py (load, latest_forecast),
                              analytics.py (decision view, accuracy view, error model), schemas.py (response models), routes.py
backend/tests/test_wind_*.py  analytics (synthetic, incl. DST days), ingest rules, API on the real snapshot; test_vercel_config.py (bundle completeness)
frontend/src/                 App, views (Decision, Accuracy, Method), charts (Line, Bar, Histogram, Scatter, ChartCard, tooltip), scales, formatters
data/elexon/wind_snapshot.json
Dockerfile(s)                 backend/Dockerfile (API), frontend/Dockerfile + nginx.conf (web), docker-compose.yml
```

## Limits

- One winter month, one source: conclusions about bias may not transfer to other seasons.
- No demand: the app cannot say how much to buy, only how much wind to count on.
- The cause of the over-forecast is not identifiable from Elexon data alone.
- The data is a snapshot taken 2026-10-24; refresh with `python -m app.wind.ingest`.
