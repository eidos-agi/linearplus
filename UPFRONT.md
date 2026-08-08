# Daniel upfront: ~5 minutes

Everything else is agent-autonomous on this laptop.

## Already true here

- `lineardb --account greenmark connect` done (`daniel@eidosagi.com`)
- OAuth app creds in macOS Keychain
- Token refresh works
- Teams visible: AIC, EID, GMW, …

## Profile aliases (no second connect)

| Profile | Token source | Default team |
|---------|--------------|--------------|
| `eidos` | aliases `greenmark` | `EID` |
| `aic` | aliases `greenmark` | `AIC` |
| `greenmark` | own | `GMW` |

## Your 5 minutes

**Option A — one message**

Reply: `go linear`

Agent runs `scripts/install-eidos-linear-grok.sh`. You only:

1. Open Grok when told
2. Click **Approve** on official Linear MCP OAuth (once)
3. Reply `linear wired`

**Option B — one command**

```bash
~/repos-eidos-agi/linearplus/scripts/install-eidos-linear-grok.sh
```

Same OAuth click in Grok afterward.

## What you never do

- Paste client id/secret
- Run `lineardb connect` again (unless token revoked)
- Pick OAuth apps per cockpit
- Configure Greenmark in generic MCP

## Optional overrides

```bash
LINEARDB_ACCOUNT=aic LINEARDB_TEAM_KEY=AIC ./scripts/install-eidos-linear-grok.sh
```