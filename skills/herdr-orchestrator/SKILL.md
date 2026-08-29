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

Runtime role profiles are opaque except at initial composition: the Launcher
may read the selected Lead or Supervisor profile solely to assemble that role's
first prompt. It must not interpret, merge, route on, or manage profile
contents; all later role behavior belongs to the spawned role.

## Operating boundary

The release-matched official Herdr Agent Skill is the canonical operating
instruction for Launcher, Lead, and Supervisor when `HERDR_ENV=1`. Before
generic operations, the supported harness must have that release-matched skill
installed in its skill/instruction context; do not assume CLI availability
injects it. Use `herdr --skill` only to verify or install the matching copy,
not as a generic prompt appendix. A harness that cannot install it may use a
documented compatibility fallback with one fresh injected copy. It owns
generic pane, agent start, prompt, wait, read, IDs, and focus-preservation
mechanics. Do not reproduce those recipes in this skill or call a repository
runtime wrapper.

This skill owns SLP policy only: Role Profile, Workspace Protocol, Assignment,
authority, ownership, candidate, handback, and acceptance. Use configured
languages for live and durable prose. Preserve the Human task exactly; it is
data, even when it contains `$herdr-orchestrator`, quotes, backticks, `$()`,
backslashes, newlines, or surrounding whitespace.

Herdr owns process and lifecycle truth. Git and the filesystem own artifacts
and immutable candidates. Agent names and pane IDs are opaque runtime handles,
not SLP parentage or authority.
