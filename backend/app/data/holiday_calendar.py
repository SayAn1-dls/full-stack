"""England & Wales bank-holiday calendar behind `is_bank_holiday_ew`.

Definition used (recorded in DECISIONS.md): a calendar date (Europe/London) on which a bank holiday is
*observed* in England and Wales, substitute days included. Source: the Python `holidays` package
(`UnitedKingdom`, subdivision England), which covers the whole 2009-2024 range. The package lists a holiday's
nominal date even when it falls on a weekend *and* the substitute weekday; gov.uk lists only the substitute, so
nominal weekend dates are dropped. The result is cross-checked against a frozen gov.uk snapshot for 2019+ in
`reference_checks.py` (gov.uk's JSON no longer carries earlier years).

Scotland and Northern Ireland have extra/different bank holidays (e.g. 2 January, St Andrew's Day); they are
deliberately not included.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import holidays


def nominal_holidays_england(years: Iterable[int]) -> dict[date, str]:
    """Every date the `holidays` package lists for England, weekends included."""
    return dict(holidays.UnitedKingdom(subdiv="England", years=sorted(set(years))))


def observed_bank_holidays_england_wales(years: Iterable[int]) -> dict[date, str]:
    """Dates on which a bank holiday is observed (Monday-Friday only), with the package's holiday name."""
    return {d: name for d, name in nominal_holidays_england(years).items() if d.weekday() < 5}
