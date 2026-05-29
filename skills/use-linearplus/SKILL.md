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
- Do not build OAuth, browser automation, or token storage unless Daniel
  explicitly asks for that implementation. Prefer the pairing procedure below.

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
