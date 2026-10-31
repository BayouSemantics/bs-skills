# Diagram Syncing

For managing diagram syncs, run the following commands from the target repository.
Replace `<python>` with its Python 3.9+ interpreter and the example skill path with
the actual installed path. The script commands read metadata and covered files from
Git's staged snapshot; unstaged edits are excluded.

| Command | Description |
| --- | --- |
| `git add -- <paths...>` | Stage selected source, diagram, or metadata files; stage updated checkpoints again before `check`. |
| `<python> .agents/skills/graphviz-contract/scripts/graphviz_contract.py find --staged` | Find diagrams covering staged changes. |
| `<python> .agents/skills/graphviz-contract/scripts/graphviz_contract.py find src/api/routes.ts` | Find diagrams covering a path. |
| `<python> .agents/skills/graphviz-contract/scripts/graphviz_contract.py check` | Run health checks: naming, router entries, matching files, coverage paths, and checkpoints. |
| `<python> .agents/skills/graphviz-contract/scripts/graphviz_contract.py checkpoint request-flow` | Update the checkpoint after review. |

Stage the intended source changes and metadata before finding affected diagrams. Review each
affected diagram at its resolution level, update its DOT and PNG if needed, then run `checkpoint`
for that diagram. Stage the resulting metadata, diagrams, and router changes before running `check`.
Naming checks enforce lowercase scope-subject syntax and reject numeric date/order tokens and
`vN` version tokens. Names must match across diagram files and router entries. Descriptive naming,
diagram accuracy, PNG freshness, and router descriptions require agent review.

## When to Change the Diagram?

Before syncing source code, compare the linked diagram with the changed code and determine
whether the change affects a diagrammed component, remembering that diagrams show a certain
level of resolution-detail. For example, if a code change entails a detail not reflected in the diagram,
no change is required and the sync can be executed as-is. Only modify diagrams when the change affects a
diagrammed facet or detail.

Before modifying diagrams, read [Writing and Editing](writing-and-editing.md).