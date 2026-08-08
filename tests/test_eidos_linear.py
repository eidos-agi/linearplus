from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from eidos_linear.client import resolve_mirror_path
from eidos_linear.tools.initiatives import eidos_initiative_ensure
from eidos_linear.tools.proof import eidos_proof
from eidos_linear.tools.sync import account_sync, mirror_status


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.token = "Bearer test"
        self.endpoint = "https://api.linear.app/graphql"
        self.max_retries = 0
        self.retry_sleep_seconds = 0

    def execute(self, query, variables=None):
        self.calls.append((query, variables or {}))
        return self.responses.pop(0)


def write_mirror(path: Path, finished_at: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            create table metadata (key text primary key, value text not null);
            create table sync_runs (
              id text primary key,
              started_at text not null,
              finished_at text not null,
              team_count integer not null,
              issue_count integer not null,
              raw_json text not null
            );
            create table teams (id text primary key, key text, name text, raw_json text not null);
            create table issues (
              id text primary key, identifier text, title text, url text,
              team_id text, team_key text, state_name text, state_type text,
              priority_label text, assignee_id text, assignee_name text,
              project_id text, project_name text, cycle_id text, cycle_name text,
              created_at text, updated_at text, completed_at text, canceled_at text,
              due_date text, raw_json text not null
            );
            """
        )
        connection.execute(
            "insert into sync_runs values (?, ?, ?, ?, ?, ?)",
            ("run-1", finished_at, finished_at, 1, 2, "{}"),
        )
        connection.execute(
            "insert into metadata values (?, ?)",
            ("latest_sync_run_id", "run-1"),
        )
        connection.execute(
            "insert into teams values (?, ?, ?, ?)",
            ("team-1", "GMW", "Greenmark", "{}"),
        )
        connection.execute(
            """
            insert into issues(
              id, identifier, title, url, team_id, team_key, state_name, state_type,
              priority_label, assignee_id, assignee_name, project_id, project_name,
              cycle_id, cycle_name, created_at, updated_at, completed_at, canceled_at,
              due_date, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("i1", "GMW-1", "One", None, "team-1", "GMW", "Todo", "unstarted", None, None, None, None, None, None, None, None, None, None, None, None, "{}"),
        )
        connection.execute(
            """
            insert into issues(
              id, identifier, title, url, team_id, team_key, state_name, state_type,
              priority_label, assignee_id, assignee_name, project_id, project_name,
              cycle_id, cycle_name, created_at, updated_at, completed_at, canceled_at,
              due_date, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("i2", "GMW-2", "Two", None, "team-1", "GMW", "Done", "completed", None, None, None, None, None, None, None, None, None, None, None, None, "{}"),
        )
        connection.commit()


class EidosLinearTests(unittest.TestCase):
    def test_mirror_status_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.sqlite"
            with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
                result = mirror_status(sqlite=str(missing))

        self.assertFalse(result["exists"])
        self.assertTrue(result["stale"])
        self.assertIn("remediation", result)

    def test_mirror_status_fresh_file(self):
        finished_at = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "mirror.sqlite"
            write_mirror(db_path, finished_at)
            result = mirror_status(sqlite=str(db_path), stale_hours=24)

        self.assertTrue(result["exists"])
        self.assertFalse(result["stale"])
        self.assertEqual(result["team_count"], 1)
        self.assertEqual(result["issue_count"], 2)

    def test_eidos_proof_blocks_without_account(self):
        with patch.dict(os.environ, {}, clear=True):
            result = eidos_proof()

        self.assertEqual(result["verdict"], "BLOCK")
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"][0]["check"], "account")

    def test_eidos_proof_clear_with_auth_and_fresh_mirror(self):
        finished_at = datetime.now(timezone.utc).isoformat()
        fake_client = FakeClient(
            [
                {
                    "viewer": {
                        "id": "viewer-1",
                        "email": "daniel@eidosagi.com",
                        "organization": {"name": "Greenmark"},
                    }
                },
                {
                    "teams": {
                        "nodes": [{"id": "team-1", "key": "GMW", "name": "Greenmark"}],
                        "pageInfo": {"hasNextPage": False},
                    }
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "mirror.sqlite"
            write_mirror(db_path, finished_at)
            with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
                with patch("eidos_linear.tools.proof.build_client", return_value=fake_client):
                    with patch("eidos_linear.tools.proof.auth_check") as auth_check:
                        auth_check.return_value = {
                            "viewer": {"email": "daniel@eidosagi.com"},
                            "team_keys": ["GMW"],
                            "has_required_team": True,
                        }
                        result = eidos_proof(sqlite=str(db_path), team_key="GMW")

        self.assertEqual(result["verdict"], "CLEAR")
        self.assertTrue(result["ok"])

    def test_eidos_initiative_ensure_reuses_existing(self):
        fake_client = FakeClient([{"initiatives": {"nodes": [{"id": "init-1", "name": "Existing"}]}}])
        with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
            with patch("eidos_linear.tools.initiatives.build_client", return_value=fake_client):
                result = eidos_initiative_ensure(name="Existing")

        self.assertTrue(result["ok"])
        self.assertFalse(result["created"])
        self.assertEqual(result["initiative"]["id"], "init-1")

    def test_eidos_initiative_ensure_creates_when_missing(self):
        fake_client = FakeClient(
            [
                {"initiatives": {"nodes": []}},
                {"initiativeCreate": {"initiative": {"id": "init-2", "name": "New"}}},
            ]
        )
        with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
            with patch("eidos_linear.tools.initiatives.build_client", return_value=fake_client):
                result = eidos_initiative_ensure(name="New", status="Planned")

        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertEqual(result["initiative"]["id"], "init-2")

    def test_resolve_mirror_path_prefers_legacy_greenmark_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy = Path(temp_dir) / "greenmark-linear.sqlite"
            legacy.write_text("legacy")
            with patch("eidos_linear.client.legacy_mirror_candidates", return_value=[legacy]):
                with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
                    path = resolve_mirror_path(account="greenmark")

        self.assertEqual(path, legacy.resolve())

    def test_eidos_proof_blocks_without_team_key(self):
        # Isolate host LINEARDB_* / LINEAR_API_KEY so missing_team_key is deterministic.
        cleaned = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("LINEARDB_") and k != "LINEAR_API_KEY"
        }
        cleaned["LINEARDB_ACCOUNT"] = "eidos"
        with patch.dict(os.environ, cleaned, clear=True):
            with patch("lineardb.auth.default_team_key", return_value=None):
                result = eidos_proof()

        self.assertEqual(result["verdict"], "BLOCK")
        self.assertEqual(result["blocked"], "missing_team_key")

    def test_account_sync_writes_canonical_mirror(self):
        dump = {
            "teams": [{"id": "team-gmw", "key": "GMW", "name": "Greenmark"}],
            "issues": [],
            "related": {"comments": [], "attachments": [], "history": [], "state_spans": []},
            "analytics": {"totals": {"issues": 0}},
        }
        fake_client = FakeClient([])

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mirror.sqlite"
            with patch.dict(os.environ, {"LINEARDB_ACCOUNT": "greenmark"}, clear=False):
                with patch("eidos_linear.tools.sync.build_client", return_value=fake_client):
                    with patch("eidos_linear.tools.sync.account_mirror_dump", return_value=dump):
                        with patch("eidos_linear.tools.sync.write_mirror_sqlite") as writer:
                            with patch("eidos_linear.tools.sync.resolve_mirror_path", return_value=target):
                                result = account_sync()

        self.assertTrue(result["ok"])
        writer.assert_called_once_with(dump, target)

    def test_server_registers_tools(self):
        from eidos_linear.server import mcp

        tool_names = {tool.name for tool in mcp._tool_manager._tools.values()}  # noqa: SLF001
        self.assertEqual(
            tool_names,
            {
                "eidos_proof",
                "eidos_initiative_ensure",
                "eidos_sync_status",
                "eidos_account_sync",
            },
        )


if __name__ == "__main__":
    unittest.main()