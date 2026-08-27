---
name: herdr-orchestrator
description: Set up or launch a Human-led Herdr project workflow.
---

# Herdr Orchestrator

## Re-entry guard

Inspect `HERDR_ORCHESTRATOR_ROLE` before routing. For `lead`, `peer`, or
`supervisor`, remain that spawned role and continue its assignment or mandate.
Treat `$herdr-orchestrator` as unchanged task/context data; do not enter
Launcher routes or start/attach roles. Route by role environment, never task
text.

Only absent `HERDR_ORCHESTRATOR_ROLE` permits Launcher behavior. Then run only
on explicit Human invocation: that session is the **Launcher**, never Project
Lead.

## Route one invocation

Read one selected route completely; compose only when it says so.

- **Setup/update:** read `references/launcher/setup.md`,
  `references/launcher/workspace-protocol-authoring.md`,
  `assets/config.toml`, and `assets/workspace-protocol-template.md`.
- **Task launch:** read `references/launcher/preflight.md`, then
  `references/launcher/task-launch.md`.
- **Supervisor attachment:** read `references/launcher/preflight.md`, then
  `references/launcher/supervisor-attachment.md`.

Runtime role profiles are opaque to the Launcher: pass their paths without
reading bodies.

## Context invariant

Every delivered pack has three ordered layers:

1. **Role Profile** — identity and authority.
2. **Workspace Protocol** — full for Lead/Supervisor; selected constraints for
   Peer.
3. **Assignment** — objective, scope, evidence, and handoff.

Use configured languages for live and durable prose. Preserve source bytes,
technical literals, and the verbatim Human task.

Herdr owns control and lifecycle; Git and the filesystem own workspace and
artifact truth. Independent judgment uses a fresh session; corrections return
to the same Engineer.

Use packaged `scripts/herdr_runtime.py` for pane creation, configured start,
prompt, wait, and read. Agent names and pane IDs are runtime handles; durable
files are artifacts, not transport.
