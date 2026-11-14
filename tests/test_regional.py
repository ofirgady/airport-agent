from unittest.mock import patch

import pytest

from airport_investment_agent.models.errors import (
    UnknownAirportError,
    UnknownRegionError,
)
from airport_investment_agent.models.models import AirportTraffic
from airport_investment_agent.tools import regional


def _traffic(code, passengers, growth_rate):
    return AirportTraffic(
        iata_code=code,
        passengers=passengers,
        departures=passengers // 100 or 1,
        seats=passengers * 2,
        load_factor=0.8,
        passengers_per_departure=100.0,
        growth_rate=growth_rate,
        completion_rate=0.95,
        caveats=[f"{code} fixture"],
    )


def test_resolve_region_is_case_and_whitespace_insensitive():
    assert regional._resolve_region("  new england ") == "New England"
    assert regional._resolve_region("TEXAS") == "Texas"


def test_resolve_region_raises_for_unknown_region():
    with pytest.raises(UnknownRegionError) as exc_info:
        regional._resolve_region("Atlantis")
    assert "New England" in str(exc_info.value)


def test_percentile_rank_spreads_values_by_relative_rank():
    values = [10, 20, 30, 40]
    assert regional._percentile_rank(values, 10) == 0.0
    assert regional._percentile_rank(values, 40) == 1.0
    assert regional._percentile_rank(values, 20) == pytest.approx(1 / 3)


def test_percentile_rank_single_value_returns_midpoint():
    assert regional._percentile_rank([42], 42) == 0.5


def test_min_max_normalize_scales_between_zero_and_one():
    values = [10, 20, 30]
    assert regional._min_max_normalize(values, 10) == 0.0
    assert regional._min_max_normalize(values, 30) == 1.0
    assert regional._min_max_normalize(values, 20) == 0.5


def test_min_max_normalize_returns_midpoint_when_all_values_equal():
    assert regional._min_max_normalize([5, 5, 5], 5) == 0.5


@patch("airport_investment_agent.tools.regional.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.regional.get_completion_data_period")
@patch("airport_investment_agent.tools.regional.get_long_haul_percentage")
@patch("airport_investment_agent.tools.regional.get_average_taxi_out_minutes")
@patch("airport_investment_agent.tools.regional.get_departure_delay_index")
@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_by_region_orders_and_normalizes_within_peer_set(
    mock_traffic,
    mock_ddi,
    mock_taxi_out,
    mock_long_haul,
    mock_period,
    mock_delay_rate,
    monkeypatch,
):
    monkeypatch.setitem(regional.REGION_AIRPORTS, "Test Region", ["AAA", "BBB"])
    monkeypatch.setitem(regional._REGION_LOOKUP, "test region", "Test Region")

    traffic_by_code = {
        "AAA": _traffic("AAA", passengers=1000, growth_rate=0.05),
        "BBB": _traffic("BBB", passengers=500, growth_rate=0.01),
    }
    ddi_by_code = {"AAA": 60.0, "BBB": 20.0}
    delay_rate_by_code = {"AAA": 50.0, "BBB": 20.0}
    taxi_out_by_code = {"AAA": 25.0, "BBB": 15.0}
    long_haul_by_code = {"AAA": 40.0, "BBB": 10.0}

    mock_traffic.side_effect = lambda code: traffic_by_code[code]
    mock_ddi.side_effect = lambda code: ddi_by_code[code]
    mock_delay_rate.side_effect = lambda code: delay_rate_by_code[code]
    mock_taxi_out.side_effect = lambda code: taxi_out_by_code[code]
    mock_long_haul.side_effect = lambda code: long_haul_by_code[code]
    mock_period.return_value = (2026, 3)

    results = regional.rank_airports_by_region("test region")

    assert [r["iata_code"] for r in results] == ["AAA", "BBB"]
    assert results[0]["rank"] == 1
    assert results[0]["investment_score"] > results[1]["investment_score"]
    # AAA is the max on every axis in this 2-airport peer set.
    assert results[0]["volume_score"] == 1.0
    assert results[0]["growth_score"] == 1.0
    assert results[0]["ddi_score"] == 1.0
    assert results[0]["taxi_out_score"] == 1.0
    assert results[0]["long_haul_score"] == 1.0
    assert results[1]["volume_score"] == 0.0
    assert results[0]["raw"]["delayed_departure_rate_pct"] == 50.0


@patch("airport_investment_agent.tools.regional.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.regional.get_completion_data_period")
@patch("airport_investment_agent.tools.regional.get_long_haul_percentage")
@patch("airport_investment_agent.tools.regional.get_average_taxi_out_minutes")
@patch("airport_investment_agent.tools.regional.get_departure_delay_index")
@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_by_region_excludes_unfetchable_airports_instead_of_failing(
    mock_traffic,
    mock_ddi,
    mock_taxi_out,
    mock_long_haul,
    mock_period,
    mock_delay_rate,
    monkeypatch,
):
    monkeypatch.setitem(regional.REGION_AIRPORTS, "Test Region", ["AAA", "BBB"])
    monkeypatch.setitem(regional._REGION_LOOKUP, "test region", "Test Region")

    def traffic_side_effect(code):
        if code == "BBB":
            raise UnknownAirportError("simulated fetch failure")
        return _traffic("AAA", passengers=1000, growth_rate=0.05)

    mock_traffic.side_effect = traffic_side_effect
    mock_ddi.return_value = 30.0
    mock_delay_rate.return_value = 25.0
    mock_taxi_out.return_value = 20.0
    mock_long_haul.return_value = 25.0
    mock_period.return_value = (2026, 3)

    results = regional.rank_airports_by_region("test region")

    assert len(results) == 1
    assert results[0]["iata_code"] == "AAA"
    assert any("BBB" in caveat for caveat in results[0]["caveats"])


@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_by_region_raises_when_entire_peer_set_is_unfetchable(
    mock_traffic, monkeypatch
):
    monkeypatch.setitem(regional.REGION_AIRPORTS, "Test Region", ["AAA", "BBB"])
    monkeypatch.setitem(regional._REGION_LOOKUP, "test region", "Test Region")
    mock_traffic.side_effect = UnknownAirportError("simulated fetch failure")

    with pytest.raises(UnknownRegionError):
        regional.rank_airports_by_region("test region")


@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_by_region_propagates_unexpected_errors(
    mock_traffic, monkeypatch
):
    monkeypatch.setitem(regional.REGION_AIRPORTS, "Test Region", ["AAA", "BBB"])
    monkeypatch.setitem(regional._REGION_LOOKUP, "test region", "Test Region")

    def traffic_side_effect(code):
        if code == "BBB":
            raise ValueError("a real bug, not a data-coverage gap")
        return _traffic("AAA", passengers=1000, growth_rate=0.05)

    mock_traffic.side_effect = traffic_side_effect

    with pytest.raises(ValueError, match="a real bug"):
        regional.rank_airports_by_region("test region")


@patch("airport_investment_agent.tools.regional.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.regional.get_completion_data_period")
@patch("airport_investment_agent.tools.regional.get_long_haul_percentage")
@patch("airport_investment_agent.tools.regional.get_average_taxi_out_minutes")
@patch("airport_investment_agent.tools.regional.get_departure_delay_index")
@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_nationwide_normalizes_across_the_full_curated_union(
    mock_traffic,
    mock_ddi,
    mock_taxi_out,
    mock_long_haul,
    mock_period,
    mock_delay_rate,
    monkeypatch,
):
    # Full replacement (not setitem) so the nationwide universe is exactly
    # these 3 codes, not the real ~46-airport union plus these.
    monkeypatch.setattr(
        regional,
        "REGION_AIRPORTS",
        {"Region One": ["AAA", "BBB"], "Region Two": ["CCC"]},
    )

    traffic_by_code = {
        "AAA": _traffic("AAA", passengers=1000, growth_rate=0.05),
        "BBB": _traffic("BBB", passengers=500, growth_rate=0.01),
        "CCC": _traffic("CCC", passengers=750, growth_rate=0.03),
    }
    ddi_by_code = {"AAA": 60.0, "BBB": 20.0, "CCC": 40.0}
    delay_rate_by_code = {"AAA": 50.0, "BBB": 20.0, "CCC": 35.0}
    taxi_out_by_code = {"AAA": 25.0, "BBB": 15.0, "CCC": 20.0}
    long_haul_by_code = {"AAA": 40.0, "BBB": 10.0, "CCC": 25.0}

    mock_traffic.side_effect = lambda code: traffic_by_code[code]
    mock_ddi.side_effect = lambda code: ddi_by_code[code]
    mock_delay_rate.side_effect = lambda code: delay_rate_by_code[code]
    mock_taxi_out.side_effect = lambda code: taxi_out_by_code[code]
    mock_long_haul.side_effect = lambda code: long_haul_by_code[code]
    mock_period.return_value = (2026, 3)

    results = regional.rank_airports_nationwide()

    assert {r["iata_code"] for r in results} == {"AAA", "BBB", "CCC"}
    assert all(r["region"] == "Nationwide" for r in results)
    # AAA is the max on every axis across all 3 codes, spanning both regions.
    assert results[0]["iata_code"] == "AAA"
    assert any("union" in caveat.lower() for caveat in results[0]["caveats"])


@patch("airport_investment_agent.tools.regional.get_airport_traffic")
def test_rank_airports_nationwide_excludes_unfetchable_airports_instead_of_failing(
    mock_traffic, monkeypatch
):
    monkeypatch.setattr(regional, "REGION_AIRPORTS", {"Region One": ["AAA", "BBB"]})

    def traffic_side_effect(code):
        if code == "BBB":
            raise UnknownAirportError("simulated fetch failure")
        return _traffic("AAA", passengers=1000, growth_rate=0.05)

    mock_traffic.side_effect = traffic_side_effect

    with (
        patch(
            "airport_investment_agent.tools.regional.get_departure_delay_index",
            return_value=30.0,
        ),
        patch(
            "airport_investment_agent.tools.regional.get_delayed_departure_rate_pct",
            return_value=25.0,
        ),
        patch(
            "airport_investment_agent.tools.regional.get_average_taxi_out_minutes",
            return_value=20.0,
        ),
        patch(
            "airport_investment_agent.tools.regional.get_long_haul_percentage",
            return_value=25.0,
        ),
        patch(
            "airport_investment_agent.tools.regional.get_completion_data_period",
            return_value=(2026, 3),
        ),
    ):
        results = regional.rank_airports_nationwide()

    assert len(results) == 1
    assert results[0]["iata_code"] == "AAA"
    assert any("BBB" in caveat for caveat in results[0]["caveats"])
