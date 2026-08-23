# Launcher procedure

The invoking session launches one fresh Project Lead or attaches one fresh
Supervisor to exact active bindings. It never coordinates Peers.

## 1. Preflight canaries without durable mutation

Require `HERDR_ENV=1` and Python 3, then run `herdr agent list` and
`herdr pane current --current`. If either cannot reach the current Herdr server,
stop on that exact error before parsing project files or probing harnesses. A
managed pane whose native sandbox blocks the Herdr socket is not launch-ready.

Resolve the repository root and absolute Git common directory. Use an
exclusive, collision-free probe file directly under the common directory to
prove actual write access, then remove only that probe in the same bounded
operation. Stop on the exact create/write/fsync/remove failure and require no
leftover. Permission bits alone are insufficient because a native sandbox may
make Git metadata read-only. This is the only preflight mutation and it leaves
no durable state.

Read current `herdr --skill` and relevant `--help` output as command authority.
Resolve the packaged
`scripts/herdr_balanced_split.py` relative to this skill and require its
`--help` check to pass. Require and strictly parse:

- `.orchestration/herdr-orchestrator.toml` at `version = 2`;
- `.orchestration/workspace-protocol.md` with all twelve protocol sections;
- exactly one `[roles.lead]` recipe, optional `[roles.supervisor]`; and
- one or more uniquely named `[peer_recipes.<name>]` entries, each with a
  nonempty `description`, `kind`, and `args`.

Reject every other top-level key, recipe indirection, placeholder, credential,
legacy profile/route/`[peer.*]` schema, or empty Peer recipe catalog.

Require the protocol's `Live orchestration language` and `Durable Markdown
artifact language` fields to contain explicit non-placeholder values. Reject a
missing or blank field; there is no package fallback. Read both before reporting
further status or building packs. Keep generated durable prose in the artifact
language and live Human handoff/status in the live language; preserve embedded
authoritative source text, verbatim tasks, and technical literals exactly.

Read live `herdr --help`, `herdr agent start --help`, and each configured
harness's help/catalog. Require a reachable Herdr server, installed executable,
supported kind, accepted native arguments, available configured model, denied
native spawning, and role-compatible read/write boundary for every configured
entry. The Lead must be able to write run evidence; every Peer recipe must have
a validated lossless report-return boundary; a project-read-only Peer must be
checkout/Git-metadata read-only and exclusive-mailbox writable; and a Supervisor
must be project-read-only and notebook-write-only. Report the exact failing
element and stop; never fall back.

Capture before-state evidence:

```text
git status --short --branch
git worktree list --porcelain
herdr agent list
herdr pane list
```

Also inspect relevant repository authority (`AGENTS.md`, domain docs, issue or
spec pointers) needed to package the Human task. Existing agents, panes,
worktrees, branches, untracked files, and working-tree changes are Human-owned.
Do not reuse, rename, close, move, clean, stash, commit, or overwrite them.

Preflight passes only when the repository, config, protocol, live recipes,
Human task or Supervisor bindings, and preserved before-state are unambiguous.

Choose exactly one branch from the explicit invocation. A project task continues
through sections 2–4. A Supervisor attachment skips sections 2–4 and runs only
section 5 against existing runs; it creates neither a run nor a Lead.

## 2. Task launch: create run evidence

Resolve the absolute Git common directory with `git rev-parse
--path-format=absolute --git-common-dir`. Choose a collision-free run ID such as
UTC timestamp plus a short random suffix, then create:

```text
<git-common-dir>/herdr-orchestrator/runs/<run-id>/
├── context/
├── assignments/
├── reports/
│   └── inbox/
├── supervisor/
├── tools/
│   └── herdr_balanced_split.py
└── events.jsonl
```

This location is outside tracked checkout content even when worktrees are used.
Never add it to a commit. Save the before-state inventory and the exact Human
task in the run directory. Copy the exact packaged layout helper into `tools/`
and record its SHA-256. Reserve `tools/layout-state.json` as the runtime state
path but leave it absent: the helper owns its atomic initialization on the first
split. Never pre-create an empty file or `{}` state.

The Launcher owns the ledger through the initial `launch` event. It atomically
creates `launcher-handoff.md` before sending the Lead context; that marker
transfers later ledger writes to the Lead. The Lead checks it once rather than
polling for it.

Follow the semantic event ledger contract in
`references/assignments-and-evidence.md` for every append. The Launcher writes
only the initial `launch` milestone; the Lead writes later milestones after
handoff. The ledger never represents current status or inferred acceptance.

Evidence preparation is complete when the directory is outside the checkout,
the required directories including an empty report inbox, ledger, helper
copy/digest, before-state, and Human task are durable.

## 3. Task launch: build the Lead context pack

Read and concatenate the exact content required by the Lead-pack row in
`SKILL.md`, with clear titled boundaries in these three layers:

1. **Role Profile:** `references/roles/lead.md`, `references/topology.md`, all
   of `references/anti-patterns.md`, `references/assignments-and-evidence.md`,
   and `references/roles/peer.md` as the template for later Peer injection;
2. **Workspace Protocol:** parsed project config with native recipes, then the
   full project Workspace Protocol; and
3. **Assignment:** verbatim Human task and relevant repository authority, then
   run ID, absolute evidence directory, repository root, before-state, and the
   absolute layout helper/state paths plus helper digest.

Add a small assignment boundary: the Lead may orchestrate only this project and
Human task; external effects and Human-only decisions remain excluded unless
explicitly granted. Do not add a preferred implementation or hidden verdict.
Save the exact bytes as `context/lead.md` and record its SHA-256. This saved file
is the canonical answer to what the Lead was told.

The pack is complete when every required source appears once, the full protocol
and anti-pattern catalog are present, Peer instructions are available for later
direct injection, and no Supervisor role text was added.

## 4. Task launch: start and transfer

Use live Herdr help as command-shape authority. Invoke the run-local helper once
with its shared state, repository cwd, and the Launcher's explicit pane ID:

```text
python3 <run>/tools/herdr_balanced_split.py --state <run>/tools/layout-state.json --cwd <repository> --anchor <launcher-pane-id>
```

Read the new Lead pane ID from `new_pane_id` in its JSON output. Do not call
`herdr pane split` separately. A recovery-only result without `new_pane_id` is
not a new pane; reconcile the same cwd first and repeat only when the helper says
`retry_required`. Generate a unique Lead name absent from the captured agent
list. Never resume or fork an existing agent.

Start the Lead with the configured role recipe in the new pane:

```text
herdr agent start <lead-name> --kind <roles.lead.kind> --pane <pane-id> -- <roles.lead.args exactly>
```

Start with no prompt and wait only for Herdr's startup-readiness result. Record
the pane ID, name, recipe, and context path/hash in the single `launch` event,
then atomically create `launcher-handoff.md` with the Lead/run/context identities
and ledger transfer.

Wrap the saved `context/lead.md` contents once in a short transport envelope
written in the configured live language; both its first and final lines tell the
Lead to use that language for conversational replies. The envelope is live
delivery, not another instruction layer or durable Markdown. Pass the complete
payload with `herdr agent prompt` using the execution environment's safe
argument facility and **without** `--wait`. Save the delivery result, context
digest, and full delivery-payload digest as a receipt outside the ledger. Do not
put a prompt in the start command, paraphrase or replace the context with a
pathname, send it twice, or wait for Lead work to finish.
After delivery is accepted, run `herdr agent focus <lead-name>`. Transfer is
complete only after the agent exists, the marker predates delivery, exact prompt
delivery succeeded, and focus targets the fresh Lead. Report the Lead name,
repository, run ID/evidence path, and preserved state.

If start or delivery fails, preserve evidence and the new pane; report the exact
failure. Do not retry unchanged prerequisites, substitute another recipe, or
close anything that might contain useful state.

## 5. Attach a Supervisor

Run this alternative branch only when the Human explicitly invokes the skill
with exact project root, run ID, and Lead name bindings. Resolve each existing
run through that project's Git common directory. Require its launch record,
Lead context digest, handoff marker, protocol, and live unique Lead to agree.

For one project, use its configured Supervisor recipe. For multiple projects,
the Human must name one host project whose configured recipe is launch
authority. Every bound protocol must permit observation, and the unchanged host
recipe must enforce read-only access to every project plus write access only to
each bound run's `supervisor/` directory. Stop if it cannot; do not merge recipes
or fall back.

Build the pack in three layers: Supervisor role plus full anti-pattern catalog;
each full protocol under a project boundary; then exact bindings, notebook
roots, authority, and Assignment. Save the exact context in the host run and its
digest in every bound run's attachment receipt; do not copy project evidence
between runs.

Create a no-focus pane at the host run's `supervisor/` directory using the bound
host run's layout helper and shared state, choose a fresh unique name, start the
exact host recipe, submit the saved context once, and confirm delivery. Prompt
each bound Lead with its local receipt path/digest; the Lead remains that
project's ledger writer. Focus the Supervisor unless the Human requests
otherwise.

On any start, delivery, or receipt failure, preserve the pane and evidence,
report the exact failure, and do not retry unchanged prerequisites. Never reuse
an existing session as fresh, infer authority from configuration alone, create
a replacement Lead, or treat a recommendation as acceptance.
