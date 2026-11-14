from unittest.mock import MagicMock, patch

import pytest
import requests

from airport_investment_agent.models.errors import (
    AirportDataError,
    CompletionDataUnavailableError,
    UnknownAirportError,
)
from airport_investment_agent.tools.traffic import get_airport_traffic


def _make_response(json_data, ok: bool = True):
    response = MagicMock()
    response.json.return_value = json_data
    if not ok:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return response


# Data age pinned to "fresh" so this test doesn't start failing once the
# committed OTP snapshot ages past STALE_DATA_WARNING_MONTHS in wall-clock
# time (the staleness caveat has its own dedicated tests below).
@patch("airport_investment_agent.tools.traffic.get_completion_data_age_months", return_value=1)
@patch("airport_investment_agent.tools.traffic.get_completion_data_period")
@patch("airport_investment_agent.tools.traffic.get_completion_rate")
@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_parses_a_real_looking_response(
    mock_get, mock_completion_rate, mock_completion_period, _mock_age_months
):
    mock_get.return_value = _make_response(
        [
            {
                "year": "2025",
                "last_month": "2025-12-01T00:00:00.000",
                "passengers": "1000",
                "departures": "10",
                "seats": "1200",
                "load_factor_pct": "83.3",
            },
            {
                "year": "2024",
                "last_month": "2024-12-01T00:00:00.000",
                "passengers": "900",
                "departures": "9",
                "seats": "1100",
                "load_factor_pct": "81.8",
            },
        ]
    )
    mock_completion_rate.return_value = 0.976
    mock_completion_period.return_value = (2026, 3)

    traffic = get_airport_traffic("JFK")

    assert traffic.passengers == 1000
    assert traffic.departures == 10
    assert traffic.seats == 1200
    assert traffic.load_factor == pytest.approx(0.833)
    # BTS reports T-100 monthly; passengers/departure is derived from the
    # year's summed passengers and departures.
    assert traffic.passengers_per_departure == pytest.approx(100.0)
    assert traffic.growth_rate == pytest.approx((1000 - 900) / 900)
    assert traffic.completion_rate == 0.976
    assert "2026-03" in traffic.caveats[-1]


@patch("airport_investment_agent.tools.traffic.get_completion_data_age_months")
@patch("airport_investment_agent.tools.traffic.get_completion_data_period")
@patch("airport_investment_agent.tools.traffic.get_completion_rate")
@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_flags_stale_completion_data(
    mock_get, mock_completion_rate, mock_completion_period, mock_age_months
):
    mock_get.return_value = _make_response(
        [
            {
                "year": "2025",
                "last_month": "2025-12-01T00:00:00.000",
                "passengers": "1000",
                "departures": "10",
                "seats": "1200",
                "load_factor_pct": "83.3",
            }
        ]
    )
    mock_completion_rate.return_value = 0.976
    mock_completion_period.return_value = (2026, 1)
    mock_age_months.return_value = 6

    traffic = get_airport_traffic("JFK")

    assert any("6 months old" in caveat for caveat in traffic.caveats)


@patch("airport_investment_agent.tools.traffic.get_completion_data_age_months")
@patch("airport_investment_agent.tools.traffic.get_completion_data_period")
@patch("airport_investment_agent.tools.traffic.get_completion_rate")
@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_does_not_flag_fresh_completion_data(
    mock_get, mock_completion_rate, mock_completion_period, mock_age_months
):
    mock_get.return_value = _make_response(
        [
            {
                "year": "2025",
                "last_month": "2025-12-01T00:00:00.000",
                "passengers": "1000",
                "departures": "10",
                "seats": "1200",
                "load_factor_pct": "83.3",
            }
        ]
    )
    mock_completion_rate.return_value = 0.976
    mock_completion_period.return_value = (2026, 3)
    mock_age_months.return_value = 1

    traffic = get_airport_traffic("JFK")

    assert not any("months old" in caveat for caveat in traffic.caveats)


@patch("airport_investment_agent.tools.traffic.get_completion_rate")
@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_degrades_gracefully_when_completion_data_unavailable(
    mock_get, mock_completion_rate
):
    mock_get.return_value = _make_response(
        [
            {
                "year": "2025",
                "last_month": "2025-12-01T00:00:00.000",
                "passengers": "1000",
                "departures": "10",
                "seats": "1200",
                "load_factor_pct": "83.3",
            }
        ]
    )
    mock_completion_rate.side_effect = CompletionDataUnavailableError("boom")

    traffic = get_airport_traffic("JFK")

    assert traffic.completion_rate is None
    assert any("Completion rate unavailable" in caveat for caveat in traffic.caveats)


@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_raises_domain_error_when_service_unreachable(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("network down")

    with pytest.raises(AirportDataError):
        get_airport_traffic("JFK")


@patch("airport_investment_agent.utils.http.requests.get")
def test_bts_traffic_raises_unknown_airport_when_no_rows(mock_get):
    mock_get.return_value = _make_response([])

    with pytest.raises(UnknownAirportError):
        get_airport_traffic("ZZZ")
