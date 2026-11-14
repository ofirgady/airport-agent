from airport_investment_agent.models.errors import AirportDataError, UnknownAirportError
from airport_investment_agent.tools.tool_errors import (
    describe_tool_error,
    describe_web_search_error,
)


def test_describe_tool_error_relays_known_domain_errors():
    result = describe_tool_error(None, UnknownAirportError("no data for XXX"))
    assert result == "Error: no data for XXX"


def test_describe_tool_error_returns_none_for_unexpected_errors():
    """None signals the SDK to re-raise the original exception instead of
    swallowing it -- see agents.tool._FailureHandlingFunctionToolInvoker.
    This is the actual fix: a real bug (here simulated with a bare
    KeyError, not an AirportDataError) must not be laundered into
    LLM-narrated text as if it were an expected data-coverage gap."""
    result = describe_tool_error(None, KeyError("real bug, not a data gap"))
    assert result is None


def test_describe_web_search_error_relays_any_error():
    """Unlike describe_tool_error, web_search_fallback's failures are
    external-service hiccups (network, rate limit, timeout), not bugs in
    our own code -- always relayed so the agent can gracefully continue
    without the fallback rather than crashing the whole turn."""
    result = describe_web_search_error(None, TimeoutError("network blip"))
    assert result == "Error: network blip"


def test_describe_web_search_error_also_relays_domain_errors_for_consistency():
    result = describe_web_search_error(None, AirportDataError("boom"))
    assert result == "Error: boom"
