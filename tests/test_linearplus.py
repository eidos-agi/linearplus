from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from linearplus.client import (
    INITIATIVE_CREATE,
    INITIATIVE_TO_PROJECT_CREATE,
    FALLBACK_OAUTH_CLIENT_ID_ENV,
    FALLBACK_OAUTH_CLIENT_SECRET_ENV,
    LinearPlusClient,
    MissingTokenError,
    clean_input,
    ensure_initiative,
    get_token,
    initiative_by_name,
    redact_token,
)
import linearplus.client as client_module
import linearplus.cli as cli_module
from linearplus.cli import GREENMARK_PROJECT_ID, greenmark_input, main


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, query, variables=None):
        self.calls.append((query, variables or {}))
        return self.responses.pop(0)


class FakeHTTPResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeErrorBody:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def close(self):
        return None


class FakeLinearDBClient:
    def __init__(self, token, endpoint, max_retries=3, retry_sleep_seconds=1.0):
        self.token = token
        self.endpoint = endpoint
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds


class LinearPlusTests(unittest.TestCase):
    def test_get_token_uses_env_without_printing_value(self):
        with patch.dict(os.environ, {"LINEAR_API_KEY": "lin-secret"}, clear=True):
            self.assertEqual(get_token(), "lin-secret")
            self.assertEqual(redact_token("token=lin-secret"), "token=[REDACTED_LINEAR_TOKEN]")

    def test_get_token_uses_oauth_client_credentials_without_printing_secret(self):
        with patch.dict(
            os.environ,
            {
                FALLBACK_OAUTH_CLIENT_ID_ENV: "client-id",
                FALLBACK_OAUTH_CLIENT_SECRET_ENV: "client-secret",
            },
            clear=True,
        ):
            with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(b'{"access_token":"oauth-token"}')) as urlopen:
                token = get_token()

        request = urlopen.call_args.args[0]
        self.assertEqual(token, "Bearer oauth-token")
        self.assertIn(b"grant_type=client_credentials", request.data)
        self.assertIn(b"scope=read", request.data)
        self.assertIn(b"client_id=client-id", request.data)
        self.assertIn(b"client_secret=client-secret", request.data)
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")

    def test_get_token_uses_account_scoped_api_key_before_ambient_key(self):
        with patch.dict(
            os.environ,
            {
                "LINEARDB_GREENMARK_LINEAR_API_KEY": "greenmark-secret",
                "LINEARPLUS_LINEAR_API_KEY": "boone-secret",
            },
            clear=True,
        ):
            self.assertEqual(get_token(account="greenmark"), "greenmark-secret")

    def test_get_token_with_account_does_not_fall_back_to_ambient_key(self):
        with patch.dict(os.environ, {"LINEARPLUS_LINEAR_API_KEY": "boone-secret"}, clear=True):
            with self.assertRaises(MissingTokenError):
                get_token(account="greenmark")

    def test_get_token_uses_account_scoped_oauth_credentials(self):
        with patch.dict(
            os.environ,
            {
                "LINEARDB_GREENMARK_OAUTH_CLIENT_ID": "greenmark-client",
                "LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET": "greenmark-secret",
                "LINEARPLUS_OAUTH_CLIENT_ID": "ambient-client",
                "LINEARPLUS_OAUTH_CLIENT_SECRET": "ambient-secret",
            },
            clear=True,
        ):
            with patch("urllib.request.urlopen", return_value=FakeHTTPResponse(b'{"access_token":"oauth-token"}')) as urlopen:
                token = get_token(account="greenmark")

        request = urlopen.call_args.args[0]
        self.assertEqual(token, "Bearer oauth-token")
        self.assertIn(b"client_id=greenmark-client", request.data)
        self.assertIn(b"client_secret=greenmark-secret", request.data)
        self.assertNotIn(b"ambient-client", request.data)
        self.assertNotIn(b"ambient-secret", request.data)

    def test_get_token_blocks_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingTokenError):
                get_token()

    def test_redact_token_removes_oauth_client_secret(self):
        with patch.dict(os.environ, {FALLBACK_OAUTH_CLIENT_SECRET_ENV: "client-secret"}, clear=True):
            redacted = redact_token("client_secret=client-secret")

        self.assertIn("[REDACTED_LINEAR_TOKEN]", redacted)
        self.assertNotIn("client-secret", redacted)

    def test_execute_retries_transient_http_errors(self):
        error = urllib.error.HTTPError(
            url="https://api.linear.app/graphql",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=FakeErrorBody(b"temporary"),
        )
        client = LinearPlusClient(token="lin-secret", max_retries=1, retry_sleep_seconds=0)

        with patch("urllib.request.urlopen", side_effect=[error, FakeHTTPResponse(b'{"data":{"ok":true}}')]) as urlopen:
            with patch("linearplus.client.time.sleep") as sleep:
                result = client.execute("query { viewer { id } }")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

    def test_clean_input_drops_empty_values(self):
        self.assertEqual(clean_input({"name": "A", "description": "", "color": None}), {"name": "A"})

    def test_initiative_by_name_exact_match(self):
        client = FakeClient(
            [
                {
                    "initiatives": {
                        "nodes": [
                            {"id": "wrong", "name": "Other"},
                            {"id": "init-1", "name": "Greenmark AI Search Visibility"},
                        ]
                    }
                }
            ]
        )

        result = initiative_by_name(client, "Greenmark AI Search Visibility")

        self.assertEqual(result["id"], "init-1")
        self.assertIn("initiatives", client.calls[0][0])
        self.assertEqual(client.calls[0][1], {"name": "Greenmark AI Search Visibility"})

    def test_ensure_initiative_avoids_duplicate_create(self):
        client = FakeClient([{"initiatives": {"nodes": [{"id": "init-1", "name": "Existing"}]}}])

        initiative, created = ensure_initiative(client, {"name": "Existing"})

        self.assertFalse(created)
        self.assertEqual(initiative["id"], "init-1")
        self.assertEqual(len(client.calls), 1)

    def test_ensure_initiative_creates_when_missing(self):
        client = FakeClient(
            [
                {"initiatives": {"nodes": []}},
                {"initiativeCreate": {"initiative": {"id": "init-2", "name": "New"}}},
            ]
        )

        initiative, created = ensure_initiative(client, {"name": "New", "description": ""})

        self.assertTrue(created)
        self.assertEqual(initiative["id"], "init-2")
        self.assertIn("initiativeCreate", client.calls[1][0])
        self.assertEqual(client.calls[1][1], {"input": {"name": "New"}})

    def test_greenmark_input_targets_existing_project(self):
        payload = greenmark_input()

        self.assertEqual(payload["name"], "Greenmark AI Search Visibility")
        self.assertEqual(GREENMARK_PROJECT_ID, "079b8875-9c80-41c8-b4b0-ea09834a7065")
        self.assertEqual(payload["status"], "Planned")

    def test_cli_missing_token_returns_blocked_without_secret(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr") as stderr:
            code = main(["greenmark-bootstrap"])

        self.assertEqual(code, 3)
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("missing_token", written)

    def test_build_client_uses_lineardb_token_store_for_explicit_account(self):
        args = type("Args", (), {"account": "greenmark", "token_env": "LINEAR_API_KEY", "endpoint": "https://example.test/graphql"})()
        with patch.object(cli_module, "lineardb_get_token", return_value="Bearer lineardb-token") as get_lineardb_token:
            client = cli_module.build_client(args)

        get_lineardb_token.assert_called_once_with(account="greenmark")
        self.assertEqual(client.token, "Bearer lineardb-token")
        self.assertEqual(client.endpoint, "https://example.test/graphql")

    def test_query_constants_use_expected_mutations(self):
        self.assertIn("initiativeCreate", INITIATIVE_CREATE)
        self.assertIn("InitiativeCreateInput", INITIATIVE_CREATE)
        self.assertIn("initiativeToProjectCreate", INITIATIVE_TO_PROJECT_CREATE)
        self.assertIn("InitiativeToProjectCreateInput", INITIATIVE_TO_PROJECT_CREATE)

    def test_dry_run_output_is_json_and_has_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("linearplus.cli.build_client") as build_client, patch("sys.stdout") as stdout:
                code = main(["greenmark-bootstrap", "--dry-run"])

        self.assertEqual(code, 0)
        build_client.assert_not_called()
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        data = json.loads(output)
        self.assertTrue(data["dry_run"])
        self.assertNotIn("LINEAR_API_KEY", output)

    def test_auth_check_reports_required_team_presence(self):
        fake_client = FakeClient(
            [
                {
                    "viewer": {
                        "id": "viewer-1",
                        "email": "daniel@greenmarkwaste.com",
                        "organization": {"name": "Greenmark"},
                    }
                },
                {
                    "teams": {
                        "nodes": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                },
            ]
        )
        with patch("linearplus.cli.build_client", return_value=fake_client), patch("sys.stdout") as stdout:
            code = main(["auth-check", "--team-key", "GMW"])

        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        self.assertTrue(data["has_required_team"])
        self.assertEqual(data["team_keys"], ["GMW"])

    def test_auth_check_delegates_to_lineardb_when_available(self):
        def fake_auth_check(client, team_key="GMW", team_page_size=100):
            self.assertIsInstance(client, FakeLinearDBClient)
            self.assertEqual(client.token, "lin-secret")
            return {
                "viewer": {"id": "viewer-1"},
                "teams": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
                "team_keys": ["GMW"],
                "required_team_key": team_key,
                "has_required_team": True,
            }

        with patch("linearplus.cli.build_client", return_value=LinearPlusClient(token="lin-secret")):
            with patch.object(cli_module, "LinearDBClient", FakeLinearDBClient):
                with patch.object(cli_module, "lineardb_auth_check", side_effect=fake_auth_check):
                    with patch("sys.stdout") as stdout:
                        code = main(["auth-check", "--team-key", "GMW"])

        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(data["source"], "lineardb")

    def test_greenmark_issue_analytics_summarizes_paginated_team_issues(self):
        analytics_fn = getattr(client_module, "greenmark_issue_analytics", None)
        self.assertIsNotNone(analytics_fn)
        client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-1",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "identifier": "GMW-1",
                                            "title": "Open work",
                                            "priorityLabel": "High",
                                            "createdAt": "2026-05-01T00:00:00Z",
                                            "updatedAt": "2026-05-20T00:00:00Z",
                                            "state": {"name": "In Progress", "type": "started"},
                                            "assignee": {"name": "Daniel"},
                                            "project": {"name": "Cerebro"},
                                            "labels": {"nodes": [{"name": "Paylocity"}]},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                                },
                            }
                        ]
                    }
                },
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-1",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "identifier": "GMW-2",
                                            "title": "Done work",
                                            "priorityLabel": "Medium",
                                            "createdAt": "2026-04-01T00:00:00Z",
                                            "updatedAt": "2026-04-15T00:00:00Z",
                                            "completedAt": "2026-04-20T00:00:00Z",
                                            "state": {"name": "Done", "type": "completed"},
                                            "assignee": None,
                                            "project": None,
                                            "labels": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                },
            ]
        )

        result = analytics_fn(client, team_key="GMW", page_size=1)

        self.assertEqual(result["team"]["key"], "GMW")
        self.assertEqual(result["totals"]["issues"], 2)
        self.assertEqual(result["state_types"], {"completed": 1, "started": 1})
        self.assertEqual(result["priorities"], {"High": 1, "Medium": 1})
        self.assertEqual(result["assignees"], {"Daniel": 1, "Unassigned": 1})
        self.assertEqual(result["projects"], {"Cerebro": 1, "No project": 1})
        self.assertEqual(result["labels"], {"Paylocity": 1})
        self.assertEqual(result["sample_issues"][0]["identifier"], "GMW-1")
        self.assertEqual(client.calls[1][1]["after"], "cursor-1")

    def test_greenmark_analytics_dry_run_output_is_json_and_has_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("linearplus.cli.build_client") as build_client, patch("sys.stdout") as stdout:
                code = main(["greenmark-analytics", "--dry-run"])

        self.assertEqual(code, 0)
        build_client.assert_not_called()
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(data["operation"], "greenmark-analytics")
        self.assertEqual(data["team_key"], "GMW")
        self.assertTrue(data["dry_run"])
        self.assertNotIn("LINEAR_API_KEY", output)

    def test_greenmark_analytics_query_targets_team_issues(self):
        query = getattr(client_module, "TEAM_ISSUES", "")

        self.assertIn("teams", query)
        self.assertIn("issues", query)
        self.assertIn("priorityLabel", query)
        self.assertNotIn("initiativeCreate", query)

    def test_greenmark_issue_dump_includes_raw_issues_and_analytics(self):
        dump_fn = getattr(client_module, "greenmark_issue_dump", None)
        self.assertIsNotNone(dump_fn)
        client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-1",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "identifier": "GMW-3",
                                            "title": "Dump this task",
                                            "priorityLabel": "Urgent",
                                            "updatedAt": "2026-06-01T00:00:00Z",
                                            "state": {"name": "Todo", "type": "unstarted"},
                                            "assignee": None,
                                            "project": {"name": "Cerebro"},
                                            "labels": {"nodes": [{"name": "API"}]},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                }
            ]
        )

        result = dump_fn(client, team_key="GMW", page_size=50, sample_size=10)

        self.assertEqual(result["team"]["key"], "GMW")
        self.assertEqual(result["analytics"]["totals"]["issues"], 1)
        self.assertEqual(result["issues"][0]["identifier"], "GMW-3")
        self.assertEqual(result["query"]["team_key"], "GMW")

    def test_greenmark_dump_command_writes_json_artifact(self):
        fake_client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-1",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "identifier": "GMW-4",
                                            "title": "Write artifact",
                                            "priorityLabel": "Low",
                                            "updatedAt": "2026-06-02T00:00:00Z",
                                            "state": {"name": "Todo", "type": "unstarted"},
                                            "assignee": {"name": "Daniel"},
                                            "project": None,
                                            "labels": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "gmw-dump.json"
            with patch("linearplus.cli.build_client", return_value=fake_client), patch("sys.stdout") as stdout:
                code = main(["greenmark-dump", "--output", str(output_path)])

            self.assertEqual(code, 0)
            written = json.loads(output_path.read_text())
            self.assertEqual(written["issues"][0]["identifier"], "GMW-4")
            self.assertEqual(written["analytics"]["totals"]["issues"], 1)
            output = "".join(call.args[0] for call in stdout.write.call_args_list)
            self.assertIn(str(output_path), output)

    def test_account_issue_dump_fetches_all_teams_and_issues(self):
        dump_fn = getattr(client_module, "account_issue_dump", None)
        self.assertIsNotNone(dump_fn)
        client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [
                            {"id": "team-gmw", "key": "GMW", "name": "Greenmark"},
                            {"id": "team-aic", "key": "AIC", "name": "AIC"},
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                },
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-gmw",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "id": "issue-1",
                                            "identifier": "GMW-1",
                                            "title": "Greenmark task",
                                            "priorityLabel": "High",
                                            "updatedAt": "2026-06-01T00:00:00Z",
                                            "state": {"name": "Todo", "type": "unstarted"},
                                            "assignee": {"id": "user-1", "name": "Daniel"},
                                            "project": {"id": "project-1", "name": "Cerebro", "url": "https://linear.app/project"},
                                            "labels": {"nodes": [{"id": "label-1", "name": "Paylocity"}]},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                },
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-aic",
                                "key": "AIC",
                                "name": "AIC",
                                "issues": {
                                    "nodes": [
                                        {
                                            "id": "issue-2",
                                            "identifier": "AIC-1",
                                            "title": "AIC task",
                                            "priorityLabel": "Medium",
                                            "updatedAt": "2026-06-02T00:00:00Z",
                                            "state": {"name": "Done", "type": "completed"},
                                            "assignee": None,
                                            "project": None,
                                            "labels": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                },
            ]
        )

        result = dump_fn(client, team_page_size=50, issue_page_size=100, include_related=False)

        self.assertEqual([team["key"] for team in result["teams"]], ["GMW", "AIC"])
        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["GMW-1", "AIC-1"])
        self.assertEqual(result["analytics"]["totals"]["issues"], 2)
        self.assertEqual(result["analytics"]["teams"], {"AIC": 1, "GMW": 1})

    def test_account_issue_dump_fetches_comments_attachments_history_and_state_spans(self):
        client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                },
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-gmw",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "id": "issue-1",
                                            "identifier": "GMW-1",
                                            "title": "Related task",
                                            "priorityLabel": "High",
                                            "updatedAt": "2026-06-01T00:00:00Z",
                                            "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                                            "assignee": {"id": "user-1", "name": "Daniel"},
                                            "project": {"id": "project-1", "name": "Cerebro"},
                                            "labels": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                },
                {
                    "issue": {
                        "comments": {
                            "nodes": [
                                {
                                    "id": "comment-1",
                                    "body": "Status note",
                                    "createdAt": "2026-06-01T01:00:00Z",
                                    "updatedAt": "2026-06-01T01:00:00Z",
                                    "user": {"id": "user-1", "name": "Daniel"},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                },
                {
                    "issue": {
                        "attachments": {
                            "nodes": [
                                {
                                    "id": "attachment-1",
                                    "title": "Proof",
                                    "url": "https://linear.app/file",
                                    "sourceType": "file",
                                    "createdAt": "2026-06-01T02:00:00Z",
                                    "creator": {"id": "user-1", "name": "Daniel"},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                },
                {
                    "issue": {
                        "history": {
                            "nodes": [
                                {
                                    "id": "history-1",
                                    "createdAt": "2026-06-01T03:00:00Z",
                                    "actor": {"id": "user-1", "name": "Daniel"},
                                    "fromState": {"id": "state-0", "name": "Backlog", "type": "backlog"},
                                    "toState": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                },
                {
                    "issue": {
                        "stateHistory": {
                            "nodes": [
                                {
                                    "id": "span-1",
                                    "stateId": "state-1",
                                    "startedAt": "2026-06-01T03:00:00Z",
                                    "endedAt": None,
                                    "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                },
            ]
        )

        result = client_module.account_issue_dump(client, include_related=True, related_page_size=25)

        self.assertEqual(result["related"]["comments"][0]["issue_id"], "issue-1")
        self.assertEqual(result["related"]["attachments"][0]["issue_identifier"], "GMW-1")
        self.assertEqual(result["related"]["history"][0]["id"], "history-1")
        self.assertEqual(result["related"]["state_spans"][0]["state"]["name"], "Todo")

    def test_write_account_dump_sqlite_persists_core_tables(self):
        writer_fn = getattr(client_module, "write_account_dump_sqlite", None)
        self.assertIsNotNone(writer_fn)
        dump = {
            "teams": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
            "issues": [
                {
                    "id": "issue-1",
                    "identifier": "GMW-1",
                    "title": "Persist me",
                    "team": {"id": "team-gmw", "key": "GMW", "name": "Greenmark"},
                    "state": {"name": "Todo", "type": "unstarted"},
                    "assignee": {"id": "user-1", "name": "Daniel"},
                    "project": {"id": "project-1", "name": "Cerebro", "url": "https://linear.app/project"},
                    "labels": {"nodes": [{"id": "label-1", "name": "Paylocity"}]},
                    "updatedAt": "2026-06-01T00:00:00Z",
                }
            ],
            "related": {
                "comments": [
                    {
                        "id": "comment-1",
                        "issue_id": "issue-1",
                        "issue_identifier": "GMW-1",
                        "body": "Persisted comment",
                        "createdAt": "2026-06-01T01:00:00Z",
                        "updatedAt": "2026-06-01T01:00:00Z",
                        "user": {"id": "user-1", "name": "Daniel"},
                    }
                ],
                "attachments": [
                    {
                        "id": "attachment-1",
                        "issue_id": "issue-1",
                        "issue_identifier": "GMW-1",
                        "title": "Proof",
                        "url": "https://linear.app/file",
                        "sourceType": "file",
                        "createdAt": "2026-06-01T02:00:00Z",
                        "creator": {"id": "user-1", "name": "Daniel"},
                    }
                ],
                "history": [
                    {
                        "id": "history-1",
                        "issue_id": "issue-1",
                        "issue_identifier": "GMW-1",
                        "createdAt": "2026-06-01T03:00:00Z",
                        "actor": {"id": "user-1", "name": "Daniel"},
                        "fromState": {"id": "state-0", "name": "Backlog", "type": "backlog"},
                        "toState": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                    }
                ],
                "state_spans": [
                    {
                        "id": "span-1",
                        "issue_id": "issue-1",
                        "issue_identifier": "GMW-1",
                        "stateId": "state-1",
                        "startedAt": "2026-06-01T03:00:00Z",
                        "endedAt": None,
                        "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                    }
                ],
            },
            "analytics": {"totals": {"issues": 1}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "linear.sqlite"

            writer_fn(dump, db_path)

            with sqlite3.connect(db_path) as connection:
                issue_count = connection.execute("select count(*) from issues").fetchone()[0]
                team_key = connection.execute("select team_key from issues where identifier = 'GMW-1'").fetchone()[0]
                label_count = connection.execute("select count(*) from issue_labels").fetchone()[0]
                snapshot_count = connection.execute("select count(*) from issue_snapshots").fetchone()[0]
                comment_count = connection.execute("select count(*) from comments").fetchone()[0]
                attachment_count = connection.execute("select count(*) from attachments").fetchone()[0]
                history_count = connection.execute("select count(*) from issue_history").fetchone()[0]
                span_count = connection.execute("select count(*) from issue_state_spans").fetchone()[0]
                sync_count = connection.execute("select count(*) from sync_runs").fetchone()[0]

        self.assertEqual(issue_count, 1)
        self.assertEqual(team_key, "GMW")
        self.assertEqual(label_count, 1)
        self.assertEqual(snapshot_count, 1)
        self.assertEqual(comment_count, 1)
        self.assertEqual(attachment_count, 1)
        self.assertEqual(history_count, 1)
        self.assertEqual(span_count, 1)
        self.assertEqual(sync_count, 1)

    def test_write_account_dump_sqlite_keeps_existing_file_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "linear.sqlite"
            db_path.write_text("previous")

            with patch("linearplus.client.write_account_dump_sqlite_file", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    client_module.write_account_dump_sqlite({}, db_path)

            temp_files = list(Path(temp_dir).glob("*.tmp"))
            self.assertEqual(db_path.read_text(), "previous")
            self.assertEqual(temp_files, [])

    def test_account_dump_command_writes_sqlite_artifact(self):
        fake_client = FakeClient(
            [
                {
                    "teams": {
                        "nodes": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                },
                {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-gmw",
                                "key": "GMW",
                                "name": "Greenmark",
                                "issues": {
                                    "nodes": [
                                        {
                                            "id": "issue-1",
                                            "identifier": "GMW-1",
                                            "title": "Account dump",
                                            "priorityLabel": "High",
                                            "updatedAt": "2026-06-01T00:00:00Z",
                                            "state": {"name": "Todo", "type": "unstarted"},
                                            "assignee": None,
                                            "project": None,
                                            "labels": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                },
                            }
                        ]
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "linear.sqlite"
            with patch("linearplus.cli.build_client", return_value=fake_client), patch("sys.stdout") as stdout:
                code = main(["account-dump", "--skip-related", "--sqlite", str(db_path)])

            self.assertEqual(code, 0)
            with sqlite3.connect(db_path) as connection:
                issue_count = connection.execute("select count(*) from issues").fetchone()[0]
            output = "".join(call.args[0] for call in stdout.write.call_args_list)

        self.assertEqual(issue_count, 1)
        self.assertIn(str(db_path), output)

    def test_account_dump_delegates_to_lineardb_when_available(self):
        dump = {
            "teams": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
            "issues": [],
            "related": {"comments": [], "attachments": [], "history": [], "state_spans": []},
            "analytics": {"totals": {"issues": 0}},
        }

        def fake_account_mirror_dump(client, **kwargs):
            self.assertIsInstance(client, FakeLinearDBClient)
            self.assertEqual(kwargs["account"], "greenmark")
            return dump

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "linear.sqlite"
            with patch("linearplus.cli.build_client", return_value=LinearPlusClient(token="lin-secret")):
                with patch.object(cli_module, "LinearDBClient", FakeLinearDBClient):
                    with patch.object(cli_module, "lineardb_account_mirror_dump", side_effect=fake_account_mirror_dump):
                        with patch.object(cli_module, "lineardb_write_mirror_sqlite") as writer:
                            with patch("sys.stdout") as stdout:
                                code = main(["--account", "greenmark", "account-dump", "--sqlite", str(db_path)])

        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(data["source"], "lineardb")
        writer.assert_called_once()
        self.assertEqual(writer.call_args.args[0], dump)
        self.assertEqual(writer.call_args.args[1], db_path.resolve())


if __name__ == "__main__":
    unittest.main()
