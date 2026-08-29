# Candidate, review, and verdict

## Freeze an exact candidate

Prefer an exact Git commit when authority permits. Otherwise use an explicitly
frozen reproducible snapshot covering the accepted base, diff, untracked
artifacts, and generated artifacts. A digest of a mutable worktree, file list,
or working-tree description is not an identity. Freeze the candidate during
verification and review; every candidate mutation creates a new identity and
invalidates earlier verification and review.

The canonical snapshot document has `kind=frozen_snapshot`, an existing exact
`base_commit`, a canonical repository-relative `artifact_path`, and the
lowercase SHA-256 digest of that frozen artifact. The artifact is a materialized
bundle/manifest of the base, diff, untracked, and generated inputs—not a digest
of the mutable worktree. Before review, resolve it under the canonical project
root, read it, verify its digest, and verify the base commit exists. A Git
candidate uses `kind=git_commit` and an existing exact commit.

The Engineer proves writes. A fresh Reviewer falsifies the exact candidate when
the protocol or risk requires independence. Verification demonstrates observed
behavior; it does not accept the candidate.

## Decide with the owning authority

The Lead inspects the exact candidate, changed artifacts, verification,
independent findings, unresolved issues, residual risk, and applicable authority
before issuing the project verdict. Missing or stale evidence keeps the decision
open. Correctable findings return to the same Engineer before a new candidate is
reviewed.

Product, portfolio, irreversible, external-effect, publication, material-cost,
and protocol-change decisions remain Human-owned. A Supervisor recommendation
is observation evidence and has no project acceptance authority. Create durable
evidence only when the task or protocol requires it.
