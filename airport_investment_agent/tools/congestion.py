"""Congestion comparison between two U.S. airports, via the Departure
Delay Index (DDI).

Reuses tools/traffic.py's get_airport_traffic and
tools/otp_kpis.py's get_congestion_score/get_departure_delay_index
-- both read the single process-lifetime cache built by
clients/bts_otp.py, so comparing two airports never triggers a second
download.
"""

from typing import Any

from airport_investment_agent.models import AirportTraffic
from airport_investment_agent.tools.otp_kpis import (
    get_completion_data_period,
    get_congestion_score,
    get_delayed_departure_rate_pct,
    get_departure_delay_index,
)
from airport_investment_agent.tools.traffic import get_airport_traffic
from airport_investment_agent.utils import merge_unique


def _simple_congestion_proxy(
    traffic: AirportTraffic,
    max_passengers: float,
    max_passengers_per_departure: float,
) -> float:
    """Context-only fallback: volume_score * passengers_per_departure_score,
    normalized against whichever of the two compared airports is
    busier/fuller. Guarded against a zero denominator."""
    volume_score = (
        min(traffic.passengers / max_passengers, 1.0) if max_passengers else 0.0
    )
    ppd_score = (
        min(traffic.passengers_per_departure / max_passengers_per_departure, 1.0)
        if max_passengers_per_departure
        else 0.0
    )
    return volume_score * ppd_score


def _describe_more_congested(
    iata_code_a: str,
    ddi_a: float,
    iata_code_b: str,
    ddi_b: float,
    period_year: int,
    period_month: int,
) -> tuple[str | None, str]:
    period = f"{period_year}-{period_month:02d}"
    if ddi_a == ddi_b:
        return None, (
            f"{iata_code_a} and {iata_code_b} are equally congested by DDI: "
            f"both score {ddi_a:.1f} ({period})."
        )

    if ddi_a > ddi_b:
        winner, winner_ddi, loser, loser_ddi = iata_code_a, ddi_a, iata_code_b, ddi_b
    else:
        winner, winner_ddi, loser, loser_ddi = iata_code_b, ddi_b, iata_code_a, ddi_a

    explanation = (
        f"{winner} is more congested than {loser}: Departure Delay Index "
        f"{winner_ddi:.1f} vs {loser_ddi:.1f} (both from the {period} BTS "
        "on-time-performance file, 0-100 scale)."
    )
    return winner, explanation


def compare_congestion(airport_a: str, airport_b: str) -> dict[str, Any]:
    """Compare congestion at two U.S. airports using the Departure Delay
    Index: departure_delay_rate_pct*0.6 + (avg delay, capped at 60 min,
    as a %)*0.4, on a 0-100 scale.

    "More congested" means "worse departure delay performance this month,"
    not "operating at or beyond physical throughput capacity" -- weather,
    staffing, and scheduling can all drive DDI independent of true
    capacity. See caveats.
    """
    if airport_a.upper() == airport_b.upper():
        raise ValueError("compare_congestion requires two different airports.")

    traffic_a = get_airport_traffic(airport_a)
    traffic_b = get_airport_traffic(airport_b)

    ddi_a = get_departure_delay_index(traffic_a.iata_code)
    ddi_b = get_departure_delay_index(traffic_b.iata_code)
    delayed_rate_pct_a = get_delayed_departure_rate_pct(traffic_a.iata_code)
    delayed_rate_pct_b = get_delayed_departure_rate_pct(traffic_b.iata_code)
    congestion_score_a = get_congestion_score(traffic_a.iata_code)
    congestion_score_b = get_congestion_score(traffic_b.iata_code)
    period_year, period_month = get_completion_data_period()

    max_passengers = max(traffic_a.passengers, traffic_b.passengers)
    max_ppd = max(
        traffic_a.passengers_per_departure, traffic_b.passengers_per_departure
    )
    proxy_a = _simple_congestion_proxy(traffic_a, max_passengers, max_ppd)
    proxy_b = _simple_congestion_proxy(traffic_b, max_passengers, max_ppd)

    more_congested, explanation = _describe_more_congested(
        traffic_a.iata_code,
        ddi_a,
        traffic_b.iata_code,
        ddi_b,
        period_year,
        period_month,
    )

    if proxy_a != proxy_b:
        higher_proxy, lower_proxy = max(proxy_a, proxy_b), min(proxy_a, proxy_b)
        proxy_leader = traffic_a.iata_code if proxy_a > proxy_b else traffic_b.iata_code
        if proxy_leader != more_congested:
            explanation += (
                f" Note: the simpler volume x passengers-per-departure proxy "
                f"instead ranks {proxy_leader} higher ({higher_proxy:.2f} vs {lower_proxy:.2f})."
            )

    caveats = [
        "departure_delay_index (DDI) is this project's own composite of departure "
        "delay rate and severity -- not an industry-standard metric (no FAA/DOT/BTS "
        "metric by this name exists) and not a direct measurement of runway, gate, "
        "or airspace capacity. delayed_departure_rate_pct alone is DOT's own "
        "standard on-time definition (14 CFR Part 234: departures 15+ minutes "
        "late), included so DDI can be cross-checked against that published "
        "figure directly.",
        "congestion_score normalizes DDI against the nationwide 5th-95th percentile "
        f"band for {period_year}-{period_month:02d}.",
        "simple_congestion_proxy is included only for context and is normalized "
        "against whichever of the two compared airports is busier/fuller, not a "
        "nationwide reference.",
    ]
    caveats = merge_unique(caveats, traffic_a.caveats, traffic_b.caveats)

    return {
        "data_period": {"year": period_year, "month": period_month},
        "airport_a": {
            "iata_code": traffic_a.iata_code,
            "departure_delay_index": round(ddi_a, 2),
            "delayed_departure_rate_pct": round(delayed_rate_pct_a, 2),
            "congestion_score": round(congestion_score_a, 4),
            "simple_congestion_proxy": round(proxy_a, 4),
            "passengers": traffic_a.passengers,
            "passengers_per_departure": round(traffic_a.passengers_per_departure, 2),
        },
        "airport_b": {
            "iata_code": traffic_b.iata_code,
            "departure_delay_index": round(ddi_b, 2),
            "delayed_departure_rate_pct": round(delayed_rate_pct_b, 2),
            "congestion_score": round(congestion_score_b, 4),
            "simple_congestion_proxy": round(proxy_b, 4),
            "passengers": traffic_b.passengers,
            "passengers_per_departure": round(traffic_b.passengers_per_departure, 2),
        },
        "more_congested": more_congested,
        "explanation": explanation,
        "caveats": caveats,
    }
