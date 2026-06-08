---
name: use-linearplus
description: Use when the user asks for LinearPlus, Linear initiatives through API, Linear GraphQL initiative creation, attaching Linear projects to initiatives, Greenmark task analytics, or when the Linear connector cannot create/list initiatives.
---

# Use LinearPlus

Use the installed LinearPlus CLI when Linear initiative workflows are needed and
the connected Linear tool surface does not expose the required operation.

## Primary Rule

Run the smallest relevant `linearplus` command first, then report from its JSON
or fail-closed output. Do not use browser UI automation as the primary path.

Useful entrypoints:

```bash
linearplus --help
linearplus --account greenmark auth-check --team-key GMW
linearplus initiative-get --name "Greenmark AI Search Visibility"
linearplus initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
linearplus attach-project --initiative-id <initiative-id> --project-id <project-id>
linearplus greenmark-bootstrap --dry-run
linearplus greenmark-bootstrap
linearplus greenmark-analytics --dry-run
linearplus greenmark-analytics
linearplus greenmark-dump --dry-run
linearplus greenmark-dump
linearplus account-dump --dry-run
linearplus account-dump
```

If the `linearplus` command is not on `PATH`, resolve the plugin root from this
skill file and run:

```bash
bin/linearplus --help
```

## LinearDB Boundary

LinearPlus uses LinearDB for connectivity and local Linear data sync. LinearDB
is the product/category for OAuth app access, identity/team validation, local
SQLite sync, time-series snapshots, and related issue metadata.

Run this before treating any credential as Greenmark-ready:

```bash
linearplus --account greenmark auth-check --team-key GMW
```

## Credential Boundary

- Preferred recurring setup is account-scoped OAuth client credentials:
  `LINEARDB_GREENMARK_OAUTH_CLIENT_ID`,
  `LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET`, and optional
  `LINEARDB_GREENMARK_OAUTH_SCOPE=read`.
- Personal API key fallback uses `LINEAR_API_KEY` or
  `LINEARPLUS_LINEAR_API_KEY`; for Greenmark prefer
  `LINEARDB_GREENMARK_LINEAR_API_KEY` if a personal key must be used.
- Explicit accounts fail closed: `--account greenmark` must not fall back to
  ambient `LINEARPLUS_*` or `LINEAR_*` credentials.
- It must not print, store, or ask the model to reveal Linear API tokens,
  OAuth client secrets, or access tokens.
- If credentials are missing, report the missing-token blocker and preserve the
  dry-run evidence.
- Prefer OAuth client credentials for Greenmark/LinearDB. Use browser pairing
  only to help Daniel create or configure the Linear OAuth app; do not scrape or
  echo secrets.

## Pairing Procedure

Use this procedure when LinearPlus needs a Linear API key.

1. Confirm the task needs live Linear API access.
   Run the dry-run command first and explain what the live command would change.

2. Ask Daniel to create or choose a Linear personal API key.
   Linear's current docs place personal API keys under:
   `Settings > Account > Security & Access`.

3. If Daniel is not an admin and cannot create a key, tell him the workspace
   may restrict member API keys under:
   `Settings > Administration > API > Member API keys`.

4. Ask Daniel to provide the key only through an approved local secret path or
   shell environment. Do not ask him to paste the token into chat.

5. Verify presence without revealing the value:

   ```bash
   test -n "$LINEARPLUS_LINEAR_API_KEY" || test -n "$LINEAR_API_KEY"
   ```

6. Run one read or dry-run-safe check first when possible, then perform the
   narrow live mutation that Daniel requested.

7. Capture evidence with the command, redacted output, created or reused Linear
   ids/urls, and any permission blocker. Never record the token.

Recommended temporary shell form:

```bash
export LINEARPLUS_LINEAR_API_KEY="..."
linearplus initiative-get --name "Greenmark AI Search Visibility"
```

Recommended persistent handling is a local vault or shell profile entry owned
by Daniel, not plugin-managed storage.

Official references:

- `https://linear.app/developers/oauth-2-0-authentication`
- `https://linear.app/docs/api-and-webhooks`
- `https://linear.app/developers/graphql`

## Greenmark Bootstrap

Use `linearplus greenmark-bootstrap` to create or reuse the
`Greenmark AI Search Visibility` initiative and attach project
`079b8875-9c80-41c8-b4b0-ea09834a7065`.

Start with:

```bash
linearplus greenmark-bootstrap --dry-run
```

Then run live only when a valid Linear API key is available in environment or
approved vault-backed shell context.

## Greenmark Analytics

Use `linearplus greenmark-analytics` for read-only analytics across the full
Greenmark Linear team (`GMW`). It returns JSON counts by state type, state,
priority, assignee, project, and label, plus sample issue summaries and stale
open issue samples.

Start with:

```bash
linearplus greenmark-analytics --dry-run
```

Then run live only when a valid Linear API key is available in environment or
approved vault-backed shell context. The command is read-only but still needs a
Linear API key for live issue data.

## Account-Wide SQLite Dump

Use `linearplus account-dump` when Daniel wants task data for all accessible
Linear teams pulled from the Linear API onto this machine. It writes a SQLite
database under `outputs/linear/` in the LinearPlus plugin root unless
`--sqlite` or `--output-dir` is supplied.

The SQLite database stores raw JSON plus queryable current-state and timeline
tables:

- Current state: `teams`, `issues`, `projects`, `users`, `labels`,
  `issue_labels`, and `metadata`.
- Per-run time series: `sync_runs` and `issue_snapshots`.
- Related issue data: `comments`, `attachments`, `issue_history`, and
  `issue_state_spans`.

Start with:

```bash
linearplus account-dump --dry-run
```

Then run live only when a valid Linear API key is available in environment or
approved vault-backed shell context. The command is read-only but still needs a
Linear API key for live issue data.

Use `--skip-related` only when Daniel explicitly wants a fast current-state
refresh without comments, attachments, issue history, and state spans.

For schema details, key-handling boundaries, Surfari pairing cautions, GMW
access validation, and useful local SQL, consult `LINEARDB.md` in the
plugin root.

## Greenmark Data Dump

Use `linearplus greenmark-dump` when Daniel wants GMW task data pulled from the
Linear API onto this machine. It writes raw issues plus computed analytics to a
local JSON artifact under `outputs/greenmark/` in the LinearPlus plugin root
unless `--output` or `--output-dir` is supplied.

Start with:

```bash
linearplus greenmark-dump --dry-run
```

Then run live only when a valid Linear API key is available in environment or
approved vault-backed shell context. The command is read-only but still needs a
Linear API key for live issue data.
