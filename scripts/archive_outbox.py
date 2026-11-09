"""Archive (delete) old processed CRM outbox rows.

Deletes rows with status 'sent' or 'failed' that are older than --archive-days
(default 30). Never touches 'pending' or 'sending' rows.

Usage:
    python scripts/archive_outbox.py [--archive-days N] [--dry-run] [--db-path PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from src.core.config import Config
from src.core.database import Database

logger = logging.getLogger("archive_outbox")


async def archive_outbox(
    db: Database,
    *,
    archive_days: int = 30,
    dry_run: bool = False,
) -> int:
    """Delete processed outbox rows older than archive_days.

    Returns the number of rows that would be/were deleted.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=archive_days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM crm_outbox "
                "WHERE status IN ('sent', 'failed') "
                "AND created_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        count = int(result.scalar_one() or 0)
        if dry_run:
            logger.info(
                "DRY-RUN: would delete %d crm_outbox rows older than %s",
                count,
                cutoff,
            )
            return count
        if count:
            await session.execute(
                text(
                    "DELETE FROM crm_outbox "
                    "WHERE status IN ('sent', 'failed') "
                    "AND created_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            logger.info("Deleted %d crm_outbox rows older than %s", count, cutoff)
        return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive old processed CRM outbox rows."
    )
    parser.add_argument(
        "--archive-days",
        type=int,
        default=30,
        help="Delete sent/failed rows older than N days (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many rows would be deleted without deleting",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (overrides DB_PATH env / default)",
    )
    args = parser.parse_args()

    config = Config()
    if args.db_path is not None:
        # Replace db_path via object replacement; Config is frozen, so rebuild.
        from dataclasses import replace

        config = replace(config, db_path=args.db_path)

    db = Database(config)
    try:
        count = asyncio.run(
            archive_outbox(db, archive_days=args.archive_days, dry_run=args.dry_run)
        )
    finally:
        asyncio.run(db.close())
    print(f"archived: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
