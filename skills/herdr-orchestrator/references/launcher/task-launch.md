# Task launch

Read `references/launcher/preflight.md` completely and pass its gate first.
This branch starts one fresh Project Lead and hands over the Human task. The
Launcher does not coordinate Peers after delivery or become the Lead.

## Start the Lead

Use the release-matched official Herdr Agent Skill. Inspect the current pane,
then split a sibling pane with the canonical project root, role context, and no
focus. Read the returned pane ID from JSON; do not predict it. Start the exact
configured Lead recipe in that pane with native arguments after `--`.

After native pane creation returns the exact Lead pane ID, create the fresh
Lead runtime binding and render its selected adapter projection as specified in
`references/launcher/runtime-binding.md`. Append that bounded projection to the
initial prompt. It supplies runtime facts only; it neither changes the selected
Lead recipe nor grants orchestration, Assignment, or lifecycle authority.

```text
herdr pane split --current --direction <right-or-down> --cwd <root> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_HELPER=<canonical-helper-absolute-path> \
  --env HERDR_ORCHESTRATOR_ROLE=lead --no-focus
herdr agent start <unique-lead-name> --kind <configured-kind> --pane <returned-pane-id> -- <configured-native-args...>
```

Read the selected concise Lead profile for this one bounded composition, then
write the prompt built from it, the applicable full Workspace Protocol, the
configured Peer recipes, and the verbatim Human task to one temporary UTF-8
prompt file. Submit it only through the installed helper path resolved in
preflight:

```text
python3 <canonical-helper> submit-prompt --agent <unique-lead-name> --prompt-file <prompt-file>
```

The helper invokes native Herdr with direct subprocess argv; do not assemble a
shell command from task text. Do not strip, normalize, route on, or
shell-evaluate that text. Pass the exact `<canonical-helper-absolute-path>` in
the Lead's launch environment as `HERDR_ORCHESTRATOR_HELPER`; it is the only
helper path the Lead may use. The default preserves Launcher focus; focus only
at Human request.

The prompt must confirm that the Lead harness has the release-matched official
Herdr skill installed in its supported instruction context. A documented
harness-specific compatibility fallback may inject one fresh `herdr --skill`
copy. It must state that the Lead uses the official Herdr skill for generic
operations, cannot create another Lead or Supervisor, and must use an explicit
Assignment for every Peer. It contains:

1. the concise Lead profile;
2. the full repository Workspace Protocol; and
3. the verbatim Human task and available configured Peer recipes; and
4. the adapter-owned runtime-binding projection.

If native startup returns `agent_not_ready` because it is blocked by an
approval or directory-trust UI, preserve the newly created agent and pane and
surface the exact native question to the Human. Do not answer the UI, destroy
or recreate the Lead, or bypass trust protections. After the Human approves,
continue with that same Lead and pane. If prompt delivery is ambiguous, use
native `agent get` or `agent read` for one bounded observation before an
explicit follow-up; do not blind-retry or destroy the pane. Only close a
newly-owned pane when a process was never established and safety is proven;
never change pre-existing topology.

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
python3 <canonical-helper> validate-acceptance --project-root <root> \
  --lead-id <exact-launched-lead-name>
```

Only a passing check permits the Launcher to surface successful project
completion. This validates the Lead's evidence contract; it does not make the
Launcher the project authority.

If that first check fails for missing, malformed, or stale acceptance evidence,
send one structured follow-up to that same Lead through the official Herdr
skill. Include the validator failure verbatim, name the missing/stale contract
fields, tell the Lead to use the canonical `freeze-candidate`,
`inspect-candidate`, and `validate-acceptance` path, and ask it to reconsider
its verdict. Do not edit implementation, manufacture evidence, create a
Reviewer, change topology, restart the task, or otherwise coach the work.

After the Lead responds, inspect its response and validate once again. On pass,
surface successful completion and report that first-pass acceptance required
one recovery. On a second failure, surface `BLOCKED` with the exact validation
evidence. There is no third validation or correction loop.
