from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import (
    LinearGraphQLError,
    LinearPlusClient,
    MissingTokenError,
    account_issue_dump,
    auth_check,
    attach_project,
    create_initiative,
    ensure_initiative,
    get_token,
    greenmark_issue_dump,
    greenmark_issue_analytics,
    initiative_by_name,
    project_by_id,
    write_account_dump_sqlite,
)

try:
    from lineardb.graphql import LinearGraphQLClient as LinearDBClient
    from lineardb.mirror import account_mirror_dump as lineardb_account_mirror_dump
    from lineardb.mirror import auth_check as lineardb_auth_check
    from lineardb.schema import write_mirror_sqlite as lineardb_write_mirror_sqlite
except ImportError:  # pragma: no cover - exercised by fallback behavior in environments without LinearDB.
    LinearDBClient = None
    lineardb_account_mirror_dump = None
    lineardb_auth_check = None
    lineardb_write_mirror_sqlite = None


GREENMARK_INITIATIVE_NAME = "Greenmark AI Search Visibility"
GREENMARK_PROJECT_ID = "079b8875-9c80-41c8-b4b0-ea09834a7065"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        client = None if getattr(args, "dry_run", False) else build_client(args)
        evidence = args.handler(args, client)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    except MissingTokenError as exc:
        print(json.dumps({"ok": False, "blocked": "missing_token", "message": str(exc)}, indent=2), file=sys.stderr)
        return 3
    except LinearGraphQLError as exc:
        print(json.dumps({"ok": False, "blocked": "linear_graphql_error", "errors": exc.errors}, indent=2), file=sys.stderr)
        return 4
    except Exception as exc:
        print(json.dumps({"ok": False, "blocked": "linearplus_error", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linearplus",
        description="CLI-first Linear GraphQL bridge for initiative workflows.",
    )
    parser.add_argument("--token-env", default="LINEAR_API_KEY", help="Environment variable containing the Linear API key.")
    parser.add_argument("--endpoint", default="https://api.linear.app/graphql", help="Linear GraphQL endpoint.")
    parser.add_argument("--account", help="LinearDB account profile name, such as greenmark.")

    subparsers = parser.add_subparsers(dest="command")

    auth = subparsers.add_parser("auth-check", help="Verify Linear identity and visible team keys.")
    auth.add_argument("--dry-run", action="store_true", help="Print the intended read-only auth check without calling Linear.")
    auth.add_argument("--team-key", default="GMW", help="Required Linear team key to check for.")
    auth.add_argument("--team-page-size", type=int, default=100, help="Linear team page size for pagination.")
    auth.set_defaults(handler=handle_auth_check)

    create = subparsers.add_parser("initiative-create", help="Create a Linear initiative.")
    add_initiative_fields(create)
    create.set_defaults(handler=handle_initiative_create)

    ensure = subparsers.add_parser("initiative-ensure", help="Find an initiative by name or create it.")
    add_initiative_fields(ensure)
    ensure.set_defaults(handler=handle_initiative_ensure)

    get = subparsers.add_parser("initiative-get", help="Fetch an initiative by exact name.")
    get.add_argument("--name", required=True)
    get.set_defaults(handler=handle_initiative_get)

    attach = subparsers.add_parser("attach-project", help="Attach an existing Linear project to an initiative.")
    attach.add_argument("--initiative-id", required=True)
    attach.add_argument("--project-id", required=True)
    attach.add_argument("--sort-order", type=float)
    attach.set_defaults(handler=handle_attach_project)

    greenmark = subparsers.add_parser("greenmark-bootstrap", help="Create/use the Greenmark initiative and attach its project.")
    greenmark.add_argument("--dry-run", action="store_true", help="Print the intended operation without calling Linear.")
    greenmark.set_defaults(handler=handle_greenmark_bootstrap)

    analytics = subparsers.add_parser(
        "greenmark-analytics",
        help="Summarize issues across the Greenmark Linear team.",
    )
    analytics.add_argument("--dry-run", action="store_true", help="Print the intended read-only operation without calling Linear.")
    analytics.add_argument("--team-key", default="GMW", help="Linear team key to analyze.")
    analytics.add_argument("--page-size", type=int, default=100, help="Linear issue page size for pagination.")
    analytics.add_argument("--sample-size", type=int, default=20, help="Number of issue summaries to include in samples.")
    analytics.set_defaults(handler=handle_greenmark_analytics)

    dump = subparsers.add_parser(
        "greenmark-dump",
        help="Dump Greenmark Linear task data and analytics to a local JSON artifact.",
    )
    dump.add_argument("--dry-run", action="store_true", help="Print the intended read-only dump without calling Linear.")
    dump.add_argument("--team-key", default="GMW", help="Linear team key to dump.")
    dump.add_argument("--page-size", type=int, default=100, help="Linear issue page size for pagination.")
    dump.add_argument("--sample-size", type=int, default=20, help="Number of issue summaries to include in analytics samples.")
    dump.add_argument("--output", help="Exact JSON output path. Defaults to outputs/greenmark under the plugin root.")
    dump.add_argument("--output-dir", help="Directory for timestamped dump output when --output is omitted.")
    dump.set_defaults(handler=handle_greenmark_dump)

    account_dump = subparsers.add_parser(
        "account-dump",
        help="Dump all accessible Linear team task data to a local SQLite database.",
    )
    account_dump.add_argument("--dry-run", action="store_true", help="Print the intended read-only SQLite dump without calling Linear.")
    account_dump.add_argument("--sqlite", help="Exact SQLite output path. Defaults to outputs/linear under the plugin root.")
    account_dump.add_argument("--output-dir", help="Directory for timestamped SQLite output when --sqlite is omitted.")
    account_dump.add_argument("--team-page-size", type=int, default=100, help="Linear team page size for pagination.")
    account_dump.add_argument("--issue-page-size", type=int, default=100, help="Linear issue page size for each team.")
    account_dump.add_argument("--related-page-size", type=int, default=100, help="Linear page size for comments, attachments, history, and state spans.")
    account_dump.add_argument("--sample-size", type=int, default=20, help="Number of issue summaries to include in analytics samples.")
    account_dump.add_argument("--skip-related", action="store_true", help="Only dump teams/issues, skipping comments, attachments, history, and state spans.")
    account_dump.set_defaults(handler=handle_account_dump)

    return parser


def add_initiative_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True)
    parser.add_argument("--description")
    parser.add_argument("--content")
    parser.add_argument("--color")
    parser.add_argument("--icon")
    parser.add_argument("--owner-id")
    parser.add_argument("--status", choices=["Planned", "Active", "Completed"])
    parser.add_argument("--target-date")
    parser.add_argument("--target-date-resolution", choices=["day", "month", "quarter", "halfYear", "year"])


def build_client(args: argparse.Namespace) -> LinearPlusClient:
    return LinearPlusClient(token=get_token(args.token_env, account=args.account), endpoint=args.endpoint)


def initiative_input(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": args.name,
        "description": args.description,
        "content": args.content,
        "color": args.color,
        "icon": args.icon,
        "ownerId": args.owner_id,
        "status": args.status,
        "targetDate": args.target_date,
        "targetDateResolution": args.target_date_resolution,
    }


def handle_auth_check(args: argparse.Namespace, client: LinearPlusClient | None) -> dict[str, Any]:
    if args.dry_run:
        return {
            "ok": True,
            "operation": "auth-check",
            "dry_run": True,
            "account": args.account,
            "team_key": args.team_key,
            "team_page_size": args.team_page_size,
            "read_only": True,
        }
    if client is None:
        raise RuntimeError("Linear client is required for live auth check.")
    source = "linearplus"
    if lineardb_auth_check is not None:
        result = lineardb_auth_check(to_lineardb_client(client), team_key=args.team_key, team_page_size=args.team_page_size)
        source = "lineardb"
    else:
        result = auth_check(client, team_key=args.team_key, team_page_size=args.team_page_size)
    return {
        "ok": result["has_required_team"],
        "operation": "auth-check",
        "account": args.account,
        "source": source,
        **result,
    }


def handle_initiative_create(args: argparse.Namespace, client: LinearPlusClient) -> dict[str, Any]:
    initiative = create_initiative(client, initiative_input(args))
    return {"ok": True, "operation": "initiative-create", "initiative": initiative}


def handle_initiative_ensure(args: argparse.Namespace, client: LinearPlusClient) -> dict[str, Any]:
    initiative, created = ensure_initiative(client, initiative_input(args))
    return {"ok": True, "operation": "initiative-ensure", "created": created, "initiative": initiative}


def handle_initiative_get(args: argparse.Namespace, client: LinearPlusClient) -> dict[str, Any]:
    initiative = initiative_by_name(client, args.name)
    return {"ok": True, "operation": "initiative-get", "found": initiative is not None, "initiative": initiative}


def handle_attach_project(args: argparse.Namespace, client: LinearPlusClient) -> dict[str, Any]:
    relation = attach_project(client, args.initiative_id, args.project_id, args.sort_order)
    return {"ok": True, "operation": "attach-project", "initiativeToProject": relation}


def handle_greenmark_bootstrap(args: argparse.Namespace, client: LinearPlusClient | None) -> dict[str, Any]:
    input_data = greenmark_input()
    if args.dry_run:
        return {
            "ok": True,
            "operation": "greenmark-bootstrap",
            "dry_run": True,
            "initiative_input": input_data,
            "project_id": GREENMARK_PROJECT_ID,
        }

    if client is None:
        raise RuntimeError("Linear client is required for live Greenmark bootstrap.")
    initiative, created = ensure_initiative(client, input_data)
    project = project_by_id(client, GREENMARK_PROJECT_ID)
    relation = attach_project(client, initiative["id"], GREENMARK_PROJECT_ID)
    return {
        "ok": True,
        "operation": "greenmark-bootstrap",
        "created": created,
        "initiative": initiative,
        "project": project or {"id": GREENMARK_PROJECT_ID},
        "initiativeToProject": relation,
    }


def handle_greenmark_analytics(args: argparse.Namespace, client: LinearPlusClient | None) -> dict[str, Any]:
    if args.dry_run:
        return {
            "ok": True,
            "operation": "greenmark-analytics",
            "dry_run": True,
            "team_key": args.team_key,
            "page_size": args.page_size,
            "sample_size": args.sample_size,
            "read_only": True,
        }

    if client is None:
        raise RuntimeError("Linear client is required for live Greenmark analytics.")
    analytics = greenmark_issue_analytics(
        client,
        team_key=args.team_key,
        page_size=args.page_size,
        sample_size=args.sample_size,
    )
    return {
        "ok": True,
        "operation": "greenmark-analytics",
        "team_key": args.team_key,
        **analytics,
    }


def handle_greenmark_dump(args: argparse.Namespace, client: LinearPlusClient | None) -> dict[str, Any]:
    output_path = resolve_dump_output(args.output, args.output_dir, args.team_key)
    if args.dry_run:
        return {
            "ok": True,
            "operation": "greenmark-dump",
            "dry_run": True,
            "team_key": args.team_key,
            "page_size": args.page_size,
            "sample_size": args.sample_size,
            "output": str(output_path),
            "read_only": True,
        }

    if client is None:
        raise RuntimeError("Linear client is required for live Greenmark dump.")
    dump = greenmark_issue_dump(
        client,
        team_key=args.team_key,
        page_size=args.page_size,
        sample_size=args.sample_size,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dump, indent=2, sort_keys=True) + "\n")
    return {
        "ok": True,
        "operation": "greenmark-dump",
        "team_key": args.team_key,
        "output": str(output_path),
        "issue_count": dump["analytics"]["totals"]["issues"],
        "analytics": dump["analytics"],
    }


def handle_account_dump(args: argparse.Namespace, client: LinearPlusClient | None) -> dict[str, Any]:
    sqlite_path = resolve_account_sqlite(args.sqlite, args.output_dir)
    if args.dry_run:
        return {
            "ok": True,
            "operation": "account-dump",
            "dry_run": True,
            "sqlite": str(sqlite_path),
            "team_page_size": args.team_page_size,
            "issue_page_size": args.issue_page_size,
            "related_page_size": args.related_page_size,
            "sample_size": args.sample_size,
            "include_related": not args.skip_related,
            "read_only": True,
        }

    if client is None:
        raise RuntimeError("Linear client is required for live account dump.")
    source = "linearplus"
    if lineardb_account_mirror_dump is not None and lineardb_write_mirror_sqlite is not None:
        dump = lineardb_account_mirror_dump(
            to_lineardb_client(client),
            account=args.account,
            team_page_size=args.team_page_size,
            issue_page_size=args.issue_page_size,
            sample_size=args.sample_size,
            include_related=not args.skip_related,
            related_page_size=args.related_page_size,
        )
        source = "lineardb"
    else:
        dump = account_issue_dump(
            client,
            team_page_size=args.team_page_size,
            issue_page_size=args.issue_page_size,
            sample_size=args.sample_size,
            include_related=not args.skip_related,
            related_page_size=args.related_page_size,
        )
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if source == "lineardb":
        lineardb_write_mirror_sqlite(dump, sqlite_path)
    else:
        write_account_dump_sqlite(dump, sqlite_path)
    return {
        "ok": True,
        "operation": "account-dump",
        "source": source,
        "sqlite": str(sqlite_path),
        "team_count": len(dump["teams"]),
        "issue_count": dump["analytics"]["totals"]["issues"],
        "related_counts": {key: len(value) for key, value in (dump.get("related") or {}).items()},
        "analytics": dump["analytics"],
    }


def resolve_dump_output(output: str | None, output_dir: str | None, team_key: str) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    directory = Path(output_dir).expanduser().resolve() if output_dir else default_dump_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{team_key.lower()}-linear-tasks-{timestamp}.json"


def default_dump_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "outputs" / "greenmark"


def resolve_account_sqlite(sqlite_path: str | None, output_dir: str | None) -> Path:
    if sqlite_path:
        return Path(sqlite_path).expanduser().resolve()
    directory = Path(output_dir).expanduser().resolve() if output_dir else default_account_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"linear-account-tasks-{timestamp}.sqlite"


def default_account_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "outputs" / "linear"


def to_lineardb_client(client: LinearPlusClient) -> Any:
    if LinearDBClient is None:
        raise RuntimeError("LinearDB is not available.")
    return LinearDBClient(
        token=client.token,
        endpoint=client.endpoint,
        max_retries=client.max_retries,
        retry_sleep_seconds=client.retry_sleep_seconds,
    )


def greenmark_input() -> dict[str, Any]:
    return {
        "name": GREENMARK_INITIATIVE_NAME,
        "description": (
            "Make Greenmark Waste Solutions the most crawlable, trusted, and citation-ready "
            "answer for high-intent DFW waste provider searches across AI search surfaces."
        ),
        "content": (
            "## Goal\n"
            "Make Greenmark Waste Solutions the safest, most-cited answer when customers ask "
            "ChatGPT, Perplexity, Gemini, Bing/Copilot, or Google AI for DFW waste providers.\n\n"
            "## First execution surface\n"
            "Attach the existing Linear project `Greenmark AI Search Visibility` and its GMW issues "
            "under this initiative.\n\n"
            "## Success criteria\n"
            "- Greenmark core service pages are discoverable without avoidable 404s or missing sitemap issues.\n"
            "- Greenmark appears as a cited or recommended option for priority DFW waste-provider prompts.\n"
            "- AI answers cite Greenmark-owned pages for factual service details.\n"
            "- Weekly tracking shows prompt-level movement, cited URLs, and gaps to fix.\n"
        ),
        "color": "#2E7D32",
        "icon": "search",
        "status": "Planned",
        "targetDate": "2026-07-31",
        "targetDateResolution": "month",
    }


if __name__ == "__main__":
    raise SystemExit(main())
