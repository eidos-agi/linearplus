#!/usr/bin/env bash
# Wire eidos-linear + official Linear MCP into Grok with zero new secrets.
# Prereq: greenmark (or any) lineardb connect already done on this machine.
set -euo pipefail

LINEARPLUS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT="${LINEARDB_ACCOUNT:-eidos}"
TEAM_KEY="${LINEARDB_TEAM_KEY:-EID}"
MIRROR="${LINEARDB_MIRROR_SQLITE:-$HOME/.lineardb/mirrors/${ACCOUNT}.sqlite}"

echo "==> Checking existing LinearDB token (via profile alias)..."
LINEARDB_ROOT="${LINEARDB_ROOT:-$(cd "$LINEARPLUS_ROOT/../lineardb" && pwd)}"
cd "$LINEARDB_ROOT"
uv run lineardb --account "$ACCOUNT" auth-check --team-key "$TEAM_KEY" >/tmp/eidos-linear-auth-check.json
cd "$LINEARPLUS_ROOT"
python3 -c "import json,sys; d=json.load(open('/tmp/eidos-linear-auth-check.json')); sys.exit(0 if d.get('ok') else 1)"

echo "==> Adding eidos-linear MCP (local checkout)..."
grok mcp add eidos-linear \
  -e "LINEARDB_ACCOUNT=${ACCOUNT}" \
  -e "LINEARDB_MIRROR_SQLITE=${MIRROR}" \
  -- uv run --directory "$LINEARPLUS_ROOT" eidos-linear-mcp

echo "==> Adding official Linear MCP..."
if grok mcp add --transport http linear https://mcp.linear.app/mcp 2>/dev/null; then
  echo "    official linear MCP added"
else
  echo "    linear MCP may already exist — continuing"
fi

echo "==> Running eidos_proof..."
export LINEARDB_ACCOUNT="$ACCOUNT"
export LINEARDB_MIRROR_SQLITE="$MIRROR"
uv run python -c "
from eidos_linear.tools.proof import eidos_proof
import json
print(json.dumps(eidos_proof(account='${ACCOUNT}', team_key='${TEAM_KEY}'), indent=2))
" >/tmp/eidos-linear-proof.json

python3 -c "import json; d=json.load(open('/tmp/eidos-linear-proof.json')); print('verdict:', d.get('verdict')); raise SystemExit(0 if d.get('verdict') in ('CLEAR','WARN') else 1)"

cat <<EOF

Done. Agent-side wiring complete.

YOUR ~5 MINUTES (only if not done before):
  1. Restart or open Grok Build
  2. When prompted, approve OAuth for the official "linear" MCP connector
  3. Reply "linear wired" in chat

eidos-linear uses your existing lineardb token — no second connect.
Profile: ${ACCOUNT}  team: ${TEAM_KEY}  mirror: ${MIRROR}
EOF