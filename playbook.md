# LinearPlus Playbook

Use LinearPlus when an Eidos/Codex workflow needs Linear initiative operations
or Greenmark task data dumps/analytics that are missing or unreliable in the
connected Linear tool surface.

LinearPlus consumes LinearDB for connectivity. LinearDB is the product category
for OAuth-backed Linear access, workspace/team validation, local SQLite sync,
time-series snapshots, and related issue metadata.

## Use When

- A user explicitly asks for a Linear initiative and the connector can only
  create projects or issues.
- A Linear project needs to be attached to an initiative through the official
  Linear GraphQL API.
- Codex needs redacted evidence that a Linear initiative was created, reused, or
  blocked by missing credentials.
- Codex needs read-only analytics across the full Greenmark Linear team (`GMW`).
- Codex needs raw Greenmark task data pulled from Linear onto this machine for
  local analysis.
- Codex needs a local SQLite database of accessible Linear task data across all
  teams.
- Codex needs time-series snapshots, comments, attachments, issue history, or
  state-span data for local Linear analysis.

## Do Not Use When

- The normal Linear connector already exposes the needed operation reliably.
- The task is only issue creation or project description editing.
- The workflow would require printing, storing, rotating, or exposing a Linear
  API token.

## Commands

From the plugin root:

```bash
bin/linearplus --help
bin/linearplus --account greenmark auth-check --team-key GMW
bin/linearplus initiative-get --name "Greenmark AI Search Visibility"
bin/linearplus initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
bin/linearplus attach-project --initiative-id <initiative-id> --project-id <project-id>
bin/linearplus greenmark-bootstrap --dry-run
bin/linearplus greenmark-bootstrap
bin/linearplus greenmark-analytics --dry-run
bin/linearplus greenmark-analytics
bin/linearplus greenmark-dump --dry-run
bin/linearplus greenmark-dump
bin/linearplus account-dump --dry-run
bin/linearplus account-dump
bin/linearplus account-dump --skip-related
```

## Credentials

Preferred recurring setup is LinearDB OAuth client credentials:

```bash
export LINEARDB_GREENMARK_OAUTH_CLIENT_ID="..."
export LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET="..."
export LINEARDB_GREENMARK_OAUTH_SCOPE="read"
```

Personal API key fallback:

```bash
export LINEARDB_GREENMARK_LINEAR_API_KEY="..."
```

LinearPlus fails closed when neither variable is present. It does not prompt for
tokens and does not write tokens to repo files.

Always run `bin/linearplus --account greenmark auth-check --team-key GMW` before treating a
credential as Greenmark-ready.

Explicit accounts fail closed: `--account greenmark` must use
`LINEARDB_GREENMARK_*` credentials and must not fall back to ambient keys.

## Pairing Procedure

Use pairing when LinearPlus needs a live Linear API key. Do not turn this into
OAuth, browser automation, or plugin-managed token storage unless Daniel
explicitly asks for that implementation.

1. Run the relevant dry-run command first and explain the intended live change.
2. Have Daniel create or select a Linear personal API key in
   `Settings > Account > Security & Access`.
3. If key creation is unavailable, have a Linear admin check
   `Settings > Administration > API > Member API keys`.
4. Have Daniel provide the key through an approved local secret path or shell
   environment, not chat.
5. Verify only that a key exists:

   ```bash
   test -n "$LINEARPLUS_LINEAR_API_KEY" || test -n "$LINEAR_API_KEY"
   ```

6. Run the narrow LinearPlus command Daniel approved.
7. Record redacted evidence: command, created or reused ids/urls, and any
   permission blocker. Never record the token.

Official Linear references:

- `https://linear.app/docs/api-and-webhooks`
- `https://linear.app/developers/graphql`

## Evidence

For Eidos loops, capture:

- command run
- redacted JSON output
- initiative id/url when live execution succeeds
- project id/url or initiative-project relation when attach succeeds
- Greenmark analytics totals and count breakdowns when `greenmark-analytics`
  succeeds
- local artifact path, issue count, and analytics totals when `greenmark-dump`
  succeeds
- SQLite database path, team count, issue count, and analytics totals when
  `account-dump` succeeds
- related row counts for comments, attachments, issue history, and state spans
  when `account-dump` runs with the default related-data collection
- missing-token or permission blocker when live execution cannot proceed
- transient Linear `429`, `502`, `503`, or `504` errors if the full related-data
  export exceeds what Linear will serve cleanly in one sequential pass

For the LinearDB boundary, OAuth setup, account-wide export schema, key
boundary, Surfari pairing caution, and local SQL examples, use `LINEARDB.md`.

The Greenmark bootstrap target project is:

```text
079b8875-9c80-41c8-b4b0-ea09834a7065
```
