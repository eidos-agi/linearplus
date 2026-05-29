from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import (
    LinearGraphQLError,
    LinearPlusClient,
    MissingTokenError,
    attach_project,
    create_initiative,
    ensure_initiative,
    get_token,
    initiative_by_name,
    project_by_id,
)


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

    subparsers = parser.add_subparsers(dest="command")

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
    return LinearPlusClient(token=get_token(args.token_env), endpoint=args.endpoint)


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
