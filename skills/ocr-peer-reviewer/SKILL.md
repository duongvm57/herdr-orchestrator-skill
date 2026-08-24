---
name: ocr-peer-reviewer
description: Run a read-only peer review of an exact Git commit with OpenCodeReview delegation. Use when a Reviewer Assignment identifies an accepted Git base and exact Git candidate; OCR selects files and resolves rules while the host agent performs the reasoning.
license: MIT
---

# OCR Peer Reviewer

Review one exact candidate as an independent, read-only Peer. OCR supplies file
selection, exclusions, and review rules; you inspect the diff and repository
context, reason about defects, and return findings. You do not own project
acceptance.

## Preconditions

Read the repository, accepted base, exact candidate identity, and report
contract from the surrounding Herdr Assignment. OCR applies only when both
identities resolve to Git commits. Verify:

```text
git rev-parse HEAD
git status --porcelain
git rev-parse <accepted-base>^{commit}
git rev-parse <exact-candidate>^{commit}
ocr version
```

Observed `HEAD` must equal the full candidate SHA and the workspace must be
clean. Preserve the workspace: do not edit, apply fixes, checkout, reset,
rebase, commit, push, merge, or deploy.

If `ocr` or its delegation commands are unavailable, return
`OCR_SKILL_SKIPPED: OCR_UNAVAILABLE` to the surrounding Reviewer workflow. This
is a request to continue with direct review, not a failed review or project
blocker.

If either Assignment identity is absent or is not a Git commit, return
`OCR_SKILL_SKIPPED: NON_GIT_CANDIDATE` for the same direct-review fallback.

## Delegate deterministic preparation

Run OCR in exact range mode and save the full JSON outputs outside the
candidate:

```text
ocr delegate preview --format json --repo <repo> --from <accepted-base> --to <exact-candidate>
ocr delegate rule --format json --repo <repo> --from <accepted-base> --to <exact-candidate> -- <selected-paths>
```

Require preview mode `range`, matching `from`/`to`, and a `merge_base` equal to
`git merge-base <accepted-base> <exact-candidate>`. Use only `reviewable_files`
as the review set. Preserve every `excluded_files` entry and its reason. Require
rule output to map every selected path; unsupported or incomplete JSON returns
`OCR_SKILL_SKIPPED: OCR_OUTPUT_UNSUPPORTED` so the surrounding workflow can
perform direct review.

## Review every selected file

Create a checklist keyed by `(path,status)`. Every entry ends as `reviewed` or
`skipped:<concrete reason>`. For each selected path:

1. Read `git diff <merge-base>..<exact-candidate> -- <path>`.
2. Apply its resolved OCR rule as a checklist.
3. Inspect relevant callers, contracts, tests, and repository instructions.
4. Check correctness, error paths, security, performance, compatibility, and
   missing regression proof.

Continue after finding a serious issue. A rule is not evidence of a defect.
Discard speculative findings and style noise.

Before reporting, rerun `git rev-parse HEAD` and `git status --porcelain`. A
changed candidate or dirty workspace invalidates the OCR review and must be
reported to the surrounding Reviewer workflow.

## Return evidence

Each finding includes path, lines, category, severity, concrete evidence,
impact, and suggested correction. Use `critical`, `high`, `medium`, or `low`;
report low severity only when clearly useful.

Merge the evidence into the surrounding Herdr report schema instead of adding
a second review schema:

- Under **Artifacts and exact candidate**, record the accepted base, assigned
  candidate, observed `HEAD`, merge base, and OCR version.
- Under **Verification commands, cwd, and results**, record the OCR commands
  and final clean-workspace check.
- Under **Findings, assumptions, and residual risks**, record discovered,
  reviewable, excluded, reviewed, and skipped counts; coverage rate; excluded
  and skipped paths with reasons; findings; and review limitations.
- Use the existing Reviewer outcome `APPROVE` or `FINDINGS` and the existing
  **Decision needed from Lead** section.

Incomplete coverage or a changed workspace cannot produce `APPROVE`. A
recommendation informs the surrounding Lead or reviewer workflow; never output
project-level `ACCEPTED`, `MERGE`, or `READY TO MERGE` authority.
