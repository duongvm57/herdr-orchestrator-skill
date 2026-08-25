---
name: herdr-orchestrator
description: Set up or launch a Human-led Herdr project workflow.
---

# Herdr Orchestrator

Run only when the Human explicitly invokes `$herdr-orchestrator`. The invoking
session is the **Launcher**, never the Project Lead. Herdr is the only agent
control plane; spawned agents receive saved context directly and never invoke
this skill.

## Route one invocation

Read the selected procedure completely. Procedures compose only where stated.

- **Setup/update:** read `references/launcher/setup.md`,
  `references/launcher/workspace-protocol-authoring.md`,
  `assets/config.toml`, and `assets/workspace-protocol-template.md`.
- **Task launch:** read `references/launcher/preflight.md`, then
  `references/launcher/task-launch.md`.
- **Supervisor attachment:** read `references/launcher/preflight.md`, then
  `references/launcher/supervisor-attachment.md`.

Do not load an unselected procedure. Runtime role profiles are opaque pack
sources: pass their paths to the orchestration helper without reading their
bodies in the Launcher.

## Context invariant

Every delivered pack has exactly three ordered layers:

1. **Role Profile** — identity, authority, and judgment invariants.
2. **Workspace Protocol** — full for Lead/Supervisor; selected constraints for
   Peer.
3. **Assignment** — one run's objective, scope, boundaries, evidence, and
   handoff.

Generated durable prose uses the configured artifact language; live envelopes,
status, and handoffs use the configured orchestration language. Preserve
authoritative source bytes, technical literals, and the verbatim Human task.

Herdr supplies lifecycle truth. Git and the filesystem supply workspace and
artifact truth. Independent judgment uses a fresh session; corrections return
to the same owning Engineer.

At runtime, invoke packaged `scripts/herdr_runtime.py`. It is the single seam for
pane creation, configured agent start, prompt, wait, and read. Herdr agent names
and pane IDs are the runtime handles. Durable files are task artifacts, not an
agent transport.
