# Supervisor attachment

Enter this route either from default task launch after its preflight, or from an
explicit Human request after reading `references/launcher/preflight.md`
completely. This is a Human/Launcher governance attachment, not Lead or Peer
work.

Continuous supervision additionally requires installed Herdr's native
event-to-prompt wake capability with an explicit Lead–Supervisor attachment and
opaque task/Assignment correlation. This repository does not emulate it with a
wrapper, polling loop, or inferred pane parentage. If that native capability is
absent, return `DEPENDENCY_REQUEST` for a requested continuous mode; the default
remains one bounded observation and is never labelled continuous.
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
Use the task's unique run scratch. For a default attachment, write this canonical
mandate unchanged to `<run-scratch>/mandate.txt`:

```text
Observe the exact attached Lead for one bounded settled turn. Then inspect its
transcript and relevant Peer lifecycle evidence. Report launcher, delegation,
review, handback, and acceptance friction with exact evidence. Do not poll,
write project files, direct roles, accept work, or send prompts.
```

For an explicit Human attachment, write the Human mandate unchanged instead.
Compose and submit it in one call:

```text
<adapter-runtime-bound-helper> submit-control-prompt --agent <supervisor-name> \
  --project-root <root> --role supervisor --payload <run-scratch>/mandate.txt \
  --runtime-context <run-scratch>/supervisor-runtime.json \
  --attached-lead-name <lead-name> --attached-lead-pane <lead-pane>
```

Add `--include-protocol` only for a protocol audit/update proposal. The command
binds the exact Lead attachment and governance-only authority, submits through
native Herdr without a prompt transport file, and never places mandate text in
a shell.

Keep the Supervisor in the background unless the Human explicitly requests
focus. The default mandate performs one native wait for the attached Lead's
current turn to settle, one bounded inspection, and one report; it does not poll
or promise whole-task coverage. For an installed native continuous attachment,
its bridge filters,
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
