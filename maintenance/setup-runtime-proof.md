# Setup runtime authority proof

Date: 2026-08-25

Status: Slice 4 implementation evidence; not setup acceptance

## Bound proof artifact

`prove_candidate(candidate, current_discovery)` returns an immutable canonical
JSON receipt. The aggregate receipt binds the candidate digest, original and
current discovery digests, every configured role receipt, and each structured
native launch-spec digest. A discovery mismatch returns `STALE` before a native
command runs.

The proof engine never asks a model to exercise an authority boundary.
`MODEL_OBSERVED` checks are structurally unable to pass.

## Native runtime result

The live canary ran against `codex-cli 0.149.1` for all alpha roles:

```text
Lead        PROVEN
Engineer    PROVEN
Reviewer    PROVEN
Supervisor  PROVEN
```

Each role proved the following effects through its exact compiled permission
profile:

```text
read selected resources             ALLOWED
write selected writable resources   ALLOWED
write selected read-only resources  DENIED
read outside selected roots         DENIED
write outside selected roots        DENIED
network socket to local listener    DENIED
native Codex agents                 DISABLED
```

Filesystem and network effects are `RUNTIME_PROBED`. Native spawning is
`STATIC_PROVEN` from the structured launch setting plus the native
`agents.enabled=false` override. A nonzero command, malformed receipt, runner
failure, missing exact root, unexpected grant, or denial without a recognized
sandbox errno produces `SMOKE_FAILED`.

Host preflight verifies every target before sandbox execution and creates then
removes bounded canaries. The live run left no canary artifacts. The network
probe uses an engine-owned loopback listener and does not depend on external
internet availability.

## Scope boundary

This slice produces evidence only. It does not accept a candidate, publish
project configuration, change runtime `setup.md`, rank models, or claim that
setup is complete. Digest-bound Human acceptance and atomic publication remain
Slice 5.

Primary provider provenance:

- [OpenAI permission profiles](https://learn.chatgpt.com/docs/permissions)
- [OpenAI agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)
- [OpenAI Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
