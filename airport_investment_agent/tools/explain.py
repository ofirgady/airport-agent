from typing import Any

from airport_investment_agent.clients.bts_traffic import (
    get_nationwide_max_load_factor,
    get_nationwide_max_passengers,
)
from airport_investment_agent.models import RankedAirport
from airport_investment_agent.tools.otp_kpis import (
    get_completion_data_period,
    get_congestion_score,
)
from airport_investment_agent.tools.scoring import (
    GROWTH_SCORE_CEILING_RATE,
    GROWTH_SCORE_FLOOR_RATE,
    UNMET_DEMAND_DRIVER_THRESHOLD,
    compute_unmet_demand_score,
)
from airport_investment_agent.tools.traffic import get_airport_traffic
from airport_investment_agent.utils import merge_unique


def estimate_unmet_demand(iata_code: str) -> dict[str, Any]:
    """Estimate unmet demand / capacity strain at a single U.S. airport.

    Returns a dict (not a string) so every number reaches the caller as a
    distinct, quotable field, plus a ready-made `narrative` string.
    """
    traffic = get_airport_traffic(iata_code)
    max_passengers = get_nationwide_max_passengers()
    max_load_factor = get_nationwide_max_load_factor()
    congestion_score = get_congestion_score(traffic.iata_code)
    period_year, period_month = get_completion_data_period()

    score = compute_unmet_demand_score(
        traffic, max_passengers, max_load_factor, congestion_score
    )

    driver_text = (
        "; ".join(score.drivers)
        if score.drivers
        else "no single factor stands out -- unmet demand looks broadly low "
        "across all four inputs"
    )

    narrative_lines = [
        f"Unmet-demand estimate for {traffic.iata_code}: {score.unmet_demand_score:.2f} "
        "on a 0-1 scale. This is an inferred proxy, not a direct measurement -- "
        "no public data source counts passengers who wanted to fly but could not "
        "get a seat.",
        f"Drivers: {driver_text}.",
        "",
        "Component scores (all normalized 0-1, all from real data, none invented):",
        f"- volume_score {score.volume_score:.2f}: passengers ({traffic.passengers:,}) "
        "relative to the busiest real U.S. commercial airport.",
        f"- load_pressure_score {score.load_pressure_score:.2f}: load factor "
        f"({traffic.load_factor:.1%}) relative to the busiest airport's load factor.",
        f"- growth_vs_fixed_band {score.growth_vs_fixed_band:.2f}: "
        f"year-over-year passenger growth ({traffic.growth_rate:+.1%}) against a "
        "fixed reference band, not a nationwide comparison.",
        f"- congestion_score {score.congestion_score:.2f}: Departure-Delay-Index-based "
        f"congestion, normalized against nationwide peers for {period_year}-{period_month:02d}.",
    ]
    narrative_lines.extend(f"- {caveat}" for caveat in traffic.caveats)
    narrative = "\n".join(narrative_lines)

    caveats = [
        "unmet_demand_score is an inferred proxy, not a measurement: no public "
        "data source counts passengers who wanted to fly but could not get a seat.",
        "Equal (25/25/25/25) weighting across volume, load pressure, growth, and "
        "congestion is a disclosed simplification, not an empirically validated weighting.",
        f"growth_vs_fixed_band uses a fixed {GROWTH_SCORE_FLOOR_RATE:.0%}-"
        f"{GROWTH_SCORE_CEILING_RATE:.0%} reference band, not a nationwide comparison -- "
        "distinct from compare_airports_tool's growth_score, which IS comparison-set-relative.",
        "load_pressure_score is based on load_factor; passengers_per_departure is "
        "reported for context but is not independently normalized.",
        f"congestion_score reflects one month's BTS on-time-performance data "
        f"({period_year}-{period_month:02d}) and can reflect weather, staffing, "
        "or scheduling rather than physical capacity strain.",
        f"drivers only lists a factor when its score is >= {UNMET_DEMAND_DRIVER_THRESHOLD} "
        "-- an empty list is a legitimate result, not an error.",
    ]
    caveats = merge_unique(caveats, traffic.caveats)

    return {
        "iata_code": traffic.iata_code,
        "unmet_demand_score": round(score.unmet_demand_score, 4),
        "is_proxy": True,
        "drivers": score.drivers,
        "components": {
            "volume_score": round(score.volume_score, 4),
            "load_pressure_score": round(score.load_pressure_score, 4),
            "growth_vs_fixed_band": round(score.growth_vs_fixed_band, 4),
            "congestion_score": round(score.congestion_score, 4),
        },
        "supporting_data": {
            "passengers": traffic.passengers,
            "passengers_per_departure": round(traffic.passengers_per_departure, 2),
            "load_factor": round(traffic.load_factor, 4),
            "growth_rate": round(traffic.growth_rate, 4),
            "data_period": {"year": period_year, "month": period_month},
        },
        "narrative": narrative,
        "caveats": caveats,
    }


def compare_unmet_demand(airport_a: str, airport_b: str) -> dict[str, Any]:
    """Compare unmet-demand proxy scores at two U.S. airports, atomically --
    fails as a whole if either airport has no data, rather than leaving the
    caller to reconcile two independent single-airport results itself (this
    is exactly what estimate_unmet_demand_tool called twice let the LLM do,
    producing a comparison with only one real side).
    """
    if airport_a.upper() == airport_b.upper():
        raise ValueError("compare_unmet_demand requires two different airports.")

    traffic_a = get_airport_traffic(airport_a)
    traffic_b = get_airport_traffic(airport_b)

    max_passengers = get_nationwide_max_passengers()
    max_load_factor = get_nationwide_max_load_factor()
    congestion_score_a = get_congestion_score(traffic_a.iata_code)
    congestion_score_b = get_congestion_score(traffic_b.iata_code)
    period_year, period_month = get_completion_data_period()

    score_a = compute_unmet_demand_score(
        traffic_a, max_passengers, max_load_factor, congestion_score_a
    )
    score_b = compute_unmet_demand_score(
        traffic_b, max_passengers, max_load_factor, congestion_score_b
    )

    if score_a.unmet_demand_score == score_b.unmet_demand_score:
        higher = None
        explanation = (
            f"{traffic_a.iata_code} and {traffic_b.iata_code} show equal "
            f"unmet-demand proxy scores: both {score_a.unmet_demand_score:.2f} "
            "on a 0-1 scale."
        )
    else:
        if score_a.unmet_demand_score > score_b.unmet_demand_score:
            higher, higher_score = traffic_a.iata_code, score_a.unmet_demand_score
            lower, lower_score = traffic_b.iata_code, score_b.unmet_demand_score
        else:
            higher, higher_score = traffic_b.iata_code, score_b.unmet_demand_score
            lower, lower_score = traffic_a.iata_code, score_a.unmet_demand_score
        explanation = (
            f"{higher} has the higher unmet-demand proxy: {higher_score:.2f} vs "
            f"{lower}'s {lower_score:.2f} (0-1 scale, an inferred proxy, not a "
            "direct measurement)."
        )

    caveats = [
        "unmet_demand_score is an inferred proxy, not a measurement: no public "
        "data source counts passengers who wanted to fly but could not get a seat.",
        "Equal (25/25/25/25) weighting across volume, load pressure, growth, and "
        "congestion is a disclosed simplification, not an empirically validated weighting.",
        f"Both scores reflect the {period_year}-{period_month:02d} BTS "
        "on-time-performance file for their congestion component.",
    ]
    caveats = merge_unique(caveats, traffic_a.caveats, traffic_b.caveats)

    return {
        "data_period": {"year": period_year, "month": period_month},
        "airport_a": {
            "iata_code": traffic_a.iata_code,
            "unmet_demand_score": round(score_a.unmet_demand_score, 4),
            "drivers": score_a.drivers,
        },
        "airport_b": {
            "iata_code": traffic_b.iata_code,
            "unmet_demand_score": round(score_b.unmet_demand_score, 4),
            "drivers": score_b.drivers,
        },
        "higher_unmet_demand": higher,
        "explanation": explanation,
        "caveats": caveats,
    }


def explain_ranking(ranked: list[RankedAirport]) -> str:
    lines: list[str] = []

    top = ranked[0]
    lines.append(
        f"Top recommendation: {top.traffic.iata_code} "
        f"(investment score {top.investment_score:.2f})."
    )
    lines.append("")

    for airport in ranked:
        lines.append(
            f"{airport.rank}. {airport.traffic.iata_code} - "
            f"investment score {airport.investment_score:.2f} "
            f"(volume {airport.score.volume_score:.2f}, "
            f"efficiency {airport.score.efficiency_score:.2f}, "
            f"growth {airport.traffic.growth_rate:+.1%})"
        )

    all_caveats = merge_unique(*(airport.traffic.caveats for airport in ranked))

    if all_caveats:
        lines.append("")
        lines.append("Caveats: " + "; ".join(all_caveats))

    return "\n".join(lines)
