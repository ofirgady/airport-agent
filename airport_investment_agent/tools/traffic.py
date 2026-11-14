from airport_investment_agent.models import (
    AirportDataError,
    AirportTraffic,
    UnknownAirportError,
)
from airport_investment_agent.clients.bts_otp import STALE_DATA_WARNING_MONTHS
from airport_investment_agent.clients.bts_traffic import _fetch_airport_rows
from airport_investment_agent.tools.otp_kpis import (
    get_completion_data_age_months,
    get_completion_data_period,
    get_completion_rate,
)


def get_airport_traffic(iata_code: str) -> AirportTraffic:
    iata_code = iata_code.upper()
    rows = _fetch_airport_rows(iata_code)

    if not rows:
        raise UnknownAirportError(f"No BTS traffic data found for '{iata_code}'.")

    complete_year_rows = [row for row in rows if row["year"].isdigit()]
    if not complete_year_rows:
        raise AirportDataError(
            f"BTS returned data for '{iata_code}', but no complete calendar year was found."
        )

    current = complete_year_rows[0]
    passengers = int(current["total_passengers"])
    departures = int(current["total_departures"])
    seats = int(current["total_seats"])
    load_factor = float(current["total_load_factor"]) / 100
    passengers_per_departure = float(current["total_passengers_flight"])

    caveats = [
        f"BTS T-100 data, year {current['year']}",
        "load_factor is BTS's own published monthly load factor, seat-mile "
        "weighted across the year; passengers_per_departure is the year's "
        "passengers divided by its departures.",
    ]

    if len(complete_year_rows) >= 2:
        previous = complete_year_rows[1]
        previous_passengers = int(previous["total_passengers"])
        growth_rate = (passengers - previous_passengers) / previous_passengers
        caveats.append(f"Growth rate compares {current['year']} vs {previous['year']}")
    else:
        growth_rate = 0.0
        caveats.append(
            "Only one complete year available - growth rate defaulted to 0.0"
        )

    try:
        completion_rate = get_completion_rate(iata_code)
        period_year, period_month = get_completion_data_period()
        caveats.append(
            f"Completion rate from BTS On-Time Performance data, {period_year}-{period_month:02d}"
        )
        age_months = get_completion_data_age_months()
        if age_months > STALE_DATA_WARNING_MONTHS:
            caveats.append(
                f"This on-time-performance data is {age_months} months old -- "
                "consider re-running scripts/build_otp_snapshots.py for a fresher snapshot."
            )
    except AirportDataError as error:
        completion_rate = None
        caveats.append(f"Completion rate unavailable this time: {error}")

    return AirportTraffic(
        iata_code=iata_code,
        passengers=passengers,
        departures=departures,
        seats=seats,
        load_factor=load_factor,
        passengers_per_departure=passengers_per_departure,
        growth_rate=growth_rate,
        completion_rate=completion_rate,
        caveats=caveats,
    )
