from unittest.mock import patch

import pytest

from airport_investment_agent.models.models import AirportTraffic
from airport_investment_agent.tools import congestion


def _traffic(code, passengers, ppd, caveats=None):
    return AirportTraffic(
        iata_code=code,
        passengers=passengers,
        departures=100,
        seats=passengers * 2,
        load_factor=0.8,
        passengers_per_departure=ppd,
        growth_rate=0.02,
        completion_rate=0.95,
        caveats=caveats or [],
    )


def test_compare_congestion_rejects_identical_airports():
    with pytest.raises(ValueError):
        congestion.compare_congestion("JFK", "jfk")


@patch("airport_investment_agent.tools.congestion.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.congestion.get_completion_data_period")
@patch("airport_investment_agent.tools.congestion.get_congestion_score")
@patch("airport_investment_agent.tools.congestion.get_departure_delay_index")
@patch("airport_investment_agent.tools.congestion.get_airport_traffic")
def test_compare_congestion_identifies_more_congested_airport(
    mock_traffic, mock_ddi, mock_score, mock_period, mock_delay_rate
):
    mock_traffic.side_effect = lambda code: _traffic(code, passengers=1000, ppd=100)
    mock_ddi.side_effect = lambda code: {"AAA": 60.0, "BBB": 20.0}[code]
    mock_score.side_effect = lambda code: {"AAA": 0.9, "BBB": 0.1}[code]
    mock_period.return_value = (2026, 3)
    mock_delay_rate.side_effect = lambda code: {"AAA": 50.0, "BBB": 15.0}[code]

    result = congestion.compare_congestion("AAA", "BBB")

    assert result["more_congested"] == "AAA"
    assert "AAA is more congested than BBB" in result["explanation"]
    assert result["airport_a"]["departure_delay_index"] == 60.0
    assert result["airport_b"]["departure_delay_index"] == 20.0
    assert result["airport_a"]["delayed_departure_rate_pct"] == 50.0
    assert result["airport_b"]["delayed_departure_rate_pct"] == 15.0
    assert result["data_period"] == {"year": 2026, "month": 3}


@patch("airport_investment_agent.tools.congestion.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.congestion.get_completion_data_period")
@patch("airport_investment_agent.tools.congestion.get_congestion_score")
@patch("airport_investment_agent.tools.congestion.get_departure_delay_index")
@patch("airport_investment_agent.tools.congestion.get_airport_traffic")
def test_compare_congestion_handles_equal_ddi(
    mock_traffic, mock_ddi, mock_score, mock_period, mock_delay_rate
):
    mock_traffic.side_effect = lambda code: _traffic(code, passengers=1000, ppd=100)
    mock_ddi.return_value = 40.0
    mock_score.return_value = 0.5
    mock_period.return_value = (2026, 3)
    mock_delay_rate.return_value = 30.0

    result = congestion.compare_congestion("AAA", "BBB")

    assert result["more_congested"] is None
    assert "equally congested" in result["explanation"]


@patch("airport_investment_agent.tools.congestion.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.congestion.get_completion_data_period")
@patch("airport_investment_agent.tools.congestion.get_congestion_score")
@patch("airport_investment_agent.tools.congestion.get_departure_delay_index")
@patch("airport_investment_agent.tools.congestion.get_airport_traffic")
def test_compare_congestion_flags_divergence_from_simple_proxy(
    mock_traffic, mock_ddi, mock_score, mock_period, mock_delay_rate
):
    # AAA: low volume/ppd but high DDI. BBB: high volume/ppd but low DDI.
    # DDI says AAA is "more congested"; the simple proxy would instead
    # rank BBB higher -- the two disagree, and the tool should say so.
    traffic_by_code = {
        "AAA": _traffic("AAA", passengers=100, ppd=10),
        "BBB": _traffic("BBB", passengers=1000, ppd=100),
    }
    mock_traffic.side_effect = lambda code: traffic_by_code[code]
    mock_ddi.side_effect = lambda code: {"AAA": 80.0, "BBB": 10.0}[code]
    mock_score.side_effect = lambda code: {"AAA": 0.9, "BBB": 0.05}[code]
    mock_period.return_value = (2026, 3)
    mock_delay_rate.return_value = 25.0

    result = congestion.compare_congestion("AAA", "BBB")

    assert result["more_congested"] == "AAA"
    assert "simpler volume x passengers-per-departure proxy" in result["explanation"]
    assert "BBB" in result["explanation"]


@patch("airport_investment_agent.tools.congestion.get_delayed_departure_rate_pct")
@patch("airport_investment_agent.tools.congestion.get_completion_data_period")
@patch("airport_investment_agent.tools.congestion.get_congestion_score")
@patch("airport_investment_agent.tools.congestion.get_departure_delay_index")
@patch("airport_investment_agent.tools.congestion.get_airport_traffic")
def test_compare_congestion_surfaces_traffic_caveats(
    mock_traffic, mock_ddi, mock_score, mock_period, mock_delay_rate
):
    mock_traffic.side_effect = lambda code: _traffic(
        code, passengers=1000, ppd=100, caveats=[f"{code} specific caveat"]
    )
    mock_ddi.return_value = 40.0
    mock_score.return_value = 0.5
    mock_period.return_value = (2026, 3)
    mock_delay_rate.return_value = 30.0

    result = congestion.compare_congestion("AAA", "BBB")

    assert "AAA specific caveat" in result["caveats"]
    assert "BBB specific caveat" in result["caveats"]
