from agents import Agent, WebSearchTool

from airport_investment_agent.tools.tool_errors import describe_web_search_error

web_search_agent = Agent(
    name="Airport Web Search Fallback",
    instructions=(
        "Search the web for airport- or aviation-related information that the "
        "deterministic tools cannot provide -- either because it's outside "
        "their subject matter (for example, an airport's recent news, "
        "expansions, incidents, or investment announcements) or because it's "
        "about a time period beyond the dataset's known coverage (for example "
        "a question about 'now', 'current', or 'the latest' conditions). "
        "Summarize the most relevant findings in 2-3 sentences. This is "
        "contextual background only -- never state or imply an investment "
        "score or ranking; that comes only from the deterministic scoring "
        "tools. Stay within airport/aviation subject matter; do not answer "
        "unrelated general-knowledge questions."
    ),
    tools=[WebSearchTool()],
)

web_search_fallback = web_search_agent.as_tool(
    tool_name="web_search_fallback",
    tool_description=(
        "Fall back to a live web search for airport/aviation questions the "
        "deterministic tools can't answer -- either off their subject matter "
        "(recent news, expansions, incidents, investment announcements) or "
        "beyond the dataset's known time coverage (current/latest/now). "
        "Context only, never a scoring input."
    ),
    failure_error_function=describe_web_search_error,
)
