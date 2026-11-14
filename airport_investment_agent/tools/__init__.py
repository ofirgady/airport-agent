from agents import Tool

from airport_investment_agent.tools.agent_tools import (
    compare_airports_tool,
    compare_congestion_tool,
    compare_unmet_demand_tool,
    estimate_unmet_demand_tool,
    get_airport_traffic_tool,
    long_haul_percentage_tool,
    rank_airports_by_region_tool,
    rank_airports_nationwide_tool,
)
from airport_investment_agent.tools.web_search import web_search_fallback

# Typed as list[Tool] (not the narrower inferred list[FunctionTool]) because
# list is invariant -- Agent(tools=...) declares list[Tool], and a
# list[FunctionTool] isn't assignable to that even though FunctionTool is a
# Tool subtype.
ALL_TOOLS: list[Tool] = [
    get_airport_traffic_tool,
    compare_airports_tool,
    estimate_unmet_demand_tool,
    compare_unmet_demand_tool,
    rank_airports_by_region_tool,
    rank_airports_nationwide_tool,
    compare_congestion_tool,
    long_haul_percentage_tool,
    web_search_fallback,
]
