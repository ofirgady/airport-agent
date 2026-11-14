"""KPI readers over the BTS monthly On-Time Performance aggregate:
completion rate, departure-delay-index (DDI) / congestion, taxi-out, and
long-haul-share.

Pure computation over the cache built by clients/bts_otp.py -- no network
or file I/O happens in this module. DDI and taxi-out use DEPARTURE-side
fields (DepDelayMinutes, TaxiOut); completion and long-haul use
Cancelled/Distance, all aggregated once upstream in the client.
"""

import functools

from airport_investment_agent.clients.bts_otp import (
    AirportMonthlyAggregate,
    _get_monthly_aggregate_cache_with_period,
    get_data_age_months,
)
from airport_investment_agent.models.errors import CompletionDataUnavailableError

# This project's own composite weights for blending delay-rate and severity
# into one 0-100 DDI number -- not an industry-standard split; see
# compute_ddi's docstring. Only the underlying 15-minute delayed-departure
# threshold (applied in clients/bts_otp.py via BTS's own DepDel15 field) is
# DOT's official definition (14 CFR Part 234).
DDI_DELAY_RATE_WEIGHT = 0.6
DDI_SEVERITY_WEIGHT = 0.4
DDI_SEVERITY_CAP_MINUTES = 60.0

# An airport needs at least this many non-cancelled departures in the month
# to count as a reference point for the nationwide DDI percentile band used
# by get_congestion_score (compare_congestion's standalone pairwise use
# case). Regional peer-set ranking does its own local normalization instead
# and doesn't use this constant.
MIN_DEPARTURES_FOR_DDI_REFERENCE = 100
DDI_LOW_PERCENTILE = 5.0
DDI_HIGH_PERCENTILE = 95.0


def get_completion_data_period() -> tuple[int, int]:
    _, period = _get_monthly_aggregate_cache_with_period()
    return period


def get_completion_data_age_months() -> int:
    return get_data_age_months()


def get_completion_rate(iata_code: str) -> float:
    cache, _ = _get_monthly_aggregate_cache_with_period()
    entry = cache.get(iata_code.upper())
    if not entry or entry["scheduled"] == 0:
        raise CompletionDataUnavailableError(
            f"No completion-rate data found for airport code '{iata_code.upper()}'."
        )
    return 1 - (entry["cancelled"] / entry["scheduled"])


def compute_delay_rate_pct(entry: AirportMonthlyAggregate) -> float:
    """DOT's own headline on-time-performance figure: % of non-cancelled
    departures delayed >=15 minutes (the 14 CFR Part 234 "on-time"
    threshold), independent of this module's own DDI severity blend --
    lets DDI be cross-checked directly against BTS's published percentage."""
    return 100 * entry["delayed_departures"] / entry["non_cancelled_departures"]


def compute_ddi(entry: AirportMonthlyAggregate) -> float:
    """Departure Delay Index, 0-100 scale (not 0-1 - this is the one KPI
    in this module that isn't, since it's a documented composite of a
    percentage and a capped-minutes ratio, both already 0-100).

    This composite (the 0.6/0.4 rate/severity blend and the 60-minute
    severity cap) is this project's own proxy, not an industry-standard
    metric -- no FAA/DOT/BTS metric by this name exists. Only its rate
    ingredient (delayed = >=15 min late) is DOT's own standard definition;
    see compute_delay_rate_pct."""
    delay_rate_pct = compute_delay_rate_pct(entry)
    avg_delay_min = (
        entry["delayed_departure_minutes_sum"] / entry["delayed_departures"]
        if entry["delayed_departures"]
        else 0.0
    )
    severity_pct = (
        min(avg_delay_min, DDI_SEVERITY_CAP_MINUTES) / DDI_SEVERITY_CAP_MINUTES * 100
    )
    return delay_rate_pct * DDI_DELAY_RATE_WEIGHT + severity_pct * DDI_SEVERITY_WEIGHT


def get_departure_delay_index(iata_code: str) -> float:
    cache, _ = _get_monthly_aggregate_cache_with_period()
    entry = cache.get(iata_code.upper())
    if not entry or entry["non_cancelled_departures"] == 0:
        raise CompletionDataUnavailableError(
            f"No departure-delay data found for airport code '{iata_code.upper()}'."
        )
    return compute_ddi(entry)


def get_delayed_departure_rate_pct(iata_code: str) -> float:
    cache, _ = _get_monthly_aggregate_cache_with_period()
    entry = cache.get(iata_code.upper())
    if not entry or entry["non_cancelled_departures"] == 0:
        raise CompletionDataUnavailableError(
            f"No departure-delay data found for airport code '{iata_code.upper()}'."
        )
    return compute_delay_rate_pct(entry)


def get_average_taxi_out_minutes(iata_code: str) -> float:
    cache, _ = _get_monthly_aggregate_cache_with_period()
    entry = cache.get(iata_code.upper())
    if not entry or entry["taxi_out_sample_count"] == 0:
        raise CompletionDataUnavailableError(
            f"No taxi-out data found for airport code '{iata_code.upper()}'."
        )
    return entry["taxi_out_minutes_sum"] / entry["taxi_out_sample_count"]


def get_long_haul_counts(iata_code: str) -> tuple[int, int]:
    cache, _ = _get_monthly_aggregate_cache_with_period()
    entry = cache.get(iata_code.upper())
    if not entry or entry["scheduled"] == 0:
        raise CompletionDataUnavailableError(
            f"No flight data found for airport code '{iata_code.upper()}'."
        )
    return entry["long_haul_count"], entry["scheduled"]


def get_long_haul_percentage(iata_code: str) -> float:
    """0-100, not 0-1."""
    long_haul_count, scheduled_count = get_long_haul_counts(iata_code)
    return 100 * (long_haul_count / scheduled_count)


def percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


@functools.lru_cache(maxsize=1)
def _get_ddi_reference_percentiles() -> tuple[float, float]:
    """Nationwide DDI reference band for get_congestion_score (the
    standalone pairwise tool). Regional ranking does NOT use this - it
    normalizes DDI within its own peer set instead."""
    cache, _ = _get_monthly_aggregate_cache_with_period()
    reference_ddis = sorted(
        compute_ddi(entry)
        for entry in cache.values()
        if entry["non_cancelled_departures"] >= MIN_DEPARTURES_FOR_DDI_REFERENCE
    )
    if len(reference_ddis) < 2:
        raise CompletionDataUnavailableError(
            "Not enough airports met the minimum-departures threshold to "
            "compute a nationwide DDI reference range."
        )
    return (
        percentile(reference_ddis, DDI_LOW_PERCENTILE),
        percentile(reference_ddis, DDI_HIGH_PERCENTILE),
    )


def get_congestion_score(iata_code: str) -> float:
    """0-1 congestion proxy: this airport's DDI, clipped and rescaled
    against the nationwide 5th-95th percentile DDI band. Not a direct
    measurement of runway/airspace capacity."""
    ddi = get_departure_delay_index(iata_code)
    low_reference, high_reference = _get_ddi_reference_percentiles()
    if high_reference == low_reference:
        return 0.5
    score = (ddi - low_reference) / (high_reference - low_reference)
    return min(max(score, 0.0), 1.0)
