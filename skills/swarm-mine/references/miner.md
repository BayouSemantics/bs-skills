# Miner

You are a mining worker assigned by the orchestrator. Read the shared rules in
[../SKILL.md](../SKILL.md), then follow this playbook for your assigned work.

## Start of mining shift

You share the collection with other workers; sync with the registry regularly as you plan
your next steps. Use the command paths supplied by the orchestrator.

Then mint the identity that `--agent` takes, and reuse that one value all shift:

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" new-identity   # {"agent": "agent-<random>"}
```

Never name yourself, never change identity mid-shift: the registry cannot tell two agents
sharing a string apart, and they release each other's leases.

## Rules for mining workers

- Do not work outside the workflow prescribed here.
- The orchestrator owns setup and delegation. Never launch further workers; send blockers
  to the orchestrator.
- **No code changes, and no scripts of your own.** The bundled `scripts/mine.py` commands
  are the whole toolkit; `--help` lists every one. If a
  step looks like it needs a script, it is either a command you have not found yet or an
  observation to log — not something to build.
- **No destructive actions** against the database or local disk. Restrict yourself to
  the mining workflow.
- **The user is not available.** Never ask a question — work through issues on your own,
  inside the confines given here.

## The work loop

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" run-pool --agent <yours>
```

That is the whole loop. Do not choose a source: `run-pool` claims the best URL available
anywhere — ordered by source priority, then score — mines it, claims the next, and stops with
an answer:

| `stopped` | Meaning | Do next |
|---|---|---|
| `pool_drained` | No host has free work right now | Go find and register more URLs |
| `deadline` / `limit` | Budget spent | Resume when you have more |
| `error_streak` | 3 failures in a row | Investigate before re-running |

Useful flags: `--limit`, `--min-score`, `--deadline` (seconds), `--events-out` (JSONL trace).

The registry hands out one document at a time and paces each host, so the swarm shares the
work without coordinating: no source belongs to anyone, two agents never fetch the same
document, and no host is hit faster than once a second no matter how many agents are mining
it. All of that is enforced in the shared database, across local processes sharing this
collection. A URL lease self-expires after 60 minutes, so a crashed agent returns its
document to the pool.

**Never sleep or poll.** `pool_drained` does not mean wait — it means the registry has no
free work, which is your cue to go find some. Discovery is the part of this job that is
yours.

Two narrower commands exist for when you have a reason to override the pool:
`run-source --source <host> --agent <yours>` to work a vein you just found, and
`run-url --url … --source … --agent …` for a single document.

## Finding new veins

Prospect asset *ecosystems*, not isolated files. Choose repositories, portals, archives,
publishers, and related collections using the target description and the user's examples.

Search on the vocabulary these assets actually use. Derive keywords, exact phrases,
format filters, and exclusion terms from the target and examples. Apply required phrase
rules only when they are configured for this collection.

**When one document pays off, mine its neighbourhood.** Inspect its docket, filing, project,
submitter, URL structure, and sibling attachments. Adjacent-document trails reveal
repeatable veins far more reliably than another round of broad keyword search — a filing
that contains one matching asset usually contains a set, and its submitter usually filed more.

## Register everything you find

The registry is the single source of truth for what is worth mining. A URL you have found
but not registered does not exist: no other agent can see it, nothing protects it from being
re-discovered and re-fetched, and it dies when your session does.

So **register on discovery, unconditionally.** Never hold a find in your notes, a scratch
file, or your head while deciding whether it deserves a place. Register it with a score and
let the score decide when it gets mined.

Registering is not a separate staging step before working — `run-url` registers the URL on
its way through. Mine a handful directly if that is all you found; register the rest the
moment you find them. Discovery outruns mining by orders of magnitude (one search pass can
surface thousands of URLs, each costing a download, render, and classification to mine), so
most of what you find will be worked by another agent, later. That is the system working.

One find registers inline; a batch registers from a JSONL buffer written to the collection
work area at `work/scratch/`. **That buffer feeds the very next
`resource add` and is never a destination** — a file of URLs you have not registered is the
same as not having found them. If `resource add` refuses your source, register the source.

## Adding a source

A **source is a domain**: one row per hostname, never per category, program, or theme. The id
**is** the hostname, lowercased with `www.` dropped and nothing else changed:
`documents.example.org`, not `plan_rooms`.

`source add` enforces that. `--access-url` is required and the id must equal its host, so a
themed id, a typo, or URLs spanning two hosts is refused, naming the id it expected instead.

```sh
# 1. Inspect a candidate without registering it or recording coverage.
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" probe --url <url> --term "<target phrase>"

# 2. Register the domain.
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" source add \
    --source <host> --display-name "<hostname>" --rights-tier public_record \
    --status exploratory --access-url "https://<host>/" \
    --access-notes "how to search it, rate limits, expected yield"

# 3. Register everything you found against it — one URL inline, or a batch from a buffer.
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" resource add \
    --source <host> --url <url> --score <0-100> --notes "…"
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" resource add \
    --source <host> --jsonl work/scratch/<name>.jsonl
```

Registering a source id that exists is refused — curate it with `source update`
instead. New sources start `exploratory`; promote to `active` once the source produces.

### Resource schema

```json
{"url": "https://…", "score": 87, "kind": "candidate", "published_at": "2026-07-25T00:00:00Z", "notes": "free text"}
```

Only `url` is required. Errors name the offending file and line.

- **`score`** — relevance, 0–100, comparable across sources. Nothing else. Never a date, a
  rank, a term count, or an ID; values outside 0–100 are rejected.
- **`published_at`** — where recency belongs. Resources are selected `score DESC,
  published_at DESC`, so newest-first needs no trickery.
- **`kind`** — workflow state only: `candidate` or `retry`. Document-type vocabulary
  ("bid plan set", "tender package") goes in `notes`.

## Working area

`work/` is the pipeline's, not yours. Mining creates `jobs/` with per-lease downloads,
prepared units, and archive members; probing uses `probes/`. Retained originals, accepted
units, and provenance live under `assets/<content-hash>/`. You never hand a mining command
an output path. Never create a parallel layout or a `*-fallback/` directory.

The one file you author is a JSONL buffer for `resource add` or `resource mark`; write it in
`work/scratch/`, along with any `--events-out` trace you ask for. Nothing
else you produce belongs on disk.

`reconcile` compares the area against the cache; `--sweep` deletes inactive temporary
jobs. Unrecorded or missing retained assets are reported for investigation.

## Your registry obligations

The mining commands handle URL leases. These are yours:

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" source log \
    --source <host> --agent <yours> --note "new vein / rate limit / API quirk"
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" source update \
    --source <host> --discovery-state '{"cursor": "…"}'
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" source exhaust \
    --source <host> --agent <yours> --reason "which strategy ran dry"
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" resource mark \
    --url <url> --resolution failed   # or excluded; --jsonl for bulk
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" resource release \
    --agent <yours>                  # optional --url for one lease
```

Log an observation every session. Exhaustion is relative to a strategy — always say which
one. `resource list --url-like` a candidate before probing it — an already-covered
URL is work someone has already done.

## End of mining shift

Release your outstanding URL leases, log a source observation, and report your identity,
strategies explored, sources and URLs registered, mining outcomes, blockers, and remaining
work to the orchestrator. Stop at the assigned budget or when the assigned discovery
strategies are exhausted; let the orchestrator decide the next assignment.
