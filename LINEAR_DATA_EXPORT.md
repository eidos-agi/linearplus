# Linear Data Export

This document is the legacy export reference. The product/category name for
this layer is now **LinearDB**. See [LINEARDB.md](LINEARDB.md) for the boundary:
LinearDB owns Linear connectivity, OAuth client-credentials access, local
database sync, schema, retries, and workspace/team validation. LinearPlus uses
LinearDB for connectivity.

## Goal

`linearplus account-dump` is a read-only Linear GraphQL export for all teams
visible to the configured API key. It writes a local SQLite database that can be
queried with `sqlite3`, Python, DuckDB, Datasette, or any other local analysis
tool.

The export is account-scoped by the API key, not organization-scoped by
LinearPlus. If the key can see `GMW`, the dump can include Greenmark tasks. If
the key only sees another workspace, the dump will only contain that workspace.

## Credential Boundary

LinearPlus reads one of these environment variables:

```bash
LINEAR_API_KEY
LINEARPLUS_LINEAR_API_KEY
```

LinearPlus must not print, persist, or commit Linear API keys. For a persistent
local setup, store the value in a Daniel-owned secret manager such as macOS
Keychain and inject it into the process environment:

```bash
LINEARPLUS_LINEAR_API_KEY="$(security find-generic-password -a "$USER" -s LINEARPLUS_LINEAR_API_KEY -w)" \
  bin/linearplus account-dump --dry-run
```

If Surfari is used to help reach Linear's settings UI, use it only as a local
browser-assistance path for Daniel to create or rotate the key. Do not scrape,
log, screenshot, or paste token values through agent-visible output.

## Commands

Dry run:

```bash
bin/linearplus account-dump --dry-run
```

Current-state-only refresh:

```bash
bin/linearplus account-dump \
  --skip-related \
  --sqlite /Users/dshanklinbv/Documents/New\ project\ 5/outputs/linear/linear-account-tasks.sqlite
```

Full metadata refresh:

```bash
bin/linearplus account-dump \
  --related-page-size 25 \
  --sqlite /Users/dshanklinbv/Documents/New\ project\ 5/outputs/linear/linear-account-tasks.sqlite
```

The full metadata refresh performs additional API calls per issue for comments,
attachments, issue history, and state spans. Use `--skip-related` for a fast
inventory refresh and the default/full mode when time-series or evidence detail
matters.

Full metadata exports are intentionally heavier than current-state dumps.
LinearPlus retries transient Linear HTTP `429`, `502`, `503`, and `504` errors,
but operators should still run the fast `--skip-related` pass first and inspect
team coverage before starting a full account-wide related-data export.

SQLite writes are atomic: LinearPlus writes to a temporary database file and
replaces the target only after the dump has been fully written. A failed full
metadata export should not destroy the previous successful SQLite artifact.

## SQLite Tables

Current state:

- `teams`: accessible Linear teams.
- `issues`: latest known task state for each issue.
- `projects`: projects referenced by exported issues.
- `users`: assignees referenced by exported issues.
- `labels`: labels referenced by exported issues.
- `issue_labels`: issue-to-label join table.
- `metadata`: latest analytics JSON and latest sync run id.

Time-series:

- `sync_runs`: one row per local export run, with run timestamps, team count,
  issue count, and query/analytics JSON.
- `issue_snapshots`: one row per issue per export run, useful for tracking
  local changes over repeated dumps.

Related issue data:

- `comments`: issue comments, including body/bodyData, author, timestamps, and
  raw JSON.
- `attachments`: issue attachments, including title, URL, source type, creator,
  timestamps, and raw JSON.
- `issue_history`: Linear issue history events, including actor, state changes,
  assignee/project/priority/due-date transitions, timestamps, and raw JSON.
- `issue_state_spans`: Linear state span intervals with state id/name/type,
  start/end timestamps, and raw JSON.

## Useful Queries

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

Issues by team:

```sql
select team_key, count(*) as issues
from issues
group by team_key
order by issues desc;
```

Open issues by assignee:

```sql
select coalesce(assignee_name, 'Unassigned') as assignee, count(*) as open_issues
from issues
where state_type not in ('completed', 'canceled')
group by assignee
order by open_issues desc, assignee;
```

Recent comments:

```sql
select issue_identifier, user_name, created_at, body
from comments
order by created_at desc
limit 25;
```

State dwell time inputs:

```sql
select issue_identifier, state_name, started_at, ended_at
from issue_state_spans
order by issue_identifier, started_at;
```

Local snapshot history for one issue:

```sql
select run_id, captured_at, identifier, state_name, priority_label, assignee_id, updated_at
from issue_snapshots
where identifier = 'GMW-1'
order by captured_at;
```

## Greenmark/GMW Caveat

`greenmark-analytics` and `greenmark-dump` target team key `GMW` by default.
`account-dump` exports every team visible to the key. A key that cannot see
`GMW` will not produce Greenmark data, even if the command succeeds for another
workspace.

When validating a new key, first check the team inventory:

```bash
bin/linearplus account-dump --skip-related --sqlite /tmp/linear-account-check.sqlite
sqlite3 /tmp/linear-account-check.sqlite "select key, name from teams order by key;"
```

Only treat a dump as Greenmark-ready when `GMW` appears in `teams`.

## Live Validation Notes

Validation on 2026-06-08 used a Linear API key loaded from macOS Keychain via
`LINEARPLUS_LINEAR_API_KEY`. The key was not printed or stored in the repo.

Current-state account dump:

- Output database:
  `/Users/dshanklinbv/Documents/New project 5/outputs/linear/linear-account-tasks.sqlite`
- Visible teams: `AICRHEA`, `OO`, `OUR`, `RHEA`.
- Visible issue count: `1121`.
- `GMW` was not visible to this key, so this validation does not prove
  Greenmark task access.
- SQLite tables created successfully, including `sync_runs` and
  `issue_snapshots`.

Bounded related-data proof:

- Sample size: 10 recent visible issues.
- Related counts returned by live Linear API: `history=3`,
  `state_spans=10`, `comments=0`, `attachments=0`.
- This proves the comments, attachments, issue history, and state-span query
  paths execute against Linear; the sampled issues did not contain comments or
  attachments.

Full related-data attempt:

- A full account-wide related-data run over 1121 issues encountered a transient
  Linear HTTP `502` after several minutes.
- LinearPlus now retries transient `429`, `502`, `503`, and `504` responses and
  writes SQLite atomically so failed exports do not replace the previous good
  database.

## Verification

Run these before shipping changes:

```bash
python -m unittest discover -s tests -v
python verify.py
```

For live validation, run the current-state-only dump first, inspect table
counts, then decide whether the slower related-data pass is needed.
