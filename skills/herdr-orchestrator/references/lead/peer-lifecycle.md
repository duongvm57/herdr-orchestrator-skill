# Peer dispatch and results

Use one bounded task with an exact configured Peer profile and only the
applicable bounded protocol constraints. The task identifies the objective,
owned and excluded scope, authority boundary, dependencies, verification, and
the decision the result informs. Keep independent judgment neutral: supply
facts and open questions without a preferred conclusion.

Choose the disposition independently from the profile:

- **Engineer:** owns one writable moving scope, preserves unrelated work,
  verifies changes, and does not self-accept difficult work.
- **Architect:** read-only; analyzes ownership, lifecycle, alternatives,
  counterarguments, and reversal conditions.
- **Reviewer:** fresh and read-only; attempts to falsify one exact candidate.
  Findings and OCR coverage are evidence; the semantic handback vocabulary is
  shared with every Peer. OCR is optional; direct review remains the fallback.
- **Other bounded Peer:** receives only the question, evidence boundary,
  exclusions, and decision it informs.

Construct the canonical Assignment first. Compile the pane launch, which
validates its route before dispatch, split it with native Herdr, then compile
the returned Peer runtime. Start through the recipe-bound helper; compose and
submit the Assignment in memory through `submit-assignment`; use the official
Herdr skill to wait and read. Prompt submission and lifecycle settle are not Assignment completion: active Lead
collection inspects output and accepts only a structured handback with the
matching `assignment_id`. The outcome is exactly `COMPLETE`, `REOPEN_REQUEST`,
`DEPENDENCY_REQUEST`, or `BLOCKED`. A detached Lead is not automatically woken.

Submit the Assignment once, then use one native `agent wait`
without a short default timeout. If a Human-selected bounded wait expires, do
one bounded native `agent get` or `agent read` observation. Do not repeat that
wait or send another prompt until new state or evidence appears. Only when the
observation shows the exact Assignment is visible but stalled, send one explicit
activation follow-up to that same Peer. Do not resend the Assignment blindly,
alter Assignment/topology, or loop retries; this is bounded recovery, not a
prompt-wait subsystem or exact-turn tracker.

Choose the distinct Peer name before constructing its Assignment. Preserve that
same exact name in `owner`, the native Peer start/prompt target, the structured
handback binding, and any evidence index. The delegating Lead's name belongs
only in `parent.id`; it is never a Peer or Supervisor entry.

A handback is a JSON object with exactly `assignment_id`, `outcome`,
`evidence`, `impact`, and `need`; each is a non-empty string. Validate that
object against its exact Assignment before routing it.

Use the canonical helper for the semantic validators below; it has no generic
Herdr lifecycle control. Normal dispatch does not run standalone
`validate-assignment` or create a rendered prompt file:

```text
python3 "$HERDR_ORCHESTRATOR_HELPER" validate-delegation --assignment <active-peer.json> \
  --assignment <new-peer.json>
python3 "$HERDR_ORCHESTRATOR_HELPER" validate-review --assignment <reviewer.json> \
  --current-candidate <current-candidate.json> --project-root <root>
python3 "$HERDR_ORCHESTRATOR_HELPER" validate-handback --assignment <peer.json> \
  --handback <handback.json>
```

Before pane creation, use `compile-runtime --target-role peer --assignment` from
the Lead's exact pane. After split, compile a fresh `peer` context from the
returned Peer pane. `submit-assignment` validates and inserts that adapter
context, submits exact bytes through native Herdr, and creates no prompt
transport artifact; no provider syntax is assembled in prose.

## Herdr worktree allocation for concurrent writers

Before dispatch, validate the entire active Assignment map. Every Assignment
has a canonical absolute `project_root`. One writer may use the assigned
existing checkout. When two or more write Assignments will be active together,
their scopes must be disjoint and every writer must receive a distinct Herdr
worktree checkout; read-only Peers may continue to share a checkout.

Create each writer checkout through Herdr, never through raw `git worktree`:

```text
herdr worktree create --cwd <canonical-integration-root> --branch <new-owned-branch> \
  --base <integration-base> --path <new-owned-absolute-worktree-path> \
  --label <writer-label> --no-focus
```

`<canonical-integration-root>` comes from the validated consumer project
identity, never from an ambient workspace or a workspace ID. Do not use
`--workspace` as a repository selector for creation: it is an allocation handle
only after Herdr has returned it. This exact-root rule also applies when a
protocol chooses an isolated checkout for one writer.

Read `workspace.workspace_id`, `workspace.worktree.checkout_path`, and
`root_pane.pane_id` from the native JSON response. Put that exact checkout path
in the writer Assignment's `project_root`, and record the returned workspace ID
plus canonical integration root in its `worktree`; use that checkout as `--cwd`.
Compile the temporary pane launch from those facts, split the returned root
pane, then compile the fresh Peer context from the resulting pane ID before
submitting the Assignment. This does not create a worktree
registry or a second lifecycle service.

Before starting any concurrent writer, capture the authoritative native list
and bind every Assignment root/workspace ID to it. This is validation evidence,
not a helper-owned Herdr operation:

```text
herdr worktree list --cwd <canonical-integration-root> > <temporary-worktree-list.json>
python3 "$HERDR_ORCHESTRATOR_HELPER" validate-delegation \
  --assignment <active-writer-a.json> --assignment <active-writer-b.json> \
  --worktree-list <temporary-worktree-list.json>
```

The validator rejects absent allocation metadata, a non-linked checkout, a
different integration repository, or a list that does not bind each exact
`project_root` and `workspace_id`. Do not dispatch after any failure.

If any required allocation, binding, or launch preparation fails, do not launch
that concurrent writer in the shared checkout. Stop the concurrent dispatch and
return the failure to the Lead for a bounded decision. The Lead may remove only
newly owned, unused successful allocations with `herdr worktree remove
--workspace <workspace.workspace_id>`; it never removes pre-existing workspaces.

After matching handbacks, the Lead or named integration owner integrates the
writer results using the project's existing Git protocol. Only then freeze the
single common candidate in the integration checkout, bind review and acceptance
to it, and remove each newly owned worktree with `herdr worktree remove
--workspace <workspace.workspace_id>`. A worktree handback never substitutes
for integration, candidate freeze, review, or acceptance.

Before creating the pane, compile its launch projection:

```text
<adapter-runtime-bound-helper> compile-runtime --project-root <root> \
  --kind <configured-peer-kind> --role lead --pane-id <lead-pane-id> \
  --source-context <lead-runtime.json> --target-role peer \
  --assignment <assignment.json> --output <peer-launch.json>
```

Use every returned `pane_launch.pane_environment` entry as one literal `--env NAME=VALUE`
argument in the next native pane call. Do not fill in a missing value from the
ambient shell, add another harness's home/context syntax, or manually add a
Herdr-managed runtime variable.

Create one native Herdr Peer pane with the canonical project and role context.
This is one direct `herdr pane split --env` call, not a pane manager:

```text
herdr pane split --pane <pane_launch.source_pane_id> \
  --direction <right-or-down> --cwd <root> \
  <literal --env arguments from peer-pane-binding.json> --no-focus
```

Read the returned pane ID from native JSON. Never set or copy Herdr-managed
`HERDR_ENV`, `HERDR_SOCKET_PATH`, `HERDR_PANE_ID`, `HERDR_TAB_ID`, or
`HERDR_WORKSPACE_ID`; Herdr injects those values for the new managed pane.
This applies unchanged to a Reviewer, which remains a Peer with disposition
`Reviewer`, not a separate runtime role.
The Reviewer pane projection also binds the exact Assignment id and owner; only
that pane may materialize the assigned candidate.

Compile `<peer-runtime.json>` with `compile-runtime --role peer --pane-id
<returned-peer-pane-id> --source-context <lead-runtime.json>` before calling
`submit-assignment`.

Start the named Peer through the recipe-bound helper, then call
`submit-assignment` once. `start-peer` is the only canonical Peer start path: it
validates the Assignment route and sends its configured native arguments
unchanged after `--`; the Assignment supplies the name and only the target pane
is a runtime launch input. Never freehand a `herdr agent start` command or
add/translate a native argument, including for a Reviewer:

```text
<adapter-runtime-bound-helper> start-peer --assignment <assignment.json> --pane <pane-id>
<adapter-runtime-bound-helper> submit-assignment --agent <peer-name> \
  --assignment <assignment.json> \
  --role-profile <peer-profile.md> --applicable-protocol <bounded-constraints.md> \
  --runtime-context <peer-runtime.json>
```

Keep the Assignment as the inspectable source; do not reconstruct it from
prose.
It is a Peer-only handoff contract, with this directly usable shape:

```json
{
  "schema_version": 2,
  "assignment_id": "<stable-id>",
  "role": "peer",
  "parent": {"role": "lead", "id": "<lead-id>"},
  "owner": "<peer-id>",
  "project_root": "/absolute/path/to/assigned-checkout",
  "worktree": null,
  "objective": "<bounded outcome>",
  "owned_scope": ["path:<project-relative-path>"],
  "exclusions": ["<out-of-scope constraint>"],
  "authority": "write|read-only",
  "disposition": "Engineer|Reviewer|Architect|<bounded role>",
  "recipe": null,
  "verification": ["<required check>"],
  "dependencies": ["<known dependency>"],
  "languages": {"live": "<configured>", "artifact": "<configured>"},
  "topology_rationale": null,
  "candidate": null,
  "review_cycle": 1,
  "prior_review": null,
  "convergence_assessment": null,
  "cost_approval": null
}
```

For a concurrent writer, replace `null` with the exact allocation binding:

```json
{"kind":"herdr_worktree","workspace_id":"<returned-workspace-id>","source_project_root":"/absolute/path/to/integration-root"}
```

`parent.id` identifies the Lead that delegated the work. `owner` identifies the
named Peer that owns the bounded technical outcome and, for `authority: write`,
the moving write scope. They must not be inferred from pane layout or agent
adjacency.

Set `topology_rationale` only for a meaningful multi-scope or nontrivial
topology decision. A Reviewer candidate is an immutable Git identity: either
`{"kind":"git_commit","value":"<40-char commit>"}` or
`{"kind":"git_tree","base_commit":"<40-char commit>","tree":"<40-char tree>"}`.
Use the canonical `freeze-candidate` document at
`.orchestration/current-candidate.json`; never substitute a mutable diff digest
or compare a candidate only to its base commit.
Before a new writer launch, use `validate-delegation` against the active Peer
Assignments. Before accepting a review, use `validate-review` against that full
current-candidate document. Before routing any Peer result, use
`validate-handback`, retain its evidence, and make the semantic decision.
Then close only that task's exact Reviewer or Architect pane; retain an
Engineer for correction. After valid acceptance, close task-owned Engineer and
remaining Peer panes. Never close a Launcher, Supervisor, or pre-existing
topology.

The project routing table chooses `engineer`, `reviewer`, `architect`, or
`default` for a custom disposition. `recipe: null` resolves that route's exact
`default_recipe`; a named recipe must be in its allowlist. Record the selected
recipe's harness/model/effort, native priority flags, and `cost_class` in
preflight. An `elevated` recipe needs Human approval before launch, copied
verbatim into the Lead prompt and `cost_approval`. At review cycle 2 or later,
`prior_review` binds `reviewer_assignment_id`, its SHA-256, and its handback
SHA-256. At review cycle 3 or later (the initial `assessment_after_cycles = 2`
guard), `convergence_assessment` groups nonempty findings by `mechanism` and
uses exactly one `decision`: `continue`, `re-architect`, `escalate`, or `block`.

Keep inline handback bounded. A durable evidence file is required only when the
task needs one or normal read cannot recover large evidence; resolve/read any
reference before treating it as valid. A temporary path is active-flow transport,
not a semantic journal or restart-safe recovery. Accept a failed premise,
dependency, missing authority, or blocker as a result to route, not permission
to widen scope.

Give each moving scope one writer. Correctable findings return to the same
Engineer, then a new stable candidate receives a fresh review. Peers communicate
through the Lead and never coordinate one another.
