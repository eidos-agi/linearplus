---
name: use-greenmark-linear
description: Greenmark-specific Linear workflows — bootstrap initiative, GMW analytics. Not generic eidos-linear; requires greenmark LinearDB account.
---

# Use Greenmark Linear

Greenmark is a **client account**, not part of the generic `eidos-linear` MCP.
Use this skill when the task is explicitly Greenmark / GMW / Greenmark Waste.

## Setup (once per machine)

```bash
export LINEARDB_GREENMARK_OAUTH_CLIENT_ID=...
export LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET=...
lineardb --account greenmark connect
```

Cockpit MCP env for Greenmark sessions:

```text
LINEARDB_ACCOUNT=greenmark
LINEARDB_MIRROR_SQLITE=~/.lineardb/mirrors/greenmark.sqlite
LINEARDB_GREENMARK_TEAM_KEY=GMW
```

## Generic MCP first

Run `eidos_proof` with `account=greenmark` and `team_key=GMW` (or rely on
LinearDB account policy for team key).

## Greenmark-only verbs (CLI, not generic MCP)

```bash
linearplus --account greenmark greenmark-bootstrap --dry-run
linearplus --account greenmark greenmark-bootstrap
linearplus --account greenmark greenmark-analytics
```

Initiative work can also use generic `eidos_initiative_ensure` with Greenmark
credentials in env — the bootstrap CLI is just the opinionated shortcut.

## Do not

- Bake `greenmark` defaults into shared `eidos-linear` config
- Use GMW as the default team key outside Greenmark cockpits