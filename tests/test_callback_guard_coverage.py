"""Every parsed callback must be checked for None before it reaches a query.

Replacing `int(callback.data.split(":")[1])` with the validating parser introduced a
branch that did not exist before: the value can now come back None, and the handler has
to answer and stop. Uncovered guards are a coverage regression - the CI gate caught
delivery dropping to 69% against a 70% floor.

The check is line-based on purpose. The handlers are nested inside `create_*_router`, so
module-level introspection cannot reach them, and a behavioural test would not notice a
handler that simply no longer parses callback data at all.
"""
from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

PARSE_CALL = re.compile(r"=\s*parse_callback_int\(")
IMPORT = re.compile(r"^\s*(from|import)\s+.*callbacks")


def _sources() -> list[pathlib.Path]:
    return [p for p in SRC.rglob("*.py") if not IMPORT.match(p.read_text().splitlines()[0] if p.read_text().splitlines() else "")]


def test_every_parsed_callback_is_guarded() -> None:
    unguarded: list[str] = []
    for path in _sources():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if IMPORT.match(line):
                continue
            if not PARSE_CALL.search(line):
                continue
            # The guard is the next non-blank line: `if <name> is None:`
            window = "\n".join(lines[i + 1 : i + 4])
            if "is None" not in window:
                unguarded.append(f"{path.relative_to(SRC)}:{i + 1}")

    assert not unguarded, (
        "parse_callback_int result is used without a None guard at:\n  "
        + "\n  ".join(unguarded)
        + "\nA None would reach the database layer, turning a clear ValueError into an "
        "obscure driver error."
    )


def test_parser_rejects_the_payloads_that_used_to_raise_or_misparse() -> None:
    from src.core.callbacks import parse_callback_int

    # int() accepted these, or raised where split() found no second segment.
    for bad in ("x:-1", "x: 5", "x:1_0", "x:5:9", "x:1.0", "x:+7", None, "x:", "y:1"):
        assert parse_callback_int(bad, "x:") is None, bad
    assert parse_callback_int("x:7", "x:") == 7
