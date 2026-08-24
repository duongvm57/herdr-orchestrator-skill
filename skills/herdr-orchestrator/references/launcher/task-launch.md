# Task launch

Read `references/launcher/preflight.md` completely and pass its preflight gate
before starting this branch. This branch creates one run and one fresh Project
Lead; it does not coordinate Peers or wait for project work.

## 1. Initialize durable run evidence

Invoke packaged `scripts/herdr_orchestrator.py init-run` according to its current
`--help`. Forward the preflight result without recomputation: its
`project_root` through `--repository-root`, config `path` and `sha256` through
`--project-config-file` and `--expected-project-config-sha256`, and protocol
`path` and `sha256` through `--workspace-protocol-file` and
`--expected-workspace-protocol-sha256`. Also pass the absolute Git common
directory, collision-free run ID, verbatim Human-task source, captured
before-state, layout helper, and these opaque `--asset name=path` inputs:

```text
topology=references/lead/topology.md
peer-lifecycle=references/lead/peer-lifecycle.md
candidate-and-verdict=references/lead/candidate-and-verdict.md
anti-pattern-details=references/anti-patterns/responses.md
peer-profile=references/roles/peer.md
```

Resolve every right-hand source relative to the installed skill root and pass
its absolute path; project cwd never resolves packaged assets.

Consume only its compact JSON metadata. It must create this layout outside the
tracked checkout:

```text
<git-common-dir>/herdr-orchestrator/runs/<run-id>/
├── human-task.md
├── context/
│   ├── project-config.toml
│   ├── workspace-protocol.md
│   └── cards/
├── assignments/
├── reports/inbox/
├── supervisor/
├── tools/
│   ├── herdr_orchestrator.py
│   ├── herdr_balanced_split.py
│   └── herdr_harnesses/
└── events.jsonl
```

Require exact copies and SHA-256 digests for both helpers and every staged
harness-adapter module, immutable
launch-time snapshots of the validated config and full protocol, byte-for-byte
staged assets with a digest-only `context/cards/manifest.json`, a durable
before-state inventory, and the exact Human task. The run manifest binds the
canonical source paths and preflight-approved snapshot digests. All path, root,
digest, schema, and protocol-root checks finish before run mutation. Reserve
`tools/layout-state.json`; leave it absent until the layout helper atomically
initializes it on first use.

The Launcher remains the `events.jsonl` owner through the later initial
`launch` event. Step 3 creates `launcher-handoff.md` only after the Lead has an
exact identity; that marker transfers all later ledger writes. The ledger
records grounded milestones, not current status or inferred acceptance.

Initialization is complete when every reported path is absolute, regular where
required, outside the checkout, durable, collision-free, and digest-verified;
the canonical project paths, protocol Repository root, retained preflight
digests, saved source binding, and config/protocol snapshots all agree; the
report inbox is empty; and no run file is staged for Git.

## 2. Assemble the initial Lead pack opaquely

Invoke the run-local helper's `pack --role lead`. Pass sources in this exact
layer order with its repeatable options, using absolute paths for every source
and output:

Before packing, atomically save the applicable repository-authority projection
as `assignments/lead-repository-authority.md` and the generated run binding as
`assignments/lead-run-binding.md`. Preserve exact directives and their scope;
include run ID, repository root, evidence root, before-state, helper/state paths
and digests, scope, authority, and Human-only boundaries in the binding.

1. `--role-source`: `references/roles/lead.md`, then
   `references/anti-patterns/index.md`, then
   `context/cards/manifest.json`;
2. `--protocol-source`: run-local `context/project-config.toml`, then run-local
   `context/workspace-protocol.md`;
3. `--assignment-source`: init-run's returned `human_task.path`, then the saved
   repository authority, then the saved run binding. The returned path is
   `<run>/human-task.md`; pass it unchanged instead of deriving a `context/`
   path.

The manifest is a Role Profile source, while the Lead profile supplies the
fixed trigger for each logical name. `peer-profile` is opaque builder input: the
Lead passes its staged path back as a future Peer `--role-source` and never
reads it. The other four assets are cards read only on their named triggers.

The Launcher passes paths; it does not read, interpolate, or print any role or
asset body. Consume only compact JSON containing pack path, digest, byte count,
per-layer source counts/digests, and byte ceiling. Save exact bytes as
`context/lead.md`; this file and its SHA-256 are the canonical answer to what
the Lead was told. Validate card identities against the separately staged
manifest. Stop on a missing source, duplicate logical asset, digest failure,
order violation, or helper byte limit.

Packing is complete when each required source appears exactly once in its
layer, the snapshotted full config/protocol and verbatim task are inline, all
cards and the opaque Peer profile are staged and digest-bound, Supervisor text
is absent, and the Launcher transcript contains no opaque body or delivery
payload.

## 3. Start, deliver, and transfer

Invoke the run-local layout helper once with its shared state, repository cwd,
and the Launcher's explicit pane ID:

```text
python3 <run>/tools/herdr_balanced_split.py --state <run>/tools/layout-state.json --cwd <repository> --anchor <launcher-pane-id>
```

Use only `new_pane_id` from its JSON. A recovery-only result is not a pane; for
`retry_required`, reconcile the same cwd before one new split request. The
Launcher never calls `herdr pane split` directly.

Choose a unique Lead name absent from the captured agent inventory. Start it in
the new pane, with no prompt, using the exact configured `[roles.lead]` kind and
argument vector. Never resume or fork an existing session. Wait only for
startup readiness.

Append the single `launch` JSONL milestone with schema version 1, UTC RFC3339
timestamp, run ID, `type: launch`, Launcher actor, and the Lead name, pane,
exact recipe, context path, and context digest. Then atomically create
`launcher-handoff.md` with the same identities. Invoke the run-local helper's
`deliver` operation once with the Lead name, saved context path, configured live
language, receipt path, and localized one-line opening/closing files. Both lines
use and contain the exact live-language value. The helper passes that envelope
plus the exact saved bytes through a safe argument vector without `--wait`; it
records delivery result, context digest, and full payload digest while keeping
payload bytes out of stdout and logs.

After accepted delivery, focus the fresh Lead. A start or delivery failure
preserves the evidence and pane and reports the exact error; unchanged
prerequisites are not retried and no substitute recipe is used.

Task launch and handoff are complete only when preflight and initialization
passed without runtime substitution; the saved pack and manifest verify; a
fresh Lead has the exact configured recipe; the launch event and handoff marker predate the
single accepted delivery; focus targets that Lead; and the Human receives the
Lead name, repository, run ID/evidence path, and preserved before-state. The
Launcher then ceases to act as orchestration proxy.
