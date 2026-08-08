from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from linearplus.client import LinearGraphQLError

from eidos_linear.client import (
    DEFAULT_ACCOUNT_ENV,
    DEFAULT_STALE_HOURS,
    build_client,
    credential_blocker,
    resolve_mirror_path,
    resolved_account,
)

try:
    from lineardb.graphql import LinearGraphQLClient
    from lineardb.mirror import account_mirror_dump
    from lineardb.schema import write_mirror_sqlite
except ImportError:  # pragma: no cover
    LinearGraphQLClient = None
    account_mirror_dump = None
    write_mirror_sqlite = None


def mirror_status(
    account: str | None = None,
    sqlite: str | None = None,
    stale_hours: float = DEFAULT_STALE_HOURS,
) -> dict[str, Any]:
    """Read-only SQLite mirror health. Does not call Linear."""
    account_name = account or os.environ.get(DEFAULT_ACCOUNT_ENV)
    try:
        path = resolve_mirror_path(account=account, sqlite=sqlite)
    except Exception:
        path = Path(sqlite).expanduser().resolve() if sqlite else Path.home() / ".lineardb" / "mirrors" / "unknown.sqlite"
    exists = path.is_file()

    if not exists:
        return {
            "ok": False,
            "operation": "eidos_sync_status",
            "account": account_name,
            "sqlite": str(path),
            "exists": False,
            "stale": True,
            "stale_hours": None,
            "last_sync_at": None,
            "team_count": 0,
            "issue_count": 0,
            "latest_sync_run_id": None,
            "remediation": "Call eidos_account_sync to refresh the canonical mirror.",
        }

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        latest_run_id = _metadata_value(connection, "latest_sync_run_id")
        last_sync_at = None
        if latest_run_id:
            row = connection.execute(
                "select finished_at from sync_runs where id = ?",
                (latest_run_id,),
            ).fetchone()
            if row:
                last_sync_at = row["finished_at"]
        if not last_sync_at:
            row = connection.execute(
                "select finished_at from sync_runs order by finished_at desc limit 1"
            ).fetchone()
            if row:
                last_sync_at = row["finished_at"]

        team_count = connection.execute("select count(*) from teams").fetchone()[0]
        issue_count = connection.execute("select count(*) from issues").fetchone()[0]

    age_hours = _age_hours(last_sync_at)
    stale = age_hours is None or age_hours > stale_hours

    return {
        "ok": not stale,
        "operation": "eidos_sync_status",
        "account": account_name,
        "sqlite": str(path),
        "exists": True,
        "stale": stale,
        "stale_hours": age_hours,
        "stale_threshold_hours": stale_hours,
        "last_sync_at": last_sync_at,
        "team_count": team_count,
        "issue_count": issue_count,
        "latest_sync_run_id": latest_run_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _metadata_value(connection: sqlite3.Connection, key: str) -> str | None:
    try:
        row = connection.execute("select value from metadata where key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _age_hours(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return round(delta.total_seconds() / 3600, 2)


def account_sync(
    account: str | None = None,
    sqlite: str | None = None,
    skip_related: bool = False,
    team_page_size: int = 100,
    issue_page_size: int = 100,
    related_page_size: int = 100,
    sample_size: int = 20,
) -> dict[str, Any]:
    """Mirror all accessible Linear teams into the canonical SQLite path."""
    account_name = resolved_account(account)
    path = resolve_mirror_path(account=account_name, sqlite=sqlite)

    if account_mirror_dump is None or write_mirror_sqlite is None or LinearGraphQLClient is None:
        return {
            "ok": False,
            "operation": "eidos_account_sync",
            "account": account_name,
            "blocked": "missing_lineardb",
            "message": "Install lineardb to run account sync.",
        }

    try:
        client = build_client(account=account_name)
        ldb_client = LinearGraphQLClient(
            token=client.token,
            endpoint=client.endpoint,
            max_retries=client.max_retries,
            retry_sleep_seconds=client.retry_sleep_seconds,
        )
        dump = account_mirror_dump(
            ldb_client,
            account=account_name,
            team_page_size=team_page_size,
            issue_page_size=issue_page_size,
            sample_size=sample_size,
            include_related=not skip_related,
            related_page_size=related_page_size,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        write_mirror_sqlite(dump, path)
        return {
            "ok": True,
            "operation": "eidos_account_sync",
            "account": account_name,
            "sqlite": str(path),
            "team_count": len(dump["teams"]),
            "issue_count": dump["analytics"]["totals"]["issues"],
            "related_counts": {key: len(value) for key, value in (dump.get("related") or {}).items()},
            "analytics": dump["analytics"],
        }
    except LinearGraphQLError as exc:
        return {
            "ok": False,
            "operation": "eidos_account_sync",
            "account": account_name,
            "blocked": "linear_graphql_error",
            "errors": exc.errors,
        }
    except Exception as exc:
        blocker = credential_blocker(exc)
        return {"ok": False, "operation": "eidos_account_sync", "account": account_name, **blocker}