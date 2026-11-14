from airport_investment_agent.utils.number_guardrail import (
    extract_numbers_from_text,
    find_unsupported_numbers,
)


def test_raw_integer_stated_verbatim_is_supported():
    tool_outputs = [{"passengers": 45231890}]
    final_output = "JFK handled 45,231,890 passengers."

    assert find_unsupported_numbers(final_output, tool_outputs) == []


def test_ratio_field_restated_as_percentage_is_supported():
    tool_outputs = [{"load_factor": 0.8734}]
    final_output = "The load factor was 87.3%."

    assert find_unsupported_numbers(final_output, tool_outputs) == []


def test_large_count_restated_as_million_is_supported():
    tool_outputs = [{"passengers": 45231890}]
    final_output = "JFK handled about 45 million passengers."

    assert find_unsupported_numbers(final_output, tool_outputs) == []


def test_number_embedded_only_in_narrative_string_is_supported():
    tool_outputs = [
        {"narrative": "Unmet-demand estimate for ATL: 0.62 on a 0-1 scale."}
    ]
    final_output = "The unmet-demand score for ATL is 0.62."

    assert find_unsupported_numbers(final_output, tool_outputs) == []


def test_genuinely_invented_number_is_flagged():
    tool_outputs = [{"completion_rate": 0.95}]
    final_output = "ATL has a 99% on-time rate."

    assert find_unsupported_numbers(final_output, tool_outputs) == [99.0]


def test_rank_ordinal_and_calendar_year_are_ignored():
    tool_outputs = [{"passengers": 100}]
    final_output = "1. JFK is the top pick, as of 2026."

    assert find_unsupported_numbers(final_output, tool_outputs) == []


def test_extract_numbers_from_text_handles_sign_percent_and_suffix():
    assert extract_numbers_from_text("Growth of +3.2% and -1.1%") == [3.2, -1.1]
    assert extract_numbers_from_text("about 45 million passengers") == [45_000_000.0]
    assert extract_numbers_from_text("45M passengers") == [45_000_000.0]


def test_extract_numbers_from_text_does_not_treat_a_leading_letter_as_a_suffix():
    """Regression test: live-verified this session (real ATL query) that
    "2025 BTS data" was parsed as "2025 billion" because the B/M suffix
    match had no word-boundary check against the next letter."""
    assert extract_numbers_from_text("2025 BTS data") == [2025.0]
    assert extract_numbers_from_text("393,372 Montreal-bound flights") == [393372.0]


def test_negative_ratio_restated_as_percentage_is_supported():
    """Regression test: live-verified this session that a negative
    growth_rate (-0.0209) never produced a -2.1 candidate, because the
    ratio-to-percent conversion only handled 0.0 <= value <= 1.0."""
    tool_outputs = [{"growth_rate": -0.02089690717221}]
    final_output = "growth was -2.1% year over year."

    assert find_unsupported_numbers(final_output, tool_outputs) == []
