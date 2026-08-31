# Candidate, review, and verdict

## Freeze the exact candidate

Do not hand-construct a candidate identity and never use a working-tree hash,
`git diff` digest, file-hash list, or mutable path as one. Freeze the current
application artifact with the canonical helper:

```text
<adapter-runtime-bound-helper> freeze-candidate --project-root <root>
```

`<adapter-runtime-bound-helper>` is the exact command form in this Lead's
runtime-binding projection. Do not replace it with a bare helper invocation:
the form binds the observed Lead pane and the helper rejects a mismatched pane.

`freeze-candidate` atomically writes `.orchestration/current-candidate.json`, a
candidate-specific immutable diff, and a deterministic synthetic Git commit
whose parent is the exact base and whose tree is the candidate. Its identity is
the immutable Git tree plus the exact base commit; it uses a temporary Git
index and a candidate-owned private object directory under Git common metadata:
`$(git rev-parse --git-common-dir)/herdr-orchestrator/candidate-objects`.
This is outside every worktree and distinct from Git's normal object database,
so candidate objects never appear as application changes in `git status`. The
real repository object directory is a read-only Git alternate: new blobs and
trees never require a write to its `objects` directory. Every helper candidate
operation resolves through that same object-store environment. It never moves
`HEAD`, never stages the user's index, and restores known project-control paths
to their base state. The document records the bounded application scope and
exclusions. The freeze receipt contains the bounded exact base-to-tree diff path
and digest; inspect that artifact before verification, review, or
verdict. Missing or corrupt candidate object storage is a clear
candidate failure, never permission to inspect mutable worktree state. Any
application mutation requires a new freeze and invalidates earlier verification
and review.

For a preexisting candidate created by an older installed skill, validation can
read its former worktree-local store once. The next `freeze-candidate` copies
and verifies those immutable objects into Git common metadata, then removes the
legacy `.orchestration/candidate-objects` directory. Do not manually delete a
legacy store before this migration or a fresh successful freeze.
Project-control paths, including `skills-lock.json`, are excluded, so creating
candidate or acceptance evidence does not itself stale the application tree.

## Decide with the owning authority

The Lead inspects the exact candidate, changed artifacts, verification,
independent findings, unresolved issues, residual risk, and applicable authority
before issuing the project verdict. Missing or stale evidence keeps the decision
open. Correctable findings return to the same Engineer before a new candidate is
reviewed.

After inspecting the frozen candidate, run actual candidate-bound verification
and write `.orchestration/current-acceptance.json` with exactly these fields:
`schema_version`, `candidate`, `candidate_document_sha256`, `lead`,
`inspection`, `verification`, `unresolved_findings`, `residual_risk`, and
`review`. `inspection` and each nonempty `verification` item contain the exact
candidate, command, and observed result. `unresolved_findings` may be empty but
must be deliberately surfaced; `residual_risk` is always nonempty. `lead` is
the exact Lead identity with role `lead`.

`review.decision` is exactly `required` or `not_required`. The latter requires
a nonempty risk/protocol rationale. Required review adds project-relative
`assignment_path` and `handback_path`; the read-only Reviewer Assignment must
bind the exact candidate and its accepted semantic handback must be `COMPLETE`.
Reviewer remains conditional: obtain independent review only when
the applicable protocol or risk requires it.

The no-review form is:

```json
{
  "schema_version": 1,
  "candidate": {"kind": "git_tree", "base_commit": "<SHA>", "tree": "<SHA>"},
  "candidate_document_sha256": "<SHA-256>",
  "lead": {"role": "lead", "id": "<Lead>"},
  "inspection": {"candidate": {"kind": "git_tree", "base_commit": "<SHA>", "tree": "<SHA>"}, "command": "<command>", "result": "<result>"},
  "verification": [{"candidate": {"kind": "git_tree", "base_commit": "<SHA>", "tree": "<SHA>"}, "command": "<command>", "result": "<result>"}],
  "unresolved_findings": [],
  "residual_risk": "<risk>",
  "review": {"decision": "not_required", "rationale": "<protocol/risk rationale>"}
}
```

Before a Human-facing verdict, run:

```text
<adapter-runtime-bound-helper> validate-acceptance --project-root <root> \
  --lead-id <exact-lead-name>
```

An acceptance or Human-facing final verdict is prohibited until this validator
passes. It checks mechanical evidence; the Lead still decides project
acceptance. Passing tests does
not create a candidate or permit a verdict.

Product, portfolio, irreversible, external-effect, publication, material-cost,
and protocol-change decisions remain Human-owned. A Supervisor recommendation
is observation evidence and has no project acceptance authority. Create durable
evidence only when the task or protocol requires it.
