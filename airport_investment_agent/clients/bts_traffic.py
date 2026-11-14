"""BTS T-100 traffic data (Socrata `data.bts.gov` dataset r495-tyji):
per-airport annual rows for a single lookup, plus nationwide-extreme
lookups (busiest airport by passengers / highest load factor) used to
normalize scores against real, not invented, reference points.

BTS publishes this dataset as one row per airport per *month*
(`reporting_month`). Every query here aggregates server-side (SoQL
`$group`) into calendar-year rows, so callers keep working with one row
per year:

- passengers / departures / seats: plain sums over the year's months.
- load factor: seat-mile weighted -- sum(monthly_lf * ASM) / sum(ASM), with
  each month's ASM approximated as seats * average stage length
  (`total_distance_flight_sm`). That keeps load factor's real RPM/ASM
  meaning instead of a flat average of monthly percentages, which would
  over-weight quiet months.
- passengers per departure: the year's passengers / its departures.

The newest year is labelled "<year> YTD" while it's still in progress, so
tools/traffic.py can keep treating only all-digit years as complete and
never compares a partial year against a full one.

Pure I/O plus that aggregation -- no domain transform (growth_rate etc.)
lives here. See tools/traffic.py for that.
"""

import functools

import requests

from airport_investment_agent.models import AirportDataError
from airport_investment_agent.utils.http import get_with_retry

BTS_ENDPOINT = "https://data.bts.gov/resource/r495-tyji.json"
REQUEST_TIMEOUT_SECONDS = 10
MIN_DEPARTURES_FOR_NATIONWIDE_COMPARISON = 10_000
YEARS_OF_HISTORY = 10

_SEAT_MILES = "total_seats * total_distance_flight_sm"
_ANNUAL_AGGREGATES = (
    "max(reporting_month) as last_month, "
    "sum(total_passengers) as passengers, "
    "sum(total_departures) as departures, "
    "sum(total_seats) as seats, "
    f"sum(total_load_factor * {_SEAT_MILES}) / sum({_SEAT_MILES}) as load_factor_pct"
)
# Months with no seats (cargo-only, or not yet reported) carry no passenger
# load factor and would only add zero-weight noise / a division by zero.
_HAS_SEATS = "total_seats > 0"


def _query(params: dict, context: str) -> list[dict]:
    try:
        response = get_with_retry(
            BTS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise AirportDataError(
            f"Could not reach the BTS data service {context}: {error}"
        ) from error
    return response.json()


def _is_december(reporting_month: str) -> bool:
    # Socrata floating timestamps look like "2025-12-01T00:00:00.000".
    return reporting_month[5:7] == "12"


def _to_annual_row(row: dict, *, in_progress: bool) -> dict:
    passengers = int(float(row["passengers"]))
    departures = int(float(row["departures"]))
    return {
        "year": f"{row['year']} YTD" if in_progress else row["year"],
        "total_passengers": passengers,
        "total_departures": departures,
        "total_seats": int(float(row["seats"])),
        "total_load_factor": float(row["load_factor_pct"]),
        "total_passengers_flight": passengers / departures,
    }


def _fetch_airport_rows(iata_code: str) -> list[dict]:
    """One row per calendar year for this airport, newest first."""
    rows = _query(
        {
            "$select": f"year, {_ANNUAL_AGGREGATES}",
            "$where": f"origin_airport_code='{iata_code}' AND {_HAS_SEATS}",
            "$group": "year",
            "$order": "year DESC",
            "$limit": YEARS_OF_HISTORY,
        },
        f"for '{iata_code}'",
    )
    rows = [
        row
        for row in rows
        if row.get("load_factor_pct") is not None and float(row["departures"]) > 0
    ]
    return [
        # Only the newest year can still be in progress; older years are
        # complete by definition, even for a seasonal airport with no
        # December service.
        _to_annual_row(
            row, in_progress=index == 0 and not _is_december(row["last_month"])
        )
        for index, row in enumerate(rows)
    ]


@functools.lru_cache(maxsize=1)
def _get_latest_complete_year() -> str:
    rows = _query(
        {
            "$select": "year, max(reporting_month) as last_month",
            "$group": "year",
            "$order": "year DESC",
            "$limit": 20,
        },
        "while looking up the latest year",
    )
    latest_complete_year = next(
        (row["year"] for row in rows if _is_december(row["last_month"])), None
    )
    if latest_complete_year is None:
        raise AirportDataError(
            "BTS returned no complete calendar year across the whole dataset."
        )
    return latest_complete_year


def _fetch_nationwide_extreme(order_by: str) -> float:
    """The highest annual `order_by` value ("passengers" or
    "load_factor_pct") among real-commercial-scale airports in the latest
    complete year."""
    latest_year = _get_latest_complete_year()
    rows = _query(
        {
            "$select": f"origin_airport_code, {_ANNUAL_AGGREGATES}",
            "$where": f"year='{latest_year}' AND {_HAS_SEATS}",
            "$group": "origin_airport_code",
            "$having": f"sum(total_departures) > {MIN_DEPARTURES_FOR_NATIONWIDE_COMPARISON}",
            "$order": f"{order_by} DESC",
            "$limit": 1,
        },
        f"while looking up the nationwide {order_by}",
    )
    if not rows:
        raise AirportDataError(
            f"BTS returned no real-commercial-scale airport for the nationwide "
            f"{order_by} lookup in {latest_year}."
        )
    return float(rows[0][order_by])


@functools.lru_cache(maxsize=1)
def get_nationwide_max_passengers() -> float:
    return _fetch_nationwide_extreme("passengers")


@functools.lru_cache(maxsize=1)
def get_nationwide_max_load_factor() -> float:
    return _fetch_nationwide_extreme("load_factor_pct") / 100
