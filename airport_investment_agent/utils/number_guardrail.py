"""Deterministic, advisory-only check: does every number in the agent's
final reply trace back to a number that actually appeared in that turn's
tool call outputs?

This is a post-hoc check over `Runner.run`'s already-available
`result.new_items`/`result.final_output` -- not the SDK's `@output_guardrail`
mechanism, which only receives `(context, agent, agent_output)` and would
need a custom context threaded through every tool to see tool outputs. Soft/
advisory: this module only detects and reports, it never blocks a reply.
"""

import re
from typing import Any

_SUFFIX_WORD = r"[Mm]illion|[Bb]illion"
_SUFFIX_LETTER = r"M|B"
_NUMBER_RE = re.compile(
    rf"(?<!\w)([+-]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?)"
    rf"(?:\s?({_SUFFIX_WORD}|{_SUFFIX_LETTER})\b)?"
    r"(\s?%)?"
)

_IGNORABLE_MAX_ABS_INT = 9
_IGNORABLE_YEAR_MIN = 1990
_IGNORABLE_YEAR_MAX = 2099

_BASE_TOLERANCE = 0.05
_RELATIVE_TOLERANCE = 0.02


def extract_numbers_from_text(text: str) -> list[float]:
    """Pull numeric tokens out of prose: handles thousands-separator commas,
    a leading +/- sign (growth rates are printed like "+3.2%"), a trailing
    %, and a million/billion/M/B magnitude suffix (e.g. "45 million",
    "45M")."""
    numbers: list[float] = []
    for raw_number, suffix, _percent in _NUMBER_RE.findall(text):
        value = float(raw_number.replace(",", ""))
        if suffix:
            if suffix.lower().startswith("m"):
                value *= 1_000_000
            elif suffix.lower().startswith("b"):
                value *= 1_000_000_000
        numbers.append(value)
    return numbers


def _is_ignorable(value: float) -> bool:
    """List/rank ordinals (e.g. "1.", "#2") and calendar years ("2026",
    a BTS data-period year) aren't invented statistics -- flagging them
    would be pure noise, not a real signal."""
    if value != int(value):
        return False
    magnitude = abs(int(value))
    if magnitude <= _IGNORABLE_MAX_ABS_INT:
        return True
    return _IGNORABLE_YEAR_MIN <= magnitude <= _IGNORABLE_YEAR_MAX


def _collect_leaf_numbers(value: Any, into: set[float]) -> None:
    if isinstance(value, bool):
        return  # bool is an int subclass; not a "number" a user would cite
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        into.add(numeric_value)
        if -1.0 <= numeric_value <= 1.0:
            # Ratio fields (load_factor, completion_rate, every *_score,
            # and growth_rate -- which can be negative) are stored as a
            # -1..1 fraction but may reasonably be restated as a percentage.
            into.add(round(numeric_value * 100, 6))
        return
    if isinstance(value, str):
        into.update(extract_numbers_from_text(value))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_leaf_numbers(item, into)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_leaf_numbers(item, into)
        return
    # Anything else (None, etc.) contributes no numbers.


def collect_observed_numbers(tool_outputs: list[Any]) -> set[float]:
    """Every number that actually appeared anywhere in this turn's tool
    call outputs -- scalar fields, ratio-to-percent conversions, and
    numbers embedded in narrative/caveat/explanation/diagnostic/summary
    strings alike."""
    observed: set[float] = set()
    for output in tool_outputs:
        _collect_leaf_numbers(output, observed)
    return observed


def _matches_any(value: float, observed: set[float]) -> bool:
    for candidate in observed:
        tolerance = max(_BASE_TOLERANCE, _RELATIVE_TOLERANCE * abs(candidate))
        if abs(value - candidate) <= tolerance:
            return True
    return False


def find_unsupported_numbers(final_output: str, tool_outputs: list[Any]) -> list[float]:
    """Numbers in `final_output` that don't trace back (within a small
    rounding tolerance) to any number in `tool_outputs`. Advisory only --
    an empty list is the expected common case, a non-empty one is a signal
    worth a human look, not proof of a hallucination."""
    observed = collect_observed_numbers(tool_outputs)
    unsupported: list[float] = []
    seen: set[float] = set()
    for value in extract_numbers_from_text(final_output):
        if _is_ignorable(value) or value in seen:
            continue
        seen.add(value)
        if not _matches_any(value, observed):
            unsupported.append(value)
    return unsupported
