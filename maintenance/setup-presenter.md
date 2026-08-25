# Setup session and presenter evidence

Date: 2026-08-25

Status: implemented and regression-tested

## Implemented interface

`SetupEngine` exposes the frozen interface:

```text
resume(project_root) -> SetupView
answer(session_id, revision, typed_answers) -> SetupView
accept(session_id, candidate_digest) -> AcceptanceReceipt
```

The engine owns discovery, typed questions, authority planning, candidate
compilation, native proof, publication preparation, state persistence, stale
handling, and acceptance. `SetupView` is a frozen projection containing only
engine facts and decisions. The CLI and Launcher instructions render that view
and return exact typed values.

## Resumable state and CAS

The stable Session ID binds the canonical project root. Canonical session JSON
lives under `.orchestration/setup/sessions/`, is protected by a per-session
publisher lock, and is replaced atomically after fsync. It stores typed Human
answers plus canonical proof and acceptance receipts; it never stores pickle or
conversation-derived objects.

Every answer names the current Setup Revision. A stale revision, unknown
question, wrong value kind, duplicate answer, or value absent from the current
option set performs no write. Whole-snapshot change produces `STALE` with one
typed restart action. Restart begins a new revision and does not transfer old
answers implicitly.

## Deterministic alpha planner

The planner supports Codex and the Lead, Engineer, Reviewer, and optional
Supervisor roles. It probes every discovered Git repository cwd, compiles one
exact selected repository/worktree/Git-common envelope, and writes controlled
Lead/evidence/notebook state under the setup control root. Parent project-write
profiles receive more-specific read rules for Git/orchestration paths when
policy denies those writes.

Model questions contain only observed harness, model identifier, and supported
reasoning effort facts. Options are sorted mechanically and carry no
quality/cost/speed ranking or recommendation. Human answers produce exact
`ModelBinding` values.

## Resume and acceptance proof

A prepared Runtime Proof Receipt is rendered canonically into the session.
Resume parses it back into typed receipts, recomputes every content digest, and
recompiles the same candidate/publication without repeating smoke. An accepted
session is verified against the immutable generation and Activation Manifest
through the Slice 5 acceptance path before `ACCEPTED` is projected.

Focused tests cover the four-role setup, unranked model inventory, revision CAS,
open-question enforcement, stale restart, failed-smoke typed retry, symlinked and
tampered session-state rejection, nested-repository selection, receipt round
trips, smoke reuse, wrong-digest no-write behavior, acceptance, verified resume,
and idempotent re-acceptance.

## Runtime handoff

The thin presenter publishes immutable generations only. Runtime resolves
the accepted Activation Manifest, snapshots the verified generation into a run,
and compiles each logical role template with exact Assignment paths. There is
no direct mutable setup file or compatibility reader.
