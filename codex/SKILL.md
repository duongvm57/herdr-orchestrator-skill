---
name: herdr-orchestrator
description: Continue one work unit in one named Herdr session from Codex Root.
---

# Herdr continuation from Codex

## Load the contract

1. Read [`../SKILL.md`](../SKILL.md) completely. It owns outcome selection,
   WIP, context packs, HANDOFF, acceptance, and cleanup.
2. Read [`../workers.toml`](../workers.toml) for `selection` and `routes`. Resolve
   the selected route's profile from [`profiles.toml`](profiles.toml), not from
   the parent file's Pi profiles.
3. Read [`references/codex.md`](references/codex.md). It replaces only the
   Pi-specific tool calls and runtime adapter named by the parent contract.

Loading is complete when one parent route resolves to one Codex profile and the
Codex adapter qualification gate passes.

## Apply the overlay

Use the parent workflow unchanged, with these substitutions:

- Perform every `herdr_layout`, `herdr_pane`, and `herdr_agent` operation
  through the equivalent Herdr CLI command in the Codex adapter.
- Read the Codex adapter where the parent asks for `references/pi.md`.
- Launch the continuation as `kind = "codex"` with the Codex profile and the
  parent route's effort. Apply an effort alias from `profiles.toml` when one is
  declared.
- Apply the same substitutions inside the parent's explicit parallel branch.

The overlay is active when all Herdr operations use the CLI adapter and every
continuation launch proves its Codex worker arguments before work is delivered.
