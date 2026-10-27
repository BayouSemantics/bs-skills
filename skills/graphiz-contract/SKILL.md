---
name: graphviz-contract
description: >-
  Provides a visual documentation contract for this project. Use when setting up the contract,
  reading code for the first time, drafting a plan, or implementing changes to architecture.
---

# Graphviz Contract

A set of Graphviz diagrams is a critical contract between AI engineers and a human PM. These
diagrams are used to document the current architecture of the codebase, to explore & propose
changes to it, and to keep human PMs up-to-speed in a rapidly changing codebase.

This skill links each diagram to source code paths and stores a single hash checkpoint of their
staged contents. A change in a covered source code file requires reviewing the linked diagrams.
Code changes which do not touch on a facet shown in a diagram require only a checkpoint update
after review.

## Layout

Write diagram sources in DOT and render them with Graphviz's `dot` command.

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

Router file only contains a markdown table with two columns: Name and Description (max 200 chars).
It is used to discover relevant diagrams. All maintained diagrams should receive an entry.
Entries should be organized in ascending order of granularity, with highest-level diagrams at the top,
and low-level systems toward the bottom. Keep related diagrams together to aid discoverability.

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
(see Determining Resolution Level and Diagram Search & Management).

## Naming

Use lowercase `<scope>-<subject>` names, e.g. `system-overview` or `api-request-flow`.
Use the same basename for DOT, PNG, metadata, and the router's Name column.
Keep names stable; omit dates, versions, and ordering prefixes. For planning docs,
use `-proposed`.

## Determining Resolution Level

A diagram is a human-readable document which efficiently communicates how a component or system works at
a certain level of detail ("resolution level"). Some diagrams are "birds' eye views" and leave a
lot of minor details out of the picture. Others are "zoomed-in" on a specific component, and are
intentionally detail-oriented. For any given diagram, determine which is the case. Silence on a
minor detail is NOT evidence of a wrong or out-of-sync diagram. Use this diagnostic: if the detail
is necessary for answering the main question the diagram is intended to answer, it should be included.
If not, it is preferred to omit it. Likewise: if an existing diagram detail contradicts the source code
state, it should be updated or removed (as appropriate).

## How to Use

Do not rely solely on diagrams to understand the codebase. They are visual aids for the human PM.
You are the engineer and must be involved with the details.

Open relevant graph PNGs when answering human queries and use it as a teaching aid.
On Mac, use `open -a Preview <graph>.png`; pass multiple PNG paths to open related graphs together.
Explain the parts that answer the query.

During planning, create DOT/PNG drafts in `<repo-root>/tmp/graphviz-contracts/`, labeled
"Proposed", and open them for discussion. Drafts need no router entries, metadata, or checkpoints.
Preserve the current diagram's layout and resolution where practical. Subdue unchanged context;
mark changes **[ADD]**, **[REMOVE]** (also dashed), or **[CHANGE]** with a brief explanation and
legend. For extensive changes, show **Current** and **Proposed** side by side. Explain the
behavioral change, rationale, and decision needed.

Save approved planning graphs (both DOT and PNG) alongside the project's planning documentation
and reference them from the plan; use durable paths outside `tmp`. Keep them labeled "Proposed"
until implemented. After implementation, update maintained diagrams to match the code and follow
the checkpoint workflow.

## What to Diagram

Not all source code needs a diagram. The diagrams map the codebase from top-down, hierarchically.
High-level and medium-level views are required across all critical components of the codebase.
Low-level modules that are critical for understanding key facets include: processing / error
handling rules, AI / ML models choices and architecture, Agentic graphs and AI context management
details (e.g. tools & tool design, prompts, middleware, compaction, etc.). Languages and libraries
used are key for understanding any system.

## How to Diagram

First choose the main question the diagram is intended to answer. Every box and connection should
then contribute to the answer.

Some examples of the types of questions you might consider (not exhaustive):

| Category | Question | Examples |
| --- | --- | --- |
| Parts and relationships | What connects to what? | Components, dependencies, ownership |
| Steps and interactions | What happens, in what order? | Requests, pipelines, agent loops |
| Data and context | Where does information go and change? | Transformations, storage, prompts, memory |
| Rules and decisions | Why does this path get chosen? | Routing, validation, model selection, retries |
| States and transitions | What changes state, and why? | Job lifecycle, approvals, recovery |
| Running environment | Where does it run? | Processes, containers, machines, external services |

Visually there are several options:

| Visual type | Shape | Useful for |
| --- | --- | --- |
| Chain / pipeline | Sequential boxes | Stages, transformations, request handling |
| Branching paths | Splitting and rejoining routes | Decisions, routing, error paths |
| Tree | Root branching into smaller pieces | Decomposition, ownership, classification |
| Layers | Stacked bands | Abstraction levels, architecture |
| Nested boxes | Containers within containers | Boundaries, subsystems, containment |
| Hub and spokes | Center with surrounding components | Orchestration, tools, integrations |
| Network | Interconnected components | Dependencies, collaboration |
| Loop / cycle | Path returning to an earlier point | Feedback, retries, iteration |
| Lanes | Steps grouped by participant | Handoffs across people or systems |

Position is important: left to right implies progression; nesting means containment; lanes identify responsibility.

Connections carry meaning: placement helps readability; arrows explain relationships.

## Quality Control

Always confirm changes visually with the rendered PNG file. Keep diagrams clean and
well-organized. Related items should be near each other. Diagram text should be clearly
legible in the rendered version and not overlapping or clashing with other elements.
Avoid unnecessarily complex and visually overwhelming edge connections.

## Diagram Search & Management

Run the following commands from the target repository. Replace `<python>` with its Python 3.9+
interpreter and the example skill path with the actual installed path. The script commands read
metadata and covered files from Git's staged snapshot; unstaged edits are excluded.

| Command | Description |
| --- | --- |
| `git add -- <paths...>` | Stage selected source, diagram, or metadata files; stage updated checkpoints again before `check`. |
| `<python> .agents/skills/graphiz-contract/scripts/graphviz_contract.py find --staged` | Find diagrams covering staged changes. |
| `<python> .agents/skills/graphiz-contract/scripts/graphviz_contract.py find src/api/routes.ts` | Find diagrams covering a path. |
| `<python> .agents/skills/graphiz-contract/scripts/graphviz_contract.py check` | Run health checks: naming, router entries, matching files, coverage paths, and checkpoints. |
| `<python> .agents/skills/graphiz-contract/scripts/graphviz_contract.py checkpoint request-flow` | Update the checkpoint after review. |

Stage the intended source changes and metadata before finding affected diagrams. Review each
affected diagram at its resolution level, update its DOT and PNG if needed, then run `checkpoint`
for that diagram. Stage the resulting metadata, diagrams, and router changes before running `check`.
Naming checks enforce lowercase scope-subject syntax and reject numeric date/order tokens and
`vN` version tokens. Names must match across diagram files and router entries. Descriptive naming,
diagram accuracy, PNG freshness, and router descriptions require agent review.

Sync checks may optionally run as a pre-commit hook (see Setup).

## Setup

When setup is requested or `<repo-root>/docs/graphviz-contracts/` does not exist, follow the
[setup process](references/setup.md).
