# Assignments and evidence

The Lead uses this contract for every created agent and runtime milestone.

## Agent creation contract

Before start, resolve and save all fields:

```text
Project ID
Task ID
Repository root
Checkout/worktree and accepted base
Role and disposition
Objective / open question
Owned scope and exclusive resources
Excluded scope
Authority and Human-only boundary
Relevant Workspace Protocol constraints
Dependencies and related owners
Verification and candidate identity
Escalation conditions
Handoff contract and evidence directory
```

Use a neutral brief: provide observations, constraints, and evidence without
embedding the preferred conclusion. One assignment has one outcome owner. A
plan and file list remain provisional.

## Disposition requirements

**Engineer:** one writable moving scope; inspect the mechanism; preserve
unrelated work; verify writes; reopen ownership/lifecycle/API premises; never
self-accept.

**Architect:** read-only; reconstruct ownership, lifecycle, failure semantics,
alternatives, recommendation, strongest counterargument, and reversal
conditions. A sealed seat reads no other seat's conclusion.

**Reviewer:** fresh and read-only; candidate identity is mandatory; attempt to
falsify the assigned behavior, scope, and proof; report findings by severity and
`APPROVE` or `FINDINGS` without redesigning unrelated modules.

**Scout/proof auditor/feature owner:** state the bounded question, mode, owned
evidence, exclusions, and decision the report will inform. The Peer role does
not itself grant broader authority.

## Context and assignment storage

Save the exact context pack under `context/` before start and its full assignment
under `assignments/<agent-name>.md`. Record SHA-256, recipe, repository,
checkout, and agent name. Send the saved pack once. A summary or terminal
transcript does not replace it.

Peer context contains the Peer profile, only relevant protocol constraints, then
one disposition/Assignment. Lead context contains the full macro pack.
Supervisor context contains its role and anti-pattern catalog, every full bound
protocol, then exact Lead/project/run bindings and notebook Assignment.

## Peer report

Require full Markdown with no line limit and save it verbatim under `reports/`:

```markdown
# PEER REPORT

## Type
<Engineer | Architect | Reviewer | Scout | request type>

## Task / Assignment / Disposition
<exact identifiers and bounded mandate>

## Outcome or request
<result | REOPEN_REQUEST | DEPENDENCY_REQUEST | BLOCKED>

## Owned and changed scope
<owned paths/resources and exact changes, including none>

## Artifacts and exact candidate
<commit or deterministic base/diff/artifact digest>

## Verification commands, cwd, and results
<each command, working directory, exit/result, relevant output>

## Findings, assumptions, and residual risks
<severity and inspectable evidence where applicable>

## Unfinished dependencies
<owners, prerequisites, or none>

## Decision needed from Lead
<one explicit decision or none>
```

A report is an evidence-bearing handoff, not proof of acceptance. Missing
candidate, verification, risk, scope, or requested decision makes it incomplete.

## Stable candidate and review chain

Prefer an exact commit when authority permits. Otherwise record a deterministic
identity including base commit, binary-safe diff digest, untracked-artifact
manifest/digests, and any generated artifact digest. Freeze it during review.
Any write produces a new candidate that requires new verification and review.

The Engineer proves writes; the Reviewer falsifies the exact candidate; the
Lead inspects evidence and binds the project verdict; the Human resolves
owner-only decisions. Never derive one link from Herdr status or test success.

## Semantic event ledger

Append-only `events.jsonl` uses one object per milestone. Every event carries
`schema_version`, UTC `timestamp`, `run_id`, `type`, `actor`, and
event-specific evidence references:

```json
{"schema_version":1,"timestamp":"<UTC RFC3339>","run_id":"<id>","type":"candidate","actor":"<lead>","task_id":"<id>","candidate":"<exact identity>","evidence":["<relative run path>"]}
```

Use only `launch`, `assignment`, `report`, `candidate`, `verification`,
`review`, `human_decision_request`, `verdict`, and `finish`. Store full text in
Markdown and reference it from JSONL. The ledger records facts already grounded
in Herdr/Git/filesystem; it never becomes live status, queue, retry engine,
parentage, or automatic acceptance.

Milestone payloads retain the decision chain:

- `launch`: agent, pane, recipe, context path, and context digest;
- `assignment`: assignee, disposition, assignment path/digest, owned scope;
- `report`: reporter, outcome/request, full report path/digest;
- `candidate`: task and exact immutable identity;
- `verification`: exact candidate, command, cwd, result, and full evidence path;
- `review`: exact candidate, Reviewer identity, decision/findings, report path;
- `human_decision_request`: exact question, boundary, options/evidence path;
- `verdict`: exact candidate, decision, authority, unresolved findings and
  residual risks, with evidence paths; and
- `finish`: terminal project outcome and durable report/verdict references.

Never truncate candidate, verification, risk, or decision information to fit
JSONL. Put the full record in Markdown and preserve its path plus digest in the
event.
