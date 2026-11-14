import pytest

from airport_investment_agent.models.errors import InvalidAirportSelectionError
from airport_investment_agent.models.models import AirportTraffic
from airport_investment_agent.tools.scoring import (
    GROWTH_SCORE_CEILING_RATE,
    GROWTH_SCORE_FLOOR_RATE,
    UNMET_DEMAND_DRIVER_THRESHOLD,
    _bounded_growth_score,
    compare_airports,
    compute_demand_pressure,
    compute_unmet_demand_score,
)


def make_traffic(
    iata_code: str,
    passengers: int,
    departures: int,
    seats: int,
    growth_rate: float = 0.0,
    completion_rate: float | None = None,
) -> AirportTraffic:
    return AirportTraffic(
        iata_code=iata_code,
        passengers=passengers,
        departures=departures,
        seats=seats,
        load_factor=passengers / seats,
        passengers_per_departure=passengers / departures,
        growth_rate=growth_rate,
        completion_rate=completion_rate,
        caveats=["test fixture"],
    )


def test_busiest_airport_scores_a_perfect_volume_of_one():
    busiest = make_traffic("BUSY", passengers=100, departures=10, seats=110)
    score = compute_demand_pressure(
        busiest,
        max_passengers=100,
        max_load_factor=busiest.load_factor,
        min_growth=0.0,
        max_growth=0.0,
    )
    assert score.volume_score == 1.0


def test_scores_never_exceed_the_zero_to_one_range():
    traffic = make_traffic("ANY", passengers=50, departures=10, seats=60)
    score = compute_demand_pressure(
        traffic,
        max_passengers=100,
        max_load_factor=1.0,
        min_growth=-0.1,
        max_growth=0.1,
    )
    assert 0.0 <= score.volume_score <= 1.0
    assert 0.0 <= score.efficiency_score <= 1.0
    assert 0.0 <= score.growth_score <= 1.0
    assert 0.0 <= score.demand_pressure_proxy <= 1.0


def test_growth_score_is_neutral_when_the_whole_set_grew_identically():
    traffic = make_traffic(
        "ANY", passengers=50, departures=10, seats=60, growth_rate=0.03
    )
    score = compute_demand_pressure(
        traffic,
        max_passengers=100,
        max_load_factor=1.0,
        min_growth=0.03,
        max_growth=0.03,
    )
    assert score.growth_score == 0.5


def test_compare_airports_rejects_fewer_than_two_airports() -> None:
    with pytest.raises(InvalidAirportSelectionError):
        compare_airports(["JFK"])


def test_compare_airports_accepts_more_than_five_airports(monkeypatch) -> None:
    """Regression test for the removed upper limit: compare_airports used
    to reject more than 5 codes; it must not anymore."""
    from airport_investment_agent.tools import scoring

    traffic_by_code = {
        code: make_traffic(code, passengers=100 * (i + 1), departures=10, seats=200 * (i + 1))
        for i, code in enumerate(["A", "B", "C", "D", "E", "F"])
    }
    monkeypatch.setattr(
        scoring, "get_airport_traffic", lambda code: traffic_by_code[code]
    )

    ranked = compare_airports(list(traffic_by_code))

    assert len(ranked) == 6
    assert {r.traffic.iata_code for r in ranked} == set(traffic_by_code)


def test_bounded_growth_score_clips_at_floor_and_ceiling():
    assert _bounded_growth_score(GROWTH_SCORE_FLOOR_RATE - 0.05) == 0.0
    assert _bounded_growth_score(GROWTH_SCORE_CEILING_RATE + 0.05) == 1.0


def test_bounded_growth_score_scales_linearly_inside_the_band():
    midpoint = (GROWTH_SCORE_FLOOR_RATE + GROWTH_SCORE_CEILING_RATE) / 2
    assert _bounded_growth_score(midpoint) == pytest.approx(0.5)


def test_compute_unmet_demand_score_components_are_bounded():
    traffic = make_traffic(
        "ANY", passengers=50, departures=10, seats=60, growth_rate=0.2
    )
    score = compute_unmet_demand_score(
        traffic, max_passengers=100, max_load_factor=1.0, congestion_score=0.5
    )
    assert 0.0 <= score.volume_score <= 1.0
    assert 0.0 <= score.load_pressure_score <= 1.0
    assert 0.0 <= score.growth_vs_fixed_band <= 1.0
    assert 0.0 <= score.congestion_score <= 1.0
    assert 0.0 <= score.unmet_demand_score <= 1.0


def test_compute_unmet_demand_score_clips_out_of_range_congestion_score():
    traffic = make_traffic("ANY", passengers=50, departures=10, seats=60)

    high = compute_unmet_demand_score(
        traffic, max_passengers=100, max_load_factor=1.0, congestion_score=1.5
    )
    assert high.congestion_score == 1.0

    low = compute_unmet_demand_score(
        traffic, max_passengers=100, max_load_factor=1.0, congestion_score=-0.5
    )
    assert low.congestion_score == 0.0


def test_compute_unmet_demand_score_lists_all_drivers_when_everything_is_maxed():
    traffic = make_traffic(
        "MAXED",
        passengers=100,
        departures=10,
        seats=100,
        growth_rate=GROWTH_SCORE_CEILING_RATE,
    )
    score = compute_unmet_demand_score(
        traffic, max_passengers=100, max_load_factor=1.0, congestion_score=1.0
    )
    assert len(score.drivers) == 4
    assert all(
        component >= UNMET_DEMAND_DRIVER_THRESHOLD
        for component in [
            score.volume_score,
            score.load_pressure_score,
            score.growth_vs_fixed_band,
            score.congestion_score,
        ]
    )


def test_compute_unmet_demand_score_no_drivers_when_everything_is_low():
    traffic = make_traffic(
        "QUIET", passengers=1, departures=10, seats=1000, growth_rate=-0.5
    )
    score = compute_unmet_demand_score(
        traffic, max_passengers=100, max_load_factor=1.0, congestion_score=0.0
    )
    assert score.drivers == []
