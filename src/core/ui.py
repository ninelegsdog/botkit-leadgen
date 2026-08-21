from __future__ import annotations

import html
import json
from typing import Any


def escape(text: str | None) -> str:
    return html.escape(str(text)) if text else ""


def mask_phone(phone: str | None) -> str:
    if not phone or len(phone) < 7:
        return "***"
    return phone[:4] + "(***)" + phone[-2:]


def lead_card(lead: dict[str, Any], *, masked: bool = True) -> str:
    phone = mask_phone(lead.get("client_phone")) if masked else str(lead.get("client_phone", ""))
    fields: dict[str, Any] = {}
    if lead.get("field_values"):
        fields = json.loads(str(lead["field_values"]))
    lines = [
        f"🔔 Новый лид! #{lead['id']}",
        f"Имя: {escape(str(lead.get('client_name', '')))}",
        f"Телефон: {phone}",
    ]
    for k, v in fields.items():
        lines.append(f"{escape(k)}: {escape(str(v))}")
    return "\n".join(lines)


def lead_summary(lead: dict[str, Any]) -> str:
    fields: dict[str, Any] = {}
    if lead.get("field_values"):
        fields = json.loads(str(lead["field_values"]))
    lines = [f"📝 Заявка #{lead['id']}"]
    for k, v in fields.items():
        lines.append(f"  {escape(k)}: {escape(str(v))}")
    lines.append(f"  Имя: {escape(str(lead.get('client_name', '')))}")
    lines.append(f"  Телефон: {escape(str(lead.get('client_phone', '')))}")
    return "\n".join(lines)
