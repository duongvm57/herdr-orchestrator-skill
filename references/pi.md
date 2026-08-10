# Pi continuation adapter

Read this adapter when Root or the continuation runs Pi. The parent
[`SKILL.md`](../SKILL.md) owns outcome selection, WIP, HANDOFF, and acceptance;
this adapter owns Pi launch and optional direct transport.

## Launch arguments

Use the Herdr session name as Pi's display name:

```text
excluded = [
  "herdr_layout",
  "herdr_pane",
  "herdr_agent",
  "ask_user_question",
]
if an agent-spawn tool is installed:
  excluded += [its actual tool name]

agentArgs = [
  "--name", continuation_name,
  "--model", profile.model,
  "--thinking", route.effort,
  "--exclude-tools", excluded.join(","),
]
```

Pass every argument explicitly. The continuation receives no
session-management, interactive-question, or installed agent-spawn tool. Any
other Pi launch option requires accepted configuration; CLI defaults are not
authority.

## Herdr transport

1. Start Pi with `herdr_agent` action `start`, the prepared `pane`,
   `name: continuation_name`, the resolved `kind`, and `agentArgs`.
2. Start or resume work with `herdr_agent` action `prompt` and `wait: false`.
3. In WIP-one mode, wait with `herdr_agent` action `wait`. Parallel mode uses
   its disclosed attention policy instead of a pane-specific wait.
4. After settlement, read `recent-unwrapped` and require HANDOFF before deciding.

An `idle` or `done` lifecycle state requests Root attention; repository evidence
determines acceptance.

## Optional intercom

Pi-intercom may carry clarification or a complete HANDOFF when both sessions
already have it enabled. It optimizes transport only; Herdr remains the recovery
channel.

Before the first intercom call, read its installed skill and call
`intercom status`. Use asynchronous `send` while work is dispatched. A complete
direct HANDOFF is canonical; a notification pointing elsewhere is not.

Use the existing session identities. Configure no session, rename no session,
and open no session merely to enable intercom.
