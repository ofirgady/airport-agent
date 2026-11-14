"""BTS T-100 traffic data (Socrata `data.bts.gov` dataset r495-tyji):
per-airport rows for a single lookup, plus nationwide-extreme lookups
(busiest airport by passengers / highest load factor) used to normalize
scores against real, not invented, reference points.

Pure I/O -- no domain transform (passengers -> load_factor, growth_rate,
etc.) lives here. See tools/traffic.py for that.
"""

import functools

import requests

from airport_investment_agent.models import AirportDataError
from airport_investment_agent.utils.http import get_with_retry

BTS_ENDPOINT = "https://data.bts.gov/resource/r495-tyji.json"
REQUEST_TIMEOUT_SECONDS = 10
MIN_DEPARTURES_FOR_NATIONWIDE_COMPARISON = 10_000


def _fetch_airport_rows(iata_code: str) -> list[dict]:
    try:
        response = get_with_retry(
            BTS_ENDPOINT,
            params={
                "origin_airport_code": iata_code,
                "$order": "year DESC",
                "$limit": 10,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise AirportDataError(
            f"Could not reach the BTS data service for '{iata_code}': {error}"
        ) from error
    return response.json()


@functools.lru_cache(maxsize=1)
def _get_latest_complete_year() -> str:
    try:
        response = get_with_retry(
            BTS_ENDPOINT,
            params={
                "$select": "year",
                "$group": "year",
                "$order": "year DESC",
                "$limit": 20,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise AirportDataError(
            f"Could not reach the BTS data service while looking up the latest year: {error}"
        ) from error

    years = [row["year"] for row in response.json()]
    latest_complete_year = next((year for year in years if year.isdigit()), None)
    if latest_complete_year is None:
        raise AirportDataError(
            "BTS returned no complete calendar year across the whole dataset."
        )
    return latest_complete_year


def _fetch_nationwide_extreme(sort_field: str) -> float:
    latest_year = _get_latest_complete_year()
    try:
        response = get_with_retry(
            BTS_ENDPOINT,
            params={
                "$where": (
                    f"year='{latest_year}' AND {sort_field} IS NOT NULL "
                    f"AND total_departures > {MIN_DEPARTURES_FOR_NATIONWIDE_COMPARISON}"
                ),
                "$order": f"{sort_field} DESC",
                "$limit": 1,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise AirportDataError(
            f"Could not reach the BTS data service while looking up the nationwide {sort_field}: {error}"
        ) from error

    rows = response.json()
    if not rows:
        raise AirportDataError(
            f"BTS returned no real-commercial-scale airport for the nationwide {sort_field} lookup in {latest_year}."
        )
    return float(rows[0][sort_field])


@functools.lru_cache(maxsize=1)
def get_nationwide_max_passengers() -> float:
    return _fetch_nationwide_extreme("total_passengers")


@functools.lru_cache(maxsize=1)
def get_nationwide_max_load_factor() -> float:
    return _fetch_nationwide_extreme("total_load_factor") / 100
