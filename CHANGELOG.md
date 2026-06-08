# Changelog

All notable changes to LinearPlus are documented here.

## 0.1.0 - 2026-05-29

- Added LinearDB as the product/category name for OAuth-backed Linear connectivity, local SQLite sync, time-series snapshots, and related issue metadata.
- Added first single-account LinearDB profile support with `--account greenmark` and `LINEARDB_GREENMARK_*` credential env vars.
- Made explicit LinearDB accounts fail closed instead of falling back to ambient Linear credentials.
- Added OAuth client-credentials support for Linear app/service-account access with personal API key fallback.
- Added `auth-check` to verify the active credential identity and required team visibility before Greenmark dumps.
- Added CLI-first Linear GraphQL adapter for initiatives.
- Added initiative create, ensure, get, and project attach commands.
- Added Greenmark AI Search Visibility bootstrap command.
- Added Greenmark task analytics/local dump commands and account-wide SQLite export for read-only issue reporting, including sync runs, issue snapshots, comments, attachments, issue history, and state spans.
- Added `LINEAR_DATA_EXPORT.md` to document the local database schema, key boundary, Surfari pairing caution, GMW validation check, and useful SQL queries.
- Added retries for transient Linear HTTP `429`, `502`, `503`, and `504` responses during large exports.
- Made SQLite dump writes atomic so failed exports do not replace the previous successful local database.
- Added token-safe fail-closed credential handling.
- Added Eidos plugin runtime metadata, Codex/Claude plugin manifests, and verification hook.
