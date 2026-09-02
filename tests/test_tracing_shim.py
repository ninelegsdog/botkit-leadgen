"""Cover src/core/tracing.py shim."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.tracing import (
    TracingMiddleware,
    get_current_span,
    set_current_span,
)


def test_get_set_current_span() -> None:
    assert get_current_span() is None
    mock_span = MagicMock()
    set_current_span(mock_span)
    assert get_current_span() is mock_span
    set_current_span(None)
    assert get_current_span() is None


@patch("src.core.tracing.setup_tracing")
def test_setup_tracing_called(mock_setup) -> None:
    mock_tracer = MagicMock()
    mock_setup.return_value = mock_tracer

    from src.core.tracing import setup_tracing

    tracer = setup_tracing(service_name="bookingbot", otlp_endpoint="http://localhost:4318/v1/traces")

    mock_setup.assert_called_once_with(service_name="bookingbot", otlp_endpoint="http://localhost:4318/v1/traces")
    assert tracer is mock_tracer


@pytest.mark.asyncio
async def test_tracing_middleware_creates_span() -> None:
    with patch("botkit_core.tracing.trace.get_tracer") as mock_get_tracer:
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span
        mock_get_tracer.return_value = mock_tracer

        mw = TracingMiddleware()

        class Event:
            update_id = 123
            __class__ = type("Message", (), {"__name__": "Message"})

        event = Event()
        data = {}

        async def handler(ev, dt):
            return "result"

        result = await mw(handler, event, data)

        assert result == "result"
        mock_tracer.start_as_current_span.assert_called_once()
        call_kwargs = mock_tracer.start_as_current_span.call_args[1]
        assert call_kwargs["kind"] is not None
        assert "botkit.update_id" in call_kwargs["attributes"]
        mock_span.set_status.assert_called()
