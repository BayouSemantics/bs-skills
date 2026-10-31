# Writing and Editing Graphviz Diagrams

Write & edit diagram sources in DOT and render them with Graphviz's `dot` command.

## Rule of Approval

Do not add a new diagram without obtaining the human PM's explicit approval first.

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
