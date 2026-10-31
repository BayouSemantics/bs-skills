# Setup

Install Graphviz to render DOT diagrams:

| Command | Purpose |
| --- | --- |
| `brew install graphviz` | Install Graphviz on macOS with Homebrew. |

The checkpoint script also requires Python 3.9+ and Git.

## Directory Setup

Set up the `docs/graphviz-contracts` dir and the `DIAGRAMS.md`, `dot/`, `png/`, `metadata/` children.

Before writing `DIAGRAMS.md`, read [Standard File Format](formats.md).

## Plan which diagrams to build

Survey the codebase and any existing diagrams, then propose a diagram plan to the user.
Explain the coverage, level of detail, and how the architecture is split across diagrams.
Ask whether they want more or less detail, different splits, or additional topics covered.
Incorporate their feedback and agree on the plan before initializing diagrams.

## Initialize diagrams

Create each diagram's DOT source and render and visually review its PNG, following
[Writing and Editing](writing-and-editing.md). For each diagram, create metadata with its covered `paths`,
then follow the staging and checkpoint workflow in [Diagram Syncing](diagram-syncing.md). Stage
the diagrams, metadata, and router, and run `check` until all health checks pass: naming, router
entries, matching files, coverage paths, and checkpoints. For an existing contract directory,
review and complete the existing artifacts.

## Optional pre-commit hook

Ask whether the user wants a pre-commit hook that blocks commits when staged diagram health checks fail,
unless they already stated a preference. If declined, leave hooks unchanged and run `check` manually.

If accepted, install [pre-commit](https://pre-commit.com/#installation), merge the hook below into
`.pre-commit-config.yaml`, and set `entry` to the installed interpreter and skill path available
on each machine. Run `pre-commit install`.

```yaml
repos:
  - repo: local
    hooks:
      - id: graphviz-contract
        name: Check diagram health
        entry: <python> .agents/skills/graphviz-contract/scripts/graphviz_contract.py check
        language: system
        always_run: true
        pass_filenames: false
```

Verify with `pre-commit run graphviz-contract --all-files`; all health checks run on every commit.
