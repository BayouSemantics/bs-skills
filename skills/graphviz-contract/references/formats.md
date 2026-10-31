# Standard File Formats

## `DIAGRAMS.md`

`DIAGRAMS.md` contains only a markdown table with two columns: Name and Description (max 200 chars).
It is used to discover relevant diagrams. All maintained diagrams should receive an entry.
Entries should be organized in ascending order of granularity, with highest-level diagrams at the top,
and low-level systems toward the bottom. Keep related diagrams together to aid discoverability.

## `metadata/{diagram}.json`

Each metadata filename identifies its diagram. Paths are repository-relative; a trailing `/`
covers a directory recursively. Each path must match at least one file in Git's staged snapshot
and must exclude diagram metadata. The script maintains `checkpoint`:

```json
{
  "paths": ["src/api/", "src/config.ts"],
  "checkpoint": "sha256:..."
}
```

Metadata is required for every maintained diagram to track its review against source code
(see [Determining Resolution Level](writing-and-editing.md#determining-resolution-level) and
[Diagram Syncing](diagram-syncing.md)).
