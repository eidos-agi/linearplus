from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
DEFAULT_TOKEN_ENV = "LINEAR_API_KEY"
FALLBACK_TOKEN_ENV = "LINEARPLUS_LINEAR_API_KEY"


class LinearPlusError(RuntimeError):
    """Base error for token-safe LinearPlus failures."""


class MissingTokenError(LinearPlusError):
    """Raised when no Linear API token is available."""


class LinearGraphQLError(LinearPlusError):
    """Raised when Linear returns GraphQL errors."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        messages = "; ".join(str(error.get("message", error)) for error in errors)
        super().__init__(messages)


@dataclass(frozen=True)
class LinearPlusClient:
    token: str
    endpoint: str = LINEAR_GRAPHQL_URL

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Authorization": self.token,
                "Content-Type": "application/json",
                "User-Agent": "LinearPlus/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise LinearPlusError(f"Linear HTTP {exc.code}: {redact_token(body_text, self.token)}") from exc
        except urllib.error.URLError as exc:
            raise LinearPlusError(f"Linear network error: {exc.reason}") from exc

        if body.get("errors"):
            raise LinearGraphQLError(body["errors"])
        return body.get("data") or {}


def get_token(token_env: str = DEFAULT_TOKEN_ENV) -> str:
    token = os.environ.get(token_env) or os.environ.get(FALLBACK_TOKEN_ENV)
    if not token:
        raise MissingTokenError(
            f"Set {token_env} or {FALLBACK_TOKEN_ENV}; LinearPlus will not prompt for or log tokens."
        )
    return token


def redact_token(value: str, token: str | None = None) -> str:
    redacted = value
    for candidate in [token, os.environ.get(DEFAULT_TOKEN_ENV), os.environ.get(FALLBACK_TOKEN_ENV)]:
        if candidate:
            redacted = redacted.replace(candidate, "[REDACTED_LINEAR_TOKEN]")
    return redacted


INITIATIVE_BY_NAME = """
query InitiativeByName($name: String!) {
  initiatives(filter: { name: { eq: $name } }, first: 10) {
    nodes {
      id
      name
      url
      slugId
      status
      targetDate
    }
  }
}
""".strip()


INITIATIVE_CREATE = """
mutation InitiativeCreate($input: InitiativeCreateInput!) {
  initiativeCreate(input: $input) {
    success
    lastSyncId
    initiative {
      id
      name
      url
      slugId
      status
      targetDate
    }
  }
}
""".strip()


INITIATIVE_TO_PROJECT_CREATE = """
mutation InitiativeToProjectCreate($input: InitiativeToProjectCreateInput!) {
  initiativeToProjectCreate(input: $input) {
    success
    lastSyncId
    initiativeToProject {
      id
      sortOrder
      initiative {
        id
        name
        url
      }
      project {
        id
        name
        url
      }
    }
  }
}
""".strip()


PROJECT_BY_ID = """
query ProjectById($id: String!) {
  project(id: $id) {
    id
    name
    url
  }
}
""".strip()


def initiative_by_name(client: LinearPlusClient, name: str) -> dict[str, Any] | None:
    data = client.execute(INITIATIVE_BY_NAME, {"name": name})
    nodes = ((data.get("initiatives") or {}).get("nodes") or [])
    for node in nodes:
        if node.get("name") == name:
            return node
    return None


def create_initiative(client: LinearPlusClient, input_data: dict[str, Any]) -> dict[str, Any]:
    data = client.execute(INITIATIVE_CREATE, {"input": clean_input(input_data)})
    payload = data.get("initiativeCreate") or {}
    return payload.get("initiative") or payload


def ensure_initiative(client: LinearPlusClient, input_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    existing = initiative_by_name(client, input_data["name"])
    if existing:
        return existing, False
    return create_initiative(client, input_data), True


def attach_project(
    client: LinearPlusClient,
    initiative_id: str,
    project_id: str,
    sort_order: float | None = None,
) -> dict[str, Any]:
    input_data: dict[str, Any] = {
        "initiativeId": initiative_id,
        "projectId": project_id,
    }
    if sort_order is not None:
        input_data["sortOrder"] = sort_order
    data = client.execute(INITIATIVE_TO_PROJECT_CREATE, {"input": input_data})
    payload = data.get("initiativeToProjectCreate") or {}
    return payload.get("initiativeToProject") or payload


def project_by_id(client: LinearPlusClient, project_id: str) -> dict[str, Any] | None:
    data = client.execute(PROJECT_BY_ID, {"id": project_id})
    return data.get("project")


def clean_input(input_data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in input_data.items() if value not in (None, "")}

