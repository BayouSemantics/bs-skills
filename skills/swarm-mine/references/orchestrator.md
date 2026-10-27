# Orchestrator

You are the orchestrator. Read the shared rules in [../SKILL.md](../SKILL.md), then complete
setup before launching mining workers.

1. Collect the target description, accepted asset formats, and either a supplied local
   classifier or user-labeled examples from which to build one. Ask for anything missing.
   Ask for the number of subagents and their model assignments when unspecified; never
   choose these on the user's behalf. The count excludes the orchestrator. Allow model
   groups, for example two workers on one user-chosen model and one on another.
2. Use the harness's native subagent mechanism. Verify it can honor the requested models
   and concurrency. Ask the user to resolve unsupported choices before launching; do not
   silently substitute models, reduce the count, or run another model through a subprocess.
3. Choose `<project-root>/swarm-mine/<collection-name>/`, or the user's explicit destination.
   Without a project root, use the invocation directory. Ask about location only when the
   project is ambiguous or an existing collection conflicts. Resolve the collection and
   installed skill paths to absolute paths; worker paths always refer to that collection.
4. Create the skill's virtual environment with `python -m venv <skill-path>/.venv`, then
   install it with `<skill-path>/.venv/bin/python -m pip install -e <skill-path>`.
   Resolve the three command paths defined in `SKILL.md` for this installation and collection.
   Read `config-schema` and `classifier-contract`, then write the collection's `config.json`:

   ```sh
   "$MINE_PYTHON" "$MINE_SCRIPT" config-schema
   "$MINE_PYTHON" "$MINE_SCRIPT" classifier-contract
   "$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" init --config <absolute-config-path>
   ```

   Without `--workspace`, `init --project-root <absolute-project-path>` chooses the standard
   collection location. Repeating identical setup resumes the collection.

5. Prepare and validate the classifier as described below. Set each format's processor
   explicitly: `pdf`, `text`, `html`, `image`, `file`, `zip`, or a local `command` that
   prepares other formats. ZIP members use the same configured formats; nested archives
   require a custom processor. Image/file processors pass the original asset to the
   supplied classifier. The text starter requires extracted text. HTML processing reads
   static content; use a custom processor when the target needs rendered content.
6. Run `"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" check`. Launch workers
   only after setup is valid and the classifier has been exercised on representative examples.
   Pass each miner the absolute paths to `SKILL.md` and `references/miner.md`, the three
   command paths, its model assignment, a distinct discovery strategy, and a bounded
   discovery/mining assignment. Instruct it to read the shared rules and miner reference.
   Each miner mints its own identity.
7. Coordinate discoveries through the registry. Divide search strategies, vocabulary,
   jurisdictions, or date ranges; sources remain shared. Collect worker summaries and
   query `stats` before reporting retained counts, asset paths, failures, and remaining work.
   When stopping workers, have them release their leases. If a worker crashes, its lease
   expires; a replacement gets a new identity. Request user input yourself when preparation
   needs it; workers send blockers to you.

### Classifier preparation

For a supplied classifier, use its local command and record every code/model file that
controls its verdict in `classifier.files`. Commands receive JSON on stdin and return JSON
on stdout; `classifier-contract` defines both classifier and custom-processor interfaces.
Record custom processor code in `classifier.files` as well. Use absolute interpreter paths
when a classifier needs its own environment; commands run with the collection as their
working directory. Verify one decision per unit, correct labels, and representative
accept/reject behavior before launching workers.

When building a classifier, first obtain positive and negative examples from the user.
Use traditional NLP/ML and small models only: for example TF-IDF with logistic regression,
or a compact classifier over user-appropriate features. The orchestrator may author
classifier and format-preparation code in `classifier/` during setup. Mining workers use
that prepared toolkit. Keep training and validation examples separate by original source;
report validation results and inspect mistakes. If examples or features are inadequate,
ask for more examples before mining.

For text, install the optional starter with
`<skill-path>/.venv/bin/python -m pip install -e '<skill-path>[text-classifier]'`. Prepare JSONL in
`seeds/` with `text`, `label` (`accept` or `reject`), `split` (`train` or `validation`), and
`group` (the original source/document identifier), then run:

```sh
"$MINE_PYTHON" "$MINE_SCRIPT" --workspace "$MINE_WORKSPACE" train-text --examples seeds/examples.jsonl
```

Choose `classifier.kind=tfidf` and an artifact path under `classifier/` in configuration.
The starter writes its model and held-out precision/recall report, checks configured quality
thresholds, and refuses duplicate examples or source groups shared between splits. Its
minimum example count is a mechanical floor, not evidence of representative performance.
Request more user examples when the held-out set is too small to support the target.

The target, formats, qualification rules, and classifier identity belong to one collection.
Use a new collection when changing them after mining; previous rejections must never hide
candidates for a different target. Worker count/model assignments can change between shifts.
