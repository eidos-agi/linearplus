# LinearPlus

LinearPlus is a small CLI-first bridge for Linear API capabilities that are not reliably exposed through the current connector surface.

The first workflow is initiative management:

- Create or reuse a Linear initiative by name.
- Attach an existing Linear project to an initiative.
- Emit redacted JSON evidence suitable for Eidos/Codex loops.

## Credentials

Set one of these environment variables:

```bash
export LINEAR_API_KEY="..."
```

or:

```bash
export LINEARPLUS_LINEAR_API_KEY="..."
```

LinearPlus never prompts for tokens, prints tokens, or writes tokens to repo files.

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

## Generic Commands

```bash
python -m linearplus.cli initiative-get --name "Greenmark AI Search Visibility"
python -m linearplus.cli initiative-ensure --name "Greenmark AI Search Visibility" --status Planned
python -m linearplus.cli attach-project --initiative-id <initiative-id> --project-id <project-id>
```

