# LinearPlus

LinearPlus is a small CLI-first bridge for Linear API capabilities that are not reliably exposed through the current connector surface.

LinearPlus uses **LinearDB** for connectivity and local Linear data sync. See
[LINEARDB.md](LINEARDB.md) for the product boundary: OAuth app access, workspace
identity checks, SQLite schema, retries, and time-series/related-data storage.

The first workflow is initiative management:

- Create or reuse a Linear initiative by name.
- Attach an existing Linear project to an initiative.
- Summarize issue analytics across the Greenmark Linear team.
- Emit redacted JSON evidence suitable for Eidos/Codex loops.

## Credentials

Preferred Greenmark/recurring setup is OAuth client credentials for the
LinearDB layer:

```bash
export LINEARDB_GREENMARK_OAUTH_CLIENT_ID="..."
export LINEARDB_GREENMARK_OAUTH_CLIENT_SECRET="..."
export LINEARDB_GREENMARK_OAUTH_SCOPE="read"
```

Personal API key fallback:

```bash
export LINEARDB_GREENMARK_LINEAR_API_KEY="..."
```

or:

```bash
export LINEARPLUS_LINEAR_API_KEY="..."
```

LinearPlus/LinearDB never prompts for tokens, prints tokens, or writes tokens to
repo files.

Verify workspace/team access before a Greenmark run:

```bash
python -m linearplus.cli auth-check --team-key GMW
```

Prefer explicit account selection:

```bash
python -m linearplus.cli --account greenmark auth-check --team-key GMW
```

An explicit account only uses `LINEARDB_GREENMARK_*` credentials. It will not
fall back to ambient `LINEARPLUS_*` or `LINEAR_*` credentials.

## Pairing For A Linear API Key

LinearPlus uses a human pairing step for credentials. It does not manage tokens.

1. Run the intended command with `--dry-run` first when available.
2. Create or select a Linear personal API key in
   `Settings > Account > Security & Access`.
3. If member keys are unavailable, ask a Linear admin to check
   `Settings > Administration > API > Member API keys`.
4. Put the key in a local shell or vault-backed environment variable:

   ```bash
   export LINEARPLUS_LINEAR_API_KEY="..."
   ```

5. Verify only presence, not value:

   ```bash
   test -n "$LINEARPLUS_LINEAR_API_KEY" || test -n "$LINEAR_API_KEY"
   ```

6. Run the narrow approved live command and capture redacted evidence.

Linear references:

- `https://linear.app/docs/api-and-webhooks`
- `https://linear.app/developers/graphql`

## Greenmark Bootstrap

Dry run:

```bash
python -m linearplus.cli greenmark-bootstrap --dry-run
```

Live run:

```bash
python -m linearplus.cli greenmark-bootstrap
```

The live run creates or reuses the `Greenmark AI Search Visibility` initiative and attaches project `079b8875-9c80-41c8-b4b0-ea09834a7065`.

## Greenmark Analytics

Dry run:

```bash
python -m linearplus.cli greenmark-analytics --dry-run
```

Live read-only run:

```bash
python -m linearplus.cli greenmark-analytics
```

The live run reads issues for Linear team key `GMW` and emits JSON counts by
state type, state, priority, assignee, project, and label, plus sample issue
summaries and oldest open issues. Use `--team-key`, `--page-size`, or
`--sample-size` to tune the report.

## Greenmark Data Dump

Dry run:

```bash
python -m linearplus.cli greenmark-dump --dry-run
```

Live read-only dump:

```bash
python -m linearplus.cli greenmark-dump
```

The live run pulls raw task data for Linear team key `GMW`, computes the same
analytics, and writes a JSON artifact under `outputs/greenmark/` in the
LinearPlus plugin root. Use `--output /path/to/file.json` for an exact path or
`--output-dir /path/to/dir` for a timestamped artifact directory.

## Account-Wide SQLite Dump

Dry run:

```bash
python -m linearplus.cli account-dump --dry-run
```

Live read-only SQLite dump:

```bash
python -m linearplus.cli account-dump
```

Greenmark account profile form:

```bash
python -m linearplus.cli --account greenmark account-dump --skip-related
```

The live run reads all accessible Linear teams, pulls issues for each team, and
writes a local SQLite database under `outputs/linear/`. The database stores raw
JSON plus queryable current-state tables and timeline tables:

- Current state: `teams`, `issues`, `projects`, `users`, `labels`,
  `issue_labels`, and `metadata`.
- Per-run time series: `sync_runs` and `issue_snapshots`.
- Related issue data: `comments`, `attachments`, `issue_history`, and
  `issue_state_spans`.

Use an explicit path when you want a stable local database:

```bash
python -m linearplus.cli account-dump --sqlite /path/to/linear.sqlite
```

Use `--skip-related` for a faster teams/issues-only refresh when comments,
attachments, issue history, and state spans are not needed.

See [LINEAR_DATA_EXPORT.md](LINEAR_DATA_EXPORT.md) for the credential boundary,
SQLite schema, time-series tables, related-data tables, and useful local SQL
queries.

## Generic Commands

```bash
python -m linearplus.cli initiative-get --name "Greenmark AI Search Visibility"
python -m linearplus.cli initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
python -m linearplus.cli attach-project --initiative-id <initiative-id> --project-id <project-id>
```
