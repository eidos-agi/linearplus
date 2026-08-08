from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from linearplus.client import LinearGraphQLError, MissingTokenError

from eidos_linear.client import (
    DEFAULT_STALE_HOURS,
    auth_check,
    build_client,
    credential_blocker,
    resolve_mirror_path,
    resolved_account,
)
from eidos_linear.tools.sync import mirror_status


def eidos_proof(
    account: str | None = None,
    team_key: str | None = None,
    sqlite: str | None = None,
    stale_hours: float = DEFAULT_STALE_HOURS,
) -> dict[str, Any]:
    """Doctor gate: token, team access, and optional mirror freshness."""
    try:
        account_name = resolved_account(account)
    except MissingTokenError as exc:
        blocker = credential_blocker(exc)
        return {
            "ok": False,
            "operation": "eidos_proof",
            "verdict": "BLOCK",
            "account": None,
            "team_key": team_key,
            "checks": [{"check": "account", "ok": False, "message": blocker["message"]}],
            **blocker,
        }

    try:
        from lineardb.auth import default_team_key
    except ImportError:  # pragma: no cover
        default_team_key = None  # type: ignore[assignment]

    resolved_team_key = team_key
    if not resolved_team_key and default_team_key is not None:
        try:
            resolved_team_key = default_team_key(account_name)
        except Exception:
            resolved_team_key = None
    if not resolved_team_key:
        return {
            "ok": False,
            "operation": "eidos_proof",
            "verdict": "BLOCK",
            "account": account_name,
            "blocked": "missing_team_key",
            "message": "Pass team_key= or set LINEARDB_<ACCOUNT>_TEAM_KEY for the account.",
        }

    checks: list[dict[str, Any]] = []
    verdict = "CLEAR"

    try:
        client = build_client(account=account_name)
        checks.append({"check": "token", "ok": True, "account": account_name})
    except Exception as exc:
        blocker = credential_blocker(exc)
        return {
            "ok": False,
            "operation": "eidos_proof",
            "verdict": "BLOCK",
            "account": account_name,
            "team_key": team_key,
            "checks": [{"check": "token", "ok": False, "message": blocker["message"]}],
            **blocker,
        }

    try:
        auth = auth_check(client, team_key=resolved_team_key)
        team_ok = bool(auth.get("has_required_team"))
        checks.append(
            {
                "check": "team_access",
                "ok": team_ok,
                "team_key": resolved_team_key,
                "team_keys": auth.get("team_keys") or [],
                "viewer_email": (auth.get("viewer") or {}).get("email"),
            }
        )
        if not team_ok:
            verdict = "BLOCK"
    except LinearGraphQLError as exc:
        checks.append({"check": "team_access", "ok": False, "errors": exc.errors})
        verdict = "BLOCK"
        auth = {}
    except Exception as exc:
        checks.append({"check": "team_access", "ok": False, "message": str(exc)})
        verdict = "BLOCK"
        auth = {}

    mirror_path = str(resolve_mirror_path(account=account_name, sqlite=sqlite))
    mirror = mirror_status(account=account_name, sqlite=mirror_path, stale_hours=stale_hours)
    mirror_ok = mirror.get("exists") and not mirror.get("stale")
    checks.append(
        {
            "check": "mirror",
            "ok": mirror_ok,
            "sqlite": mirror.get("sqlite"),
            "exists": mirror.get("exists"),
            "stale": mirror.get("stale"),
            "stale_hours": mirror.get("stale_hours"),
            "last_sync_at": mirror.get("last_sync_at"),
        }
    )
    if mirror.get("exists") and mirror.get("stale") and verdict == "CLEAR":
        verdict = "WARN"
    if not mirror.get("exists") and verdict == "CLEAR":
        verdict = "WARN"

    return {
        "ok": verdict != "BLOCK",
        "operation": "eidos_proof",
        "verdict": verdict,
        "account": account_name,
        "team_key": resolved_team_key,
        "stale_threshold_hours": stale_hours,
        "viewer": (auth.get("viewer") or {}) if auth else None,
        "organization": ((auth.get("viewer") or {}).get("organization")) if auth else None,
        "mirror": mirror,
        "checks": checks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }