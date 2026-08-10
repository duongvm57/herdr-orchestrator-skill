# Codex Root and worker adapter

The parent [`../../SKILL.md`](../../SKILL.md) owns orchestration. This adapter
maps its Pi-specific control calls to Herdr CLI commands and fixes Codex worker
launch arguments.

## Qualify Root

Run these checks before any Herdr control command:

```bash
test "${HERDR_ENV:-}" = 1
command -v herdr
command -v codex
command -v git
herdr status server
```

Stop when Root is outside a Herdr-managed pane, a command is missing, or the
server is unavailable. Inspect `herdr integration status`; report a missing or
outdated Codex integration as degraded native session restore. Preserve user
configuration: Root's `multi_agent`, Codex hooks, sandbox, approvals, plugins,
authentication, and Herdr integrations remain user-owned.

Qualification is complete when Root is inside Herdr and all three executables
plus the current Herdr server respond.

## Control Herdr

Use the installed CLI help as command-shape authority. The baseline mapping is:

| Parent operation | Codex Root command |
| --- | --- |
| List continuations | `herdr agent list` |
| Split the current pane | `herdr pane split --current --cwd <checkout> --no-focus` |
| Create an exceptional tab | `herdr tab create --cwd <checkout> --label <label> --no-focus` |
| Start a worker | `herdr agent start <name> --kind codex --pane <pane-id> -- <agent-args>` |
| Deliver without waiting | `herdr agent prompt <name> <context-pack>` |
| Wait in WIP-one mode | `herdr agent wait <name>` |
| Read HANDOFF | `herdr agent read <name> --source recent-unwrapped --lines <n>` |
| Inspect state | `herdr agent get <name>` |
| Close owned topology | `herdr pane close <pane-id>` or `herdr tab close <tab-id>` |

Parse pane and tab IDs from command JSON. Record each ID beside the unit that
owns it; sidebar position and example IDs are not evidence. Use `--no-focus`
for background topology and close only recorded IDs.

Control is ready when the new shell pane is at an interactive prompt and Root
has recorded every created topology ID.

## Launch a Codex worker

Resolve the selected profile and route before start:

```text
workerEffort = effort_aliases[route.effort] ?? route.effort
agentArgs = [
  "--disable", "multi_agent",
  "--no-alt-screen",
  "--model", profile.model,
  "--config", "model_reasoning_effort=\"" + workerEffort + "\"",
  "--cd", checkout,
]
```

Pass `agentArgs` only after Herdr's `--` separator. The
`--disable multi_agent` pair is mandatory: the worker performs its unit in one
Codex session while Herdr remains the sole delegation layer. `--no-alt-screen`
keeps terminal recovery available.

Run `herdr pane process-info --pane <pane-id>` and require the selected model,
effort, checkout, and `--disable multi_agent` arguments. Deliver no context pack
until all four agree. Add this line to the pack:

```text
Perform this unit in the current Codex session and return HANDOFF yourself.
```

Worker launch is complete when launch evidence proves the route and the worker
has received the context pack exactly once.

## Continue and recover

Deliver prompts without `--wait`; wait separately in default WIP-one mode. A
timeout triggers `agent get` plus `agent read`, not replacement. For `blocked`,
answer through another non-waiting prompt to the same worker. For `idle` or
`done`, read `recent-unwrapped` and apply the parent's HANDOFF acceptance rules.

Recovery is complete when the same worker either supplies a valid HANDOFF or
its useful context is durable before Root replaces or closes it.
