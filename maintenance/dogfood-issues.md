# Dogfood issues

This maintenance log records failures observed in real orchestration runs. It
is not shipped in the installable skill and does not define runtime behavior.

## HD-001: Lead cannot write run evidence under the Git common directory

- Status: Fixed and regression-tested
- Observed: 2026-08-24
- Run: `discord-message-tool-20260824-015422-8968`
- Environment: `ancient-discord-dogfood`; Codex Lead with `workspace-write`
- Evidence: the Lead could read
  `<git-common-dir>/herdr-orchestrator/runs/<run-id>/` but a bounded
  writability check returned `writable=no`. It wrote the Human decision request
  to `/tmp` and could not append the semantic ledger.
- Configuration evidence: the generated Lead recipe enabled
  `workspace-write` but omitted the documented
  `--add-dir <absolute-git-common-dir>` permission.
- Impact: after Launcher handoff, the designated ledger owner cannot persist
  reports or later ledger events in the authoritative evidence root.
- Correction: setup and preflight prove the exact Lead recipe can
  write a disposable canary in the resolved Git common directory. A recipe
  that cannot pass is corrected or rejected before launch. Static project
  validation and `init-run` also reject a Codex `workspace-write` Lead whose
  native args omit the exact Git common directory.
- Verification: the original `ancient-discord` config now fails
  `validate-project --git-common-dir ...` with the exact missing-boundary error;
  the corrected recipe passes the regression test.

## HD-002: Launcher derived the wrong run-local Human-task path

- Status: Fixed and regression-tested
- Observed: 2026-08-24
- Run: `discord-message-tool-20260824-015422-8968`
- Evidence: the first Lead-pack attempt passed
  `<run>/context/human-task.md` and failed with `assignment source is not a
  readable file`; `init-run` had saved the file at `<run>/human-task.md`. The
  transcript confirms argv contained no literal quote characters; quotes in
  the exception were Python representation syntax.
- Impact: launch performs avoidable recovery work and risks diverging from the
  intended saved task source.
- Correction: `init-run` returns the canonical Human-task path and digest in
  compact metadata. Task launch consumes that returned path without deriving
  it, and the documented run tree includes the root-level file.
- Verification: `init-run` metadata is asserted to bind the exact root-level
  path, byte count, and digest; the task-launch contract is tested against that
  returned field.

## HD-003: Codex Lead could not initialize approval-gated MCP tools

- Status: Mitigated in dogfood; follow-up validation pending
- Observed: 2026-08-27
- Run: dogfood orchestration session
- Evidence: Lead and Peer showed `MCP startup interrupted`; an external MCP call
  returned `MCP tool call requires approval, but approval policy is never`.
  The same MCP successfully completed under an approval-capable Codex smoke
  session, proving discovery/credentials were not the cause.
- Cause: the dogfood Codex Lead and Peer recipes configured
  `--ask-for-approval never`, which is incompatible with the approval required
  by an approval-gated MCP connector.
- Correction: change Lead and Peer dogfood recipes to
  `--ask-for-approval on-request`; recreate the Lead session because approval
  policy is fixed at process startup.
- Residual risk: MCP calls may pause for Human approval in the panel; this is
  intentional and must be exercised in the restarted session.

## HD-004: Runtime prompt wait raced with completed Peer handback

- Status: Observed; no code change yet
- Observed: 2026-08-27
- Run: dogfood orchestration session
- Evidence: `herdr_runtime.py prompt --wait` returned a Herdr timeout while
  the Lead remained active; the prompt was delivered and the Lead subsequently
  read the completed Peer handback successfully.
- Impact: the Launcher/Lead sees a false delivery failure and may retry a
  prompt that was already accepted, risking duplicate instructions.
- Likely boundary: the runtime waits for an agent-status transition even when
  the prompt has been accepted and the agent is processing it; this needs a
  deterministic prompt-delivery versus completion contract.
- Follow-up: reproduce with a settled/near-settled Peer and add a regression
  test before changing wait semantics.

## HD-005: Lead forwarded multiple tasks without sufficient decomposition

- Status: Observed; no code change yet
- Observed: 2026-08-27
- Run: dogfood orchestration session
- Evidence: the Lead's Peer prompt contained four separate task scopes, then
  one Peer investigated and implemented the only currently actionable item.
- Impact: the Lead added little decomposition value; the Peer had to classify
  the scopes instead of receiving one bounded assignment with an explicit
  effort, dependency, and topology rationale.
- Likely boundary: the Lead recognized multiple scopes but did not first
  evaluate their size, independence, dependencies, or whether one Peer was
  actually the smallest useful topology.
- Follow-up: require the Lead to record that evaluation and rationale before
  assigning work. Splitting is optional; forwarding the original multi-task
  request without a bounded rationale is the friction.
