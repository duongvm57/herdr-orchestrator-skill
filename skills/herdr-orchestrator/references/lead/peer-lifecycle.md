# Peer dispatch and results

Use one bounded task with an exact configured Peer profile and only the
applicable Workspace Protocol constraints. The task identifies the objective,
owned and excluded scope, authority boundary, dependencies, verification, and
the decision the result informs. Keep independent judgment neutral: supply
facts and open questions without a preferred conclusion.

Choose the disposition independently from the profile:

- **Engineer:** owns one writable moving scope, preserves unrelated work,
  verifies changes, and does not self-accept difficult work.
- **Architect:** read-only; analyzes ownership, lifecycle, alternatives,
  counterarguments, and reversal conditions.
- **Reviewer:** fresh and read-only; attempts to falsify one exact candidate and
  returns severity findings plus `APPROVE` or `FINDINGS`. OCR is optional; direct
  review remains the fallback.
- **Other bounded Peer:** receives only the question, evidence boundary,
  exclusions, and decision it informs.

Construct the canonical Assignment first, validate it, and render it with the
selected Peer profile plus a bounded applicable-protocol projection. The
projection contains only task-relevant constraints; never pass the full
`WORKSPACE_PROTOCOL.md` to a Peer renderer. Submit the rendered result through
the official Herdr skill to start, prompt, wait, and read the Peer. Prompt
submission and lifecycle settle are not Assignment completion: active Lead
collection inspects output and accepts only a structured handback with the
matching `assignment_id`. The outcome is exactly `COMPLETE`, `REOPEN_REQUEST`,
`DEPENDENCY_REQUEST`, or `BLOCKED`. A detached Lead is not automatically woken.
On timeout or stall inspect the current state/output before any explicit
follow-up; never blind-resend.

Choose the distinct Peer name before constructing its Assignment. Preserve that
same exact name in `owner`, the native Peer start/prompt target, the structured
handback binding, and any evidence index. The delegating Lead's name belongs
only in `parent.id`; it is never a Peer or Supervisor entry.

A handback is a JSON object with exactly `assignment_id`, `outcome`,
`evidence`, `impact`, and `need`; each is a non-empty string. Validate that
object against its exact Assignment before routing it.

Use the canonical helper only for these contract boundaries, never for Herdr
lifecycle control:

```text
python3 scripts/herdr_orchestrator.py validate-assignment --assignment <assignment.json>
python3 scripts/herdr_orchestrator.py render-assignment --assignment <assignment.json> \
  --role-profile <peer-profile.md> --applicable-protocol <bounded-constraints.md> \
  --output <rendered-prompt.md>
python3 scripts/herdr_orchestrator.py validate-delegation --assignment <active-peer.json> \
  --assignment <new-peer.json>
python3 scripts/herdr_orchestrator.py validate-review --assignment <reviewer.json> \
  --current-candidate <current-candidate.json> --project-root <root>
python3 scripts/herdr_orchestrator.py validate-handback --assignment <peer.json> \
  --handback <handback.json>
```

Then pass the rendered prompt as one direct Herdr prompt value. Keep the
Assignment as the inspectable source; do not reconstruct it from prose.
It is a Peer-only handoff contract, with this directly usable shape:

```json
{
  "schema_version": 1,
  "assignment_id": "<stable-id>",
  "role": "peer",
  "parent": {"role": "lead", "id": "<lead-id>"},
  "owner": "<peer-id>",
  "objective": "<bounded outcome>",
  "owned_scope": ["path:<project-relative-path>"],
  "exclusions": ["<out-of-scope constraint>"],
  "authority": "write|read-only",
  "disposition": "Engineer|Reviewer|Architect|<bounded role>",
  "recipe": "<configured-peer-recipe>",
  "verification": ["<required check>"],
  "dependencies": ["<known dependency>"],
  "languages": {"live": "<configured>", "artifact": "<configured>"},
  "topology_rationale": null,
  "candidate": null
}
```

`parent.id` identifies the Lead that delegated the work. `owner` identifies the
named Peer that owns the bounded technical outcome and, for `authority: write`,
the moving write scope. They must not be inferred from pane layout or agent
adjacency.

Set `topology_rationale` only for a meaningful multi-scope or nontrivial
topology decision. A Reviewer candidate is an immutable document: either
`{"kind":"git_commit","value":"<40-char commit>"}` or a frozen snapshot
with `base_commit`, `artifact_path`, and `sha256`. Write the same full document
to `current-candidate.json`; never compare a snapshot to only its base commit.
Before a new writer launch, use `validate-delegation` against the active Peer
Assignments. Before accepting a review, use `validate-review` against that full
current-candidate document. Before routing any Peer result, use
`validate-handback` and then make the semantic decision yourself.

Keep inline handback bounded. A durable evidence file is required only when the
task needs one or normal read cannot recover large evidence; resolve/read any
reference before treating it as valid. A temporary path is active-flow transport,
not a semantic journal or restart-safe recovery. Accept a failed premise,
dependency, missing authority, or blocker as a result to route, not permission
to widen scope.

Give each moving scope one writer. Correctable findings return to the same
Engineer, then a new stable candidate receives a fresh review. Peers communicate
through the Lead and never coordinate one another.
