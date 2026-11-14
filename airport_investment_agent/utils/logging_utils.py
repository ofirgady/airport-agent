import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agents import ToolCallItem, ToolCallOutputItem, Usage

from airport_investment_agent.utils.number_guardrail import find_unsupported_numbers

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUN_LOG_PATH = DATA_DIR / "runs.jsonl"


def log_run(
    session_id: str,
    query: str,
    new_items: list,
    response: str,
    usage: Usage | None = None,
    latency_seconds: float | None = None,
) -> None:
    tool_calls = [
        item.tool_name for item in new_items if isinstance(item, ToolCallItem)
    ]
    tool_outputs = [
        item.output for item in new_items if isinstance(item, ToolCallOutputItem)
    ]
    unsupported_numbers = find_unsupported_numbers(response, tool_outputs)
    if unsupported_numbers:
        print(
            f"[number-guardrail] session={session_id} numbers not traced to any "
            f"tool output this turn: {unsupported_numbers}",
            file=sys.stderr,
        )

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "query": query,
        "tool_calls": tool_calls,
        "response": response,
        "unsupported_numbers": unsupported_numbers,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "latency_seconds": (
            round(latency_seconds, 3) if latency_seconds is not None else None
        ),
    }
    with RUN_LOG_PATH.open("a") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def read_runs() -> list[dict]:
    if not RUN_LOG_PATH.exists():
        return []
    with RUN_LOG_PATH.open() as log_file:
        return [json.loads(line) for line in log_file if line.strip()]
