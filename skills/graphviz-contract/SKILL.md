---
name: graphviz-contract
description: >-
  Provides a visual documentation contract for this project. Use when understanding or explaining
  code layout / logic, drafting a plan, or implementing changes.
---

# Graphviz Contract

A set of Graphviz diagrams is a critical contract between AI engineers and a human PM. These
diagrams are used to document the current architecture of the codebase, to explore & propose
changes to it, and to keep human PMs up-to-speed in a rapidly changing codebase.

This skill syncs each diagram to source code paths and stores a single hash checkpoint of their
staged contents. A change in a covered source code file requires reviewing the linked diagrams.
Code changes which do not touch on a facet shown in a diagram require only a checkpoint update
after review.

## Layout

Diagram contracts are stored in this directory layout:

```
docs/
└── graphviz-contracts/
    ├── DIAGRAMS.md         # router file
    ├── dot/
    │   └── {diagram}.dot   # diagram source code
    ├── png/
    │   └── {diagram}.png   # rendered diagram
    └── metadata/
        └── {diagram}.json  # diagram metadata
```

## Writing and Editing

Before writing or editing Graphviz Contracts always read [Writing and Editing](references/writing-and-editing.md).

## How to Use

Graphviz contracts are a design contract between you the (AI engineer) and a human PM (user).
They are a visual surface for the human to inspect the underlying code organization and
logic that you maintain. The human PM can opt to inspect or approve your code changes using these contracts.
As the implementing engineer, you must treat the diagrams as authoritative, while recognizing that
they are typically not exhaustive, but big-picture details. Diagrams of low-level systems may be
more detailed.

As the engineer, never rely solely on diagrams to understand the codebase.

Open relevant graph PNGs when answering human queries and use it as a teaching aid.
On Mac, use `open -a Preview <graph>.png`; pass multiple PNG paths to open related graphs together.
Explain the parts that answer the human's query.

Graphs can be used during planning with human PMs to show proposed changes in existing architecture,
or to explore new architectures. For this, read [Planning Discussions](references/planning-discussions.md).

## Syncing Diagrams with Changes

To sync diagrams with code changes, read [Diagram Syncing](references/diagram-syncing.md).

Sync checks may optionally run as a pre-commit hook (see Setup).

## Setup

When setup is requested or `<repo-root>/docs/graphviz-contracts/` does not exist, follow
[Setup](references/setup.md).
