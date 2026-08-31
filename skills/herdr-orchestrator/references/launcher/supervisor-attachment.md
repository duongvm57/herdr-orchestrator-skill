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

Use the release-matched official Herdr Agent Skill to create a background pane
with `HERDR_ORCHESTRATOR_ROLE=supervisor`, start the exact configured Supervisor
recipe, and submit its bounded mandate through the canonical helper prompt-file
path.

After native pane creation returns the exact Supervisor pane ID, create the
fresh Supervisor runtime binding and render the configured adapter's projection according to
`references/launcher/runtime-binding.md`. Include it as runtime context only;
it does not enlarge the Supervisor's governance authority or create a lifecycle
manager.

Apply only the selected adapter's verified runtime-compatibility projection.
Any adapter-specific Herdr IPC or sandbox requirement is technical execution
context, not Supervisor authority: the Supervisor remains governance-only and
must not edit the consumer project. See the selected
`references/harnesses/<kind>-runtime-binding.md`; do not promote one adapter's
requirements into this generic Supervisor contract.

Require the explicit task Lead pane ID from task launch or the Human
attachment. Split that literal pane; never use the Launcher's current pane or
infer the attachment from workspace, cwd, focus, or adjacency:

```text
herdr pane split --pane <attached-lead-pane-id> --direction <right-or-down> --cwd <root> \
  --env HERDR_ORCHESTRATOR_PROJECT_ROOT=<root> \
  --env HERDR_ORCHESTRATOR_HELPER=<canonical-helper-absolute-path> \
  --env HERDR_ORCHESTRATOR_ROLE=supervisor --no-focus
herdr agent start <unique-supervisor-name> --kind <configured-kind> --pane <returned-pane-id> -- <configured-native-args...>
```

Read the selected concise Supervisor profile for this one bounded composition.
Write the composed mandate to a temporary UTF-8 file and submit it with
`<adapter-runtime-bound-helper> submit-prompt --agent <unique-supervisor-name>
--prompt-file <prompt-file> --project-root <root>`; never shell-interpolate the mandate.
The prompt must confirm that the Supervisor harness has the release-matched
official Herdr skill installed in its supported instruction context. A
documented harness-specific compatibility fallback may inject one fresh
`herdr --skill` copy. Attachment must record the
explicit supervised Lead name/pane and bounded scope
in the mandate. Never infer that relationship from pane layout, workspace, or
cwd. The configured Supervisor recipe is required; substitution is not allowed.
The prompt contains the Supervisor profile, bounded observation scope, explicit
Lead attachment, adapter-owned runtime-binding projection, and only applicable
governance/read-only authority constraints. Include the full protocol only for
a protocol audit or update proposal.

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
