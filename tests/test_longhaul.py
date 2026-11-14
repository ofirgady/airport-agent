from unittest.mock import patch

from airport_investment_agent.tools import longhaul


@patch("airport_investment_agent.tools.longhaul.get_completion_data_period")
@patch("airport_investment_agent.tools.longhaul.get_long_haul_counts")
@patch("airport_investment_agent.tools.longhaul.get_long_haul_percentage")
def test_long_haul_percentage_returns_expected_shape(
    mock_percentage, mock_counts, mock_period
):
    mock_percentage.return_value = 33.333333
    mock_counts.return_value = (1, 3)
    mock_period.return_value = (2026, 3)

    result = longhaul.long_haul_percentage("jfk")

    assert result["iata_code"] == "JFK"
    assert result["threshold_miles"] == 2300
    assert result["long_haul_percentage"] == 33.33
    assert result["long_haul_flight_count"] == 1
    assert result["scheduled_flight_count"] == 3
    assert result["data_period"] == {"year": 2026, "month": 3}
    assert len(result["caveats"]) == 2
    assert result["summary"] == (
        "JFK has a long-haul share of 33.3% this month "
        "(1 of 3 scheduled flights ≥2300 statute miles)."
    )


@patch("airport_investment_agent.tools.longhaul.get_completion_data_period")
@patch("airport_investment_agent.tools.longhaul.get_long_haul_counts")
@patch("airport_investment_agent.tools.longhaul.get_long_haul_percentage")
def test_long_haul_percentage_uppercases_iata_code(
    mock_percentage, mock_counts, mock_period
):
    mock_percentage.return_value = 0.0
    mock_counts.return_value = (0, 10)
    mock_period.return_value = (2026, 3)

    result = longhaul.long_haul_percentage("lax")

    mock_percentage.assert_called_once_with("LAX")
    mock_counts.assert_called_once_with("LAX")
    assert result["iata_code"] == "LAX"
