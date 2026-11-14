from unittest.mock import patch

import pytest

from airport_investment_agent.models.errors import UnknownAirportError
from airport_investment_agent.models.models import AirportTraffic
from airport_investment_agent.tools.explain import (
    compare_unmet_demand,
    estimate_unmet_demand,
)


@patch("airport_investment_agent.tools.explain.get_completion_data_period")
@patch("airport_investment_agent.tools.explain.get_congestion_score")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_load_factor")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_passengers")
@patch("airport_investment_agent.tools.explain.get_airport_traffic")
def test_estimate_unmet_demand_discloses_assumptions(
    mock_get_traffic,
    mock_max_passengers,
    mock_max_load_factor,
    mock_congestion_score,
    mock_period,
):
    mock_get_traffic.return_value = AirportTraffic(
        iata_code="TST",
        passengers=80,
        departures=10,
        seats=100,
        load_factor=0.8,
        passengers_per_departure=8.0,
        growth_rate=0.02,
        completion_rate=None,
        caveats=["test fixture"],
    )
    mock_max_passengers.return_value = 100
    mock_max_load_factor.return_value = 0.9
    mock_congestion_score.return_value = 0.5
    mock_period.return_value = (2026, 3)

    result = estimate_unmet_demand("TST")

    assert result["iata_code"] == "TST"
    assert result["is_proxy"] is True
    assert "proxy" in result["narrative"].lower()
    assert "not a direct measurement" in result["narrative"].lower()


@patch("airport_investment_agent.tools.explain.get_completion_data_period")
@patch("airport_investment_agent.tools.explain.get_congestion_score")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_load_factor")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_passengers")
@patch("airport_investment_agent.tools.explain.get_airport_traffic")
def test_estimate_unmet_demand_surfaces_traffic_caveats(
    mock_get_traffic,
    mock_max_passengers,
    mock_max_load_factor,
    mock_congestion_score,
    mock_period,
):
    mock_get_traffic.return_value = AirportTraffic(
        iata_code="TST",
        passengers=80,
        departures=10,
        seats=100,
        load_factor=0.8,
        passengers_per_departure=8.0,
        growth_rate=0.02,
        completion_rate=None,
        caveats=["a very specific caveat"],
    )
    mock_max_passengers.return_value = 100
    mock_max_load_factor.return_value = 0.9
    mock_congestion_score.return_value = 0.5
    mock_period.return_value = (2026, 3)

    result = estimate_unmet_demand("TST")

    assert "a very specific caveat" in result["caveats"]


@patch("airport_investment_agent.tools.explain.get_completion_data_period")
@patch("airport_investment_agent.tools.explain.get_congestion_score")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_load_factor")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_passengers")
@patch("airport_investment_agent.tools.explain.get_airport_traffic")
def test_estimate_unmet_demand_components_are_bounded(
    mock_get_traffic,
    mock_max_passengers,
    mock_max_load_factor,
    mock_congestion_score,
    mock_period,
):
    mock_get_traffic.return_value = AirportTraffic(
        iata_code="TST",
        passengers=80,
        departures=10,
        seats=100,
        load_factor=0.8,
        passengers_per_departure=8.0,
        growth_rate=0.02,
        completion_rate=None,
        caveats=[],
    )
    mock_max_passengers.return_value = 100
    mock_max_load_factor.return_value = 0.9
    mock_congestion_score.return_value = 0.5
    mock_period.return_value = (2026, 3)

    result = estimate_unmet_demand("TST")

    assert 0.0 <= result["unmet_demand_score"] <= 1.0
    for value in result["components"].values():
        assert 0.0 <= value <= 1.0


def _traffic(code, passengers, load_factor, growth_rate, caveats=None):
    return AirportTraffic(
        iata_code=code,
        passengers=passengers,
        departures=passengers // 100 or 1,
        seats=passengers * 2,
        load_factor=load_factor,
        passengers_per_departure=100.0,
        growth_rate=growth_rate,
        completion_rate=None,
        caveats=caveats or [],
    )


@patch("airport_investment_agent.tools.explain.get_completion_data_period")
@patch("airport_investment_agent.tools.explain.get_congestion_score")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_load_factor")
@patch("airport_investment_agent.tools.explain.get_nationwide_max_passengers")
@patch("airport_investment_agent.tools.explain.get_airport_traffic")
def test_compare_unmet_demand_names_the_higher_airport(
    mock_get_traffic,
    mock_max_passengers,
    mock_max_load_factor,
    mock_congestion_score,
    mock_period,
):
    traffic_by_code = {
        "AAA": _traffic("AAA", passengers=1000, load_factor=0.9, growth_rate=0.08),
        "BBB": _traffic("BBB", passengers=100, load_factor=0.5, growth_rate=0.0),
    }
    mock_get_traffic.side_effect = lambda code: traffic_by_code[code]
    mock_max_passengers.return_value = 1000
    mock_max_load_factor.return_value = 0.9
    mock_congestion_score.side_effect = lambda code: 0.8 if code == "AAA" else 0.1
    mock_period.return_value = (2026, 3)

    result = compare_unmet_demand("AAA", "BBB")

    assert result["higher_unmet_demand"] == "AAA"
    assert "AAA" in result["explanation"]
    assert result["airport_a"]["iata_code"] == "AAA"
    assert result["airport_b"]["iata_code"] == "BBB"
    assert (
        result["airport_a"]["unmet_demand_score"]
        > result["airport_b"]["unmet_demand_score"]
    )


def test_compare_unmet_demand_rejects_the_same_airport_twice():
    with pytest.raises(ValueError, match="two different airports"):
        compare_unmet_demand("JFK", "jfk")


@patch("airport_investment_agent.tools.explain.get_airport_traffic")
def test_compare_unmet_demand_fails_atomically_when_either_airport_has_no_data(
    mock_get_traffic,
):
    """Regression test: this must NOT behave like two
    independent estimate_unmet_demand_tool calls, where one airport's
    failure still lets the other's result through to be narrated as half
    of a false comparison. Either side failing must fail the whole call."""

    def traffic_side_effect(code):
        if code == "HTR":
            raise UnknownAirportError("No BTS traffic data found for 'HTR'.")
        return _traffic("JFK", passengers=1000, load_factor=0.9, growth_rate=0.05)

    mock_get_traffic.side_effect = traffic_side_effect

    with pytest.raises(UnknownAirportError, match="HTR"):
        compare_unmet_demand("JFK", "HTR")
