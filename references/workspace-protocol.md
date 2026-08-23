# Workspace Protocol authoring

The Workspace Protocol is the repository-specific tactical contract interpreted
by the Project Lead. The Lead always receives it in full. A Supervisor receives
it only for an explicit audit/update/observation assignment. A Peer never reads
it; the Lead extracts only constraints relevant to that Peer assignment.

Use `assets/workspace-protocol.md` as the tracked template. Complete all twelve
sections:

1. status, Human owner, version, review date, canonical absolute Repository
   root, readers, live orchestration language, and durable Markdown artifact
   language;
2. criticality, risk classes, costly reversals, external effects, and budget;
3. Lead decisions; edit/commit/push/deploy/publish authority; scope expansion;
   reserved architecture contracts; Human-only boundaries; prohibited effects;
4. task classes mapped to the smallest useful topology;
5. per-Assignment Peer recipe selection, reuse/mixing, and native
   availability/no-fallback principle;
6. fresh Architect, Reviewer, sealed council, and same-Engineer correction gates;
7. one writer, concurrent-worktree isolation, resources, handback, integration;
8. allowed stable-candidate identities and candidate invalidation;
9. verification by risk, minimum verdict evidence, independent falsification,
   Human evidence, and residual risk;
10. `REOPEN_REQUEST`, `DEPENDENCY_REQUEST`, and `BLOCKED` handling;
11. project-specific anti-pattern hypotheses, Supervisor observation
   retention/export policy, and project-read/notebook-write boundary;
12. versioned evolution, review triggers, repeated causal evidence, Human approval.

Keep global role identity in role profiles and one-run details in assignments.
Keep model IDs and native flags in config. Keep secrets out of both files. Avoid
task-specific path lists, guessed fallback models, topology ceremony for every
task, or authority that the Human did not grant.

Protocol candidates come from repeated causal evidence, not a single
Supervisor verdict. Material authority or workflow changes are applied only in
a later explicit setup/update invocation, shown as a tracked diff, and approved
by the Human. Until then, the Supervisor notebook remains evidence only.

The protocol is ready when a Lead can classify a task, choose topology and a
configured recipe independently for each Peer Assignment, assign one writer,
identify a stable candidate and proof gate, handle all three escalation
requests, and tell which remaining decision belongs to the Human without
guessing.
