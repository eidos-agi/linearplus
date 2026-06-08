from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_OAUTH_TOKEN_URL = "https://api.linear.app/oauth/token"
DEFAULT_TOKEN_ENV = "LINEAR_API_KEY"
FALLBACK_TOKEN_ENV = "LINEARPLUS_LINEAR_API_KEY"
DEFAULT_OAUTH_CLIENT_ID_ENV = "LINEAR_OAUTH_CLIENT_ID"
FALLBACK_OAUTH_CLIENT_ID_ENV = "LINEARPLUS_OAUTH_CLIENT_ID"
DEFAULT_OAUTH_CLIENT_SECRET_ENV = "LINEAR_OAUTH_CLIENT_SECRET"
FALLBACK_OAUTH_CLIENT_SECRET_ENV = "LINEARPLUS_OAUTH_CLIENT_SECRET"
DEFAULT_OAUTH_SCOPE_ENV = "LINEARPLUS_OAUTH_SCOPE"
DEFAULT_ACCOUNT_ENV = "LINEARDB_ACCOUNT"
DEFAULT_OAUTH_SCOPE = "read"


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
    max_retries: int = 3
    retry_sleep_seconds: float = 1.0

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
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                body_text = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds * (attempt + 1))
                    continue
                raise LinearPlusError(f"Linear HTTP {exc.code}: {redact_token(body_text, self.token)}") from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.retry_sleep_seconds * (attempt + 1))
                    continue
                raise LinearPlusError(f"Linear network error: {exc.reason}") from exc

        if body.get("errors"):
            raise LinearGraphQLError(body["errors"])
        return body.get("data") or {}


def get_token(token_env: str = DEFAULT_TOKEN_ENV, account: str | None = None) -> str:
    account_name = account or os.environ.get(DEFAULT_ACCOUNT_ENV)
    token = account_env_value(account_name, "LINEAR_API_KEY")
    if not account_name:
        if not token and token_env != DEFAULT_TOKEN_ENV:
            token = os.environ.get(token_env)
        token = token or os.environ.get(DEFAULT_TOKEN_ENV) or os.environ.get(FALLBACK_TOKEN_ENV)
    if token:
        return token

    client_id = account_env_value(account_name, "OAUTH_CLIENT_ID")
    client_secret = account_env_value(account_name, "OAUTH_CLIENT_SECRET")
    if not account_name:
        client_id = client_id or os.environ.get(DEFAULT_OAUTH_CLIENT_ID_ENV) or os.environ.get(FALLBACK_OAUTH_CLIENT_ID_ENV)
        client_secret = (
            client_secret
            or os.environ.get(DEFAULT_OAUTH_CLIENT_SECRET_ENV)
            or os.environ.get(FALLBACK_OAUTH_CLIENT_SECRET_ENV)
        )
    if client_id and client_secret:
        return oauth_client_credentials_token(client_id, client_secret, scope=account_env_value(account_name, "OAUTH_SCOPE"))

    if account_name:
        account_key = account_env_key(account_name)
        raise MissingTokenError(
            f"Set LINEARDB_{account_key}_LINEAR_API_KEY or "
            f"LINEARDB_{account_key}_OAUTH_CLIENT_ID/LINEARDB_{account_key}_OAUTH_CLIENT_SECRET; "
            "LinearPlus will not use ambient credentials for an explicit LinearDB account."
        )

    raise MissingTokenError(
        f"Set LINEARDB_<ACCOUNT>_LINEAR_API_KEY, {token_env}, or {FALLBACK_TOKEN_ENV}; "
        f"or set LINEARDB_<ACCOUNT>_OAUTH_CLIENT_ID/SECRET or "
        f"{FALLBACK_OAUTH_CLIENT_ID_ENV}/{FALLBACK_OAUTH_CLIENT_SECRET_ENV}; "
        "LinearPlus will not prompt for or log tokens."
    )


def account_env_value(account: str | None, suffix: str) -> str | None:
    if not account:
        return None
    return os.environ.get(f"LINEARDB_{account_env_key(account)}_{suffix}")


def account_env_key(account: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in account.upper()).strip("_")


def oauth_client_credentials_token(
    client_id: str,
    client_secret: str,
    scope: str | None = None,
    endpoint: str = LINEAR_OAUTH_TOKEN_URL,
) -> str:
    resolved_scope = scope or os.environ.get(DEFAULT_OAUTH_SCOPE_ENV) or DEFAULT_OAUTH_SCOPE
    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": resolved_scope,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=form,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "LinearPlus/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise LinearPlusError(f"Linear OAuth HTTP {exc.code}: {redact_token(body_text)}") from exc
    except urllib.error.URLError as exc:
        raise LinearPlusError(f"Linear OAuth network error: {exc.reason}") from exc

    access_token = body.get("access_token")
    if not access_token:
        raise LinearPlusError("Linear OAuth response did not include an access_token.")
    token_type = body.get("token_type") or "Bearer"
    return f"{token_type} {access_token}"


def redact_token(value: str, token: str | None = None) -> str:
    redacted = value
    for candidate in [
        token,
        os.environ.get(DEFAULT_TOKEN_ENV),
        os.environ.get(FALLBACK_TOKEN_ENV),
        os.environ.get(DEFAULT_OAUTH_CLIENT_SECRET_ENV),
        os.environ.get(FALLBACK_OAUTH_CLIENT_SECRET_ENV),
    ]:
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


TEAM_ISSUES = """
query TeamIssues($teamKey: String!, $first: Int!, $after: String) {
  teams(filter: { key: { eq: $teamKey } }, first: 1) {
    nodes {
      id
      key
      name
      issues(first: $first, after: $after) {
        nodes {
          id
          identifier
          title
          url
          priority
          priorityLabel
          createdAt
          updatedAt
          completedAt
          canceledAt
          dueDate
          state {
            id
            name
            type
          }
          assignee {
            id
            name
          }
          project {
            id
            name
            url
          }
          cycle {
            id
            name
          }
          labels {
            nodes {
              id
              name
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
""".strip()


TEAMS = """
query Teams($first: Int!, $after: String) {
  teams(first: $first, after: $after) {
    nodes {
      id
      key
      name
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()


VIEWER = """
query Viewer {
  viewer {
    id
    name
    email
    organization {
      id
      name
      urlKey
    }
  }
}
""".strip()


ISSUE_COMMENTS = """
query IssueComments($id: String!, $first: Int!, $after: String) {
  issue(id: $id) {
    comments(first: $first, after: $after, includeArchived: true) {
      nodes {
        id
        createdAt
        updatedAt
        archivedAt
        body
        bodyData
        url
        reactionData
        user {
          id
          name
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
""".strip()


ISSUE_ATTACHMENTS = """
query IssueAttachments($id: String!, $first: Int!, $after: String) {
  issue(id: $id) {
    attachments(first: $first, after: $after, includeArchived: true) {
      nodes {
        id
        createdAt
        updatedAt
        archivedAt
        title
        subtitle
        url
        metadata
        source
        sourceType
        bodyData
        creator {
          id
          name
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
""".strip()


ISSUE_HISTORY = """
query IssueHistory($id: String!, $first: Int!, $after: String) {
  issue(id: $id) {
    history(first: $first, after: $after, includeArchived: true) {
      nodes {
        id
        createdAt
        updatedAt
        archivedAt
        actorId
        updatedDescription
        fromTitle
        toTitle
        fromAssigneeId
        toAssigneeId
        fromPriority
        toPriority
        fromTeamId
        toTeamId
        fromProjectId
        toProjectId
        fromStateId
        toStateId
        fromCycleId
        toCycleId
        fromEstimate
        toEstimate
        fromDueDate
        toDueDate
        autoClosed
        autoArchived
        actor {
          id
          name
        }
        fromState {
          id
          name
          type
        }
        toState {
          id
          name
          type
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
""".strip()


ISSUE_STATE_HISTORY = """
query IssueStateHistory($id: String!, $first: Int!, $after: String) {
  issue(id: $id) {
    stateHistory(first: $first, after: $after) {
      nodes {
        id
        stateId
        startedAt
        endedAt
        state {
          id
          name
          type
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
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


def greenmark_issue_analytics(
    client: LinearPlusClient,
    team_key: str = "GMW",
    page_size: int = 100,
    sample_size: int = 20,
) -> dict[str, Any]:
    team, issues = issues_for_team(client, team_key=team_key, page_size=page_size)
    return summarize_issue_analytics(team or {"key": team_key}, issues, sample_size=sample_size)


def greenmark_issue_dump(
    client: LinearPlusClient,
    team_key: str = "GMW",
    page_size: int = 100,
    sample_size: int = 20,
) -> dict[str, Any]:
    team, issues = issues_for_team(client, team_key=team_key, page_size=page_size)
    resolved_team = team or {"key": team_key}
    return {
        "query": {
            "team_key": team_key,
            "page_size": page_size,
            "sample_size": sample_size,
        },
        "team": resolved_team,
        "analytics": summarize_issue_analytics(resolved_team, issues, sample_size=sample_size),
        "issues": issues,
    }


def account_issue_dump(
    client: LinearPlusClient,
    team_page_size: int = 100,
    issue_page_size: int = 100,
    sample_size: int = 20,
    include_related: bool = True,
    related_page_size: int = 100,
) -> dict[str, Any]:
    teams = teams_for_account(client, page_size=team_page_size)
    issues: list[dict[str, Any]] = []
    for team in teams:
        _, team_issues = issues_for_team(client, team_key=team["key"], page_size=issue_page_size)
        for issue in team_issues:
            issue["team"] = team
        issues.extend(team_issues)

    analytics = summarize_issue_analytics({"key": "ALL", "name": "All accessible Linear teams"}, issues, sample_size=sample_size)
    analytics["teams"] = counts((issue.get("team") or {}).get("key") or "No team" for issue in issues)
    related = empty_related()
    if include_related:
        related = account_issue_related(client, issues, page_size=related_page_size)
    return {
        "query": {
            "team_page_size": team_page_size,
            "issue_page_size": issue_page_size,
            "sample_size": sample_size,
            "include_related": include_related,
            "related_page_size": related_page_size,
        },
        "teams": teams,
        "analytics": analytics,
        "issues": issues,
        "related": related,
    }


def teams_for_account(client: LinearPlusClient, page_size: int = 100) -> list[dict[str, Any]]:
    after = None
    teams: list[dict[str, Any]] = []
    while True:
        data = client.execute(TEAMS, {"first": page_size, "after": after})
        connection = data.get("teams") or {}
        teams.extend(connection.get("nodes") or [])
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return teams
        after = page_info.get("endCursor")


def auth_check(client: LinearPlusClient, team_key: str = "GMW", team_page_size: int = 100) -> dict[str, Any]:
    viewer = client.execute(VIEWER).get("viewer")
    teams = teams_for_account(client, page_size=team_page_size)
    return {
        "viewer": viewer,
        "teams": teams,
        "team_keys": [team.get("key") for team in teams],
        "required_team_key": team_key,
        "has_required_team": any(team.get("key") == team_key for team in teams),
    }


def account_issue_related(
    client: LinearPlusClient,
    issues: list[dict[str, Any]],
    page_size: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    related = empty_related()
    for issue in issues:
        issue_id = issue.get("id") or issue.get("identifier")
        if not issue_id:
            continue
        related["comments"].extend(issue_related_nodes(client, issue, "comments", ISSUE_COMMENTS, page_size))
        related["attachments"].extend(issue_related_nodes(client, issue, "attachments", ISSUE_ATTACHMENTS, page_size))
        related["history"].extend(issue_related_nodes(client, issue, "history", ISSUE_HISTORY, page_size))
        related["state_spans"].extend(issue_related_nodes(client, issue, "stateHistory", ISSUE_STATE_HISTORY, page_size))
    return related


def empty_related() -> dict[str, list[dict[str, Any]]]:
    return {"comments": [], "attachments": [], "history": [], "state_spans": []}


def issue_related_nodes(
    client: LinearPlusClient,
    issue: dict[str, Any],
    connection_name: str,
    query: str,
    page_size: int,
) -> list[dict[str, Any]]:
    after = None
    issue_id = issue.get("id") or issue.get("identifier")
    nodes: list[dict[str, Any]] = []
    while True:
        data = client.execute(query, {"id": issue_id, "first": page_size, "after": after})
        connection = ((data.get("issue") or {}).get(connection_name) or {})
        for node in connection.get("nodes") or []:
            node["issue_id"] = issue_id
            node["issue_identifier"] = issue.get("identifier")
            nodes.append(node)
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return nodes
        after = page_info.get("endCursor")


def write_account_dump_sqlite(dump: dict[str, Any], db_path: str | os.PathLike[str]) -> None:
    target_path = os.fspath(db_path)
    temp_path = f"{target_path}.{current_run_id()}.tmp"
    try:
        write_account_dump_sqlite_file(dump, temp_path)
        os.replace(temp_path, target_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def write_account_dump_sqlite_file(dump: dict[str, Any], db_path: str | os.PathLike[str]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("pragma foreign_keys = off")
        create_account_schema(connection)
        run_id = current_run_id()
        captured_at = current_timestamp()
        insert_sync_run(connection, run_id, captured_at, dump)
        clear_account_schema(connection)
        for team in dump.get("teams") or []:
            upsert_team(connection, team)
        for issue in dump.get("issues") or []:
            upsert_issue_related_records(connection, issue)
            upsert_issue(connection, issue)
            insert_issue_snapshot(connection, run_id, captured_at, issue)
        upsert_related(connection, dump.get("related") or empty_related())
        connection.execute(
            "insert into metadata(key, value) values (?, ?)",
            ("analytics", json.dumps(dump.get("analytics") or {}, sort_keys=True)),
        )
        connection.execute(
            "insert into metadata(key, value) values (?, ?)",
            ("latest_sync_run_id", run_id),
        )
        connection.commit()


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def create_account_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists metadata (
          key text primary key,
          value text not null
        );
        create table if not exists sync_runs (
          id text primary key,
          started_at text not null,
          finished_at text not null,
          team_count integer not null,
          issue_count integer not null,
          raw_json text not null
        );
        create table if not exists teams (
          id text primary key,
          key text,
          name text,
          raw_json text not null
        );
        create table if not exists users (
          id text primary key,
          name text,
          raw_json text not null
        );
        create table if not exists projects (
          id text primary key,
          name text,
          url text,
          raw_json text not null
        );
        create table if not exists labels (
          id text primary key,
          name text,
          raw_json text not null
        );
        create table if not exists issues (
          id text primary key,
          identifier text,
          title text,
          url text,
          team_id text,
          team_key text,
          state_name text,
          state_type text,
          priority_label text,
          assignee_id text,
          assignee_name text,
          project_id text,
          project_name text,
          cycle_id text,
          cycle_name text,
          created_at text,
          updated_at text,
          completed_at text,
          canceled_at text,
          due_date text,
          raw_json text not null
        );
        create table if not exists issue_labels (
          issue_id text not null,
          label_id text not null,
          label_name text,
          primary key (issue_id, label_id)
        );
        create table if not exists issue_snapshots (
          run_id text not null,
          issue_id text not null,
          identifier text,
          team_key text,
          state_name text,
          state_type text,
          priority_label text,
          assignee_id text,
          project_id text,
          updated_at text,
          captured_at text not null,
          raw_json text not null,
          primary key (run_id, issue_id)
        );
        create table if not exists comments (
          id text primary key,
          issue_id text,
          issue_identifier text,
          body text,
          body_data text,
          url text,
          user_id text,
          user_name text,
          created_at text,
          updated_at text,
          archived_at text,
          raw_json text not null
        );
        create table if not exists attachments (
          id text primary key,
          issue_id text,
          issue_identifier text,
          title text,
          subtitle text,
          url text,
          source_type text,
          creator_id text,
          creator_name text,
          created_at text,
          updated_at text,
          archived_at text,
          raw_json text not null
        );
        create table if not exists issue_history (
          id text primary key,
          issue_id text,
          issue_identifier text,
          actor_id text,
          actor_name text,
          from_state_id text,
          from_state_name text,
          to_state_id text,
          to_state_name text,
          from_assignee_id text,
          to_assignee_id text,
          from_project_id text,
          to_project_id text,
          from_priority real,
          to_priority real,
          from_due_date text,
          to_due_date text,
          updated_description integer,
          created_at text,
          updated_at text,
          archived_at text,
          raw_json text not null
        );
        create table if not exists issue_state_spans (
          id text primary key,
          issue_id text,
          issue_identifier text,
          state_id text,
          state_name text,
          state_type text,
          started_at text,
          ended_at text,
          raw_json text not null
        );
        """
    )


def clear_account_schema(connection: sqlite3.Connection) -> None:
    for table in ["metadata", "issue_labels", "issues", "labels", "projects", "users", "teams"]:
        connection.execute(f"delete from {table}")


def insert_sync_run(connection: sqlite3.Connection, run_id: str, started_at: str, dump: dict[str, Any]) -> None:
    connection.execute(
        """
        insert or replace into sync_runs(id, started_at, finished_at, team_count, issue_count, raw_json)
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            started_at,
            current_timestamp(),
            len(dump.get("teams") or []),
            len(dump.get("issues") or []),
            json.dumps({"query": dump.get("query"), "analytics": dump.get("analytics")}, sort_keys=True),
        ),
    )


def upsert_team(connection: sqlite3.Connection, team: dict[str, Any]) -> None:
    connection.execute(
        "insert or replace into teams(id, key, name, raw_json) values (?, ?, ?, ?)",
        (team.get("id"), team.get("key"), team.get("name"), json.dumps(team, sort_keys=True)),
    )


def upsert_issue_related_records(connection: sqlite3.Connection, issue: dict[str, Any]) -> None:
    team = issue.get("team") or {}
    if team.get("id"):
        upsert_team(connection, team)
    assignee = issue.get("assignee") or {}
    if assignee.get("id"):
        connection.execute(
            "insert or replace into users(id, name, raw_json) values (?, ?, ?)",
            (assignee.get("id"), assignee.get("name"), json.dumps(assignee, sort_keys=True)),
        )
    project = issue.get("project") or {}
    if project.get("id"):
        connection.execute(
            "insert or replace into projects(id, name, url, raw_json) values (?, ?, ?, ?)",
            (project.get("id"), project.get("name"), project.get("url"), json.dumps(project, sort_keys=True)),
        )
    for label in (issue.get("labels") or {}).get("nodes") or []:
        label_id = label.get("id") or label.get("name")
        if not label_id:
            continue
        connection.execute(
            "insert or replace into labels(id, name, raw_json) values (?, ?, ?)",
            (label_id, label.get("name"), json.dumps(label, sort_keys=True)),
        )
        connection.execute(
            "insert or replace into issue_labels(issue_id, label_id, label_name) values (?, ?, ?)",
            (issue.get("id") or issue.get("identifier"), label_id, label.get("name")),
        )


def upsert_issue(connection: sqlite3.Connection, issue: dict[str, Any]) -> None:
    team = issue.get("team") or {}
    state = issue.get("state") or {}
    assignee = issue.get("assignee") or {}
    project = issue.get("project") or {}
    cycle = issue.get("cycle") or {}
    connection.execute(
        """
        insert or replace into issues(
          id, identifier, title, url, team_id, team_key, state_name, state_type,
          priority_label, assignee_id, assignee_name, project_id, project_name,
          cycle_id, cycle_name, created_at, updated_at, completed_at, canceled_at,
          due_date, raw_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            issue.get("id") or issue.get("identifier"),
            issue.get("identifier"),
            issue.get("title"),
            issue.get("url"),
            team.get("id"),
            team.get("key"),
            state.get("name"),
            state.get("type"),
            issue.get("priorityLabel"),
            assignee.get("id"),
            assignee.get("name"),
            project.get("id"),
            project.get("name"),
            cycle.get("id"),
            cycle.get("name"),
            issue.get("createdAt"),
            issue.get("updatedAt"),
            issue.get("completedAt"),
            issue.get("canceledAt"),
            issue.get("dueDate"),
            json.dumps(issue, sort_keys=True),
        ),
    )


def insert_issue_snapshot(
    connection: sqlite3.Connection,
    run_id: str,
    captured_at: str,
    issue: dict[str, Any],
) -> None:
    team = issue.get("team") or {}
    state = issue.get("state") or {}
    assignee = issue.get("assignee") or {}
    project = issue.get("project") or {}
    connection.execute(
        """
        insert or replace into issue_snapshots(
          run_id, issue_id, identifier, team_key, state_name, state_type,
          priority_label, assignee_id, project_id, updated_at, captured_at, raw_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            issue.get("id") or issue.get("identifier"),
            issue.get("identifier"),
            team.get("key"),
            state.get("name"),
            state.get("type"),
            issue.get("priorityLabel"),
            assignee.get("id"),
            project.get("id"),
            issue.get("updatedAt"),
            captured_at,
            json.dumps(issue, sort_keys=True),
        ),
    )


def upsert_related(connection: sqlite3.Connection, related: dict[str, list[dict[str, Any]]]) -> None:
    for comment in related.get("comments") or []:
        user = comment.get("user") or {}
        connection.execute(
            """
            insert or replace into comments(
              id, issue_id, issue_identifier, body, body_data, url, user_id, user_name,
              created_at, updated_at, archived_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment.get("id"),
                comment.get("issue_id"),
                comment.get("issue_identifier"),
                comment.get("body"),
                comment.get("bodyData"),
                comment.get("url"),
                user.get("id"),
                user.get("name"),
                comment.get("createdAt"),
                comment.get("updatedAt"),
                comment.get("archivedAt"),
                json.dumps(comment, sort_keys=True),
            ),
        )

    for attachment in related.get("attachments") or []:
        creator = attachment.get("creator") or {}
        connection.execute(
            """
            insert or replace into attachments(
              id, issue_id, issue_identifier, title, subtitle, url, source_type,
              creator_id, creator_name, created_at, updated_at, archived_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attachment.get("id"),
                attachment.get("issue_id"),
                attachment.get("issue_identifier"),
                attachment.get("title"),
                attachment.get("subtitle"),
                attachment.get("url"),
                attachment.get("sourceType"),
                creator.get("id"),
                creator.get("name"),
                attachment.get("createdAt"),
                attachment.get("updatedAt"),
                attachment.get("archivedAt"),
                json.dumps(attachment, sort_keys=True),
            ),
        )

    for event in related.get("history") or []:
        actor = event.get("actor") or {}
        from_state = event.get("fromState") or {}
        to_state = event.get("toState") or {}
        connection.execute(
            """
            insert or replace into issue_history(
              id, issue_id, issue_identifier, actor_id, actor_name,
              from_state_id, from_state_name, to_state_id, to_state_name,
              from_assignee_id, to_assignee_id, from_project_id, to_project_id,
              from_priority, to_priority, from_due_date, to_due_date,
              updated_description, created_at, updated_at, archived_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("id"),
                event.get("issue_id"),
                event.get("issue_identifier"),
                actor.get("id") or event.get("actorId"),
                actor.get("name"),
                from_state.get("id") or event.get("fromStateId"),
                from_state.get("name"),
                to_state.get("id") or event.get("toStateId"),
                to_state.get("name"),
                event.get("fromAssigneeId"),
                event.get("toAssigneeId"),
                event.get("fromProjectId"),
                event.get("toProjectId"),
                event.get("fromPriority"),
                event.get("toPriority"),
                event.get("fromDueDate"),
                event.get("toDueDate"),
                int(bool(event.get("updatedDescription"))) if event.get("updatedDescription") is not None else None,
                event.get("createdAt"),
                event.get("updatedAt"),
                event.get("archivedAt"),
                json.dumps(event, sort_keys=True),
            ),
        )

    for span in related.get("state_spans") or []:
        state = span.get("state") or {}
        connection.execute(
            """
            insert or replace into issue_state_spans(
              id, issue_id, issue_identifier, state_id, state_name, state_type,
              started_at, ended_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span.get("id"),
                span.get("issue_id"),
                span.get("issue_identifier"),
                state.get("id") or span.get("stateId"),
                state.get("name"),
                state.get("type"),
                span.get("startedAt"),
                span.get("endedAt"),
                json.dumps(span, sort_keys=True),
            ),
        )


def summarize_issue_analytics(
    team: dict[str, Any],
    issues: list[dict[str, Any]],
    sample_size: int = 20,
) -> dict[str, Any]:
    state_types = counts(issue.get("state", {}).get("type") or "No state type" for issue in issues)
    assignees = counts((issue.get("assignee") or {}).get("name") or "Unassigned" for issue in issues)
    projects = counts((issue.get("project") or {}).get("name") or "No project" for issue in issues)

    return {
        "team": team,
        "totals": {
            "issues": len(issues),
            "open": sum(1 for issue in issues if issue_state_type(issue) not in {"completed", "canceled"}),
            "completed": state_types.get("completed", 0),
            "canceled": state_types.get("canceled", 0),
            "unassigned": assignees.get("Unassigned", 0),
            "without_project": projects.get("No project", 0),
        },
        "state_types": state_types,
        "states": counts((issue.get("state") or {}).get("name") or "No state" for issue in issues),
        "priorities": counts(issue.get("priorityLabel") or "No priority" for issue in issues),
        "assignees": assignees,
        "projects": projects,
        "labels": counts(
            label.get("name") or "Unnamed label"
            for issue in issues
            for label in ((issue.get("labels") or {}).get("nodes") or [])
        ),
        "sample_issues": [issue_summary(issue) for issue in issues[:sample_size]],
        "stale_open_issues": [issue_summary(issue) for issue in stale_open_issues(issues, limit=sample_size)],
    }


def issues_for_team(
    client: LinearPlusClient,
    team_key: str,
    page_size: int = 100,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    after = None
    team: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = []

    while True:
        data = client.execute(TEAM_ISSUES, {"teamKey": team_key, "first": page_size, "after": after})
        nodes = ((data.get("teams") or {}).get("nodes") or [])
        team = next((node for node in nodes if node.get("key") == team_key), nodes[0] if nodes else None)
        if not team:
            return None, issues

        issue_connection = team.get("issues") or {}
        issues.extend(issue_connection.get("nodes") or [])
        page_info = issue_connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return strip_issue_connection(team), issues
        after = page_info.get("endCursor")


def strip_issue_connection(team: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in team.items() if key != "issues"}


def issue_state_type(issue: dict[str, Any]) -> str:
    return (issue.get("state") or {}).get("type") or ""


def counts(values) -> dict[str, int]:
    counter = Counter(values)
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": (issue.get("state") or {}).get("name"),
        "state_type": issue_state_type(issue) or None,
        "priority": issue.get("priorityLabel"),
        "assignee": (issue.get("assignee") or {}).get("name"),
        "project": (issue.get("project") or {}).get("name"),
        "updatedAt": issue.get("updatedAt"),
        "dueDate": issue.get("dueDate"),
    }


def stale_open_issues(issues: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    open_issues = [issue for issue in issues if issue_state_type(issue) not in {"completed", "canceled"}]
    return sorted(open_issues, key=lambda issue: issue.get("updatedAt") or "")[:limit]


def clean_input(input_data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in input_data.items() if value not in (None, "")}
