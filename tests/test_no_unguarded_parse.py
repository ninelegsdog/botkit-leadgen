"""Every callback handler must parse client data through the validating parser.

`int(callback.data.split(":")[1])` had two defects: `int()` accepts `"-1"`, `" 5"`,
`"1_0"` and non-ASCII digits, and `split(":")[1]` silently takes the first segment of
`"5:9"` while raising ValueError on anything without a second segment. Callback data is
client-controlled, so anything parsed out of it is untrusted input.

These tests read the handler sources rather than driving Telegram: the point is that no
site is left using the unguarded form, which a behavioural test would not catch if the
handler happened to be unreachable.
"""
from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

UNGUARDED = re.compile(r"int\(\s*callback\.data\.split\(")


def _handler_sources() -> list[pathlib.Path]:
    return [p for p in SRC.rglob("*.py") if "callbacks.py" not in p.name]


def test_no_handler_uses_the_unguarded_parse() -> None:
    offenders = []
    for path in _handler_sources():
        text = path.read_text(encoding="utf-8")
        if UNGUARDED.search(text):
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, (
        f"these files still parse callback data unguarded: {offenders}. "
        f"Use parse_callback_int(callback.data, '<prefix>:') and guard the None."
    )


def test_parser_is_importable() -> None:
    from src.core.callbacks import parse_callback_int

    assert parse_callback_int("x:7", "x:") == 7
    assert parse_callback_int("x:-7", "x:") is None
    assert parse_callback_int("x:5:9", "x:") is None
    assert parse_callback_int("x: 5", "x:") is None
    assert parse_callback_int(None, "x:") is None

