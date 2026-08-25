# Task launch

Read `references/launcher/preflight.md` completely and pass it before this
branch. This branch creates one run and one fresh Project Lead, then transfers
control to that Lead.

## 1. Initialize durable run evidence

Invoke packaged `scripts/herdr_orchestrator.py init-run` with the retained exact
project root, selected Git common directory, and Activation Manifest digest:

```text
python3 <helper> init-run \
  --project-root <project_root> \
  --git-common-dir <git_common_dir> \
  --expected-activation-sha256 <activation.sha256> \
  --run-id <collision-free-run-id> \
  --human-task-file <verbatim-task-file> \
  --before-state-file <saved-before-state> \
  --layout-helper <packaged-layout-helper> \
  --asset topology=references/lead/topology.md \
  --asset peer-lifecycle=references/lead/peer-lifecycle.md \
  --asset candidate-and-verdict=references/lead/candidate-and-verdict.md \
  --asset anti-pattern-details=references/anti-patterns/responses.md \
  --asset peer-profile=references/roles/peer.md
```

Resolve asset sources relative to the installed skill root. The helper reloads
and verifies the accepted generation under the expected activation digest
before mutation, then atomically creates:

```text
<git-common-dir>/herdr-orchestrator/runs/<run-id>/
├── human-task.md
├── context/
│   ├── setup-activation.json
│   ├── project-config.toml
│   ├── workspace-protocol.md
│   └── cards/
├── assignments/
├── reports/inbox/
├── supervisor/
├── tools/
│   ├── herdr_orchestrator.py
│   ├── herdr_runtime.py
│   └── herdr_balanced_split.py
└── events.jsonl
```

Require exact staged bytes and manifest digests for the activation, config,
protocol, helpers, assets, before-state, and Human task. All run paths are
outside the tracked checkout.

## 2. Bind the exact Lead launch

Invoke the run-local helper's `bind-role --role lead` against
`context/project-config.toml` and
`run-manifest.json.artifacts.project_config.sha256`. Supply exactly the Lead
template's returned `required_bindings`:

```text
python3 <run>/tools/herdr_orchestrator.py bind-role \
  --project-config-file <run>/context/project-config.toml \
  --expected-project-config-sha256 <project_config.sha256> \
  --role lead \
  --cwd <repository_root> \
  --bind workspace=<repository_root> \
  --bind git_common=<git_common_dir> \
  --bind evidence=<run_directory> \
  --bind orchestration=<project_root>/.orchestration \
  --output <run>/context/lead-launch.json
```

Include `--bind orchestration=...` only when `required_bindings` contains
`orchestration`; include no unrequested binding. The helper compiles the logical
template into one native Codex permission profile, exact argument vector,
effective filesystem receipt, and bound launch digest. A missing, extra,
noncanonical, or unavailable path fails closed.

## 3. Assemble the Lead pack opaquely

Atomically save the applicable repository-authority projection as
`assignments/lead-repository-authority.md` and a run binding as
`assignments/lead-run-binding.md`. Include run ID, project/repository/Git-common
roots, evidence root, before-state, helper paths and digests, Candidate and
Publication Digests, Lead launch receipt/digest, scope, authority, and
Human-only decisions.

Invoke the run-local helper's `pack --role lead` in this exact layer order:

1. `--role-source`: packaged `references/roles/lead.md`, packaged
   `references/anti-patterns/index.md`, then run-local
   `context/cards/manifest.json`;
2. `--protocol-source`: run-local `context/project-config.toml`, then
   `context/workspace-protocol.md`;
3. `--assignment-source`: returned `human_task.path`, saved repository
   authority, then saved run binding.

Pass absolute paths without reading opaque role/card bodies. Save exact bytes as
`context/lead.md`; retain its digest and ordered source receipt. The Lead gets
the full accepted protocol and config snapshot, while disclosed card bodies and
the Peer profile remain staged and digest-bound.

## 4. Start, deliver, and transfer

Invoke the run-local layout helper once with its shared state, selected
repository cwd, and Launcher pane anchor. Accept only `new_pane_id`; reconcile a
same-cwd `retry_required` result before one new split request.

Choose a unique Lead name. Read only `context/lead-launch.json`, then call
`herdr agent start` with its exact `kind`, pane, and argument vector after `--`.
Start with no prompt, never resume an existing session, and wait only for
startup readiness.

Append one `launch` milestone binding the Lead identity, pane, saved context
digest, Candidate Digest, and bound launch digest. Atomically create
`launcher-handoff.md` with the same identities. Then invoke the run-local
helper's `deliver` once with the saved context, configured live language,
receipt path, and localized opening/closing files. It sends one shell-free
payload without `--wait` and keeps payload bytes out of stdout and logs.

After accepted delivery, focus the fresh Lead. A start or delivery failure
preserves the pane and evidence and reports the exact error. Completion requires
the accepted generation, run manifest, exact Lead binding, pack, launch event,
handoff marker, and delivery receipt to agree. Return the Lead name, selected
repository, run ID/evidence path, and preserved before-state, then cease acting
as orchestration proxy.
