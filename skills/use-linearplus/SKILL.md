---
name: use-linearplus
description: Use when the user asks for LinearPlus, Linear initiatives through API, Linear GraphQL initiative creation, attaching Linear projects to initiatives, or when the Linear connector cannot create/list initiatives.
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
linearplus initiative-get --name "Greenmark AI Search Visibility"
linearplus initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
linearplus attach-project --initiative-id <initiative-id> --project-id <project-id>
linearplus greenmark-bootstrap --dry-run
linearplus greenmark-bootstrap
```

If the `linearplus` command is not on `PATH`, resolve the plugin root from this
skill file and run:

```bash
bin/linearplus --help
```

## Credential Boundary

- LinearPlus reads `LINEAR_API_KEY` or `LINEARPLUS_LINEAR_API_KEY`.
- It must not print, store, or ask the model to reveal Linear API tokens.
- If credentials are missing, report the missing-token blocker and preserve the
  dry-run evidence.

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
