"""Long-haul flight-share KPI for a single U.S. airport.

Reuses the shared monthly BTS on-time-performance aggregate from
clients/bts_otp.py -- calling this never triggers a second download of
that (large, throttled) source file.
"""

from typing import Any

from airport_investment_agent.clients.bts_otp import LONG_HAUL_DISTANCE_MILES
from airport_investment_agent.models import LongHaulPercentage
from airport_investment_agent.tools.otp_kpis import (
    get_completion_data_period,
    get_long_haul_counts,
    get_long_haul_percentage,
)


def long_haul_percentage(iata_code: str) -> dict[str, Any]:
    """Percentage of an airport's scheduled flights this month that are
    long-haul (Distance >= 2300 statute miles), with raw counts and the
    source month/year.

    Args:
        iata_code: The airport's 3-letter IATA code, e.g. "JFK", "LAX", "ORD".
    """
    iata_code = iata_code.upper()
    percentage = get_long_haul_percentage(iata_code)
    long_haul_count, scheduled_count = get_long_haul_counts(iata_code)
    period_year, period_month = get_completion_data_period()

    return LongHaulPercentage(
        iata_code=iata_code,
        threshold_miles=int(LONG_HAUL_DISTANCE_MILES),
        long_haul_percentage=round(percentage, 2),
        long_haul_flight_count=long_haul_count,
        scheduled_flight_count=scheduled_count,
        data_period={"year": period_year, "month": period_month},
        summary=(
            f"{iata_code} has a long-haul share of {percentage:.1f}% this month "
            f"({long_haul_count:,} of {scheduled_count:,} scheduled flights "
            f"≥{int(LONG_HAUL_DISTANCE_MILES)} statute miles)."
        ),
        caveats=[
            f"Reflects one month's published schedule ({period_year}-"
            f"{period_month:02d}), not an annual average -- long-haul share "
            "can vary seasonally.",
            f"Long-haul cutoff ({int(LONG_HAUL_DISTANCE_MILES)} statute miles) is "
            "a disclosed, round-number judgment call, not a BTS-defined category.",
        ],
    ).model_dump()
