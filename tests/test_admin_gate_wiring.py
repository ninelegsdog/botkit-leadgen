"""The admin password check must be rate-limited and timing-safe.

Before this change `check_password` compared `message.text == config.admin_password` with
no attempt limit, so the admin surface had unlimited password guesses and the comparison
was timing-observable. `AdminGate` was imported by the module's tests but never wired into
the router. These tests pin the behaviour that is actually reachable from Telegram.
"""
from __future__ import annotations

import time

from botkit_core.admin import AdminGate

PASSWORD = "correct horse battery staple"


def test_wrong_password_is_recorded_and_throttles() -> None:
    gate = AdminGate(PASSWORD, [1])
    uid = 42
    assert gate.authorize(uid, "nope") is False
    assert not gate.is_throttled(uid)
    for _ in range(4):
        gate.authorize(uid, "nope")
    assert gate.is_throttled(uid) is True
    # authorize() itself accepts the correct password even inside the window (an admin who
    # types correctly is not locked out). The router therefore checks is_throttled BEFORE
    # calling authorize — that gate is what refuses guesses during the window.
    assert gate.authorize(uid, PASSWORD) is True


def test_correct_password_authorises_and_clears_attempts() -> None:
    gate = AdminGate(PASSWORD, [])
    uid = 7
    gate.authorize(uid, "nope")
    assert gate.authorize(uid, PASSWORD) is True
    assert gate.is_admin(uid) is True
    assert gate.is_throttled(uid) is False


def test_throttle_window_expires() -> None:
    gate = AdminGate(PASSWORD, [])
    gate._throttle_window = 0.2  # shrink instead of sleeping
    uid = 9
    for _ in range(5):
        gate.authorize(uid, "nope")
    assert gate.is_throttled(uid) is True
    time.sleep(0.25)
    assert gate.is_throttled(uid) is False


def test_deauthorised_user_loses_access() -> None:
    gate = AdminGate(PASSWORD, [])
    gate.authorize(9, PASSWORD)
    assert gate.is_admin(9) is True
    gate.deauthorize(9)
    assert gate.is_admin(9) is False


def test_config_admins_are_admins_without_a_password() -> None:
    gate = AdminGate(PASSWORD, [5])
    assert gate.is_admin(5) is True
    assert gate.is_admin(6) is False

