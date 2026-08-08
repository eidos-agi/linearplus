---
name: use-eidos-linear
description: Use when the agent needs generic Eidos Linear extensions — initiative ensure, proof gate, mirror sync — beyond official Linear MCP issue CRUD. Client-specific flows (Greenmark) use separate skills.
---

# Use eidos-linear

`eidos-linear` is the MCP surface for Linear capabilities the official connector
does not cover. Pair it with official Linear MCP for issues, comments, and
projects.

## Primary rule

1. Run `eidos_proof` before initiative writes or mirror-dependent work.
2. Use **official Linear MCP** for issue/project CRUD.
3. Use **eidos-linear** for initiatives, proof, and mirrors.

## Tools (v1)

| Tool | When |
|------|------|
| `eidos_proof` | Doctor gate: token, team access, mirror freshness |
| `eidos_initiative_ensure` | Create or reuse initiative by exact name |
| `eidos_sync_status` | Read mirror health (no Linear call) |
| `eidos_account_sync` | Refresh canonical SQLite mirror |

## Credential boundary

- Auth via LinearDB OAuth: `lineardb --account <profile> connect`
- MCP env per cockpit: `LINEARDB_ACCOUNT`, optional `LINEARDB_MIRROR_SQLITE`, optional `LINEARDB_<ACCOUNT>_TEAM_KEY`
- Greenmark-specific flows → `skills/use-greenmark-linear/` + `linearplus greenmark-*` CLI
- Never print or store tokens in chat or repo files.

## Typical flow

```text
eidos_proof(account, team_key) → eidos_initiative_ensure(...)
eidos_proof warns mirror → eidos_account_sync → eidos_sync_status
```

## Sunset rule

When official Linear MCP gains parity for an `eidos_*` verb, retire that tool.

## Official pairing

```bash
grok mcp add --transport http linear https://mcp.linear.app/mcp
```

See [EIDOS_LINEAR.md](../../EIDOS_LINEAR.md) for architecture decisions.