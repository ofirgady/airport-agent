from agents import WebSearchTool

from airport_investment_agent.tools.tool_errors import describe_web_search_error
from airport_investment_agent.tools.web_search import web_search_agent, web_search_fallback


def test_web_search_agent_is_named_and_equipped_with_web_search_tool():
    assert web_search_agent.name == "Airport Web Search Fallback"
    assert len(web_search_agent.tools) == 1
    assert isinstance(web_search_agent.tools[0], WebSearchTool)


def test_web_search_fallback_tool_is_registered_with_expected_name():
    assert web_search_fallback.name == "web_search_fallback"


def test_web_search_fallback_uses_the_web_search_specific_error_function():
    """Module-local check of the same fact test_agent_tools.py's
    test_domain_tools_share_one_failure_error_function_web_search_uses_another
    already verifies cross-tool -- kept here too so this file
    stands alone as complete coverage of web_search.py."""
    assert web_search_fallback._failure_error_function is describe_web_search_error


def test_web_search_agent_instructions_forbid_scoring():
    """The main agent's own system prompt (agent.py) tells the LLM to treat
    web_search_fallback as background only and never let it affect a score
    -- this sub-agent's own instructions must carry the same constraint,
    not rely solely on the caller remembering to enforce it."""
    instructions = web_search_agent.instructions
    assert "never state or imply an investment" in instructions.lower()


def test_web_search_fallback_description_states_context_only():
    assert "context only" in web_search_fallback.description.lower()
    assert "never a scoring input" in web_search_fallback.description.lower()
