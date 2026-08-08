from __future__ import annotations

from typing import Any

from linearplus.client import LinearGraphQLError, clean_input, ensure_initiative

from eidos_linear.client import build_client, credential_blocker, resolved_account


def eidos_initiative_ensure(
    name: str,
    account: str | None = None,
    description: str | None = None,
    content: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    owner_id: str | None = None,
    status: str | None = None,
    target_date: str | None = None,
    target_date_resolution: str | None = None,
) -> dict[str, Any]:
    """Find a Linear initiative by exact name or create it."""
    account_name = resolved_account(account)
    input_data = clean_input(
        {
            "name": name,
            "description": description,
            "content": content,
            "color": color,
            "icon": icon,
            "ownerId": owner_id,
            "status": status,
            "targetDate": target_date,
            "targetDateResolution": target_date_resolution,
        }
    )

    try:
        client = build_client(account=account_name)
        initiative, created = ensure_initiative(client, input_data)
        return {
            "ok": True,
            "operation": "eidos_initiative_ensure",
            "account": account_name,
            "created": created,
            "initiative": initiative,
        }
    except LinearGraphQLError as exc:
        return {
            "ok": False,
            "operation": "eidos_initiative_ensure",
            "account": account_name,
            "blocked": "linear_graphql_error",
            "errors": exc.errors,
        }
    except Exception as exc:
        blocker = credential_blocker(exc)
        return {"ok": False, "operation": "eidos_initiative_ensure", "account": account_name, **blocker}