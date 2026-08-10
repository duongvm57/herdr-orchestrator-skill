# Herdr orchestrator runtime notes

Human-facing runtime and dependency notes for the repository-local
`herdr-orchestrator` skill. This README is intentionally not linked from
`SKILL.md` or its agent references, so normal skill execution does not load it.

## Runtime layers

The workflow has three independent layers:

1. **Herdr control plane** — creates tabs and panes, starts coding agents,
   submits prompts, waits, reads output, focuses sessions, and closes panes.
2. **Root control adapter** — exposes those Herdr operations to whichever
   coding-agent CLI is running Root.
3. **Continuation CLI** — the route-selected coding agent that performs the
   delegated work.

A dependency in one layer does not become a requirement for every other layer.
In particular, a Pi control adapter does not make Pi the only continuation CLI.

## Required capabilities

| Capability | Current provider |
| --- | --- |
| Herdr workspace, pane, agent, and worktree control | [Herdr](https://herdr.dev) |
| Typed `herdr_layout`, `herdr_pane`, and `herdr_agent` tools in a Pi Root | `@ogulcancelik/pi-herdr` |
| Repository state and explicit parallel worktrees | Git |
| Continuation process | The coding-agent CLI selected by `workers.toml` |

`@ogulcancelik/pi-herdr` is a Pi-specific Root adapter. It is not built into Pi
or Herdr, and it is not required merely because a continuation worker uses a
different supported CLI. Pi currently loads it from:

```text
~/.pi/agent/settings.json        npm:@ogulcancelik/pi-herdr
~/.pi/agent/npm/package.json     @ogulcancelik/pi-herdr
```

Its upstream source is
[`ogulcancelik/pi-extensions/packages/pi-herdr`](https://github.com/ogulcancelik/pi-extensions/tree/main/packages/pi-herdr).
The skill never edits installed files under `~/.pi/agent/npm/node_modules/`.

A non-Pi Root needs an equivalent accepted control adapter exposing the Herdr
capabilities used by `SKILL.md`. This repository currently includes only the Pi
runtime adapter in `references/pi.md`.

## Continuation coding-agent CLIs

Herdr `0.8.0` currently advertises these agent kinds:

```text
pi, claude, codex, gemini, cursor, devin, agy, cline, omp,
mastracode, opencode, copilot, kimi, kiro, droid, amp, grok,
hermes, kilo, qodercli, maki
```

Recognition by Herdr is not installation or configuration. A selected kind also
needs:

- its canonical executable installed and authenticated;
- a `workers.toml` profile selecting that kind, model, and effort; and
- an accepted runtime adapter defining launch arguments and transport behavior.

The bundled `workers.toml` currently selects `kind = "pi"` for all profiles, so
the checked-in configuration launches Pi continuations today. Supporting
another CLI is a profile-and-adapter change, not a rewrite of the orchestration
contract.

## Optional integrations

| Integration | Scope |
| --- | --- |
| `pi-intercom` | Optional direct clarification or HANDOFF delivery between already-connected Pi sessions |
| Attention Broker | Optional attention delivery when explicit parallel sessions are active |

Herdr prompt, wait, and read operations are the baseline. Optional integrations
do not own routing, work state, or acceptance.

## Explicit parallel work

Parallel mode loads only after the user explicitly requests it. Each writer uses
an isolated Git branch and worktree; read-only sessions may share a checkout.
Parallel mode adds no coding-agent package requirement: every unit uses its own
route-selected Herdr agent kind.

When Attention Broker and runtime-specific messaging are absent, Root uses
nonblocking Herdr status/read operations rather than waiting on one of several
sessions.

## Observed local versions

These are observations of the current machine, not minimum-version promises:

| Component | Version |
| --- | --- |
| Herdr | `0.8.0` |
| Pi coding agent | `0.84.1` |
| `@ogulcancelik/pi-herdr` | `0.4.0` |
| Git | `2.43.0` |

## Local skill files

```text
.pi/skills/herdr-orchestrator/SKILL.md
.pi/skills/herdr-orchestrator/workers.toml
.pi/skills/herdr-orchestrator/references/pi.md
.pi/skills/herdr-orchestrator/references/parallel.md
```

Runtime handoff artifacts live under `.pi/herdr/`, ignored by this repository's
`.gitignore`.

## Inspection commands

```bash
herdr --version
herdr agent start --help
git --version
grep -n 'pi-herdr' ~/.pi/agent/settings.json ~/.pi/agent/npm/package.json
```
