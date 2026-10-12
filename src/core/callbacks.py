"""Callback parsing shim — re-exports botkit_core.callbacks.

`botkit-core` is pinned by tag. Where the pinned tag does not yet carry
`botkit_core.callbacks`, the parser is kept here so this bot's handlers do not have to
wait for a library release. Switching to the shared module is a one-line import change.
"""
from __future__ import annotations

MAX_CALLBACK_BYTES = 64


def parse_callback_int(data: str | None, prefix: str) -> int | None:
    """Return the integer argument of `"<prefix><n>"`, or None if it is not exactly that.

    Returns None rather than raising so a handler can answer normally instead of pushing
    a ValueError into the error middleware. Rejects extra segments, whitespace, signs and
    over-long digit runs - `int()` alone would accept `"-1"`, `" 5"`, `"5:9"` and `"1_0"`.
    """
    if not data or not data.startswith(prefix):
        return None
    raw = data[len(prefix) :]
    if not raw or len(raw) > 18:
        return None
    if not raw.isascii() or not raw.isdigit():
        return None
    return int(raw)


def callback_is_wellformed(data: str | None, prefix: str) -> bool:
    """True when `data` is a well-formed `"<prefix><n>"` within the 64-byte cap."""
    if data is not None and len(data.encode()) > MAX_CALLBACK_BYTES:
        return False
    return parse_callback_int(data, prefix) is not None
