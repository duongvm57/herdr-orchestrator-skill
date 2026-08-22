---
name: herdr-orchestrator
description: Set up or launch a Human-led, Lead-and-Peer project workflow through Herdr.
---

# Herdr Orchestrator

Run only when the current user message explicitly invokes `$herdr-orchestrator`.
Otherwise do not inspect, create, prompt, focus, wait for, or close Herdr agents.

The invoking session is the **Launcher**, never the Project Lead. For a project
task, create a fresh Lead, deliver the Human task and a role-specific context
pack, then focus the Human on that Lead. Herdr is the only agent control plane.
Spawned agents receive their instructions inline and never invoke this skill.

## Modes and required loads

Read each listed file completely before acting. Do not load other role manuals
unless a listed file explicitly requires their contents in a context pack.

| Mode | Required files | Trigger |
| --- | --- | --- |
| Setup or update | `references/setup.md`, `references/workspace-protocol.md`, `assets/config.toml`, `assets/workspace-protocol.md` | The Human asks to create, repair, or update project orchestration files |
| Launch | `references/launcher.md` | The Human gives a project task to orchestrate |
| Lead pack | `references/roles/lead.md`, `references/topology.md`, `references/anti-patterns.md`, `references/assignments-and-evidence.md`, `references/roles/peer.md`, project config, full project Workspace Protocol, Human task | Before starting every Lead |
| Peer pack | `references/roles/peer.md` plus one concrete disposition/assignment and only the relevant protocol constraints extracted by Lead | Before starting every Peer |
| Supervisor pack | `references/roles/supervisor.md`, `references/anti-patterns.md`, exact Lead binding, full project Workspace Protocol, evidence/notebook contract | Only after the Human explicitly requests a Supervisor |
| Maintenance audit | `references/orchestration-invariant-coverage.md` | Editing this package or auditing invariant ownership and behavioral coverage |

`README.md` is for humans, not a runtime instruction source.

## Invariants

Every agent context has three layers in this order:

1. **Role Profile** — durable identity and authority.
2. **Workspace Protocol** — repository tactics; only Lead and an explicitly
   requested Supervisor receive it in full.
3. **Assignment** — one run's objective, scope, authority, verification, and
   handoff.

The Lead owns project framing, topology, dependencies, integration,
verification, and the project verdict. The Lead creates Peers. A Supervisor is
fresh and independent, observes governance, and exists only on explicit Human
request. Reviewer, Supervisor, Architect council seats, and other independent
judgment sessions are fresh rather than forks. Corrections return to the same
Engineer session.

Treat `idle`, `done`, successful exit, and passing tests as attention signals.
Acceptance requires an exact stable candidate, inspected evidence, the required
independent review, and a decision by the role with authority. Human-only
product, cost, irreversible, external-effect, publication, and protocol-change
decisions remain with the Human.

Herdr supplies terminal/agent lifecycle truth. Git and the filesystem supply
workspace and artifact truth. This static skill does not claim semantic
parentage, authorization enforcement, queues, retries, schedules, or protocol
enforcement that Herdr does not provide.

## Completion gates

**Setup/update is complete** only when the new schema parses; both tracked
project files exist; every configured kind, executable, native argument, and
selected model is validated against live local capabilities; no credential is
stored; the protocol has all twelve required sections; the Human has reviewed
the diff; and no legacy schema was retained.

**Launch is complete** only when preflight passes without fallback, a fresh Lead
has the exact saved context pack, the launch event is recorded, the Lead has
received the task once, and focus has moved to the Lead. Existing agents,
panes, worktrees, and user-owned changes remain intact.

**Handoff is complete** only when the Human is interacting with the fresh Lead,
the Lead can locate its run evidence directory, and the Launcher reports the
Lead name, repository, run ID, and preserved pre-existing state. The Launcher
does not remain an orchestration proxy after focus transfer.
