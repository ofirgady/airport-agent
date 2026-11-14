from agents import function_tool

from airport_investment_agent.tools.traffic import get_airport_traffic
from airport_investment_agent.tools.scoring import compare_airports
from airport_investment_agent.tools.explain import (
    compare_unmet_demand,
    estimate_unmet_demand,
)
from airport_investment_agent.tools.regional import (
    rank_airports_by_region,
    rank_airports_nationwide,
)
from airport_investment_agent.tools.congestion import compare_congestion
from airport_investment_agent.tools.longhaul import long_haul_percentage
from airport_investment_agent.tools.tool_errors import describe_tool_error


@function_tool(failure_error_function=describe_tool_error)
def get_airport_traffic_tool(iata_code: str) -> dict:
    """Look up real flight-traffic statistics for a single U.S. airport.

    Args:
        iata_code: The airport's 3-letter IATA code, e.g. "JFK", "LAX", "ORD".
    """
    traffic = get_airport_traffic(iata_code)
    return traffic.model_dump()


@function_tool(failure_error_function=describe_tool_error)
def compare_airports_tool(codes: list[str]) -> list[dict]:
    """Compare 2 or more U.S. airports and rank them by investment potential.

    Args:
        codes: A list of 2 or more airport IATA codes to compare, e.g. ["JFK", "LAX"].
    """
    ranked = compare_airports(codes)
    return [
        {
            "rank": r.rank,
            "iata_code": r.traffic.iata_code,
            "investment_score": round(r.investment_score, 4),
            "volume_score": round(r.score.volume_score, 4),
            "efficiency_score": round(r.score.efficiency_score, 4),
            "growth_score": round(r.score.growth_score, 4),
            "demand_pressure_proxy": round(r.score.demand_pressure_proxy, 4),
            "traffic": r.traffic.model_dump(),
        }
        for r in ranked
    ]


@function_tool(failure_error_function=describe_tool_error)
def estimate_unmet_demand_tool(iata_code: str) -> dict:
    """Estimate unmet demand / capacity strain at a single U.S. airport as a
    0-1 score with named drivers, disclosed as an inferred proxy.

    Args:
        iata_code: The airport's 3-letter IATA code, e.g. "JFK", "LAX", "ORD".
    """
    return estimate_unmet_demand(iata_code)


@function_tool(failure_error_function=describe_tool_error)
def compare_unmet_demand_tool(airport_a: str, airport_b: str) -> dict:
    """Compare unmet-demand / capacity-strain proxy scores between exactly
    two U.S. airports in one atomic call -- fails clearly if either airport
    has no data rather than letting a comparison be built from one real
    result and one failure.

    Args:
        airport_a: The first airport's 3-letter IATA code, e.g. "JFK".
        airport_b: The second airport's 3-letter IATA code, e.g. "LAX".
    """
    return compare_unmet_demand(airport_a, airport_b)


@function_tool(failure_error_function=describe_tool_error)
def rank_airports_by_region_tool(region_name: str) -> list[dict]:
    """Rank U.S. airports within a named region by investment potential,
    scored relative to the other airports in that region only.

    Args:
        region_name: e.g. "New England", "Pacific Northwest", "Texas",
            "Southeast", or "Mid-Atlantic".
    """
    return rank_airports_by_region(region_name)


@function_tool(failure_error_function=describe_tool_error)
def rank_airports_nationwide_tool() -> list[dict]:
    """Rank major U.S. airports nationally by investment potential, scored
    against one consistent nationwide peer set (the curated union of all
    five regions' airports). Use for "best airport in the US"/nationwide
    questions with no named scope -- do not answer these by comparing
    separate rank_airports_by_region_tool calls, whose scores aren't
    comparable across regions.
    """
    return rank_airports_nationwide()


@function_tool(failure_error_function=describe_tool_error)
def compare_congestion_tool(airport_a: str, airport_b: str) -> dict:
    """Compare congestion (Departure Delay Index) at two U.S. airports.

    Args:
        airport_a: The first airport's 3-letter IATA code, e.g. "JFK".
        airport_b: The second airport's 3-letter IATA code, e.g. "LAX".
    """
    return compare_congestion(airport_a, airport_b)


@function_tool(failure_error_function=describe_tool_error)
def long_haul_percentage_tool(iata_code: str) -> dict:
    """Percentage of an airport's scheduled flights this month that are
    long-haul (>= 2300 statute miles), with raw counts and source month/year.

    Args:
        iata_code: The airport's 3-letter IATA code, e.g. "JFK", "LAX", "ORD".
    """
    return long_haul_percentage(iata_code)
