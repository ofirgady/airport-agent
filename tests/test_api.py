from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agents import RawResponsesStreamEvent, Usage
from airport_investment_agent.api import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tools_endpoint_lists_registered_tools():
    response = client.get("/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()}
    assert "get_airport_traffic_tool" in names
    assert "compare_airports_tool" in names
    assert "estimate_unmet_demand_tool" in names
    assert "compare_unmet_demand_tool" in names
    assert "rank_airports_by_region_tool" in names
    assert "rank_airports_nationwide_tool" in names
    assert "compare_congestion_tool" in names
    assert "long_haul_percentage_tool" in names


def test_runs_endpoint_returns_a_list():
    response = client.get("/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def _text_delta_event(delta: str, sequence_number: int) -> RawResponsesStreamEvent:
    return RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            type="response.output_text.delta",
            delta=delta,
            item_id="item-1",
            output_index=0,
            content_index=0,
            sequence_number=sequence_number,
            logprobs=[],
        )
    )


@patch("airport_investment_agent.api.Runner.run_streamed")
def test_chat_endpoint_streams_text_deltas(mock_run_streamed):
    async def fake_stream_events():
        yield _text_delta_event("Hello", 0)
        yield _text_delta_event(" world", 1)

    mock_result = MagicMock()
    mock_result.stream_events = fake_stream_events
    mock_result.new_items = []
    mock_result.final_output = "Hello world"
    mock_result.context_wrapper.usage = Usage()
    mock_run_streamed.return_value = mock_result

    with client.stream(
        "POST", "/chat", json={"session_id": "test", "message": "hi"}
    ) as response:
        body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert b"data: Hello\n\n" in body
    assert b"data:  world\n\n" in body


@patch("airport_investment_agent.api.Runner.run_streamed")
def test_chat_endpoint_returns_500_when_starting_the_run_fails(mock_run_streamed):
    # Runner.run_streamed does real synchronous setup (session/state
    # validation) before any streaming begins, so it can genuinely raise
    # before the response even starts -- that path should still be a plain
    # 500, unlike a failure that happens mid-stream (see the test below).
    mock_run_streamed.side_effect = RuntimeError("boom")

    response = client.post("/chat", json={"session_id": "test", "message": "hello"})

    assert response.status_code == 500


@patch("airport_investment_agent.api.Runner.run_streamed")
def test_chat_endpoint_emits_error_event_on_mid_stream_failure(mock_run_streamed):
    async def failing_stream_events():
        yield _text_delta_event("partial answer", 0)
        raise RuntimeError("mid-stream failure")

    mock_result = MagicMock()
    mock_result.stream_events = failing_stream_events
    mock_run_streamed.return_value = mock_result

    with client.stream(
        "POST", "/chat", json={"session_id": "test", "message": "hi"}
    ) as response:
        body = b"".join(response.iter_bytes())

    # The HTTP response already started streaming by the time the failure
    # happens, so the status is still 200 -- the failure is communicated
    # in-band via an SSE error event instead, which is what a client must
    # actually check for.
    assert response.status_code == 200
    assert b"data: partial answer\n\n" in body
    assert b"event: error" in body
    assert b"mid-stream failure" in body
