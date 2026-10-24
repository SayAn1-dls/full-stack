"""Schema constants for the NESO "Historic Demand Data" files.

Everything that describes *what the columns are* lives here so the pipeline, the reference
checks, the tests and the data dictionary agree on one definition.

Field definitions and units are copied from NESO's own datastore schema
(https://api.neso.energy/api/3/action/datastore_search?resource_id=f6d02c0f-957b-48cb-82ee-09003f2ba759),
retrieved 2026-10-24.
"""

from __future__ import annotations

KEY_COLUMNS = ("settlement_date", "settlement_period")

# Canonical order = union of every era's columns. Column *position* in a raw file is never used.
POWER_COLUMNS = (
    "nd",
    "tsd",
    "england_wales_demand",
    "embedded_wind_generation",
    "embedded_wind_capacity",
    "embedded_solar_generation",
    "embedded_solar_capacity",
    "non_bm_stor",
    "pump_storage_pumping",
    "scottish_transfer",
    "ifa_flow",
    "ifa2_flow",
    "britned_flow",
    "moyle_flow",
    "east_west_flow",
    "nemo_flow",
    "nsl_flow",
    "eleclink_flow",
    "viking_flow",
    "greenlink_flow",
)
CANONICAL_COLUMNS = KEY_COLUMNS + POWER_COLUMNS

FIRST_YEAR = 2009
LAST_YEAR = 2024
YEARLY_FILE_TEMPLATE = "historic_demand_year_{year}.csv"
COMBINED_FILE = "historic_demand_2009_2024.csv"
NONAN_FILE = "historic_demand_2009_2024_noNaN.csv"

# Rule 5: a reading of exactly 0 is physically impossible for these columns -> invalid -> NaN.
# (column, flag name). Flag columns are `flag_<name>`; quality_flags tokens are `<name>`.
INVALID_ZERO_RULES = (
    ("nd", "nd_zero"),
    ("tsd", "tsd_zero"),
    ("england_wales_demand", "england_wales_demand_zero"),
)

# Rule 6: suspect readings keep their value and gain a flag.
SUSPECT_FLAGS = ("tsd_below_nd", "wind_gen_above_capacity", "negative_stor")
CONSTANT_COLUMN_FLAG = "constant_column"

# A column is "constant" only if it has at least this many published values and one distinct value.
CONSTANT_COLUMN_MIN_ROWS = 1000

INVALID_FLAG_NAMES = tuple(flag for _, flag in INVALID_ZERO_RULES)
ALL_FLAG_NAMES = INVALID_FLAG_NAMES + SUSPECT_FLAGS + (CONSTANT_COLUMN_FLAG,)

REASON_NOT_PUBLISHED = "column_not_published"
REASON_INVALID_ZERO = "invalid_zero_reading"

# Column metadata used to generate docs/DATA_DICTIONARY.md. Definitions are NESO's wording
# (lightly shortened); `notes` carries what this project found in the data.
COLUMN_DOCS: dict[str, dict[str, str]] = {
    "nd": {
        "unit": "MW",
        "definition": (
            "National Demand: GB generation requirement, equal to the Initial National Demand Outturn (INDO). "
            "Sum of metered generation, excluding generation required for station load, pump storage pumping "
            "and interconnector exports."
        ),
    },
    "tsd": {
        "unit": "MW",
        "definition": (
            "Transmission System Demand: ND plus the additional generation required to meet station load, "
            "pump storage pumping and interconnector exports. Includes an estimated station load of 500 MW in "
            "BST and 600 MW in GMT."
        ),
    },
    "england_wales_demand": {
        "unit": "MW",
        "definition": "England and Wales Demand: as ND, but on an England and Wales basis.",
        "notes": (
            "Six non-zero readings look inconsistent with `nd` (england_wales_demand / nd below 0.8 or above 1.05, "
            "e.g. 7,654 MW against ND 40,330 on 2010-10-11 period 23). They are not flagged or altered; see "
            "docs/DATA_CLEANING_REPORT.md."
        ),
    },
    "embedded_wind_generation": {
        "unit": "MW",
        "definition": (
            "NESO's model estimate of GB wind generation from wind farms without transmission metering "
            "(embedded in distribution networks). NOT total national wind output."
        ),
    },
    "embedded_wind_capacity": {
        "unit": "MW",
        "definition": "NESO's best view of installed embedded wind capacity in GB (estimate, not definitive).",
    },
    "embedded_solar_generation": {
        "unit": "MW",
        "definition": "NESO's model estimate of GB solar PV generation embedded in distribution networks.",
    },
    "embedded_solar_capacity": {
        "unit": "MW",
        "definition": "As embedded wind capacity, but for solar.",
    },
    "non_bm_stor": {
        "unit": "MW",
        "definition": (
            "Non-Balancing Mechanism Short-Term Operating Reserve: units not included in the ND generator "
            "definition; can be generation or demand reduction."
        ),
    },
    "pump_storage_pumping": {
        "unit": "MW",
        "definition": "Demand due to pumping at hydro pump storage units.",
        "notes": (
            "NESO's schema says 'the -ve signifies pumping load', but every published value is >= 0 "
            "(min 0, max 2019): values are the MW magnitude of pumping load, not signed. Not altered."
        ),
    },
    "scottish_transfer": {
        "unit": "MW",
        "definition": (
            "Volume of power flowing from Scotland to England and Wales. Negative values denote a flow from "
            "England and Wales to Scotland."
        ),
    },
}
for _name, _title in (
    ("ifa_flow", "IFA"),
    ("ifa2_flow", "IFA2"),
    ("britned_flow", "BritNed"),
    ("moyle_flow", "Moyle"),
    ("east_west_flow", "East-West"),
    ("nemo_flow", "Nemo"),
    ("nsl_flow", "North Sea Link"),
    ("eleclink_flow", "ElecLink"),
    ("viking_flow", "Viking"),
    ("greenlink_flow", "Greenlink"),
):
    COLUMN_DOCS[_name] = {
        "unit": "MW",
        "definition": (
            f"Flow on the {_title} interconnector. NEGATIVE = export out of GB; POSITIVE = import into GB "
            "(NESO sign convention; signs are kept, never absolute-valued)."
        ),
    }
