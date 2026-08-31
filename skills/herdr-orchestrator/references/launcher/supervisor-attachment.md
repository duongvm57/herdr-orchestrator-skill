# Supervisor attachment

Read `references/launcher/preflight.md` completely first. Run this branch only
when the Human explicitly asks for a Supervisor. This is a Human/Launcher
governance attachment, not Lead or Peer work.

Continuous supervision additionally requires installed Herdr's native
event-to-prompt wake capability with an explicit Lead–Supervisor attachment and
opaque task/Assignment correlation. This repository does not emulate it with a
wrapper, polling loop, or inferred pane parentage. If that native capability is
absent, return `DEPENDENCY_REQUEST`; offer one-shot on-demand observation only
when the Human explicitly chooses it, and never label it continuous.
This repository has no native-wake proof bundled with it: do not enable or
dogfood continuous supervision until the matching Herdr release supplies and
live-proves that capability.

Use the official Herdr skill to create a background pane with
`HERDR_ORCHESTRATOR_ROLE=supervisor`. The helper compiles the configured start,
runtime context, and bounded prompt; Herdr performs the native lifecycle.

Apply only the selected adapter's verified runtime-compatibility projection.
Any adapter-specific Herdr IPC or sandbox requirement is technical execution
context, not Supervisor authority: the Supervisor remains governance-only and
must not edit the consumer project. Adapter code, not this generic Supervisor
contract, owns those requirements.

Require the explicit task Lead pane ID from task launch or the Human
attachment. Split that literal pane; never use the Launcher's current pane or
infer the attachment from workspace, cwd, focus, or adjacency:

```text
herdr pane split --pane <attached-lead-pane-id> --direction <right-or-down> --cwd <root> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_HELPER=<canonical-helper-absolute-path> \
  --env HERDR_ORCHESTRATOR_ROLE=supervisor --no-focus
```

Compile the configured launch manifest with `prepare-control-role-launch`, then
execute its unmodified `herdr_argv`. Compile the returned Supervisor pane with
`compile-runtime` as specified in `references/launcher/runtime-binding.md`.
Write the Human mandate unchanged to a temporary UTF-8 file and render it:

```text
<canonical-helper> render-control-prompt --project-root <root> --role supervisor \
  --payload <mandate-file> --runtime-context <supervisor-runtime.json> \
  --attached-lead-name <lead-name> --attached-lead-pane <lead-pane> \
  --output <prompt-file>
```

Add `--include-protocol` only for a protocol audit/update proposal. The renderer
binds the exact Lead attachment and governance-only authority. Submit through
`<adapter-runtime-bound-helper> submit-prompt`; no mandate text enters a shell.

Keep the Supervisor in the background unless the Human explicitly requests
focus. For an installed native continuous attachment, its bridge filters,
correlates, and prompts only on relevant status/exit/blocked/settled transitions
with transition deduplication; it does not reason, route Assignments, accept,
or detect silence. While active, it may use native `agent wait`, `agent read`, and inspect
operations from the official skill against its explicitly attached Lead and
relevant Peers. Lifecycle/event signals only trigger inspection; they do not
create a Supervisor inference turn, verdict, or automatic wake.

The Supervisor may send an evidence-backed open question or explicit Human
decision directly to the attached Lead. It does not order a correction, accept
the project, spawn Peers, or modify code. A notebook or report exists only when
the mandate explicitly requests a durable artifact. Lead and Peer neither wake,
maintain, nor need to know whether the Supervisor is running.
