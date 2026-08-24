---
name: ocr-peer-reviewer
description: Run a read-only peer review of an exact Git commit with OpenCodeReview delegation. Use when a Reviewer Assignment identifies an accepted Git base and exact Git candidate; OCR selects files and resolves rules while the host agent performs the reasoning.
license: Apache-2.0
---

<!--
Adapted from Alibaba OpenCodeReview's open-code-review-delegate skill under
Apache-2.0. Modified for Herdr exact-candidate, evidence, fallback, and authority
contracts. See LICENSE and NOTICE in this skill directory.
-->

# OCR Peer Reviewer

Review one exact candidate as an independent, read-only Peer. OCR supplies file
selection, exclusions, and review rules; you inspect the diff and repository
context, reason about defects, and return findings. Project acceptance remains
with the surrounding Lead.

## Bind the candidate and evidence root

Read the repository, accepted base, exact candidate, report-return path, and
report contract from the Herdr Assignment. Let `<inbox>` be the parent directory
of that report-return path. For a project-read-only Reviewer, `<inbox>/ocr/` is
the only writable OCR evidence directory; the candidate remains read-only.

OCR applies only when both identities resolve to Git commits. Resolve full SHAs
and verify:

```text
git rev-parse HEAD
git status --porcelain
git rev-parse <accepted-base>^{commit}
git rev-parse <exact-candidate>^{commit}
ocr version
```

Observed `HEAD` must equal the full candidate SHA and the workspace must be
clean. Preserve the candidate: write only evidence under `<inbox>/ocr/`; do not
edit, apply fixes, checkout, reset, rebase, commit, push, merge, or deploy.

If either Assignment identity is absent or is not a Git commit, return
`OCR_SKILL_SKIPPED: NON_GIT_CANDIDATE`. If `ocr` or either delegation command is
unavailable, return `OCR_SKILL_SKIPPED: OCR_UNAVAILABLE`. Both statuses require
the surrounding Reviewer to continue with direct exact-candidate review.

## Save deterministic preparation

Create `<inbox>/ocr/`. Capture complete stdout through sibling partial files,
then atomically rename successful JSON results to these durable paths:

```text
<inbox>/ocr/preview.json
<inbox>/ocr/rules.json
```

Run preview with the resolved full SHAs:

```text
ocr delegate preview --format json --repo <repo> --from <accepted-base-sha> --to <exact-candidate-sha>
```

Require schema version `1`, mode `range`, matching `from` and `to`, and a
`merge_base` equal to the output of:

```text
git merge-base <accepted-base-sha> <exact-candidate-sha>
```

Preserve every `excluded_files` entry and its reason. Use only
`reviewable_files` as the OCR review set.

If the review set is nonempty, resolve rules by path, independent of the Git
range:

```text
ocr delegate rule --format json --repo <repo> -- <selected-paths>
```

Require schema version `1` and rule groups that account for every selected
path. After each final rename, compute SHA-256 over the exact artifact bytes.
An unsuccessful command, invalid JSON, unsupported schema, mismatched range, or
incomplete path mapping returns `OCR_SKILL_SKIPPED: OCR_OUTPUT_UNSUPPORTED` with
any available diagnostic artifact path. The surrounding Reviewer then performs
direct review; unsupported OCR output is not review evidence.

If `reviewable_files` is empty, preserve and hash `preview.json`, do not invoke
`rule`, and return `OCR_SKILL_SKIPPED: NO_REVIEWABLE_FILES`. The surrounding
Reviewer directly inspects the exact candidate and every exclusion rationale
when feasible, and records the preview path, digest, and exclusions. It may
`APPROVE` only from a complete direct review, never from zero-of-zero OCR
coverage; otherwise it returns the limitation to the Lead.

## Review every selected file

Create a checklist keyed by `(path,status)`. Every entry ends as `reviewed` or
`skipped:<concrete reason>`. For each selected path:

1. Read `git diff <merge-base>..<exact-candidate-sha> -- <path>`.
2. Apply its resolved OCR rule as a checklist.
3. Inspect relevant callers, contracts, tests, and repository instructions.
4. Check correctness, error paths, security, performance, compatibility, and
   missing regression proof.

Continue after finding a serious issue. A rule is not evidence of a defect.
Discard speculative findings and style noise.

Before reporting, rerun `git rev-parse HEAD` and `git status --porcelain`. A
changed candidate or dirty workspace invalidates the review: report `BLOCKED`
with `OCR status: CANDIDATE_CHANGED` instead of an approval disposition.

## Return evidence

Each finding includes path, lines, category, severity, concrete evidence,
impact, and suggested correction. Use `critical`, `high`, `medium`, or `low`;
report low severity only when clearly useful.

Merge evidence into the surrounding Herdr report schema. For a completed OCR
review, use this exact procedure receipt under **Findings, assumptions, and
residual risks**:

```text
Review procedure: ocr-delegate
OCR status: USED
```

- Under **Artifacts and exact candidate**, record the accepted base, candidate,
  observed `HEAD`, merge base, OCR version, both OCR artifact paths, and each
  artifact SHA-256.
- Under **Verification commands, cwd, and results**, record the OCR commands and
  final clean-workspace check.
- Under **Findings, assumptions, and residual risks**, record discovered,
  reviewable, excluded, reviewed, and skipped counts; coverage rate; excluded
  and skipped paths with reasons; findings; and review limitations.
- Use only the existing Reviewer outcome `APPROVE` or `FINDINGS` and the existing
  **Decision needed from Lead** section.

Any skipped selected file makes coverage incomplete and prevents `APPROVE`.
The review informs the Lead; never output project-level `ACCEPTED`, `MERGE`, or
`READY TO MERGE` authority.
