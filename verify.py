#!/usr/bin/env python3
"""Eidos plugin verification hook for LinearPlus."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def verify(work_dir: Path | str | None = None, draft_dir: Path | str | None = None) -> dict[str, Any]:
    checks = [
        [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ["bin/linearplus", "--help"],
        ["bin/linearplus", "auth-check", "--dry-run"],
        ["bin/linearplus", "initiative-ensure", "--help"],
        ["bin/linearplus", "greenmark-bootstrap", "--dry-run"],
        ["bin/linearplus", "greenmark-analytics", "--dry-run"],
        ["bin/linearplus", "greenmark-dump", "--dry-run"],
        ["bin/linearplus", "account-dump", "--dry-run"],
    ]
    failures = []
    for command in checks:
        ok, output = run(command)
        if not ok:
            failures.append({"command": command, "output": output})

    required = [
        "plugin.yaml",
        "playbook.md",
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        "skills/use-linearplus/SKILL.md",
        "linearplus/client.py",
        "linearplus/cli.py",
        "tests/test_linearplus.py",
        "bin/linearplus",
        "README.md",
        "LINEARDB.md",
        "LINEAR_DATA_EXPORT.md",
        "LICENSE",
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            failures.append({"command": ["file-exists", rel], "output": "missing"})

    return {
        "passed": not failures,
        "reasons": ["LinearPlus plugin checks passed"] if not failures else [f"{len(failures)} checks failed"],
        "detail": {
            "plugin_root": str(ROOT),
            "work_dir": str(work_dir) if work_dir is not None else None,
            "draft_dir": str(draft_dir) if draft_dir is not None else None,
            "failures": failures,
        },
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
