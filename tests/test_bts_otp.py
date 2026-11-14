import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from airport_investment_agent.clients import bts_otp
from airport_investment_agent.models.errors import CompletionDataUnavailableError


@pytest.fixture(autouse=True)
def _clear_cache():
    bts_otp._monthly_aggregate_cache = None
    yield
    bts_otp._monthly_aggregate_cache = None


SAMPLE_CSV = (
    "Origin,Cancelled,DepDelayMinutes,DepDel15,TaxiOut,Distance\n"
    "JFK,0.00,20.00,1.00,15.00,3000.00\n"
    "JFK,0.00,5.00,0.00,10.00,500.00\n"
    "JFK,1.00,,,,1000.00\n"
    "LAX,0.00,0.00,0.00,12.00,2500.00\n"
    "LAX,0.00,30.00,1.00,25.00,800.00\n"
)


def test_aggregate_from_csv_stream_computes_expected_sums():
    aggregate = bts_otp._aggregate_from_csv_stream(io.StringIO(SAMPLE_CSV))

    jfk = aggregate["JFK"]
    assert jfk["scheduled"] == 3
    assert jfk["cancelled"] == 1
    assert jfk["non_cancelled_departures"] == 2
    assert jfk["delayed_departures"] == 1  # only the 20.00 row clears 15min
    assert jfk["delayed_departure_minutes_sum"] == pytest.approx(20.0)
    assert jfk["taxi_out_minutes_sum"] == pytest.approx(25.0)
    assert jfk["taxi_out_sample_count"] == 2
    assert jfk["long_haul_count"] == 1  # only the 3000mi row clears 2300
    assert jfk["distance_observed"] is True

    lax = aggregate["LAX"]
    assert lax["non_cancelled_departures"] == 2
    assert lax["delayed_departures"] == 1
    assert lax["long_haul_count"] == 1


def test_step_back_one_month_handles_year_rollover():
    assert bts_otp._step_back_one_month(2026, 1) == (2025, 12)
    assert bts_otp._step_back_one_month(2026, 7) == (2026, 6)


def test_months_since_computes_month_difference_across_year_rollover():
    assert bts_otp._months_since(2026, 4, today=date(2026, 7, 6)) == 3
    assert bts_otp._months_since(2025, 12, today=date(2026, 1, 6)) == 1


@patch("airport_investment_agent.clients.bts_otp.requests.get")
def test_resolve_latest_available_month_uses_first_published_estimate(mock_get):
    mock_get.return_value = MagicMock(status_code=206)
    year, month = bts_otp.resolve_latest_available_month(today=date(2026, 7, 6))
    assert (year, month) == (2026, 5)


@patch("airport_investment_agent.clients.bts_otp.requests.get")
def test_resolve_latest_available_month_steps_back_when_not_yet_published(mock_get):
    mock_get.side_effect = [MagicMock(status_code=404), MagicMock(status_code=206)]
    year, month = bts_otp.resolve_latest_available_month(today=date(2026, 7, 6))
    assert (year, month) == (2026, 4)


@patch("airport_investment_agent.clients.bts_otp.requests.get")
def test_resolve_latest_available_month_raises_when_none_found(mock_get):
    mock_get.return_value = MagicMock(status_code=404)
    with pytest.raises(CompletionDataUnavailableError):
        bts_otp.resolve_latest_available_month(today=date(2026, 7, 6))


@patch("airport_investment_agent.utils.http.requests.get")
def test_download_and_aggregate_raises_domain_error_on_network_failure(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("network down")
    with pytest.raises(CompletionDataUnavailableError):
        bts_otp.download_and_aggregate(2026, 3)
