from airport_investment_agent.models import (
    AirportScore,
    AirportTraffic,
    InvalidAirportSelectionError,
    RankedAirport,
    UnmetDemandScore,
)
from airport_investment_agent.tools.traffic import get_airport_traffic

VOLUME_WEIGHT = 0.35
EFFICIENCY_WEIGHT = 0.25
GROWTH_WEIGHT = 0.25
DEMAND_PRESSURE_WEIGHT = 0.15

DEMAND_PRESSURE_VOLUME_SHARE = 0.5
DEMAND_PRESSURE_EFFICIENCY_SHARE = 0.5

# --- estimate_unmet_demand -------------------------------------------------

UNMET_DEMAND_VOLUME_WEIGHT = 0.25
UNMET_DEMAND_LOAD_PRESSURE_WEIGHT = 0.25
UNMET_DEMAND_GROWTH_WEIGHT = 0.25
UNMET_DEMAND_CONGESTION_WEIGHT = 0.25

# Fixed reference band for a single airport's growth_rate -> 0-1 score. No
# nationwide-max-growth lookup exists anywhere in this codebase (building
# one honestly would mean pulling two years of BTS T-100 data for every
# U.S. airport), so this is a disclosed, fixed judgment call instead.
GROWTH_SCORE_FLOOR_RATE = 0.0
GROWTH_SCORE_CEILING_RATE = 0.10

UNMET_DEMAND_DRIVER_THRESHOLD = 0.6


def compute_demand_pressure(
    record: AirportTraffic,
    max_passengers: float,
    max_load_factor: float,
    min_growth: float,
    max_growth: float,
) -> AirportScore:
    volume_score = min(record.passengers / max_passengers, 1.0)
    efficiency_score = min(record.load_factor / max_load_factor, 1.0)

    if max_growth == min_growth:
        growth_score = 0.5
    else:
        # No clamp needed (unlike _bounded_growth_score below): min_growth/
        # max_growth are always derived from this same comparison set, so
        # record.growth_rate is guaranteed to fall inside [min_growth,
        # max_growth] and the result is always exactly in [0, 1] already.
        growth_score = (record.growth_rate - min_growth) / (max_growth - min_growth)

    # Deliberately excludes growth_score: this proxy represents current
    # capacity utilization -- how full/busy the airport is right now, not
    # its trajectory. Growth already gets its own explicit GROWTH_WEIGHT in
    # compare_airports's top-level investment_score; folding it in here too
    # would double-count it, giving growth more real influence than the
    # stated composite weights suggest.
    demand_pressure_proxy = (DEMAND_PRESSURE_VOLUME_SHARE * volume_score) + (
        DEMAND_PRESSURE_EFFICIENCY_SHARE * efficiency_score
    )
    return AirportScore(
        iata_code=record.iata_code,
        volume_score=volume_score,
        efficiency_score=efficiency_score,
        growth_score=growth_score,
        demand_pressure_proxy=demand_pressure_proxy,
    )


def compare_airports(
    codes: list[str],
    max_passengers: float | None = None,
    max_load_factor: float | None = None,
) -> list[RankedAirport]:
    if len(codes) < 2:
        raise InvalidAirportSelectionError(
            "You must select at least 2 airports for comparison."
        )
    records = [get_airport_traffic(code) for code in codes]

    if max_passengers is None:
        max_passengers = max(r.passengers for r in records)
    if max_load_factor is None:
        max_load_factor = max(r.load_factor for r in records)

    min_growth = min(r.growth_rate for r in records)
    max_growth = max(r.growth_rate for r in records)

    scores = [
        compute_demand_pressure(
            record, max_passengers, max_load_factor, min_growth, max_growth
        )
        for record in records
    ]
    temp_list = []
    for record, score in zip(records, scores):
        investment_score = (
            VOLUME_WEIGHT * score.volume_score
            + EFFICIENCY_WEIGHT * score.efficiency_score
            + GROWTH_WEIGHT * score.growth_score
            + DEMAND_PRESSURE_WEIGHT * score.demand_pressure_proxy
        )
        temp_list.append((record, score, investment_score))

    temp_list.sort(key=lambda x: x[2], reverse=True)
    ranked_airports = [
        RankedAirport(
            traffic=record, score=score, investment_score=investment_score, rank=rank
        )
        for rank, (record, score, investment_score) in enumerate(temp_list, start=1)
    ]
    return ranked_airports


def _bounded_growth_score(growth_rate: float) -> float:
    if growth_rate <= GROWTH_SCORE_FLOOR_RATE:
        return 0.0
    if growth_rate >= GROWTH_SCORE_CEILING_RATE:
        return 1.0
    return (growth_rate - GROWTH_SCORE_FLOOR_RATE) / (
        GROWTH_SCORE_CEILING_RATE - GROWTH_SCORE_FLOOR_RATE
    )


def compute_unmet_demand_score(
    record: AirportTraffic,
    max_passengers: float,
    max_load_factor: float,
    congestion_score: float,
) -> UnmetDemandScore:
    """Pure computation behind explain.estimate_unmet_demand - no I/O here,
    matching compute_demand_pressure's shape."""
    volume_score = min(record.passengers / max_passengers, 1.0)
    load_pressure_score = min(record.load_factor / max_load_factor, 1.0)
    growth_vs_fixed_band = _bounded_growth_score(record.growth_rate)
    bounded_congestion_score = min(max(congestion_score, 0.0), 1.0)

    unmet_demand_score = (
        UNMET_DEMAND_VOLUME_WEIGHT * volume_score
        + UNMET_DEMAND_LOAD_PRESSURE_WEIGHT * load_pressure_score
        + UNMET_DEMAND_GROWTH_WEIGHT * growth_vs_fixed_band
        + UNMET_DEMAND_CONGESTION_WEIGHT * bounded_congestion_score
    )

    candidate_drivers = [
        (volume_score, "high passenger volume"),
        (load_pressure_score, "high passengers per departure / load pressure"),
        (growth_vs_fixed_band, "strong growth"),
        (bounded_congestion_score, "high congestion relative to peers"),
    ]
    drivers = [
        label
        for score, label in sorted(
            candidate_drivers, key=lambda item: item[0], reverse=True
        )
        if score >= UNMET_DEMAND_DRIVER_THRESHOLD
    ]

    return UnmetDemandScore(
        iata_code=record.iata_code,
        volume_score=volume_score,
        load_pressure_score=load_pressure_score,
        growth_vs_fixed_band=growth_vs_fixed_band,
        congestion_score=bounded_congestion_score,
        unmet_demand_score=unmet_demand_score,
        drivers=drivers,
    )
