# Contributing

LinearPlus is intentionally small. Keep changes focused on Linear API operations
that are missing or unreliable in higher-level connector surfaces.

## Development

```bash
python -m unittest discover -s tests -v
bin/linearplus --help
bin/linearplus greenmark-bootstrap --dry-run
python verify.py
```

## Rules

- Do not print or persist Linear API tokens.
- Prefer official Linear GraphQL mutations over browser automation.
- Keep the CLI dependency-free unless a dependency removes substantial risk.
- Add tests for request construction, redaction, and error paths.
