"""Scope and defaults for the January 2026 purchase-decision window (single place to change them).

The PRD asks for "data relevant only for purchase decisions to be made in January 2026". Day-ahead decisions are
taken on D-1 for delivery day D, so decisions made 1-31 January 2026 cover delivery days 2 January - 1 February.
Delivery on 1 January (decided on 31 December) is included too, so that every January 2026 target time is covered;
the app labels that day. Forecast publications are fetched from three days before the first delivery day so each
delivery day has its full forecast history.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

LOCAL_TZ = "Europe/London"

DELIVERY_FIRST = date(2026, 1, 1)
DELIVERY_LAST = date(2026, 2, 1)
DECISION_WINDOW_FIRST = date(2026, 1, 1)  # decisions *made* in January 2026 ...
DECISION_WINDOW_LAST = date(2026, 1, 31)  # ... for delivery 2 January - 1 February

FORECAST_PUBLISH_FROM = datetime(2025, 12, 29, tzinfo=timezone.utc)
FORECAST_PUBLISH_TO = datetime(2026, 2, 2, tzinfo=timezone.utc)

# GB day-ahead auction gate closures, UK local time (see docs/APP_DESIGN.md for sources). Editable in the UI.
DEFAULT_DECISION_TIME = time(9, 20)
DECISION_PRESETS = (
    {"label": "EPEX GB day-ahead gate closure", "time": "09:20"},
    {"label": "N2EX day-ahead gate closure", "time": "09:50"},
)
