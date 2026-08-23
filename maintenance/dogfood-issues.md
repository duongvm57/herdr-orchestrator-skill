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
