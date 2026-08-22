# Launcher procedure

The invoking session performs this procedure, creates one fresh Project Lead,
and transfers the Human to it. The Launcher does not coordinate Peers.

## 1. Preflight without mutation

Resolve the repository root with Git. Require and strictly parse:

- `.orchestration/herdr-orchestrator.toml` at `version = 1`;
- `.orchestration/workspace-protocol.md` with all twelve protocol sections;
- one `[lead]` recipe; and
- the configured `default_peer` plus every declared Peer recipe.

Read live `herdr --help`, `herdr agent start --help`, and each configured
harness's help/catalog. Require a reachable Herdr server, installed executable,
supported kind, accepted native arguments, and available configured model for
every entry that this run may use. Report the exact table and failing element,
then stop; never fall back.

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
Human task, and preserved before-state are unambiguous.

## 2. Create run evidence

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

Append semantic events as one valid JSON object per line. Each event has
`schema_version`, UTC `timestamp`, `run_id`, `type`, `actor`, and
event-specific evidence references. Allowed milestone types are `launch`,
`assignment`, `report`, `candidate`, `verification`, `review`,
`human_decision_request`, `verdict`, and `finish`. Do not encode current agent
status, a queue, retry counters, or acceptance inferred from status.

Evidence preparation is complete when the directory is outside the checkout,
all five entries exist, and before-state plus Human task are durable.

## 3. Build the Lead context pack

Read and concatenate, with clear titled boundaries, the exact content required
by the Lead-pack row in `SKILL.md`:

1. `references/roles/lead.md`;
2. `references/topology.md`;
3. all of `references/anti-patterns.md`;
4. `references/assignments-and-evidence.md`;
5. `references/roles/peer.md` as the template the Lead will inject into Peers;
6. the parsed project config, including native recipes;
7. the full project Workspace Protocol;
8. the verbatim Human task and relevant repository authority; and
9. run ID, absolute evidence directory, repository root, and before-state.

Add a small assignment boundary: the Lead may orchestrate only this project and
Human task; external effects and Human-only decisions remain excluded unless
explicitly granted. Do not add a preferred implementation or hidden verdict.
Save the exact bytes as `context/lead.md` and record its SHA-256. This saved file
is the canonical answer to what the Lead was told.

The pack is complete when every required source appears once, the full protocol
and anti-pattern catalog are present, Peer instructions are available for later
direct injection, and no Supervisor role text was added.

## 4. Start and transfer

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

Then run `herdr agent focus <lead-name>`. The transfer is complete only after
Herdr confirms the agent exists, the prompt was delivered, and focus targets
that fresh Lead. Report the Lead name, repository, run ID/evidence path, and
preserved pre-existing state to the Human.

If start or delivery fails, preserve evidence and the new pane; report the exact
failure. Do not retry unchanged prerequisites, substitute another recipe, or
close anything that might contain useful state.
