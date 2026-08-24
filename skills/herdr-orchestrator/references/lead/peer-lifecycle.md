# Peer dispatch and report lifecycle

This is the disclosed `peer-lifecycle` card. Read it completely after the Lead
core's manifest check and before drafting, starting, continuing, retiring, or
collecting the first Peer.

## 1. Bind one Assignment

Resolve and save every field before start:

```text
Project ID and task ID
Repository root
Checkout/worktree and accepted base
Role = Peer; disposition
Objective or open question
Owned scope and exclusive resources
Excluded scope
Authority and Human-only boundary
Dependencies and related owners
Verification and exact candidate identity
Escalation conditions
Handoff contract, report-return path, and writable boundary
```

Use a neutral brief: facts, open questions, and evidence without the preferred
conclusion. Plans and file lists are provisional. One Assignment has one
outcome owner.

Choose a disposition and enforce its boundary:

- **Engineer:** one writable moving scope; inspect the mechanism, preserve
  unrelated work, verify writes, reopen failed premises, and never self-accept.
- **Architect:** read-only; reconstruct ownership, lifecycle, failure semantics,
  alternatives, strongest counterargument, and reversal conditions. A sealed
  seat reads no other seat's conclusion.
- **Reviewer:** fresh, read-only, and bound to an exact candidate; attempt to
  falsify assigned behavior, scope, and proof; return severity findings and
  `APPROVE` or `FINDINGS` without unrelated redesign. When
  `ocr-peer-reviewer` is installed for the selected Peer recipe, explicitly
  require the Peer to load it. Supply the Git base through the Assignment's
  accepted-base field and the reviewed commit through its exact-candidate
  field. Every Reviewer Assignment requires the procedure/status receipt in the
  report schema below, including direct review when the add-on is unavailable.
- **Scout, proof auditor, or feature owner:** bind the bounded question, mode,
  evidence, exclusions, and the decision informed. The title grants no extra
  authority.

Choose one configured Peer recipe whose description satisfies the Assignment's
risk, independence, access, and cost needs. Recipe selection and disposition
are independent; reuse or mix recipes as needed. Pass the selected `kind` and
native `args` unchanged. If no specialized recipe fits, use the configured
`fallback_peer_recipe` and record that fallback choice in the Assignment. Its
existing access boundary remains binding; request a Human-approved setup update
when the Assignment requires capability outside it.

Reserve a collision-free return path before start. A project-read-only Peer
uses `reports/inbox/<agent-name>/report.md`; its exclusive inbox directory is
the pane cwd and only writable project/orchestration-evidence root. A writable
Peer uses that inbox when its validated boundary permits, or one exact temporary
path inside its owned workspace. Temporary report evidence is outside the
candidate and is removed only after byte-identical promotion. Reserve
`reports/inbox/<agent-name>/ocr/preview.json` and `ocr/rules.json` as durable raw
OCR evidence paths for a Reviewer that loads the add-on.

Every Assignment reproduces this complete schema rather than referencing this
card or a pathname:

```markdown
# PEER REPORT

## Type
<Engineer | Architect | Reviewer | Scout | proof auditor | feature owner | request type>

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
<for Reviewer, begin with exactly:
Review procedure: <ocr-delegate | direct>
OCR status: <USED | SKILL_NOT_AVAILABLE | OCR_UNAVAILABLE | NON_GIT_CANDIDATE | OCR_OUTPUT_UNSUPPORTED | NO_REVIEWABLE_FILES | CANDIDATE_CHANGED>
then severity and inspectable evidence; for USED include both raw artifact paths and SHA-256 digests; for NO_REVIEWABLE_FILES include preview path and digest>

## Unfinished dependencies
<owners, prerequisites, or none>

## Decision needed from Lead
<one explicit decision or none>
```

Require the Peer to write the durable-language report through a sibling partial
file and atomic rename before sending a short live-language summary. Missing
candidate, verification, risk, scope, or decision fields make it incomplete.
Terminal output is not the report.

Assignment preparation is complete when every Assignment field, disposition
boundary, recipe, exclusive return path, full report schema, and completion
evidence is explicit and mutually consistent with the constraints selected for
layer 2.

## 2. Build and deliver the Peer pack

Save the Assignment under `assignments/<agent-name>.md`. Also atomically save
only the applicable protocol and repository constraints, including both
languages, under `assignments/<agent-name>-constraints.md`; do not reference
this card or the full protocol from either file. Invoke run-local
`tools/herdr_orchestrator.py pack --role peer` with:

1. `--role-source` set to the staged `peer-profile` path from the verified
   manifest;
2. `--protocol-source` set to the saved constraints file; and
3. `--assignment-source` for the complete saved Assignment.

Resolve every run-relative path against the absolute assigned run root and pass
absolute source/output paths to the helper.

Pass the opaque Peer profile directly to the helper without opening it. Save
the exact output under `context/` and record its SHA-256, byte count, ordered
sources, recipe, repository, checkout, and agent name. The Peer receives no full
protocol, topology, anti-pattern, Lead, or Supervisor manual.

Project every repository instruction that governs assigned paths into the
constraints while preserving its scope. A mailbox cwd does not bypass
repository authority discovery.

Read only targeted current Herdr help needed for the operation. Invoke the
layout helper with shared state, correct cwd, and Lead pane anchor. Use only
`new_pane_id`; reconcile a same-cwd recovery before a permitted retry. A
writable Peer starts in its owned checkout/worktree. A project-read-only Peer
starts in its exclusive inbox and must prove project and broader common-
directory paths remain unwritable.

Choose a unique fresh name and start the exact configured recipe with no
prompt. Invoke the orchestration helper's `deliver` operation once with the
saved context, assigned live language, receipt path, and localized one-line
opening/closing files that use and contain the exact live-language value. It
sends that envelope and exact pack bytes via a safe argument vector without
`--wait`, records both context and payload digests, and keeps payload bytes out
of stdout and logs. Record the grounded `assignment` event only after exact
identities and delivery receipt exist.

Dispatch is complete when the saved Assignment and pack are byte/digest-bound,
the fresh agent and pane have exact identities, access matches disposition, the
single delivery is accepted, and the ledger references the durable evidence.

## 3. Wait, collect, and continue once

Use standalone `herdr agent wait <peer-name>` for one exact active Peer at a
time. A bounded timeout permits one evidence inspection; unchanged state waits
for another event. Lifecycle status only wakes the Lead.

After settlement, inspect identity with `herdr agent get`; use
`herdr agent read` only for live summary or diagnosis. Require the assigned
return path to be a regular file, validate the full schema, compute SHA-256, and
atomically promote the same bytes to `reports/<agent-name>.md`. If paths differ,
verify matching digests before removing only the reserved temporary source.
For a Reviewer, validate the procedure/status receipt. When status is `USED`,
also require both OCR artifacts under the reserved inbox, verify their reported
SHA-256 digests, and preserve them after report promotion. For
`NO_REVIEWABLE_FILES`, require and preserve the hashed preview artifact.

If `idle` or `done` arrives without a complete file, send one bounded
continuation with `herdr agent prompt` through a safe argument vector and
without `--wait`, preserve its immediate receipt, then wait once more on that
Peer. A second premature settlement is a recipe/harness failure: preserve
evidence and report `BLOCKED`. Never redeliver the context or rebuild a report
from terminal snapshots.

Accept `REOPEN_REQUEST`, `DEPENDENCY_REQUEST`, and `BLOCKED` as first-class
outcomes. Route dependencies through the Lead; Peers never coordinate one
another. Clarification and dependency prompts stay bounded. A correctable
Reviewer finding returns to the same owning Engineer, followed by a new stable
candidate and fresh review. Independent Reviewer, Architect, and council seats
always use fresh neutral sessions.

Collection is complete when the exact return bytes are schema-valid, promoted,
hashed, recorded in a grounded `report` event, and either accepted as decision
input or routed to one explicit continuation, dependency, correction, reopen,
or Human decision.

## 4. Retire only a closed lifecycle

Pane capacity never weakens fresh-session rules. Retire a run-created Peer pane
only after its complete report and delivery evidence are durable and no
continuation or correction can return. Preserve Launcher, Lead, pre-existing or
unmanaged panes, and an Engineer whose correction lifecycle remains open.

Retire only through:

```text
python3 <helper> --state <state> --anchor <lead-pane-id> --retire <peer-pane-id>
```

The helper persists intent and closes transactionally. An unregistered
disappearance is an error. Retirement is complete only when helper state and
Herdr lifecycle agree and every required artifact remains durable.
