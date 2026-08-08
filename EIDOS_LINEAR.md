# eidos-linear — Composite Linear MCP

Locked architecture (Daniel delegated picks, 2026-06-26). Evolved same day.

## Position

`eidos-linear` is the **account-agnostic, agent-facing MCP surface** for Linear
work at Eidos. It wraps capabilities that the official Linear MCP
(`https://mcp.linear.app/mcp`) does not cover, without duplicating issue CRUD.

**Client-specific workflows** (Greenmark, etc.) live in CLI verbs and cockpit
skills — not in this MCP server.

LinearPlus remains the implementation home. The MCP server lives in
`eidos_linear/` inside this repo.

## v1 scope (now)

| Pick | Choice |
|------|--------|
| Name | `eidos-linear` |
| Repo | Evolve `linearplus` (no greenfield) |
| Delivery | `eidos_*` tools only; keep official `linear` MCP enabled alongside |
| Auth | LinearDB OAuth profiles (`lineardb --account <name> connect`) |
| Tool prefix | `eidos_*` only for extensions |
| Tools | `eidos_proof`, `eidos_initiative_ensure`, `eidos_sync_status`, `eidos_account_sync` |
| Account config | Per-cockpit env: `LINEARDB_ACCOUNT`, optional mirror + team key |
| Sunset rule | Retire each `eidos_*` verb when official MCP gains parity |
| Grok delivery | `.mcp.json` in plugin + `skills/use-eidos-linear/` |

## v2 scope (later)

- Upstream proxy: forward official MCP tools through one server
- Optional: disable raw `linear` MCP once parity is proven

## Architecture

```
Agent → eidos-linear MCP (stdio)          ← generic, account-agnostic
          ├── eidos_* → LinearPlus + LinearDB
          └── (v2) forward → mcp.linear.app

Greenmark / client hats → skills/use-greenmark-linear + linearplus greenmark-* CLI
```

## Tool contracts

### `eidos_proof`

Doctor-style gate before Linear work:

1. Token present (LinearDB OAuth store)
2. Viewer can see required team key (pass `team_key` or set `LINEARDB_<ACCOUNT>_TEAM_KEY`)
3. SQLite mirror freshness (WARN if stale/missing)

Returns `verdict`: `CLEAR` | `WARN` | `BLOCK`.

### `eidos_initiative_ensure`

Find initiative by exact name or create it.

### `eidos_sync_status`

Read-only mirror health. Does not call Linear.

### `eidos_account_sync`

Pull all accessible teams/issues into the canonical mirror path.

## Credentials (per cockpit, not repo defaults)

```text
LINEARDB_ACCOUNT=<profile>
LINEARDB_MIRROR_SQLITE=~/.lineardb/mirrors/<profile>.sqlite   # optional
LINEARDB_<PROFILE>_TEAM_KEY=<key>                            # optional
```

Connect once: `lineardb --account <profile> connect`

## MCP install

**Marketplace plugin** (local checkout):

```json
"command": "uv",
"args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}/.", "eidos-linear-mcp"]
```

**Published / any machine**:

```json
"command": "uvx",
"args": ["--from", "git+https://github.com/eidos-agi/linearplus", "eidos-linear-mcp"]
```

Pair with official Linear MCP:

```bash
grok mcp add --transport http linear https://mcp.linear.app/mcp
```

Use **official** for issues/comments/projects. Use **eidos-linear** for
initiatives, proof gates, and mirror sync.