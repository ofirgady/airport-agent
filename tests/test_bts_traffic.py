from unittest.mock import MagicMock, patch

import pytest

from airport_investment_agent.clients import bts_traffic
from airport_investment_agent.tools.traffic import get_airport_traffic


def _make_response(json_data):
    response = MagicMock()
    response.json.return_value = json_data
    return response


def _annual_row(year, last_month, passengers, departures, seats, load_factor_pct):
    """One row of BTS's monthly T-100 data after SoQL `$group=year`."""
    return {
        "year": year,
        "last_month": f"{year}-{last_month:02d}-01T00:00:00.000",
        "passengers": str(passengers),
        "departures": str(departures),
        "seats": str(seats),
        "load_factor_pct": str(load_factor_pct),
    }


@pytest.fixture(autouse=True)
def _clear_bts_caches():
    bts_traffic._get_latest_complete_year.cache_clear()
    bts_traffic.get_nationwide_max_passengers.cache_clear()
    bts_traffic.get_nationwide_max_load_factor.cache_clear()
    yield
    bts_traffic._get_latest_complete_year.cache_clear()
    bts_traffic.get_nationwide_max_passengers.cache_clear()
    bts_traffic.get_nationwide_max_load_factor.cache_clear()


@patch("airport_investment_agent.utils.http.requests.get")
def test_airport_rows_are_aggregated_per_year_with_seat_mile_weighted_load_factor(mock_get):
    mock_get.return_value = _make_response(
        [_annual_row("2025", 12, 31_040_364, 220_185, 37_915_448, 81.9)]
    )

    rows = bts_traffic._fetch_airport_rows("JFK")

    params = mock_get.call_args.kwargs["params"]
    assert params["$group"] == "year"
    assert "origin_airport_code='JFK'" in params["$where"]
    # Load factor must be weighted by seat-miles, not a flat monthly average.
    assert (
        "sum(total_load_factor * total_seats * total_distance_flight_sm)"
        in params["$select"]
    )
    assert rows == [
        {
            "year": "2025",
            "total_passengers": 31_040_364,
            "total_departures": 220_185,
            "total_seats": 37_915_448,
            "total_load_factor": 81.9,
            "total_passengers_flight": pytest.approx(31_040_364 / 220_185),
        }
    ]


@patch("airport_investment_agent.utils.http.requests.get")
def test_newest_year_without_december_is_labelled_year_to_date(mock_get):
    mock_get.return_value = _make_response(
        [
            _annual_row("2026", 7, 16_596_708, 121_106, 20_354_585, 81.6),
            _annual_row("2025", 12, 31_040_364, 220_185, 37_915_448, 81.9),
        ]
    )

    years = [row["year"] for row in bts_traffic._fetch_airport_rows("JFK")]

    assert years == ["2026 YTD", "2025"]


@patch("airport_investment_agent.utils.http.requests.get")
def test_older_year_without_december_service_still_counts_as_complete(mock_get):
    # A seasonal airport can have no December flights in a finished year.
    mock_get.return_value = _make_response(
        [
            _annual_row("2025", 12, 900, 9, 1100, 80.0),
            _annual_row("2024", 10, 800, 8, 1000, 79.0),
        ]
    )

    years = [row["year"] for row in bts_traffic._fetch_airport_rows("ACK")]

    assert years == ["2025", "2024"]


@patch("airport_investment_agent.utils.http.requests.get")
def test_rows_without_a_load_factor_are_dropped(mock_get):
    no_seat_data = _annual_row("2025", 12, 0, 50, 0, 0)
    no_seat_data["load_factor_pct"] = None
    mock_get.return_value = _make_response([no_seat_data])

    assert bts_traffic._fetch_airport_rows("XYZ") == []


@patch("airport_investment_agent.tools.traffic.get_completion_data_age_months", return_value=1)
@patch("airport_investment_agent.tools.traffic.get_completion_data_period", return_value=(2026, 9))
@patch("airport_investment_agent.tools.traffic.get_completion_rate", return_value=0.98)
@patch("airport_investment_agent.utils.http.requests.get")
def test_traffic_uses_complete_years_only_when_current_year_is_in_progress(mock_get, *_):
    mock_get.return_value = _make_response(
        [
            _annual_row("2026", 7, 16_596_708, 121_106, 20_354_585, 81.6),
            _annual_row("2025", 12, 1100, 11, 1300, 82.0),
            _annual_row("2024", 12, 1000, 10, 1200, 80.0),
        ]
    )

    traffic = get_airport_traffic("JFK")

    assert traffic.passengers == 1100
    assert traffic.growth_rate == pytest.approx(0.1)
    assert "BTS T-100 data, year 2025" in traffic.caveats
    assert "Growth rate compares 2025 vs 2024" in traffic.caveats


@patch("airport_investment_agent.utils.http.requests.get")
def test_latest_complete_year_skips_the_year_in_progress(mock_get):
    mock_get.return_value = _make_response(
        [
            {"year": "2026", "last_month": "2026-07-01T00:00:00.000"},
            {"year": "2025", "last_month": "2025-12-01T00:00:00.000"},
        ]
    )

    assert bts_traffic._get_latest_complete_year() == "2025"


@patch("airport_investment_agent.clients.bts_traffic._get_latest_complete_year", return_value="2025")
@patch("airport_investment_agent.utils.http.requests.get")
def test_nationwide_max_load_factor_is_annual_and_returned_as_a_fraction(mock_get, _):
    mock_get.return_value = _make_response(
        [{"origin_airport_code": "RFD", "load_factor_pct": "86.4"}]
    )

    assert bts_traffic.get_nationwide_max_load_factor() == pytest.approx(0.864)

    params = mock_get.call_args.kwargs["params"]
    assert params["$group"] == "origin_airport_code"
    assert params["$order"] == "load_factor_pct DESC"
    assert "year='2025'" in params["$where"]
    assert "sum(total_departures) > 10000" in params["$having"]
