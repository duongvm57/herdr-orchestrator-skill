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
as engine-owned state. Summarize its `harnesses` and `repositories` inventory
before the questions, including partial and unsupported harness statuses; do not
turn inventory entries into selectable options unless the engine does.

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

Normal setup asks one batch of six project preferences: default Lead, Peer, and
Supervisor harness/model/effort; the global ad-hoc Peer routing fallback; live
language; and artifact language. Supervisor is a stored project default, not a
task participant. Repository inventory, Lead write authority, Git operations,
technical architecture ownership, and Supervisor attachment are runtime facts
or protocol invariants and are not setup questions.

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

An incompatible pre-redesign session is not migrated. If `resume` reports an
unsupported session schema, explain that explicit restart archives the old
bytes and resets its unanswered decisions. After the Human confirms that exact
recovery, rerun `resume --restart`; never add the flag proactively.

## Present the candidate

When status is `AWAITING_ACCEPTANCE`, show:

- the exact Candidate Digest, Discovery Digest, Runtime Proof Digest, and
  Publication Digest;
- every `authority_binding`, including harness, model, reasoning effort, proof cwd,
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

Discovery inventories every known harness and every nested Git repository.
Harnesses without an enforceable authority adapter remain visible and
ineligible; Codex is the first implemented adapter. The candidate proves Lead,
Peer-writable, Peer-readonly/evidence-write, and Supervisor-notebook authority
templates without choosing task topology. Acceptance publishes the immutable
generation through `.orchestration/setup/current.json` and publishes or
snapshots the tracked root `WORKSPACE_PROTOCOL.md`. Runtime selects one or more
exact repository/worktree scopes and binds one compatible authority template.
