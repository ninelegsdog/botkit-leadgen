"""Direct coverage of the callback parser's rejection branches.

`src/core/callbacks.py` is the new shared code path; its reject branches (the ones that
decide a payload is not a bare integer) must be exercised by real tests, not just by
reading the source. These are the cases the parser exists to refuse.
"""
from __future__ import annotations

from src.core.callbacks import MAX_CALLBACK_BYTES, callback_is_wellformed, parse_callback_int


def test_accepts_a_bare_positive_integer():
    assert parse_callback_int("p:1", "p:") == 1
    assert parse_callback_int("p:4242", "p:") == 4242


def test_rejects_wrong_prefix_and_missing_data():
    assert parse_callback_int(None, "p:") is None
    assert parse_callback_int("", "p:") is None
    assert parse_callback_int("q:1", "p:") is None
    assert parse_callback_int("p:", "p:") is None


def test_rejects_digits_int_would_have_accepted():
    # int() is happy with a sign, underscores, surrounding spaces and non-ASCII digits;
    # split(":")[1] silently took the first segment of "5:9".
    assert parse_callback_int("p:-1", "p:") is None
    assert parse_callback_int("p:+7", "p:") is None
    assert parse_callback_int("p: 5", "p:") is None
    assert parse_callback_int("p:5 ", "p:") is None
    assert parse_callback_int("p:1_0", "p:") is None
    assert parse_callback_int("p:1.0", "p:") is None
    assert parse_callback_int("p:٥", "p:") is None  # arabic-indic digit five
    assert parse_callback_int("p:5:9", "p:") is None  # extra segment


def test_rejects_an_overlong_digit_run():
    assert parse_callback_int("p:" + "9" * 19, "p:") is None


def test_wellformed_respects_the_64_byte_cap():
    assert MAX_CALLBACK_BYTES == 64
    assert callback_is_wellformed("p:1", "p:") is True
    over = "p:" + "1" * (MAX_CALLBACK_BYTES - 1)
    assert len(over.encode()) > MAX_CALLBACK_BYTES
    assert callback_is_wellformed(over, "p:") is False
