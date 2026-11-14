"""BTS monthly On-Time Performance file: probing for the latest published
month, downloading it, streaming/parsing the CSV inside its zip, and
snapshot-caching the aggregated result.

This is pure I/O and parsing -- no KPI math lives here. See
tools/otp_kpis.py for the completion/DDI/taxi-out/long-haul readers that
consume the AirportMonthlyAggregate cache this module produces.

The source file is large (hundreds of MB) and throttled server-side
(~60-90 KB/s) -- downloading it once per process (or reading a prebuilt
snapshot) instead of once per KPI is the reason this aggregation step
exists as a single shared cache at all.
"""

import csv
import io
import json
import logging
import zipfile
from datetime import date
from pathlib import Path
from typing import TypedDict

import requests

from airport_investment_agent.models.errors import CompletionDataUnavailableError
from airport_investment_agent.utils.http import get_with_retry

logger = logging.getLogger(__name__)

# Reporting Carrier table (not the newer Marketing Carrier table): BTS's own
# reporting directives require a codeshare flight to be filed as a separate
# record per marketing carrier code, so the Marketing Carrier table can
# count one physical departure more than once. Reporting Carrier is keyed
# to whoever actually operated and reported the flight -- one row per
# physical operation, no codeshare duplication. Also covers 1987-present
# instead of 2018-present, though that's irrelevant here since we only ever
# use the latest month.
PREZIP_URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

PUBLICATION_LAG_MONTHS = 2
MAX_MONTH_LOOKBACK_ATTEMPTS = 4
PROBE_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 600

# How old the cached OTP month can get before it's worth a warning -- the
# committed snapshot file (see OTP_SNAPSHOT_PATH below) is always preferred
# over a live check once one exists, so nothing else would otherwise notice
# it's gone stale until someone happens to look at the date themselves.
STALE_DATA_WARNING_MONTHS = 3

# Verified live: 2300mi tracks true transcontinental-or-longer stage lengths
# (JFK-LAX ~2475mi) without sweeping in ordinary narrowbody routes
# (ORD-LAX ~1745mi would incorrectly count under a 1500mi cutoff).
LONG_HAUL_DISTANCE_MILES = 2300.0


class AirportMonthlyAggregate(TypedDict):
    scheduled: int
    cancelled: int
    non_cancelled_departures: int
    delayed_departures: int
    delayed_departure_minutes_sum: float
    taxi_out_minutes_sum: float
    taxi_out_sample_count: int
    long_haul_count: int
    distance_observed: bool


def _prezip_url(year: int, month: int) -> str:
    return PREZIP_URL_TEMPLATE.format(year=year, month=month)


def _step_back_one_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _file_is_published(year: int, month: int) -> bool:
    try:
        response = requests.get(
            _prezip_url(year, month),
            headers={"Range": "bytes=0-1024"},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException:
        return False
    return response.status_code in (200, 206)


def resolve_latest_available_month(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    year, month = today.year, today.month
    for _ in range(PUBLICATION_LAG_MONTHS):
        year, month = _step_back_one_month(year, month)

    for _ in range(MAX_MONTH_LOOKBACK_ATTEMPTS):
        if _file_is_published(year, month):
            return year, month
        year, month = _step_back_one_month(year, month)

    raise CompletionDataUnavailableError(
        "Could not find a published BTS on-time-performance file in the "
        f"last {MAX_MONTH_LOOKBACK_ATTEMPTS} months checked."
    )


def _new_aggregate_entry() -> AirportMonthlyAggregate:
    return {
        "scheduled": 0,
        "cancelled": 0,
        "non_cancelled_departures": 0,
        "delayed_departures": 0,
        "delayed_departure_minutes_sum": 0.0,
        "taxi_out_minutes_sum": 0.0,
        "taxi_out_sample_count": 0,
        "long_haul_count": 0,
        "distance_observed": False,
    }


def _aggregate_from_csv_stream(stream) -> dict[str, AirportMonthlyAggregate]:
    aggregate: dict[str, AirportMonthlyAggregate] = {}
    for row in csv.DictReader(stream):
        origin = row.get("Origin")
        if not origin:
            continue
        entry = aggregate.setdefault(origin, _new_aggregate_entry())

        entry["scheduled"] += 1
        cancelled = row.get("Cancelled") == "1.00"
        if cancelled:
            entry["cancelled"] += 1
        else:
            entry["non_cancelled_departures"] += 1

        # DepDel15 is BTS's own precomputed "departure delayed >=15 minutes"
        # indicator (14 CFR Part 234's own on-time threshold) -- using it
        # directly, rather than re-deriving the same threshold from
        # DepDelayMinutes ourselves, guarantees our delay classification
        # always matches BTS's official definition exactly. DepDelayMinutes
        # is still needed for the *severity* sum (how late, not just
        # whether late), which BTS doesn't publish as its own field.
        if row.get("DepDel15") == "1.00":
            entry["delayed_departures"] += 1
            dep_delay_raw = row.get("DepDelayMinutes")
            if dep_delay_raw:
                try:
                    entry["delayed_departure_minutes_sum"] += float(dep_delay_raw)
                except ValueError:
                    pass

        taxi_out_raw = row.get("TaxiOut")
        if taxi_out_raw:
            try:
                entry["taxi_out_minutes_sum"] += float(taxi_out_raw)
                entry["taxi_out_sample_count"] += 1
            except ValueError:
                pass

        # Distance is BTS's fixed airport-pair reference mileage - present
        # for every row, cancelled or not.
        distance_raw = row.get("Distance")
        if distance_raw:
            entry["distance_observed"] = True
            try:
                if float(distance_raw) >= LONG_HAUL_DISTANCE_MILES:
                    entry["long_haul_count"] += 1
            except ValueError:
                pass
    return aggregate


def _aggregate_from_zip_bytes(zip_bytes: bytes) -> dict[str, AirportMonthlyAggregate]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_name = next(
            name for name in archive.namelist() if name.lower().endswith(".csv")
        )
        with archive.open(csv_name) as raw_stream:
            text_stream = io.TextIOWrapper(
                raw_stream, encoding="utf-8", errors="replace"
            )
            return _aggregate_from_csv_stream(text_stream)


def download_and_aggregate(year: int, month: int) -> dict[str, AirportMonthlyAggregate]:
    try:
        response = get_with_retry(
            _prezip_url(year, month), timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise CompletionDataUnavailableError(
            f"Could not download BTS on-time-performance data for {year}-{month:02d}: {error}"
        ) from error
    return _aggregate_from_zip_bytes(response.content)


OTP_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "otp_snapshots.json"
)

_monthly_aggregate_cache: (
    tuple[dict[str, AirportMonthlyAggregate], tuple[int, int]] | None
) = None


def _load_snapshot_cache() -> (
    tuple[dict[str, AirportMonthlyAggregate], tuple[int, int]] | None
):
    if not OTP_SNAPSHOT_PATH.exists():
        return None
    with OTP_SNAPSHOT_PATH.open() as snapshot_file:
        snapshots = json.load(snapshot_file)
    if not snapshots:
        return None

    latest_key = max(
        snapshots, key=lambda key: tuple(int(part) for part in key.split("-"))
    )
    latest = snapshots[latest_key]
    aggregate: dict[str, AirportMonthlyAggregate] = {
        origin: {
            "scheduled": data["scheduled"],
            "cancelled": data["cancelled"],
            "non_cancelled_departures": data["non_cancelled_departures"],
            "delayed_departures": data["delayed_departures"],
            "delayed_departure_minutes_sum": data["delayed_departure_minutes_sum"],
            "taxi_out_minutes_sum": data["taxi_out_minutes_sum"],
            "taxi_out_sample_count": data["taxi_out_sample_count"],
            "long_haul_count": data["long_haul_count"],
            "distance_observed": data["distance_observed"],
        }
        for origin, data in latest["airports"].items()
    }
    return aggregate, (latest["year"], latest["month"])


def _months_since(year: int, month: int, today: date | None = None) -> int:
    today = today or date.today()
    return (today.year - year) * 12 + (today.month - month)


def _get_monthly_aggregate_cache_with_period() -> (
    tuple[dict[str, AirportMonthlyAggregate], tuple[int, int]]
):
    global _monthly_aggregate_cache
    if _monthly_aggregate_cache is None:
        snapshot = _load_snapshot_cache()
        if snapshot is not None:
            _monthly_aggregate_cache = snapshot
        else:
            year, month = resolve_latest_available_month()
            _monthly_aggregate_cache = (
                download_and_aggregate(year, month),
                (year, month),
            )

        _, (cached_year, cached_month) = _monthly_aggregate_cache
        age_months = _months_since(cached_year, cached_month)
        if age_months > STALE_DATA_WARNING_MONTHS:
            logger.warning(
                "BTS on-time-performance data is %d months old (%d-%02d) -- "
                "consider re-running scripts/build_otp_snapshots.py for a fresher snapshot.",
                age_months,
                cached_year,
                cached_month,
            )
    return _monthly_aggregate_cache


def get_data_age_months() -> int:
    """How many months old the cached OTP data is, for surfacing as a caveat."""
    _, (year, month) = _get_monthly_aggregate_cache_with_period()
    return _months_since(year, month)


def is_monthly_aggregate_cache_warm() -> bool:
    return _monthly_aggregate_cache is not None
