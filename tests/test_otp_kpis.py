import io
from unittest.mock import patch

import pytest

from airport_investment_agent.clients import bts_otp
from airport_investment_agent.models.errors import CompletionDataUnavailableError
from airport_investment_agent.tools import otp_kpis


@pytest.fixture(autouse=True)
def _clear_caches():
    bts_otp._monthly_aggregate_cache = None
    otp_kpis._get_ddi_reference_percentiles.cache_clear()
    yield
    bts_otp._monthly_aggregate_cache = None
    otp_kpis._get_ddi_reference_percentiles.cache_clear()


SAMPLE_CSV = (
    "Origin,Cancelled,DepDelayMinutes,DepDel15,TaxiOut,Distance\n"
    "JFK,0.00,20.00,1.00,15.00,3000.00\n"
    "JFK,0.00,5.00,0.00,10.00,500.00\n"
    "JFK,1.00,,,,1000.00\n"
    "LAX,0.00,0.00,0.00,12.00,2500.00\n"
    "LAX,0.00,30.00,1.00,25.00,800.00\n"
)


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_completion_rate(mock_load_snapshot, mock_resolve, mock_download):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    assert otp_kpis.get_completion_rate("jfk") == pytest.approx(1 - 1 / 3)
    assert otp_kpis.get_completion_data_period() == (2026, 3)
    mock_download.assert_called_once()


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_departure_delay_index(mock_load_snapshot, mock_resolve, mock_download):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    # JFK: delay_rate=100*1/2=50, avg_delay=20, severity=20/60*100=33.33
    # DDI = 50*0.6 + 33.33*0.4 = 43.33
    assert otp_kpis.get_departure_delay_index("JFK") == pytest.approx(43.33, abs=0.01)


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_delayed_departure_rate_pct(
    mock_load_snapshot, mock_resolve, mock_download
):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    # JFK: 1 of 2 non-cancelled departures has DepDel15=1.00 -> 50%. This is
    # DOT's own on-time figure (14 CFR Part 234), independent of DDI's
    # severity blend.
    assert otp_kpis.get_delayed_departure_rate_pct("JFK") == pytest.approx(50.0)


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_average_taxi_out_minutes(mock_load_snapshot, mock_resolve, mock_download):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    assert otp_kpis.get_average_taxi_out_minutes("JFK") == pytest.approx(12.5)


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_long_haul_percentage(mock_load_snapshot, mock_resolve, mock_download):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    assert otp_kpis.get_long_haul_percentage("JFK") == pytest.approx(100 / 3)
    assert otp_kpis.get_long_haul_counts("JFK") == (1, 3)


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_completion_rate_raises_for_unknown_airport(
    mock_load_snapshot, mock_resolve, mock_download
):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)
    mock_download.return_value = bts_otp._aggregate_from_csv_stream(
        io.StringIO(SAMPLE_CSV)
    )

    with pytest.raises(CompletionDataUnavailableError):
        otp_kpis.get_completion_rate("ZZZ")


@patch("airport_investment_agent.clients.bts_otp.download_and_aggregate")
@patch("airport_investment_agent.clients.bts_otp.resolve_latest_available_month")
@patch("airport_investment_agent.clients.bts_otp._load_snapshot_cache")
def test_get_congestion_score_normalizes_against_nationwide_band(
    mock_load_snapshot, mock_resolve, mock_download
):
    mock_load_snapshot.return_value = None
    mock_resolve.return_value = (2026, 3)

    def make_entry(non_cancelled, delayed, delay_minutes_sum):
        entry = bts_otp._new_aggregate_entry()
        entry["scheduled"] = non_cancelled
        entry["non_cancelled_departures"] = non_cancelled
        entry["delayed_departures"] = delayed
        entry["delayed_departure_minutes_sum"] = delay_minutes_sum
        return entry

    # Three reference airports (>=100 non-cancelled departures) spanning a
    # range of DDI, plus a target airport that doesn't need to clear the
    # reference bar itself.
    mock_download.return_value = {
        "LOW": make_entry(100, 5, 50),
        "MID": make_entry(100, 20, 400),
        "HIGH": make_entry(100, 50, 3000),
        "TGT": make_entry(10, 5, 100),
    }

    score = otp_kpis.get_congestion_score("TGT")
    assert 0.0 <= score <= 1.0
