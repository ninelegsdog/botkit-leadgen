"""Tracing shim — re-exports botkit_core.tracing + aiogram middleware."""
from __future__ import annotations

from botkit_core.tracing import (
    TracingMiddleware as TracingMiddleware,
)
from botkit_core.tracing import (
    get_current_span as get_current_span,
)
from botkit_core.tracing import (
    set_current_span as set_current_span,
)
from botkit_core.tracing import (
    setup_tracing as setup_tracing,
)

__all__ = [
    "TracingMiddleware",
    "get_current_span",
    "set_current_span",
    "setup_tracing",
]
