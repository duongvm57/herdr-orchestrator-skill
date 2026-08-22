# Project setup and update

Read this file only for setup or update. The result is exactly two tracked
project files: `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`.

## 1. Preserve and discover

Resolve the Git repository root and inspect status, existing worktrees, current
agents/panes, and both destination paths. Preserve user-owned changes. If a
destination already exists, treat it as user data: propose a diff and update it
in place only after understanding its current intent.

Read live command authority before choosing recipes:

```text
herdr --help
herdr agent start --help
<chosen-harness> --help
```

Require `git`, `herdr`, every configured harness executable, and a reachable
Herdr server. Derive accepted `kind` values from the installed
`herdr agent start --help`, not this package. Use a harness-native model catalog
or picker when it has one. Otherwise validate the exact model with that
harness's documented local mechanism or a bounded smoke launch approved for any
material cost. Never infer availability from an old config or silently replace
an unavailable selection.

Ask the Human in plain language for:

- the reasoning/cost preference for the Lead;
- the default ordinary implementation preference;
- which genuinely distinct task classes need another Peer route;
- whether a Supervisor recipe should be configured; and
- project risk, review, external-effect, and Human-only boundaries.

Translate those answers into each harness's current native arguments. Do not
invent a shared effort vocabulary. Do not store API keys, tokens, credential
paths, environment values, or secret-bearing arguments.

For every role, inspect the harness's current agent-spawn facilities and add its
native flags/tool exclusions to disable them. The Lead creates Peers by issuing
Herdr commands itself; a native subagent tree would create a second control
plane. Validate the actual installed feature/tool names instead of copying the
asset examples. Treat this as behavior shaping, not a claim that prompts or CLI
flags provide process, filesystem, identity, or authorization isolation.

Discovery is complete when every proposed recipe names an installed Herdr kind,
an installed executable, native arguments accepted by current help, and a model
proven available on this machine.

## 2. Write the config

Copy `assets/config.toml` to
`.orchestration/herdr-orchestrator.toml`, then replace every example and
placeholder. The accepted schema is:

```toml
version = 1
default_peer = "general"

[lead]
kind = "codex"
args = ["--model", "model-id", "--config", "model_reasoning_effort=\"high\"", "--disable", "multi_agent"]

[supervisor] # optional; configuration is not launch authority
kind = "claude"
args = ["--model", "model-id", "--effort", "medium"]

[peer.general]
kind = "codex"
args = ["--model", "model-id", "--config", "model_reasoning_effort=\"medium\"", "--disable", "multi_agent"]
```

Each `[peer.<route>]` is a complete launch recipe. Route names are local to the
project. `default_peer` must resolve to one peer table. `kind` and every `args`
element are passed unchanged to `herdr agent start`; no adapter, profile lookup,
effort translation, fallback, or inherited route exists.

Reject every top-level key except `version`, `default_peer`, `lead`, optional
`supervisor`, and `peer`, and reject indirection from any recipe to another
table or file. Create this schema from live answers rather than translating an
older project configuration. Package-level legacy files are not project inputs.

Config writing is complete when TOML parsing and strict schema checks succeed,
all placeholders are gone, and each recipe independently passes discovery.

## 3. Write the protocol

Read `references/workspace-protocol.md`, copy
`assets/workspace-protocol.md`, and interview the Human only for project facts
that cannot be discovered. Fill all twelve numbered sections. Describe which
task class selects each configured Peer route; keep model IDs and native flags
in TOML. The protocol contains tactics and decision boundaries, never secrets,
task-specific file lists, or global role manuals.

Protocol writing is complete when every section has a concrete project answer,
the default route exists, independent-review triggers are decidable, one-writer
and stable-candidate rules are explicit, and the Human-only boundary is clear.

## 4. Validate and review

Parse TOML with the standard library or equivalent and check the schema, not
only syntax. Re-run live availability checks for every final entry. Check that
the project diff contains only the intended two files and no credential-like
value. Present the diff and unresolved assumptions to the Human.

Do not start a Lead as a side effect of setup unless the same explicit Human
request also includes a task to launch. Setup/update completes at the gate in
`SKILL.md`.
