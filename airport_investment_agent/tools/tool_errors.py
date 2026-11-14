"""failure_error_function callables for every tool exposed to the agent.

describe_tool_error (the 6 @function_tool-wrapped domain tools in
agent_tools.py) only relays known AirportDataError-family failures to the
LLM as text; anything else is a real bug in our own code, not an expected
data-coverage gap, and is left to propagate instead of being laundered into
plausible-sounding LLM prose. Returning None from a failure_error_function
makes the SDK re-raise the original exception rather than swallowing it --
see agents.tool._FailureHandlingFunctionToolInvoker.__call__.

describe_web_search_error (web_search.py's Agent.as_tool()-based
web_search_fallback) stays unconditional: a live web search's failures
(network, rate limit, timeout) are external-service hiccups, not bugs in
our own code, so they're always relayed as text so the agent can gracefully
continue without the fallback rather than crashing the whole turn.

Both produce the same "Error: {error}" text shape when they do relay a
message, preserving the original goal of sharing one function across every
tool -- one consistent shape reaching the LLM -- while splitting out the
part of that design that conflated "expected data gap" with "our own bug."
"""

from typing import Any

from agents import RunContextWrapper

from airport_investment_agent.models import AirportDataError


def describe_tool_error(context: RunContextWrapper[Any], error: Exception) -> str | None:
    if isinstance(error, AirportDataError):
        return f"Error: {error}"
    return None


def describe_web_search_error(context: RunContextWrapper[Any], error: Exception) -> str:
    return f"Error: {error}"
