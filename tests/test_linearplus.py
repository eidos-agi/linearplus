from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from linearplus.client import (
    INITIATIVE_CREATE,
    INITIATIVE_TO_PROJECT_CREATE,
    MissingTokenError,
    clean_input,
    ensure_initiative,
    get_token,
    initiative_by_name,
    redact_token,
)
from linearplus.cli import GREENMARK_PROJECT_ID, greenmark_input, main


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, query, variables=None):
        self.calls.append((query, variables or {}))
        return self.responses.pop(0)


class LinearPlusTests(unittest.TestCase):
    def test_get_token_uses_env_without_printing_value(self):
        with patch.dict(os.environ, {"LINEAR_API_KEY": "lin-secret"}, clear=True):
            self.assertEqual(get_token(), "lin-secret")
            self.assertEqual(redact_token("token=lin-secret"), "token=[REDACTED_LINEAR_TOKEN]")

    def test_get_token_blocks_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingTokenError):
                get_token()

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


if __name__ == "__main__":
    unittest.main()
