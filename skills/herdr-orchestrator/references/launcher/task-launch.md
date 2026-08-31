# Task launch

Read `references/launcher/preflight.md` completely and pass its gate first.
This branch starts one fresh Project Lead and hands over the Human task. The
Launcher does not coordinate Peers after delivery or become the Lead.

## Start the Lead

Use the release-matched official Herdr Agent Skill. Create one fresh task
workspace with the canonical project root, role context, and no focus. This
keeps the Launcher in its existing workspace: never split the Launcher pane to
start a Lead. Read the exact root pane ID from native JSON.

```text
herdr workspace create --cwd <root> --label <unique-task-label> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_HELPER=<canonical-helper-absolute-path> \
  --env HERDR_ORCHESTRATOR_ROLE=lead --no-focus
```

Read `.result.root_pane.pane_id`; it is the Lead pane and task topology anchor.
Same-checkout Supervisor and Peers split it; an isolated concurrent writer uses
its own Herdr worktree workspace.

Compile the exact configured start manifest after pane creation. An elevated
recipe requires the verbatim Human decision:

```text
<canonical-helper> prepare-control-role-launch --project-root <root> --role lead \
  --name <unique-lead-name> --pane <returned-task-root-pane-id> \
  --cost-approval <verbatim-human-decision-if-elevated> --output <launch.json>
```

Inspect the manifest, then execute its `herdr_argv` through the official Herdr
skill without editing or shell-reconstructing it. Compile the returned Lead
pane as specified in `references/launcher/runtime-binding.md`. Write the Human
task unchanged to a temporary UTF-8 file, then machine-render the prompt:

```text
<canonical-helper> render-control-prompt --project-root <root> --role lead \
  --payload <human-task-file> --runtime-context <lead-runtime.json> \
  --cost-approval <verbatim-human-decision-if-elevated> --output <prompt-file>
```

The renderer inserts the full Workspace Protocol, configured Peer recipes,
Lead boundary, adapter runtime context, and payload hash. Submit only through
the installed helper:

```text
<adapter-runtime-bound-helper> submit-prompt --agent <unique-lead-name> --prompt-file <prompt-file> \
  --project-root <root>
```

`<adapter-runtime-bound-helper>` comes from the compiled Lead runtime context.
The helpers use direct subprocess argv and preserve the task bytes; no task text
is shell input. Pass the canonical helper path in the workspace environment.
The default preserves Launcher focus; focus only at Human request.

If native startup returns `agent_not_ready` because it is blocked by an
approval or directory-trust UI, preserve the newly created agent and pane and
surface the exact native question to the Human. Do not answer the UI, destroy
or recreate the Lead, or bypass trust protections. After the Human approves,
continue with that same Lead and pane. If prompt delivery is ambiguous, use
native `agent get` or `agent read` for one bounded observation before an
explicit follow-up; do not blind-retry or destroy the pane. During launch,
close a newly-owned Lead pane only when a process was never established and
safety is proven; never change pre-existing topology. Peer cleanup after
validated handback or acceptance belongs to the Lead lifecycle.

Safe prompt submission proves a submission/delivery attempt, not semantic
completion. Use native `agent get` or `agent read` for bounded lifecycle and
transcript observation; do not depend on a final result from `agent prompt
--wait`. Lifecycle settlement alone also does not prove semantic completion.
Peer semantic completion requires its matching Assignment handback, and Lead
project completion requires a candidate plus valid acceptance evidence. Launch
setup is complete when native start and safe prompt submission have been
observed. Report the exact Lead name and pane ID to the Human. No durable
transport state is created.

## Production completion gate and one recovery

A Lead completion message, final answer, lifecycle settle, or passing tests is
not successful project completion. When the same launched Lead announces a
final-completion state, use the official Herdr skill to inspect its final output,
then run this semantic check locally:

```text
<adapter-runtime-bound-helper> validate-acceptance --project-root <root> \
  --lead-id <exact-launched-lead-name>
```

Here the form is the Launcher's freshly compiled runtime projection;
it binds the observed Launcher pane for this guarded call.

Only a passing check permits the Launcher to surface successful project
completion. This validates the Lead's evidence contract; it does not make the
Launcher the project authority.

If that first check fails for missing, malformed, or stale acceptance evidence,
send one structured follow-up to that same Lead through the official Herdr
skill. Include the validator failure verbatim, name the missing/stale contract
fields, tell the Lead to use the canonical `freeze-candidate` and
`validate-acceptance` path, and ask it to reconsider
its verdict. Do not edit implementation, manufacture evidence, create a
Reviewer, change topology, restart the task, or otherwise coach the work.

After the Lead responds, inspect its response and validate once again. On pass,
surface successful completion and report that first-pass acceptance required
one recovery. On a second failure, surface `BLOCKED` with the exact validation
evidence. There is no third validation or correction loop.
