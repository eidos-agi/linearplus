# LinearPlus Playbook

Use LinearPlus when an Eidos/Codex workflow needs Linear initiative operations
that are missing or unreliable in the connected Linear tool surface.

## Use When

- A user explicitly asks for a Linear initiative and the connector can only
  create projects or issues.
- A Linear project needs to be attached to an initiative through the official
  Linear GraphQL API.
- Codex needs redacted evidence that a Linear initiative was created, reused, or
  blocked by missing credentials.

## Do Not Use When

- The normal Linear connector already exposes the needed operation reliably.
- The task is only issue creation or project description editing.
- The workflow would require printing, storing, rotating, or exposing a Linear
  API token.

## Commands

From the plugin root:

```bash
bin/linearplus --help
bin/linearplus initiative-get --name "Greenmark AI Search Visibility"
bin/linearplus initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
bin/linearplus attach-project --initiative-id <initiative-id> --project-id <project-id>
bin/linearplus greenmark-bootstrap --dry-run
bin/linearplus greenmark-bootstrap
```

## Credentials

Set one of:

```bash
export LINEAR_API_KEY="..."
export LINEARPLUS_LINEAR_API_KEY="..."
```

LinearPlus fails closed when neither variable is present. It does not prompt for
tokens and does not write tokens to repo files.

## Evidence

For Eidos loops, capture:

- command run
- redacted JSON output
- initiative id/url when live execution succeeds
- project id/url or initiative-project relation when attach succeeds
- missing-token or permission blocker when live execution cannot proceed

The Greenmark bootstrap target project is:

```text
079b8875-9c80-41c8-b4b0-ea09834a7065
```
