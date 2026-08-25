# Project setup and update

The Launcher is a thin presenter over the deterministic setup engine. It calls
only `resume`, `answer`, and `accept`; it does not discover facts, construct
questions, rank models, compile authority, write configuration, run its own
smoke, or claim completion.

Resolve separately:

- `<absolute-project-root>`: canonical target project root.
- `<installed-skill-root>`: absolute directory containing the loaded
  `SKILL.md`.

Never resolve helpers from the project root or current directory. Invoke with
Python 3.11+:

```text
python3 <installed-skill-root>/scripts/herdr_setup_cli.py resume \
  --project-root <absolute-project-root>
```

The helper returns one canonical `SetupView` JSON document. Treat every field
as engine-owned state.

## Present unresolved questions

When status is `NEEDS_HUMAN_INPUT`, present only `questions` from the current
view. Preserve each question `id`, `kind`, option value, and fact. The wording
may be made easier to read, but add no option, recommendation, model ranking,
cost/quality claim, policy, or trade-off absent from the view.

Use structured user input when it can represent every engine option exactly.
If a question has more options than the UI permits, show the complete numbered
engine list and ask for one exact value. Questions may be batched, but submit
only answers to questions open in the same revision.

Never ask the Human to write JSON or CLI payloads. Ask in ordinary language,
preserve exact option values, and translate the reply into typed input.

Return typed answers unchanged:

```text
python3 <installed-skill-root>/scripts/herdr_setup_cli.py answer \
  --session-id <session_id> \
  --revision <revision> \
  --answers-json '[{"id":"<question-id>","kind":"CHOICE","value":"<exact-value>"}]'
```

Use JSON booleans for `BOOLEAN` answers. Consume the new `SetupView`; its
revision replaces the prior revision. A revision conflict returns the current
view and performs no answer write. For `TEXT`, return the Human's nonempty
canonical string exactly; the engine supplies no options or default.

`STALE`, `CAPABILITY_INVALID`, and `SMOKE_FAILED` views may contain one typed
engine recovery question. Present that question exactly. Never retry, reset
Human decisions, weaken authority, or substitute a model without its answer.

## Present the candidate

When status is `AWAITING_ACCEPTANCE`, show:

- the exact Candidate Digest, Discovery Digest, Runtime Proof Digest, and
  Publication Digest;
- every `role_binding`, including harness, model, reasoning effort, cwd,
  selected binding, and complete effective authority; and
- all engine issues, if any.

Ask the Human to accept the exact Candidate Digest. A generic “yes” is not a
digest confirmation. On exact confirmation, call:

```text
python3 <installed-skill-root>/scripts/herdr_setup_cli.py accept \
  --session-id <session_id> \
  --candidate-digest <candidate_digest>
```

Setup is accepted only when this command returns a canonical Acceptance Receipt
with status `ACCEPTED`. Report its Candidate, Publication, and Acceptance
Receipt digests. Any other result is not completion.

## Current boundary

The current setup supports Codex and binds one exact discovered Git repository for Lead,
Engineer, Reviewer, and optional Supervisor proof. Acceptance publishes the
only runtime authority through `.orchestration/setup/current.json`. Task
launch resolves that immutable generation and binds its logical role templates
to exact run/Assignment paths; no mutable compatibility config is generated.
