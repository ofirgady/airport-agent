from airport_investment_agent.agent import airport_agent


def test_agent_model_is_pinned_explicitly():
    """Regression test for model pinning: the
    model must be a stated, reproducible choice, not whatever the SDK
    happens to default to if this line is ever accidentally removed."""
    assert airport_agent.model == "gpt-5.4-mini"


def test_agent_has_no_reasoning_effort_override():
    """Live-compared against reasoning.effort="low" -- no
    correctness improvement was found, so gpt-5.4-mini's own default
    effort ("none", resolved automatically since model_settings isn't
    overridden in agent.py) is kept rather than raised here."""
    reasoning = airport_agent.model_settings.reasoning
    assert reasoning is not None
    assert reasoning.effort == "none"
