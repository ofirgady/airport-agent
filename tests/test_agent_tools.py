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
from airport_investment_agent.tools.tool_errors import (
    describe_tool_error,
    describe_web_search_error,
)


def test_tools_are_registered_with_expected_names():
    assert get_airport_traffic_tool.name == "get_airport_traffic_tool"
    assert compare_airports_tool.name == "compare_airports_tool"
    assert estimate_unmet_demand_tool.name == "estimate_unmet_demand_tool"
    assert compare_unmet_demand_tool.name == "compare_unmet_demand_tool"
    assert rank_airports_by_region_tool.name == "rank_airports_by_region_tool"
    assert rank_airports_nationwide_tool.name == "rank_airports_nationwide_tool"
    assert compare_congestion_tool.name == "compare_congestion_tool"
    assert long_haul_percentage_tool.name == "long_haul_percentage_tool"


def test_tool_descriptions_are_distinct_enough_to_avoid_routing_confusion():
    descriptions = {
        get_airport_traffic_tool.description,
        compare_airports_tool.description,
        estimate_unmet_demand_tool.description,
        compare_unmet_demand_tool.description,
        rank_airports_by_region_tool.description,
        rank_airports_nationwide_tool.description,
        compare_congestion_tool.description,
        long_haul_percentage_tool.description,
    }
    assert len(descriptions) == 8


def test_get_airport_traffic_tool_schema_requires_iata_code():
    schema = get_airport_traffic_tool.params_json_schema
    assert "iata_code" in schema["required"]


def test_compare_airports_tool_schema_requires_codes_list():
    schema = compare_airports_tool.params_json_schema
    assert "codes" in schema["required"]
    assert schema["properties"]["codes"]["type"] == "array"


def test_compare_unmet_demand_tool_schema_requires_both_airports():
    schema = compare_unmet_demand_tool.params_json_schema
    assert "airport_a" in schema["required"]
    assert "airport_b" in schema["required"]


def test_rank_airports_by_region_tool_schema_requires_region_name():
    schema = rank_airports_by_region_tool.params_json_schema
    assert "region_name" in schema["required"]


def test_rank_airports_nationwide_tool_schema_requires_no_arguments():
    schema = rank_airports_nationwide_tool.params_json_schema
    assert not schema.get("required")


def test_compare_congestion_tool_schema_requires_both_airports():
    schema = compare_congestion_tool.params_json_schema
    assert "airport_a" in schema["required"]
    assert "airport_b" in schema["required"]


def test_long_haul_percentage_tool_schema_requires_iata_code():
    schema = long_haul_percentage_tool.params_json_schema
    assert "iata_code" in schema["required"]


def test_domain_tools_share_one_failure_error_function_web_search_uses_another():
    """Regression test for two related rules (all tools must produce a
    consistently-shaped error message, AND a domain-tool bug must
    not be laundered into LLM-narrated text the same way an expected data
    error is) together: the 6 domain tools share describe_tool_error --
    narrow, only a known AirportDataError is relayed, anything else
    propagates as a real failure. web_search_fallback uses the separate,
    intentionally more permissive describe_web_search_error, since its
    failures (network, rate limit, timeout) are external-service hiccups,
    not bugs in our own code."""
    domain_tools = [
        get_airport_traffic_tool,
        compare_airports_tool,
        estimate_unmet_demand_tool,
        compare_unmet_demand_tool,
        rank_airports_by_region_tool,
        rank_airports_nationwide_tool,
        compare_congestion_tool,
        long_haul_percentage_tool,
    ]
    for tool in domain_tools:
        assert tool._failure_error_function is describe_tool_error

    assert web_search_fallback._failure_error_function is describe_web_search_error
    assert web_search_fallback._failure_error_function is not describe_tool_error


def test_both_failure_error_functions_produce_the_same_text_shape_when_relayed():
    """The split above must not reintroduce the original inconsistent-shape bug --
    when either function does relay an error, the text shape must still
    match, so the LLM sees a consistent format regardless of which tool
    failed."""
    from airport_investment_agent.models.errors import AirportDataError

    error = AirportDataError("boom")
    assert (
        describe_tool_error(None, error)
        == describe_web_search_error(None, error)
        == "Error: boom"
    )
