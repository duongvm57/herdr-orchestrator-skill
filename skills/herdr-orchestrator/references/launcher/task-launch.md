# Task launch

Read `references/launcher/preflight.md` completely and pass its gate first.
This branch starts one fresh Project Lead and hands over the Human task. The
Launcher does not coordinate Peers after delivery.

## Start the Lead

Invoke the packaged runtime directly:

```text
python3 scripts/herdr_runtime.py start \
  --role lead \
  --project-root <canonical-project-root> \
  --task <verbatim-human-task>
```

Resolve the script relative to the installed skill root and pass its absolute
path. By default the runtime preserves the Launcher's focus. Add `--focus` only
when the Human requested an immediate UI handoff to the Lead.

The runtime reads the accepted project config and Workspace Protocol, splits a
sibling pane without focus, starts the exact configured Lead recipe, and sends
one prompt containing:

1. the concise Lead profile;
2. the full repository Workspace Protocol; and
3. the verbatim Human task, available Peer profiles, and three runtime
   operations: `start`, `result`, and `prompt`.

If native startup returns `agent_not_ready`, preserve the returned agent and
pane. Inspect the same agent until it becomes promptable or report its blocked
state to the Human. Never create a replacement for that startup attempt.

Launch is complete when the runtime returns `status: prompted` with the exact
Lead name and pane ID. Report those identities to the Human. No durable transport
state is created.
