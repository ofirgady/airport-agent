"""Live regression tests for chat-response clarity.

LLM output is inherently non-deterministic, so these assert on content/
structure properties rather than exact strings. Not run by default --
`pytest -m live`, same convention as test_session_memory.py -- since each
test makes a real call against the live OpenAI API.

This file (plus test_session_memory.py) is also the *only* place real
tool-selection/routing behavior gets exercised at all -- the default,
non-live `pytest` run has zero coverage of whether the LLM picks the
correct tool for a given question. Disclosed, accepted gap; see
.doc/design.md's "Assumptions, Limitations, Proxies" section for why a
scripted fake-Model test double wasn't built to close it.
"""

import os
import re

import pytest


def _skip_without_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("requires a real OPENAI_API_KEY")


@pytest.mark.live
def test_congestion_explanation_names_delay_in_plain_language():
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-congestion")

    result = Runner.run_sync(
        airport_agent,
        "Is JFK more congested than LAX? Give me the details.",
        session=session,
    )
    output_lower = result.final_output.lower()

    assert (
        "delay" in output_lower
    ), "DDI should be explained in terms of delay, not left as a bare acronym"
    assert (
        "49.7" in result.final_output or "49.72" in result.final_output
    ), "real DDI figures should still be traceable in the explained answer"


@pytest.mark.live
def test_unmet_demand_leads_with_plain_english_sentence():
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-unmet-demand")

    result = Runner.run_sync(
        airport_agent, "Is there unmet demand at ATL?", session=session
    )
    first_line = result.final_output.strip().splitlines()[0]

    assert not first_line.lstrip().startswith(
        ("-", "*", "•")
    ), f"answer should open with a plain-English sentence, not a bare bullet: {first_line!r}"


@pytest.mark.live
def test_regional_ranking_long_haul_percentage_carries_a_unit_label():
    from agents import Runner

    from airport_investment_agent.tools.regional import rank_airports_by_region
    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()

    # Ground truth, no LLM involved.
    top = rank_airports_by_region("Texas")[0]
    raw_percentage = top["raw"]["long_haul_percentage"]

    session = get_session("pytest-live-explanations-regional")
    result = Runner.run_sync(
        airport_agent,
        "Which Texas airport most warrants investment?",
        session=session,
    )
    output = result.final_output

    assert top["iata_code"] in output

    # The raw percentage may be stated rounded to 1 decimal (see
    # longhaul.py's summary field) or as printed by regional.py's caveats;
    # accept either, but require it to appear with a unit, not a bare
    # decimal that could be misread as the 0-1 long_haul_score.
    percentage_str_1dp = f"{raw_percentage:.1f}"
    percentage_str_2dp = f"{raw_percentage:.2f}"
    mentions_percentage_figure = (
        percentage_str_1dp in output or percentage_str_2dp in output
    )
    if mentions_percentage_figure:
        assert "%" in output or "percent" in output.lower(), (
            "a stated long-haul percentage must carry a '%'/'percent' unit "
            "label -- a bare decimal reads as a 0-1 score, not a percentage"
        )


@pytest.mark.live
def test_long_haul_query_uses_contextual_units():
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-longhaul")

    result = Runner.run_sync(
        airport_agent,
        "What percentage of JFK's flights are long-haul this month?",
        session=session,
    )
    output_lower = result.final_output.lower()

    assert "%" in result.final_output or "percent" in output_lower
    assert (
        "mile" in output_lower
    ), "the long-haul distance threshold should be explained in miles, not left implicit"


@pytest.mark.live
def test_recency_question_uses_web_search_fallback_and_discloses_it():
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-web-search-fallback")

    result = Runner.run_sync(
        airport_agent,
        "What's the latest news on JFK -- any current expansion plans or incidents?",
        session=session,
    )
    output_lower = result.final_output.lower()

    assert (
        "web search" in output_lower or "search" in output_lower
    ), "a web-search-fallback answer should disclose it came from a live search, not the internal dataset"


@pytest.mark.live
def test_off_topic_question_is_declined_not_answered():
    """Regression test: previously the agent just answered an
    entirely unrelated question (observed live with "why do dogs hate
    cats?") instead of declining/redirecting."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-off-topic")

    result = Runner.run_sync(
        airport_agent,
        "Why do dogs hate cats?",
        session=session,
    )
    output_lower = result.final_output.lower()

    assert (
        "dog" not in output_lower and "cat" not in output_lower
    ), "the agent should decline/redirect, not actually answer the unrelated question"
    assert "airport" in output_lower or "invest" in output_lower, (
        "a decline should redirect the user back toward what this assistant "
        "can actually help with"
    )


@pytest.mark.live
def test_comparison_with_an_invalid_airport_makes_no_comparative_claim():
    """Regression test: previously asking to compare unmet
    demand between JFK and an invalid code (HTR) produced a confident
    comparative conclusion ("JFK has the higher unmet-demand proxy...")
    built from one real result and one failure."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-invalid-comparison")

    result = Runner.run_sync(
        airport_agent,
        "Which airport has higher unmet demand, JFK or HTR?",
        session=session,
    )
    output_lower = result.final_output.lower()

    assert "higher" not in output_lower and "more unmet demand" not in output_lower, (
        "the agent should not declare a comparative winner when one airport "
        "in the comparison has no data"
    )
    assert (
        "htr" in output_lower
    ), "the agent should name the airport that couldn't be analyzed"


@pytest.mark.live
def test_best_airport_in_the_us_routes_to_the_nationwide_tool():
    """Regression test: previously the agent could only
    answer "best airport to invest in" relative to one curated region at a
    time, or by invalidly cross-comparing investment_score values from
    separate rank_airports_by_region_tool calls."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-nationwide")

    result = Runner.run_sync(
        airport_agent,
        "What's the single best airport to invest in across the whole US?",
        session=session,
    )
    tool_names = {
        item.tool_name for item in result.new_items if item.type == "tool_call_item"
    }

    assert "rank_airports_nationwide_tool" in tool_names, (
        f"expected the nationwide tool to be called for a scope-free 'best in "
        f"the US' question, got: {tool_names}"
    )


@pytest.mark.live
def test_uncurated_scope_question_gets_a_real_answer_with_disclosure():
    """Regression test: a named U.S. scope
    that isn't one of the 5 curated regions (here, a state) must still get
    a real, non-refused answer -- via compare_airports_tool over a
    self-identified airport list -- with the self-identification disclosed."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-uncurated-scope")

    result = Runner.run_sync(
        airport_agent,
        "What's the best airport to invest in in California?",
        session=session,
    )
    tool_names = {
        item.tool_name for item in result.new_items if item.type == "tool_call_item"
    }
    output_lower = result.final_output.lower()

    assert "compare_airports_tool" in tool_names, (
        f"expected compare_airports_tool over a self-identified California "
        f"airport list, got: {tool_names}"
    )
    assert not first_line_is_a_refusal(
        output_lower
    ), "an uncurated-but-named U.S. scope should get a real answer, not a refusal"


@pytest.mark.live
def test_answer_separates_caveats_into_their_own_section():
    """Regression test for the 2026-07-08 response-formatting request: a
    substantive answer must not read as one dense paragraph -- caveats in
    particular must be visually separated (a blank line, then their own
    "Caveats:" line), not interleaved into the same paragraph as the
    figures."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    _skip_without_api_key()
    session = get_session("pytest-live-explanations-caveats-section")

    result = Runner.run_sync(airport_agent, "How is JFK doing?", session=session)
    output = result.final_output
    output_lower = output.lower()

    assert "caveats:" in output_lower, (
        "a substantive answer should surface a clearly labeled Caveats section, "
        "not bury caveats inline in the middle of a sentence"
    )
    text_before_caveats = output[: output_lower.index("caveats:")]

    assert re.search(r"\n[ \t]*\n[ \t]*$", text_before_caveats), (
        "the Caveats section should be separated from the rest of the answer "
        "by a full blank line, not run directly into the preceding sentence"
    )


def first_line_is_a_refusal(output_lower: str) -> bool:
    refusal_markers = (
        "i can only",
        "i'm not able to",
        "i cannot",
        "i don't have a tool",
    )
    first_line = output_lower.strip().splitlines()[0]
    return any(marker in first_line for marker in refusal_markers)
