# Security

LinearPlus touches Linear API credentials and must fail in the safe direction.

## Reporting

Report security issues to `daniel@eidosagi.com`.

## Threat Model

- Linear API keys grant workspace access according to the issuing user's
  permissions.
- Tokens must be provided through `LINEAR_API_KEY`,
  `LINEARPLUS_LINEAR_API_KEY`, or an approved vault-backed shell context.
- Tokens must never be printed, committed, added to evidence bundles, or written
  to plugin cache files.
- Live mutation commands should emit only redacted JSON evidence.
