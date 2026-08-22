# Topology selection

Choose the smallest topology that can change the decision or supply required
evidence. Agent count is not confidence. Before dispatch, map each moving scope
to exactly one writer and each decision/evidence boundary to one owner.

## Tiny task

```text
Lead → one Engineer or Lead-local tightly coupled work → focused checks → Lead inspect
```

Use Lead-local work only when the protocol permits it and separation of
judgment adds no meaningful protection. The Lead still identifies an exact
candidate and evidence.

## Bounded implementation

```text
Lead → Engineer → stable candidate → optional fresh Reviewer → Lead verdict
```

Use one Engineer for a known bounded scope. Add a Reviewer only when protocol or
risk requires independent falsification.

## Architecture-sensitive vertical slice

```text
Lead
  → fresh Architect (read-only, neutral problem)
  → binding Lead design decision
  → Engineer (one moving scope)
  → fresh Reviewer (exact candidate)
  → correction in the same Engineer
  → new stable candidate and review
  → Lead verdict
```

The Architect reports ownership, lifecycle, alternatives, strongest
counterargument, and reversal conditions. It does not write the implementation.

## Difficult council

```text
Lead
  ├── fresh sealed seat A: ownership/lifecycle/alternatives
  └── fresh sealed seat B: failure/falsification/migration
sealed reports → material propositions → decision-changing verification → one verdict
```

Each seat needs a distinct mandate and may not read another seat's conclusion
before reporting. The Lead extracts three to five material propositions, checks
only claims that could change the decision, permits at most one scoped
challenge/response per proposition, then binds one verdict. A council is not a
vote and provider plurality does not grant authority.

## Multiple projects

```text
Human
  ├── explicitly requested Supervisor observing governance
  ├── Lead A → Peers → evidence A
  └── Lead B → Peers → evidence B
```

Every Lead retains authority only for its project. Cross-project observation
does not let a Supervisor accept either project or reuse one project's evidence
for another.

## Ownership and workspaces

Read-only agents may share a checkout. One moving write scope has one writer.
Concurrent writers require non-overlapping ownership and separate Git
worktrees, branches, exclusive resources, artifact paths, and verification.
Record the base and integration owner before start. The Lead alone creates,
hands back, integrates, and removes worktrees it owns; pre-existing worktrees
remain untouched.

Review starts only after the writer identifies a stable candidate: an exact
commit, or a deterministic base/diff/artifact digest when commit authority is
absent. A changed candidate invalidates its earlier review.
