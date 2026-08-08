from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from linearplus.client import LinearPlusClient, MissingTokenError, get_token

try:
    from lineardb.auth import MissingCredentialError, get_token as lineardb_get_token
    from lineardb.graphql import LinearGraphQLClient
    from lineardb.mirror import auth_check as lineardb_auth_check
except ImportError:  # pragma: no cover
    MissingCredentialError = None  # type: ignore[misc, assignment]
    lineardb_get_token = None
    LinearGraphQLClient = None
    lineardb_auth_check = None


DEFAULT_ACCOUNT_ENV = "LINEARDB_ACCOUNT"
DEFAULT_MIRROR_ENV = "LINEARDB_MIRROR_SQLITE"
DEFAULT_STALE_HOURS = 24


def resolved_account(account: str | None = None) -> str:
    name = account or os.environ.get(DEFAULT_ACCOUNT_ENV)
    if not name:
        raise MissingTokenError("Set LINEARDB_ACCOUNT or pass account= to eidos-linear tools.")
    return name


def build_client(account: str | None = None, endpoint: str = "https://api.linear.app/graphql") -> LinearPlusClient:
    account_name = resolved_account(account)
    if lineardb_get_token is not None:
        return LinearPlusClient(token=lineardb_get_token(account=account_name), endpoint=endpoint)
    return LinearPlusClient(token=get_token(account=account_name), endpoint=endpoint)


def auth_check(client: LinearPlusClient, team_key: str, team_page_size: int = 100) -> dict[str, Any]:
    if lineardb_auth_check is not None and LinearGraphQLClient is not None:
        ldb_client = LinearGraphQLClient(
            token=client.token,
            endpoint=client.endpoint,
            max_retries=client.max_retries,
            retry_sleep_seconds=client.retry_sleep_seconds,
        )
        return lineardb_auth_check(ldb_client, team_key=team_key, team_page_size=team_page_size)
    from linearplus.client import auth_check as lp_auth_check

    return lp_auth_check(client, team_key=team_key, team_page_size=team_page_size)


def canonical_mirror_path(account: str) -> Path:
    return Path.home() / ".lineardb" / "mirrors" / f"{account}.sqlite"


def legacy_mirror_candidates(account: str) -> list[Path]:
    """Pre-convention mirror locations, checked before assuming canonical path."""
    filenames = [f"{account}-linear.sqlite", "greenmark-linear.sqlite"] if account == "greenmark" else [f"{account}-linear.sqlite"]
    repo_root = Path(__file__).resolve().parents[1]
    bases = [
        Path.home() / ".lineardb" / "outputs",
        Path.home() / "repos-eidos-agi" / "lineardb" / "outputs",
        repo_root / "outputs" / "linear",
        repo_root / "outputs" / "greenmark",
    ]
    candidates: list[Path] = []
    for base in bases:
        for filename in filenames:
            candidates.append(base / filename)
    return candidates


def resolve_mirror_path(account: str | None = None, sqlite: str | None = None) -> Path:
    if sqlite:
        return Path(sqlite).expanduser().resolve()
    configured = os.environ.get(DEFAULT_MIRROR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    account_name = resolved_account(account)
    for candidate in legacy_mirror_candidates(account_name):
        if candidate.is_file():
            return candidate.resolve()
    return canonical_mirror_path(account_name)


def default_mirror_path(account: str) -> Path:
    return resolve_mirror_path(account=account)


def credential_blocker(exc: Exception) -> dict[str, Any]:
    if MissingCredentialError is not None and isinstance(exc, MissingCredentialError):
        account = os.environ.get(DEFAULT_ACCOUNT_ENV, "<account>")
        return {
            "ok": False,
            "blocked": "missing_credential",
            "message": str(exc),
            "remediation": f"Run `lineardb --account {account} connect` first.",
        }
    if isinstance(exc, MissingTokenError):
        return {
            "ok": False,
            "blocked": "missing_token",
            "message": str(exc),
            "remediation": "Connect LinearDB OAuth or set LINEARDB_<ACCOUNT>_ credentials.",
        }
    return {"ok": False, "blocked": "client_error", "message": str(exc)}