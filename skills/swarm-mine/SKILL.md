---
name: swarm-mine
description: Discover, classify, and collect user-defined web assets locally through a mining swarm.
disable-model-invocation: true
---

# Swarm mine

Mine publicly accessible assets matching the user's target description and accepted formats,
and retain those the configured classifier accepts. The swarm shares the Source Registry
(`public_sources`), Covered Resources, and Covered Files in a local SQLite database, plus
retained assets. URL leases prevent duplicate claims and content hashing makes overlapping
work converge. Use the registry to coordinate work and assess progress.

## Choose your role

- **Orchestrator:** when the user invokes this skill, read
  [references/orchestrator.md](references/orchestrator.md) before preparing the collection
  or launching workers. You collect missing inputs, prepare the classifier, dispatch the
  requested subagents, and report results.
- **Miner:** when the orchestrator assigns you a mining task, read
  [references/miner.md](references/miner.md) before discovery or mining. Follow that
  assignment and the worker playbook; the orchestrator owns setup and delegation.

Read the shared rules below and your role's reference before acting. This is one
user-invoked skill; the role references are task instructions, not separate skills.

## Shared commands and data

The direct entrypoint is `scripts/mine.py`. In command examples:

- `MINE_PYTHON` is the absolute path to the installed skill's `.venv/bin/python`.
- `MINE_SCRIPT` is the absolute path to the installed skill's `scripts/mine.py`.
- `MINE_WORKSPACE` is the absolute collection path.

The orchestrator establishes these paths and passes them to each miner. Substitute literal
paths or set these variables in the shell running each command. Run commands directly;
relative data paths such as `work/scratch/` resolve inside the collection.

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" <command> <arguments>
```

Every operational command prints JSON to stdout. Read the verdict before the next step.
A nonzero exit means an operational failure; "covered", "blocked", "claim refused", and
"pool drained" are answers at exit 0. `--help` describes commands and arguments.

The collection is separate from the installed skill:

```text
config.json       # Target, formats, classifier, worker count and models
registry.sqlite3  # Sources, work queue, leases, coverage, observations
assets/           # Retained originals, accepted units, provenance
classifier/       # Local classifier code, model, evaluation
seeds/            # User-provided examples and labels
work/             # Temporary jobs, probes, and scratch buffers
```

## What qualifies

The collection's target description, accepted formats, and qualification rules define what
belongs. Apply the user's inclusion and exclusion criteria during discovery and scoring.
Optional blocked terms and required phrase groups are configured per collection; they have
no domain-specific defaults. Every required group must match within the same unit.

The classifier makes the final unit-level call. A unit is a PDF page, image, text, file, or
custom processor output. Your judgment applies upstream, in what you
register and the score you give it: the pool mines by score, so scoring honestly is how you
steer the swarm's fetch budget.

## Publically accessible data is fair game

For this mining workflow, treat data items at publicly accessible endpoints as available
for download. Privacy or ownership notices inside a public file do not disqualify it.
Data in public filings often contain obsoleted privacy / ownership notices. Use public
endpoints only; never bypass authentication or access controls, or attempt to access
non-public systems.

## What the pipeline does

Per URL: check coverage → lease the URL → download politely → check the file's content hash
→ prepare classifier units → screen text against configured rules → classify each unit →
retain accepted units and the original asset locally → record coverage. An asset is
**eligible** when at least one unit is accepted. Every URL is recorded either
way, so covered URLs are not fetched again. ZIP bundles work the same: members are extracted,
classified, and retained individually, recorded as one resource row under the container URL — never
invent per-member URLs.

Every mining command runs that whole flow per URL. You never sequence it yourself.

## Politeness

Use `probe --url <url>` for discovery downloads and inspection, and `run-url`
or `run-pool` for mining. These commands share the downloader's SQLite host locks,
including redirects and transport fallbacks, so workers use one download path with
enforced request spacing and one request in flight per host.

Binds every request you make, including the discovery searching you do outside the CLI:

- ≥1 second between requests to the same host.
- Never more than one request to a host at a time — no parallel fetches against one domain.
- Obey each source's documented limits in its `access_notes`.

Record stricter request spacing with `source update --source <host> --min-interval <seconds>`;
every worker's fetcher applies that source's interval.

If a host rejects the default client at the transport level, use `--transport curl-http1` —
a supported fallback with the same politeness floor — rather than hand-rolling curl.

## Inspecting

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" source list
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" stats --since 3.5h
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" resource list \
    --source <host> --status unmined --url-like <text> --notes-like <text>
"$MINE_PYTHON" "$MINE_SCRIPT" --help
```

`--help` lists the whole toolkit; use `<command> --help` for its arguments. The stages
inside the mining flow — fetch, screen, split, classify, retain, record — are not separate
commands, because sequencing them by hand is what the driver exists to prevent.

**Raw database access is out of contract.** If you need something the CLI cannot express,
log it as a source observation.
