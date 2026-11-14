import json

from agents import Agent, ToolCallItem, ToolCallOutputItem

from airport_investment_agent.utils import logging_utils

# A minimal real Agent, not a hand-rolled stand-in -- ToolCallItem/
# ToolCallOutputItem type their `agent` param as Agent[Any], and nothing
# here reads any of its fields beyond needing it to be weakly-referenceable.
_FAKE_AGENT = Agent(name="fake-agent")


def _tool_call_item(tool_name: str) -> ToolCallItem:
    return ToolCallItem(agent=_FAKE_AGENT, raw_item={"name": tool_name})


def _tool_call_output_item(output) -> ToolCallOutputItem:
    return ToolCallOutputItem(agent=_FAKE_AGENT, raw_item={}, output=output)


def _read_last_entry(log_path) -> dict:
    with log_path.open() as log_file:
        lines = [line for line in log_file if line.strip()]
    return json.loads(lines[-1])


def test_log_run_records_empty_unsupported_numbers_for_a_traceable_answer(
    tmp_path, monkeypatch
):
    log_path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(logging_utils, "RUN_LOG_PATH", log_path)

    new_items = [
        _tool_call_item("get_airport_traffic_tool"),
        _tool_call_output_item({"passengers": 45231890}),
    ]

    logging_utils.log_run(
        "session-1", "traffic at JFK", new_items, "JFK handled 45,231,890 passengers."
    )

    entry = _read_last_entry(log_path)
    assert entry["session_id"] == "session-1"
    assert entry["query"] == "traffic at JFK"
    assert entry["tool_calls"] == ["get_airport_traffic_tool"]
    assert entry["response"] == "JFK handled 45,231,890 passengers."
    assert entry["unsupported_numbers"] == []


def test_log_run_records_unsupported_numbers_for_an_untraceable_answer(
    tmp_path, monkeypatch, capsys
):
    log_path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(logging_utils, "RUN_LOG_PATH", log_path)

    new_items = [_tool_call_output_item({"completion_rate": 0.95})]

    logging_utils.log_run(
        "session-2", "on-time rate at ATL", new_items, "ATL has a 99% on-time rate."
    )

    entry = _read_last_entry(log_path)
    assert entry["unsupported_numbers"] == [99.0]

    captured = capsys.readouterr()
    assert "number-guardrail" in captured.err
    assert "session-2" in captured.err


def test_read_runs_returns_logged_entries_unchanged(tmp_path, monkeypatch):
    log_path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(logging_utils, "RUN_LOG_PATH", log_path)

    logging_utils.log_run("session-3", "query", [], "a response with no numbers")

    runs = logging_utils.read_runs()
    assert len(runs) == 1
    assert runs[0]["session_id"] == "session-3"
    assert runs[0]["unsupported_numbers"] == []
