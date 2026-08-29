# Supervisor attachment

Read `references/launcher/preflight.md` completely first. Run this branch only
when the Human explicitly asks for a Supervisor. This is a Human/Launcher
governance attachment, not Lead or Peer work.

Use the release-matched official Herdr Agent Skill to create a background pane
with `HERDR_ORCHESTRATOR_ROLE=supervisor`, start the exact configured Supervisor
recipe, and submit its bounded mandate as one direct prompt argument.

```text
herdr pane split --current --direction <right-or-down> --cwd <root> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_ROLE=supervisor --no-focus
herdr agent start <unique-supervisor-name> --kind <configured-kind> --pane <returned-pane-id> -- <configured-native-args...>
```

Read the selected concise Supervisor profile for this one bounded composition.
The prompt must confirm that the Supervisor harness has the release-matched
official Herdr skill installed in its supported instruction context. A
documented harness-specific compatibility fallback may inject one fresh
`herdr --skill` copy. Attachment must record the
explicit supervised Lead name/pane and bounded scope
in the mandate. Never infer that relationship from pane layout, workspace, or
cwd. The configured Supervisor recipe is required; substitution is not allowed.
The prompt contains the Supervisor profile, bounded observation scope, explicit
Lead attachment, and only applicable read-only constraints. Include the full
protocol only for a protocol audit or update proposal.

Keep the Supervisor in the background unless the Human explicitly requests
focus. While active, it may use native `agent wait`, `agent read`, and inspect
operations from the official skill against its explicitly attached Lead and
relevant Peers. Lifecycle/event signals only trigger inspection; they do not
create a Supervisor inference turn, verdict, or automatic wake.

The Supervisor may send an evidence-backed open question or explicit Human
decision directly to the attached Lead. It does not order a correction, accept
the project, spawn Peers, or modify code. A notebook or report exists only when
the mandate explicitly requests a durable artifact. Lead and Peer neither wake,
maintain, nor need to know whether the Supervisor is running.
