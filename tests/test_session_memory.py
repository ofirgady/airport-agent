import os

import pytest


@pytest.mark.live
def test_session_remembers_context_across_turns():
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("requires a real OPENAI_API_KEY")

    session = get_session("pytest-live-session")

    first = Runner.run_sync(
        airport_agent, "Compare JFK and LAX for investment potential", session=session
    )
    assert "JFK" in first.final_output and "LAX" in first.final_output

    second = Runner.run_sync(airport_agent, "What about ORD too?", session=session)
    assert "ORD" in second.final_output


@pytest.mark.live
def test_session_resolves_pronoun_reference_to_prior_topic():
    """Distinct from test_session_remembers_context_across_turns above:
    that test's "What about ORD too?" only requires extending a set, never
    identifying *which* prior thing is being referred to. This one requires
    resolving "that" to a single specific prior topic (JFK's congestion)
    before it can even decide which tool to call next."""
    from agents import Runner

    from airport_investment_agent.agent import airport_agent
    from airport_investment_agent.utils.sessions import get_session

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("requires a real OPENAI_API_KEY")

    session = get_session("pytest-live-session-pronoun")

    first = Runner.run_sync(
        airport_agent, "What's the departure delay index at JFK?", session=session
    )
    assert "JFK" in first.final_output

    second = Runner.run_sync(
        airport_agent, "How does that compare to LAX?", session=session
    )
    assert "JFK" in second.final_output and "LAX" in second.final_output
