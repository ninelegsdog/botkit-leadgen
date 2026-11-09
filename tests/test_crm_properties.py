"""Property-based tests for CRM payload serialization (Hypothesis).

Tests that ``build_payload`` always produces valid, round-trippable JSON and
that no lead shape can break the serializer — protecting against a malformed
payload being retried forever in the outbox.

Serializer rules (src/crm/service.build_payload):
  * field_values=None or {}  -> stored as "{}" string
  * field_values=non-empty dict -> stored as JSON string of that dict
  * field_values=string -> stored as-is (must be valid JSON for round-trip)
  * created_at=None -> utc_now() timestamp
  * All fields always present in output
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

from src.crm.service import build_payload, utc_now

# Strategies mirroring real lead shapes from Telegram handlers.
_client_name = st.one_of(st.none(), st.text(min_size=0, max_size=200))
_client_phone = st.one_of(st.none(), st.text(min_size=0, max_size=50))
_created_at = st.one_of(st.none(), st.text(min_size=0, max_size=100))

# Non-empty dict: round-trips exactly through JSON stringification.
_field_values_dict_nonempty = st.dictionaries(
    st.text(min_size=1, max_size=50),
    st.one_of(st.text(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.booleans()),
    min_size=1,
    max_size=20,
)

# field_values shapes the serializer normalizes to "{}" (parses to {} dict).
_field_values_empty_like: st.SearchStrategy[Any] = st.one_of(st.none(), st.just({}), st.just("{}"))

# Any field_values shape — used for "never raises" and "valid JSON" tests.
_field_values_any = st.one_of(
    st.none(),
    st.text(max_size=200),
    st.dictionaries(
        st.text(min_size=1, max_size=50),
        st.one_of(st.text(), st.integers(), st.booleans()),
        max_size=20,
    ),
)

_lead_dict = st.dictionaries(
    st.sampled_from(["id", "client_name", "client_phone", "field_values", "created_at"]),
    st.one_of(st.integers(), st.text(max_size=200), st.none()),
    min_size=1,
    max_size=5,
)


@settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    phases=[Phase.generate, Phase.target],
)
@given(lead=_lead_dict)
def test_build_payload_is_valid_json(lead: dict[str, Any]) -> None:
    """Every lead shape must serialize to parseable JSON."""
    payload = build_payload(lead)
    parsed = json.loads(payload)
    assert isinstance(parsed, dict)


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(
    client_name=_client_name,
    client_phone=_client_phone,
    field_values=_field_values_dict_nonempty,
    created_at=_created_at,
    lead_id=st.integers(min_value=0, max_value=10**9),
)
def test_build_payload_dict_field_values_round_trip(
    client_name: str | None,
    client_phone: str | None,
    field_values: dict[str, Any],
    created_at: str | None,
    lead_id: int,
) -> None:
    """Non-empty dict field_values round-trips exactly through JSON."""
    lead = {
        "id": lead_id,
        "client_name": client_name,
        "client_phone": client_phone,
        "field_values": field_values,
        "created_at": created_at,
    }
    parsed = json.loads(build_payload(lead))
    assert parsed["id"] == lead_id
    assert parsed["client_name"] == client_name
    assert parsed["client_phone"] == client_phone
    assert parsed["field_values"] == field_values
    assert parsed["created_at"] == (created_at if created_at else parsed["created_at"])


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(
    field_values=_field_values_empty_like,
    lead_id=st.integers(min_value=0, max_value=10**9),
)
def test_build_payload_empty_field_values_normalizes_to_empty_json(
    field_values: str | dict[str, Any] | None,
    lead_id: int,
) -> None:
    """None / {} / "{}" all normalize to "{}" which parses to {}."""
    lead = {
        "id": lead_id,
        "client_name": "Test",
        "client_phone": "+7",
        "field_values": field_values,
    }
    parsed = json.loads(build_payload(lead))
    assert json.loads(parsed["field_values"]) == {}


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(lead=_lead_dict)
def test_build_payload_never_raises(lead: dict[str, Any]) -> None:
    """build_payload must never raise — a bad payload must not poison the outbox."""
    payload = build_payload(lead)
    assert isinstance(payload, str)
    assert len(payload) > 0
    json.loads(payload)  # must be parseable


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    client_name=st.text(max_size=100),
    client_phone=st.text(max_size=50),
    field_values=st.dictionaries(st.text(min_size=1, max_size=30), st.text(max_size=100), max_size=10),
    lead_id=st.integers(min_value=1, max_value=10**6),
)
def test_build_payload_contains_required_keys(
    client_name: str,
    client_phone: str,
    field_values: dict[str, Any],
    lead_id: int,
) -> None:
    """Payload must always contain the five required keys."""
    lead = {
        "id": lead_id,
        "client_name": client_name,
        "client_phone": client_phone,
        "field_values": json.dumps(field_values, ensure_ascii=False),
    }
    parsed = json.loads(build_payload(lead))
    for key in ("id", "client_name", "client_phone", "field_values", "created_at"):
        assert key in parsed, f"missing key {key!r} in payload {parsed!r}"


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(ts=st.datetimes())
def test_utc_now_format_matches_payload_created_at(ts: datetime) -> None:
    """utc_now() produces the same format used for missing created_at."""
    produced = utc_now()
    assert len(produced) == 19  # "YYYY-MM-DD HH:MM:SS"
    assert produced[4] == "-" and produced[7] == "-"
    assert produced[10] == " " and produced[13] == ":" and produced[16] == ":"
