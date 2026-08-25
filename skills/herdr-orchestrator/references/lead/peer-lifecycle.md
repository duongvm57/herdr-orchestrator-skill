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

Start the Peer through the runtime `start` operation. Read its normal terminal
response through `result`; use `prompt` only when the same owner should continue.
A durable evidence file is required only when the task needs one. Accept a
failed premise, dependency, missing authority, or blocker as a result to route,
not as permission to widen scope.

Give each moving scope one writer. Correctable findings return to the same
Engineer, then a new stable candidate receives a fresh review. Peers communicate
through the Lead and never coordinate one another.
