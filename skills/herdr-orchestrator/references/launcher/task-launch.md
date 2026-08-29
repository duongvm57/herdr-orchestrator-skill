# Task launch

Read `references/launcher/preflight.md` completely and pass its gate first.
This branch starts one fresh Project Lead and hands over the Human task. The
Launcher does not coordinate Peers after delivery or become the Lead.

## Start the Lead

Use the release-matched official Herdr Agent Skill. Inspect the current pane,
then split a sibling pane with the canonical project root, role context, and no
focus. Read the returned pane ID from JSON; do not predict it. Start the exact
configured Lead recipe in that pane with native arguments after `--`.

```text
herdr pane split --current --direction <right-or-down> --cwd <root> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_ROLE=lead --no-focus
herdr agent start <unique-lead-name> --kind <configured-kind> --pane <returned-pane-id> -- <configured-native-args...>
```

Read the selected concise Lead profile for this one bounded composition, then
submit a prompt built from it, the applicable full Workspace
Protocol, the configured Peer recipes, and the verbatim Human task. Pass it as
one direct CLI argument or socket/API value; never assemble a shell command
from task text. Do not strip, normalize, route on, or shell-evaluate that text.
The default preserves Launcher focus; focus only at Human request.

The prompt must confirm that the Lead harness has the release-matched official
Herdr skill installed in its supported instruction context. A documented
harness-specific compatibility fallback may inject one fresh `herdr --skill`
copy. It must state that the Lead uses the official Herdr skill for generic
operations, cannot create another Lead or Supervisor, and must use an explicit
Assignment for every Peer. It contains:

1. the concise Lead profile;
2. the full repository Workspace Protocol; and
3. the verbatim Human task and available configured Peer recipes.

If native startup returns `agent_not_ready`, preserve the newly created agent
and pane, inspect it, and expose blocked evidence. Do not replace it. If prompt
delivery is ambiguous or times out, inspect the current agent/output before an
explicit follow-up; do not blind-retry or destroy the pane. Only close a
newly-owned pane when a process was never established and safety is proven;
never change pre-existing topology.

Launch is complete when native start and direct prompt submission have been
observed. Report the exact Lead name and pane ID to the Human. Prompt submission
is not Assignment completion; no durable transport state is created.
