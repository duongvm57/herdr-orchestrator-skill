# Launcher procedure

The invoking session launches one fresh Project Lead or attaches one fresh
Supervisor to exact active bindings. It never coordinates Peers.

## 1. Preflight without mutation

Require `HERDR_ENV=1`, then read current `herdr --skill` and relevant `--help`
output as command authority. Resolve the repository root with Git. Require and
strictly parse:

- `.orchestration/herdr-orchestrator.toml` at `version = 1`;
- `.orchestration/workspace-protocol.md` with all twelve protocol sections;
- one `[lead]` recipe, optional `[supervisor]`; and
- the configured `default_peer` plus every declared Peer recipe.

Reject every other top-level key, recipe indirection, placeholder, credential,
legacy profile/route schema, or unresolved default.

Read live `herdr --help`, `herdr agent start --help`, and each configured
harness's help/catalog. Require a reachable Herdr server, installed executable,
supported kind, accepted native arguments, available configured model, denied
native spawning, and role-compatible read/write boundary for every configured
entry. The Lead must be able to write run evidence; a Supervisor must be
project-read-only and notebook-write-only. Report the exact failing element and
stop; never fall back.

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
├── supervisor/
└── events.jsonl
```

This location is outside tracked checkout content even when worktrees are used.
Never add it to a commit. Save the before-state inventory and the exact Human
task in the run directory.

The Lead Assignment requires waiting for `launcher-handoff.md` before
orchestrating or appending events. The Launcher owns initial evidence until that
marker transfers ledger ownership, preventing concurrent writers.

Append semantic events as one valid JSON object per line. Each event has
`schema_version`, UTC `timestamp`, `run_id`, `type`, `actor`, and
event-specific evidence references. Allowed milestone types are `launch`,
`assignment`, `report`, `candidate`, `verification`, `review`,
`human_decision_request`, `verdict`, and `finish`. Do not encode current agent
status, a queue, retry counters, or acceptance inferred from status.

Evidence preparation is complete when the directory is outside the checkout,
all five entries exist, and before-state plus Human task are durable.

## 3. Task launch: build the Lead context pack

Read and concatenate the exact content required by the Lead-pack row in
`SKILL.md`, with clear titled boundaries in these three layers:

1. **Role Profile:** `references/roles/lead.md`, `references/topology.md`, all
   of `references/anti-patterns.md`, `references/assignments-and-evidence.md`,
   and `references/roles/peer.md` as the template for later Peer injection;
2. **Workspace Protocol:** parsed project config with native recipes, then the
   full project Workspace Protocol; and
3. **Assignment:** verbatim Human task and relevant repository authority, then
   run ID, absolute evidence directory, repository root, and before-state.

Add a small assignment boundary: the Lead may orchestrate only this project and
Human task; external effects and Human-only decisions remain excluded unless
explicitly granted. Do not add a preferred implementation or hidden verdict.
Save the exact bytes as `context/lead.md` and record its SHA-256. This saved file
is the canonical answer to what the Lead was told.

The pack is complete when every required source appears once, the full protocol
and anti-pattern catalog are present, Peer instructions are available for later
direct injection, and no Supervisor role text was added.

## 4. Task launch: start and transfer

Use live Herdr help as command-shape authority. Create a new pane in the
repository checkout without focusing it. Generate a unique Lead name that is
absent from the captured agent list. Never resume or fork an existing agent.

Start the Lead with the configured recipe in the new pane:

```text
herdr agent start <lead-name> --kind <lead.kind> --pane <pane-id> -- <lead.args exactly>
```

Pass the saved `context/lead.md` contents as one exact prompt using the execution
environment's safe argument facility. Do not paraphrase it, send it twice, or
ask the Lead to invoke this skill. Record the pane ID, name, recipe, context
path/hash, and prompt delivery in a `launch` event.

After recording the launch event, run `herdr agent focus <lead-name>`. Only after
Herdr confirms that focus targets the fresh Lead, atomically create
`launcher-handoff.md` with the Lead/run/context identities and ledger transfer.
Transfer is complete only after the agent exists, prompt delivery succeeded,
focus succeeded, and the marker released the Lead. Report the Lead name,
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

Create a no-focus pane at the host run's `supervisor/` directory, choose a fresh
unique name, start the exact host recipe, submit the saved context once, and
confirm delivery. Prompt each bound Lead with its local receipt path/digest; the
Lead remains that project's ledger writer. Focus the Supervisor unless the
Human requests otherwise.

On any start, delivery, or receipt failure, preserve the pane and evidence,
report the exact failure, and do not retry unchanged prerequisites. Never reuse
an existing session as fresh, infer authority from configuration alone, create
a replacement Lead, or treat a recommendation as acceptance.
