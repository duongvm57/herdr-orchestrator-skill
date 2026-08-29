# Current refactor acceptance record

Captured 2026-08-29T09:41:19+07:00 for the current dirty worktree. This is a
bounded static acceptance record for the refactor; it is not a Lead or Human
project verdict and does not claim live Herdr behavior.

## Provenance

- Repository/worktree: `/home/duongvm/projects/herdr-orchestrator`
- Branch: `main`
- Exact `HEAD`: `0fcf081ebaff1ef59af84ed68bb015b6da50782d`
  (`0fcf081 docs: update dogfood-issues`)
- Worktree: dirty. The tracked `HEAD` diff contains 45 changed paths, with
  5,323 insertions and 7,294 deletions.
- Tracked binary patch SHA-256 (`git diff --no-ext-diff --binary HEAD`):
  `b853b5bf4aca6607e2e8784381959d4f0a7ed01e4e1b76d812efc26019d31f54`
- Task-owned instruction entrypoint SHA-256: `AGENTS.md` =
  `5b6977484492b404f8f49f9d6e396b1dc27d0cdf40d2e8891fd023393d47f673`.

This record is an additional non-executable, untracked evidence document. It
does not alter the captured core-source patch above.

## Validation evidence

| Scope | Command | Result |
| --- | --- | --- |
| Focused core contracts | `python3 -m unittest -v tests.test_instruction_architecture tests.test_assignment_contract tests.test_herdr_orchestrator tests.test_package_flow tests.test_context_budget tests.test_coverage_manifest tests.test_repository_hygiene` | PASS — 45 tests, 5.065 s |
| Full static suite | `python3 -m unittest discover -s tests -v` | PASS — 86 tests, 8.519 s (final rerun) |
| Coverage maintenance gate | `python3 scripts/render_coverage.py --check` | PASS — manifest and generated document current |
| Context-budget maintenance gate | `python3 scripts/context_budget.py --check` | PASS — all measured routes within their limits |
| Tracked diff whitespace | `git diff --check` | PASS — no output / no errors |

The full suite includes deterministic/static tests around live-eval tooling; it
does not constitute a new live Herdr evaluation. No live eval was run in this
acceptance task. The manifest's live release-gate cases
`assignment-peer-handback-binding`, `prompt-correlation`,
`supervisor-routing`, `decomposition-independent`, and
`decomposition-coupled` were not executed.

After the two untracked task documents were added, `git diff --no-index --check
/dev/null` against each also emitted no whitespace diagnostics. Its exit status
of 1 is the expected "files differ" status for a no-index comparison.

## CI and residual evidence boundary

- CI outcome for this worktree/revision: **Unobserved**. The workflow exists,
  but no direct run result was available or inferred.
- Live Herdr/dogfood behavior: **Unobserved**. Full live release reliability
  is **NOT PROVEN** because the live release-gate cases were not executed.
- Human/Lead project acceptance, external effects, and runtime recovery:
  **Not proven** by these checks.
- The worktree remains uncommitted, so no immutable commit candidate or remote
  CI association is claimed.

## Verdict

**ACCEPTED for the bounded static repository-validation scope.** The focused
contracts, full static suite, maintenance gates, and tracked-diff check passed
for the provenance above. This verdict must not be read as a live-runtime,
CI, or SLP project-acceptance claim.
