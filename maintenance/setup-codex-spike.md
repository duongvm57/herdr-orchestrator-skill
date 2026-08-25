# Setup Codex authority spike

Date: 2026-08-25

Status: Slice 2 implementation evidence; not setup acceptance

## Observed runtime

- Executable status: detected and launchable
- Codex version: `0.149.1`
- Bundled model inventory: eight models with native reasoning-effort metadata
- Permission-profile minimum used by the adapter: `0.138.0`
- Profile assurance: `RUNTIME_PROBED`
- Network-denial assurance: `RUNTIME_PROBED`
- Native-agent control provenance: `STATIC_PROVEN`

The model inventory is used only to validate an exact Human binding. The probe
does not assign quality, price, speed, or role suitability.

## Deterministic receipt

The spike invoked the native `codex sandbox` primitive with a temporary custom
permission profile. It did not ask a model to exercise the boundary.

```text
read project file       ALLOWED
write evidence file     ALLOWED
write project file      DENIED
write outside scope     DENIED
read outside scope      DENIED
open network socket     DENIED
```

Codex installed through FNM also needed read access to its own resolved package
root. The adapter normalizes that prerequisite as
`fs.read(runtime:codex)`; it is visible in the selected effective envelope
rather than hidden in launch arguments.

## Compiler consequences

- Emit a custom permission profile through invocation-local config overrides.
- Emit no `--sandbox` or `--add-dir` compatibility approximation.
- Bind every filesystem rule to the exact runtime resource path.
- Require writable resources to contain both normalized read and write atoms.
- Require the launch `cwd` to be covered by selected filesystem authority.
- Disable native Codex agents explicitly.
- Reject network grants in this alpha; compile network denial only.
- Return structured `STATIC_INVALID` or `CAPABILITY_INVALID` rejections.

Primary provenance:

- [OpenAI permission profiles](https://learn.chatgpt.com/docs/permissions)
- [OpenAI Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [OpenAI agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)
