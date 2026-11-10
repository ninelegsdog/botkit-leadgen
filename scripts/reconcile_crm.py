"""Reconcile CRM outbox sent rows with actual CRM leads.

Compares crm_outbox rows with status='sent' against leads reported by the CRM
provider (via its list endpoint). Reports leads that are marked as sent in the
outbox but missing from the CRM — candidates for manual re-delivery.

Usage:
    python scripts/reconcile_crm.py [--provider bitrix24|amocrm|generic] [--db-path PATH]

Requires CRM_PROVIDER and CRM_* env vars to be set (same as the bot).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from src.core.config import Config
from src.core.database import Database
from src.crm.adapters import CrmSettings

logger = logging.getLogger("reconcile_crm")


async def fetch_crm_lead_ids(
    settings: CrmSettings, client: Any, limit: int = 500
) -> set[str]:
    """Fetch lead IDs from the CRM provider.

    Bitrix24: crm.lead.list with ID filter.
    AmoCRM: GET /api/v4/leads with limit.
    Generic: not supported (no list endpoint) — returns empty set.
    """
    import httpx

    if client is None:
        client = httpx.AsyncClient(timeout=settings.timeout)
        owned = True
    else:
        owned = False

    try:
        if settings.provider == "bitrix24":
            url = (
                f"{settings.base_url}/rest/{settings.bitrix_user_id}/"
                f"{settings.bitrix_webhook_token}/crm.lead.list.json"
            )
            params = {"select": ["ID"], "limit": limit}
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return {str(item["ID"]) for item in data.get("result", [])}

        if settings.provider == "amocrm":
            url = f"{settings.base_url}/api/v4/leads"
            headers = {"Authorization": f"Bearer {settings.access_token}"}
            response = await client.get(url, params={"limit": limit}, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                str(lead["id"])
                for lead in data.get("_embedded", {}).get("leads", [])
            }

        # Generic has no standard list endpoint.
        return set()
    finally:
        if owned:
            await client.aclose()


async def reconcile(
    db: Database,
    settings: CrmSettings,
    *,
    limit: int = 500,
) -> dict[str, Any]:
    """Reconcile sent outbox rows with CRM lead IDs.

    Returns a dict with counts and details of discrepancies.
    """
    # Get sent outbox rows with external_id
    async with db.session() as session:
        result = await session.execute(
            """
            SELECT id, lead_id, provider, payload, external_id
            FROM crm_outbox
            WHERE status = 'sent'
            ORDER BY id
            LIMIT :limit
            """,
            {"limit": limit},
        )
        rows = [dict(r) for r in result.mappings().all()]

    crm_lead_ids = await fetch_crm_lead_ids(settings, None, limit=limit)

    missing_from_crm = []
    for row in rows:
        ext_id = row["external_id"]
        if ext_id and ext_id not in crm_lead_ids:
            missing_from_crm.append(row)

    return {
        "outbox_sent_count": len(rows),
        "crm_lead_count": len(crm_lead_ids),
        "missing_from_crm_count": len(missing_from_crm),
        "missing_from_crm": missing_from_crm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile CRM outbox sent rows with CRM leads."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max outbox rows to check (default: 500)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (overrides DB_PATH env / default)",
    )
    args = parser.parse_args()

    config = Config()
    if args.db_path is not None:
        from dataclasses import replace

        config = replace(config, db_path=args.db_path)

    db = Database(config)
    try:
        result = asyncio.run(reconcile(db, CrmSettings.from_config(config), limit=args.limit))
    finally:
        asyncio.run(db.close())

    print(
        f"Outbox sent: {result['outbox_sent_count']}, "
        f"CRM leads: {result['crm_lead_count']}, "
        f"Missing from CRM: {result['missing_from_crm_count']}"
    )
    for row in result["missing_from_crm"]:
        payload = json.loads(row["payload"])
        print(
            f"  outbox_id={row['id']} lead_id={row['lead_id']} "
            f"external_id={row['external_id']} name={payload.get('client_name')}"
        )
    return 0 if result["missing_from_crm_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
