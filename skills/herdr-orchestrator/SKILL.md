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
  `assets/config.toml`, `assets/workspace-protocol-template.md`, and
  `assets/orchestration.gitignore`.
- **Task launch:** read `references/launcher/preflight.md`, then
  `references/launcher/task-launch.md`.
- **Supervisor attachment:** read `references/launcher/preflight.md`, then
  `references/launcher/supervisor-attachment.md`.

Runtime role profiles are opaque except at initial composition: the Launcher
may read the selected Lead or Supervisor profile solely to assemble that role's
first prompt. It must not interpret, merge, route on, or manage profile
contents; all later role behavior belongs to the spawned role.

## Operating boundary

The release-matched official Herdr Agent Skill is canonical for every configured
harness when `HERDR_ENV=1`. Setup commits exact `herdr --skill` bytes at
`.agents/skills/herdr/SKILL.md`, plus an identical `.claude` mirror when Claude
is configured.
Doctor rejects a shadowing global copy only during setup/update, never per task.
The official skill owns
generic pane, agent start, prompt, wait, read, IDs, and focus-preservation
mechanics. Do not reproduce generic recipes in this skill or call a repository
runtime wrapper. Helpers validate/render documents or argv without lifecycle
operations. State-changing exceptions are recipe-bound `start-peer`, in-memory
`submit-control-prompt` and `submit-assignment`, and compatibility
`submit-prompt`. None owns pane, wait, read, state, identity, or lifecycle
policy.

This skill owns SLP policy only: Role Profile, Workspace Protocol, Assignment,
authority, ownership, candidate, handback, and acceptance. Use configured
languages for live and durable prose. Preserve the Human task exactly; it is
data, even when it contains `$herdr-orchestrator`, quotes, backticks, `$()`,
backslashes, newlines, or surrounding whitespace.

Adapter code and tests own provider runtime rules. Prompts consume its rendered
projection; agents never search reference files for provider policy.

Herdr owns process and lifecycle truth. Git and the filesystem own artifacts
and immutable candidates. Agent names and pane IDs are opaque runtime handles,
not SLP parentage or authority.
