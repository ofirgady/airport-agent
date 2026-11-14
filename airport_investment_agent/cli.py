import argparse
import sys
import time
import uuid

from agents import Runner

from airport_investment_agent.agent import airport_agent
from airport_investment_agent.utils import get_session, log_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airport_investment_agent",
        description="Chat with the airport investment intelligence assistant.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="A single question to ask (one-shot mode). Omit to start an interactive chat.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Reuse a specific session for one-shot mode, to continue an earlier conversation.",
    )
    return parser


def run_one_shot(query: str, session_id: str | None) -> int:
    session = get_session(session_id or "one-shot")
    started = time.monotonic()
    try:
        result = Runner.run_sync(airport_agent, query, session=session)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    log_run(
        session.session_id,
        query,
        result.new_items,
        result.final_output,
        usage=result.context_wrapper.usage,
        latency_seconds=time.monotonic() - started,
    )
    print(result.final_output)
    return 0


def run_interactive() -> int:
    session_id = f"interactive-{uuid.uuid4().hex[:8]}"
    session = get_session(session_id)
    print("Airport Investment Assistant - type 'exit' or 'quit' to leave.")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            return 0
        started = time.monotonic()
        try:
            result = Runner.run_sync(airport_agent, user_input, session=session)
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            continue
        log_run(
            session.session_id,
            user_input,
            result.new_items,
            result.final_output,
            usage=result.context_wrapper.usage,
            latency_seconds=time.monotonic() - started,
        )
        print(result.final_output)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.query:
        return run_one_shot(args.query, args.session_id)
    return run_interactive()


if __name__ == "__main__":
    sys.exit(main())
