"""eidos-linear MCP server — Eidos extensions over LinearPlus + LinearDB.

v1 ships eidos_* tools only. Pair with official Linear MCP for issue CRUD.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from eidos_linear.tools.initiatives import eidos_initiative_ensure as initiative_ensure_impl
from eidos_linear.tools.proof import eidos_proof as proof_impl
from eidos_linear.tools.sync import account_sync, mirror_status

mcp = FastMCP("eidos-linear")


@mcp.tool()
def eidos_proof(
    account: str | None = None,
    team_key: str | None = None,
    sqlite: str | None = None,
    stale_hours: float = 24,
) -> dict:
    """Doctor gate before Linear work: token, team access, mirror freshness.

    Returns verdict CLEAR | WARN | BLOCK. Run this before initiative writes or
    mirror-dependent analytics. Does not mutate Linear or local files.
    """
    return proof_impl(account=account, team_key=team_key, sqlite=sqlite, stale_hours=stale_hours)


@mcp.tool()
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
) -> dict:
    """Find a Linear initiative by exact name or create it.

    Use official Linear MCP for issue CRUD. This tool covers initiative writes
    missing from the official connector. Requires LinearDB OAuth for the account.
    """
    return initiative_ensure_impl(
        name=name,
        account=account,
        description=description,
        content=content,
        color=color,
        icon=icon,
        owner_id=owner_id,
        status=status,
        target_date=target_date,
        target_date_resolution=target_date_resolution,
    )


@mcp.tool()
def eidos_sync_status(
    account: str | None = None,
    sqlite: str | None = None,
    stale_hours: float = 24,
) -> dict:
    """Read-only LinearDB SQLite mirror health.

    Reports path, last sync time, issue/team counts, and staleness. Does not
    call Linear. Checks legacy mirror paths before the canonical location.
    """
    return mirror_status(account=account, sqlite=sqlite, stale_hours=stale_hours)


@mcp.tool()
def eidos_account_sync(
    account: str | None = None,
    sqlite: str | None = None,
    skip_related: bool = False,
) -> dict:
    """Mirror all accessible Linear teams into the canonical SQLite path.

    Writes to LINEARDB_MIRROR_SQLITE or ~/.lineardb/mirrors/<account>.sqlite.
    Read-only against Linear except for the local mirror write.
    """
    return account_sync(account=account, sqlite=sqlite, skip_related=skip_related)


def run() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    run()