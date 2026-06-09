# LinearDB

LinearDB is the Eidos product category for turning Linear into a durable local
database. It owns connectivity, sync, schema, credential truth, and local
analytics over the mirrored data. LinearPlus uses LinearDB for Linear access,
then layers initiative and Greenmark-specific commands on top.

The standalone LinearDB package now lives at:

```text
/Users/dshanklinbv/repos-eidos-agi/lineardb
```

LinearPlus still carries compatible LinearDB-shaped commands while the package
boundary is wired through the plugin.

## Boundary

LinearDB owns:

- Linear authentication and workspace identity checks.
- OAuth installed-user connection, local token storage, and refresh-token
  rotation.
- Visible team inventory and required-team validation.
- Local SQLite schema for issues, snapshots, comments, attachments, issue
  history, and state spans.
- Atomic writes and retry behavior for large syncs.
- Local analytics over the SQLite mirror without additional Linear API calls.

LinearPlus owns:

- Greenmark initiative bootstrap.
- Initiative lookup/create/attach workflows.
- Greenmark task analytics and JSON dump commands.
- User-facing CLI routing for LinearPlus plugin workflows.

## Why OAuth

Personal API keys drift with the currently active Linear login and browser
profile. That already produced a Boone Voyage export when the intended target
was Greenmark `GMW`.

For recurring data products, LinearDB uses Linear OAuth installed-user
authorization:

- Scope: `read`.
- Actor: `user`.
- Token lifetime: 24-hour access token plus refresh token.
- Refresh behavior: LinearDB refreshes and rotates stored refresh tokens.
- First Greenmark account: `greenmark`, connected as `daniel@eidosagi.com`,
  validated against team `GMW`.

This moves connectivity from "whatever user login/profile is active" to a
workspace app identity that can be validated before any dump runs.

## Environment Variables

Single-account profile support is implemented first. The first intended account
profile is `greenmark`.

Account-scoped OAuth app credentials:

```bash
LINEARDB_GREENMARK_OAUTH_CLIENT_ID
LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET
LINEARDB_GREENMARK_OAUTH_SCOPE=read
```

Optional account policy overrides:

```bash
LINEARDB_GREENMARK_OAUTH_REDIRECT_URI=http://localhost:8721/oauth/callback
LINEARDB_GREENMARK_EXPECTED_EMAIL=daniel@eidosagi.com
LINEARDB_GREENMARK_TEAM_KEY=GMW
LINEARDB_TOKEN_DB=~/.lineardb/credentials.sqlite
```

LinearDB must never print, commit, or write OAuth client secrets or access
tokens to repo files. OAuth tokens are stored in the local credential database;
OAuth client secrets should come from a local shell, Keychain, or another
Daniel-owned secret store.

When `--account greenmark` is supplied, LinearDB only uses
the stored OAuth profile and `LINEARDB_GREENMARK_*` app settings. It does not
fall back to ambient `LINEARPLUS_*`, `LINEAR_*`, or personal API-key
credentials, because that would reintroduce the wrong-workspace failure mode.

## Validation

Run this before any Greenmark dump:

```bash
cd /Users/dshanklinbv/repos-eidos-agi/lineardb
bin/lineardb --account greenmark connect
bin/lineardb --account greenmark auth-check --team-key GMW
```

The current LinearPlus compatibility command is:

```bash
bin/linearplus --account greenmark auth-check --team-key GMW
```

A Greenmark-ready credential must show `has_required_team: true` for `GMW`.
If it does not, stop. Do not run `greenmark-dump`, `greenmark-analytics`, or a
full `account-dump` and call it Greenmark data.

## SQLite Tables

Current state:

- `teams`
- `issues`
- `projects`
- `users`
- `labels`
- `issue_labels`
- `metadata`

Time-series:

- `sync_runs`
- `issue_snapshots`

Related issue data:

- `comments`
- `attachments`
- `issue_history`
- `issue_state_spans`

Every object table includes `raw_json` so the mirror can preserve Linear fields
before every field has a first-class column.

## Local Analytics

The standalone package can analyze a mirror without calling Linear:

```bash
cd /Users/dshanklinbv/repos-eidos-agi/lineardb
bin/lineardb analytics --sqlite outputs/greenmark-linear.sqlite --team-key GMW
```

It reports issue totals, counts by team/state/priority/assignee/project/label,
stale open issue samples, snapshot run history, and state trends.

## Operational Notes

- Start with `--account greenmark auth-check --team-key GMW`.
- Then run `--account greenmark account-dump --skip-related` to prove
  workspace/team coverage and local write behavior.
- For the standalone product path, use `lineardb sync` and
  `lineardb analytics`.
- Use the full related-data dump only when comments, attachments, history, or
  state spans are needed.
- SQLite writes are atomic: failed exports should not replace a previous good
  database.
- LinearDB retries transient Linear `429`, `502`, `503`, and `504` responses.

## Useful Queries

Team inventory:

```sql
select key, name from teams order by key;
```

Table counts:

```sql
select 'teams', count(*) from teams
union all select 'issues', count(*) from issues
union all select 'sync_runs', count(*) from sync_runs
union all select 'issue_snapshots', count(*) from issue_snapshots
union all select 'comments', count(*) from comments
union all select 'attachments', count(*) from attachments
union all select 'issue_history', count(*) from issue_history
union all select 'issue_state_spans', count(*) from issue_state_spans;
```

State span inputs:

```sql
select issue_identifier, state_name, started_at, ended_at
from issue_state_spans
order by issue_identifier, started_at;
```
