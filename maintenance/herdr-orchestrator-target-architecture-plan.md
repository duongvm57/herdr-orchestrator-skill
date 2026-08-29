# Herdr Orchestrator Skill — Refactor Plan

> **Goal:** refactor `herdr-orchestrator-skill` so that Herdr becomes the sole runtime/control-plane infrastructure, the official Herdr Agent Skill becomes the canonical agent-facing instruction for operating Herdr, while this repository owns only the semantics of the Supervisor – Lead – Peer (SLP) model.
>
> This plan is written so it can be handed directly to a coding agent for sequential execution. **Phase is only the implementation order in the plan; phase/version must not appear as a concept in file, class, function, test, command, or production artifact names.**

---

## 0. Source of truth and authority by domain

Do not use a simple total order for every kind of conflict. Each source is authoritative only within its own domain:

1. **SLP operating model / mindset**
   - `agent-orchestration-supervisor-lead-peer-tong-hop(1).md`
   - Authoritative for: independent judgment, attention allocation, role authority, three instruction layers, `WORKSPACE_PROTOCOL.md`, one-writer, stable candidate, REOPEN/DEPENDENCY/BLOCKED, evidence-based acceptance, smallest useful topology, Supervisor governance/attention plane.
2. **Installed Herdr runtime contract + release-matched official Agent Skill**
   - installed `herdr` binary and the schema/CLI that binary actually exposes;
   - release-matched official skill from `herdr --skill`;
   - `https://herdr.dev/docs/agents/` (supporting official lifecycle/detection reference);
   - `https://herdr.dev/docs/agent-skill/`;
   - `https://herdr.dev/docs/agent-automation/`;
   - `https://herdr.dev/docs/socket-api/`;
   - `https://herdr.dev/docs/plugins/`;
   - `https://herdr.dev/docs/integrations/`;
   - `https://herdr.dev/docs/session-state/`;
   - `https://herdr.dev/docs/cli-reference/`.
   - Installed binary + release-matched `herdr --skill` + bundled schema are authoritative for runtime mechanics. Web docs are supporting official reference. Authoritative for: CLI syntax, IDs, pane/workspace/process behavior, lifecycle semantics, session restore, event/socket/plugin contract.
   - `https://herdr.dev/agent-guide.md` is only used for Human-facing setup/troubleshooting, **not** as the agent-operation contract.
3. **Gap analysis Herdr vs Paseo**
   - `Báo cáo Gap Analysis_ Herdr vs Paseo cho kiến trúc Supervisor – Lead – Peer.md`
   - Used as an analysis/mapping reference; recommendations in the Gap Analysis **do not automatically become mandatory implementation** if an SLP invariant can be achieved with a smaller boundary.
4. **Current repository**
   - `skills/herdr-orchestrator/SKILL.md`
   - `skills/herdr-orchestrator/references/**`
   - `skills/herdr-orchestrator/assets/**`
   - `skills/herdr-orchestrator/scripts/**`
   - `maintenance/**`
   - `tests/**`
   - Evidence of the current implementation; do not keep the old architecture merely to preserve stale behavior/tests.

### Mandatory architecture principles

```text
Herdr
    = runtime/control-plane infrastructure truth

Official Herdr Agent Skill
    = canonical agent-facing knowledge for operating Herdr

herdr-orchestrator skill
    = SLP policy + role semantics + assignment/authority contracts
      + project/task routing

WORKSPACE_PROTOCOL.md
    = repository-specific strategy

Git / filesystem
    = artifact/workspace truth

Exact Git commit
or explicitly frozen reproducible snapshot
    = immutable candidate truth

Human
    = owner-only decisions
```

**Do not create a second lifecycle/control-plane alongside Herdr. Do not create durable SLP infrastructure merely because a semantic concept exists in SLP.**

The default implementation strategy for this refactor is:

> **remove duplication first → formalize contracts second → dogfood native Herdr path → convert stable behaviors into repeatable live evals → only add infrastructure when observed failure proves it is necessary.**

# 1. Non-negotiable implementation rules

## 1.1 Naming & Artifact Integrity Contract

**Mandatory for the entire refactor.**

Phase/version may appear only in:

- this plan file;
- commit message / PR description if the Human wants;
- changelog/release metadata when actually describing a release.

Phase/version **must not** become the name of a production/test artifact.

### Do not create milestone/migration-style names

Do not create new names such as:

```text
phase1_test.py
phase_2_runtime.py
step3_assignment.py
assignment_v2.py
assignment-v2.md
runtime_v2.py
new_runtime.py
runtime_new.py
runtime_final.py
runtime_refactored.py
legacy_runtime.py
candidate_manager_v2.py
build_assignment_v2()
create_assignment_new()
parse_result_phase2()
SupervisorV2
AssignmentV2
```

Also do not create parallel copies solely for migration:

```text
foo.py
foo_v2.py

assignment.py
new_assignment.py
```

### Names must reflect the final responsibility

Correct:

```text
assignment.py
candidate.py
recipe_config.py
repository_hygiene.py

test_assignment_contract.py
test_candidate_contract.py
test_authority_contract.py

create_assignment()
render_assignment()
freeze_candidate()
validate_recipe()
```

Naming examples **must not be used to imply that a component must exist**. In particular, do not make `registry`, `attention_router`, or `actions` production artifacts merely because they appeared in the Gap Analysis; those responsibilities may only be reopened through the evidence gate in §1.3.

### Migration rules

- Prefer modifying the current canonical file **in place**.
- If a responsibility truly requires a new file, give it its **final name the first time it is created**.
- If a new file replaces an old file, move callers/tests to the new canonical file and delete the old file in the same bounded change; do not leave two implementations in parallel solely for migration.
- Do not create `old/`, `new/`, `v2/`, `phase-*`, or `migration-*` directories to hold intermediate implementation.
- Temporary probes may exist only in OS temp / test temp directories and must be deleted in the same operation.
- Do not create separate progress files such as `phase1-done.md`, `migration-status.md`, or `refactor-notes-v2.md`. Use this plan's checklist or report in the agent response.
- Do not use suffixes/prefixes `v2`, `v3`, `next`, `new`, `old`, `final`, `refactor`, `phaseN`, `stepN` in symbols/files merely to indicate “the new version”.
- The only exception: the version is genuinely an **external/domain protocol concept** that already exists, for example a schema wire format with `version = 3`. Do not use this exception to name implementation.

### Repository hygiene gate

Add a deterministic test/check named by stable responsibility, for example `test_repository_hygiene.py` or integrated into the existing test architecture, to verify that **new/changed code artifacts** do not introduce milestone/version naming into the source tree or Python identifiers.

The check must avoid false positives for:

- external schema/version literals;
- fixtures intentionally testing legacy input;
- changelog/release documentation;
- this plan.

If implementation needs to split files for cohesion, split by responsibility, not by phase.

---

## 1.2 Do not overfit the plan into implementation

This plan defines **boundary + invariant + acceptance**; it does not permit the agent to turn every bullet into an abstraction/class/file.

Before creating a new file/class/helper, the agent must be able to answer:

1. Will this responsibility still exist after the refactor is complete?
2. Is there a current canonical owner to modify in place?
3. Does Herdr/the official Herdr skill already provide this primitive?
4. Is the new file/function named for a domain responsibility or merely a migration step?

If the answer to (1) is “no” or (4) is “migration step”, **do not create that artifact**.

---

## 1.3 Lean-first / evidence gate for new infrastructure

This refactor **does not build by default**:

- Herdr plugin;
- durable SLP agent registry/database;
- semantic journal service;
- long-lived Attention Router daemon/subscriber;
- generic SLP message bus;
- authority wrapper around every Herdr operation.

A new infrastructure component may only be added when there is **recorded live evidence from dogfood or a repeatable live eval** showing that at least one core SLP invariant cannot be achieved reliably with:

1. installed Herdr + official Herdr Agent Skill;
2. role/Assignment/Workspace Protocol contracts;
3. Git/worktree/candidate primitives;
4. bounded scripts/helpers purely for validation/rendering that do not own lifecycle.

When the gate triggers, the agent must issue `REOPEN_REQUEST` with:

- observed failure;
- affected invariant;
- why native Herdr + current contracts are insufficient;
- smallest candidate fix;
- why that fix does not create a second control plane.

**Failure-recording policy:** dogfood is a discovery activity, not a checked-in database. Actionable live/dogfood failures are recorded in the project issue tracker; reproducible failures are converted into regression scenarios/evals. Do not maintain a parallel `maintenance/dogfood-issues.md` ledger solely to store PASS/FAIL status or history.

**A Herdr plugin is only a possible extension point, not a default target artifact of this refactor.** If dogfood later requires a persistent semantic/event component, compare at least native socket/event use, a thin local helper, and the plugin boundary before choosing.

Mandatory clarifications to avoid reverse over-engineering or overclaiming capability:

- **Safe task submission is an invocation constraint, not an architecture component.** If code is needed to preserve task text and avoid shell interpolation, prefer direct argv/socket invocation or a small helper in the existing canonical owner; that helper must not own wait/lifecycle/session/pane state.
- **One-writer in core is a Lead orchestration invariant + explicit Assignment ownership + dogfood evidence.** Do not create an ephemeral/shared ownership store merely to call the invariant “executable”. Only open shared state when observed concurrency/context-loss failure proves it is necessary.
- **Supervisor activation belongs on the Human/governance side.** Lead/Peer do not have a responsibility to know that the Supervisor exists, wake the Supervisor, maintain the Supervisor, or route project events to the Supervisor. If automatic wake is added later, the bridge must live on the Supervisor/governance side and observe Herdr independently.
- **A Herdr event or Peer lifecycle transition does not itself create an inference turn for Supervisor/Lead.** Core only claims synchronous/active `wait/read/inspect` flow while the caller is still orchestrating. Detached automatic wake is a separate capability and may only be claimed when a real bridge exists.
- **Native `wait/read` or lifecycle settle does not imply exact Assignment correlation/completion.** Native primitives only trigger/collect observation; an Assignment is complete only when structured handback has a matching `assignment_id`.
- **Role authority contract does not imply technical ACL.** If raw `$herdr` remains globally reachable, core only claims that Peer has no SLP authority/operating instruction to orchestrate; do not write that Peer “cannot orchestrate” at runtime unless capability enforcement exists.
- **Event wake cannot detect silence.** Stall/no-transition/forgotten follow-up requires separate heartbeat/schedule semantics if a later product requirement demands unattended supervision; do not merge it into the event bridge.
- **Evidence path does not imply readable/durable evidence.** A reference/path is valid only after the collector can resolve/read the target; temp-path fallback is scoped only to the active orchestration lifetime unless the artifact contract explicitly states different durability.
- **Native Herdr/provider session restore does not imply SLP orchestration recovery.** Resume/rebind may restore provider conversation/process/layout according to the Herdr contract but does not itself prove recovery of Assignment identity, parent/owner relationship, active delegation map, candidate binding, unresolved dependency, or Supervisor attachment semantics. Core only claims recovery for facts proven by dogfood; failure across restart/rebind triggers the §1.3 evidence gate and must not be overclaimed from native session restore.

---

## 1.4 Preserve unrelated state

- Do not modify unrelated Human changes.
- Do not broadly reset/checkout/clean the repository.
- Do not commit/push/publish unless the Human separately requests it.
- Each phase must leave the repository coherent and testable; do not intentionally leave a broken intermediate architecture expecting a later phase to fix it.
- If discovery proves a premise of the plan wrong because the Herdr API/repo has changed, use `REOPEN_REQUEST` with evidence instead of inventing a compatibility layer.

---

# 2. Target architecture

## 2.1 High-level runtime flow

```text
                              HUMAN
                                │
                                ▼
                    $herdr-orchestrator
                    ──────────────────
                       Launcher route
                                │
                      setup / task launch
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
              LEAD                          SUPERVISOR
       SLP Lead profile                  SLP Supervisor profile
       + official Herdr skill            + official Herdr skill
                │                               │
                ▼                               │
          bounded Assignment                    │
       objective/scope/authority                │
       disposition/verification                 │
                │                               │
                ▼                               │
             PEER(S)                            │
       thin SLP Peer profile                    │
       bounded technical work                   │
       no orchestration authority               │
                │                               │
                ▼                               │
   COMPLETE / REOPEN / DEPENDENCY / BLOCKED     │
        + candidate + evidence                  │
                │                               │
                └───────────────┬───────────────┘
                                ▼
                         Lead reconcile
                    verification / acceptance
                                │
                                ▼
                              HERDR
                    ─────────────────────────
                    pane / workspace / process
                    worktree provenance
                    agent start/prompt/read/wait
                    lifecycle/session restore
                    socket events / observation
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
                Codex         Claude          Pi / ...
```

SLP semantics in the core refactor are **contracts carried by role/profile/protocol/assignment/handback/evidence**, not a persistent runtime database by default.

**The Supervisor branch is attached by Human/Launcher governance setup independently from Lead/Peer.** Lead/Peer do not wake or maintain the Supervisor. In core, the Supervisor attachment must carry enough scope to know which Lead it is supervising; a Herdr pane/workspace event is not itself an SLP parentage mapping.

If live dogfood after the core refactor proves a need for durable cross-session correlation, shared cross-Lead ownership state, detached Lead/Supervisor wake, multi-Lead attention routing, or silence detection, reopen the architecture under §1.3 instead of pre-building infrastructure.

## 2.2 Responsibility boundary

### Herdr owns

- workspace/tab/pane;
- process lifecycle;
- worktree runtime/provenance;
- agent start/prompt/read/wait;
- native provider-session restore;
- agent lifecycle detection/reporting;
- socket event stream;
- plugin host/event hooks if actually used later;
- terminal history/observation.

### Official Herdr Agent Skill owns

Agent-facing operating knowledge for:

- checking `HERDR_ENV=1`;
- inspect layout/panes/agents;
- balanced pane operations;
- start helper agent;
- prompt/wait/read;
- focus preservation;
- ID handling;
- fallback read behavior;
- normal Herdr coordination recipes.

This repository **does not hard-code these generic recipes again in a runtime wrapper** if the official skill already covers them.

### `herdr-orchestrator` owns

- SLP roles and authority;
- Launcher routes;
- project configuration;
- `WORKSPACE_PROTOCOL.md`;
- smallest-useful-topology policy;
- Peer disposition;
- Assignment contract;
- explicit parent/owner relationship in active orchestration;
- one-writer policy/preflight within the scope the Lead is orchestrating;
- REOPEN/DEPENDENCY/BLOCKED handback semantics;
- stable candidate contract;
- acceptance chain;
- Supervisor attention policy;
- model/recipe policy that Herdr does not make first-class;
- language separation.

The repository **does not own by default** a durable agent database, global semantic registry, event daemon, or transcript journal.

### Git/filesystem owns

- actual source artifact;
- exact diff;
- repository/worktree state;
- exact Git commit or explicitly frozen reproducible snapshot used as the candidate.

A Herdr worktree **does not itself imply a stable candidate**.

---

# 3. Target repository shape

This is a **target conceptual tree**, not a requirement to create files merely to match the diagram. Only create a file when the responsibility truly requires separate code. Do not create artifacts by phase.

```text
herdr-orchestrator-skill/
├── README.md
├── LICENSE
├── requirements-dev.txt
│
├── skills/
│   ├── herdr-orchestrator/
│   │   ├── SKILL.md
│   │   ├── agents/
│   │   │   └── openai.yaml
│   │   ├── assets/
│   │   │   ├── config.toml
│   │   │   └── workspace-protocol-template.md
│   │   ├── references/
│   │   │   ├── launcher/
│   │   │   │   ├── preflight.md
│   │   │   │   ├── setup.md
│   │   │   │   ├── task-launch.md
│   │   │   │   ├── supervisor-attachment.md
│   │   │   │   └── workspace-protocol-authoring.md
│   │   │   ├── roles/
│   │   │   │   ├── lead.md
│   │   │   │   ├── peer.md
│   │   │   │   └── supervisor.md
│   │   │   ├── lead/
│   │   │   │   ├── topology.md
│   │   │   │   ├── peer-lifecycle.md
│   │   │   │   └── candidate-and-verdict.md
│   │   │   └── anti-patterns/
│   │   │       ├── index.md
│   │   │       └── responses.md
│   │   └── scripts/
│   │       ├── herdr_orchestrator.py
│   │       └── herdr_harnesses/
│   │           ├── base.py
│   │           └── <provider adapters>
│   │
│   └── ocr-peer-reviewer/
│       └── ...
│
├── tests/
│   ├── <existing behavior/invariant tests that remain valid>
│   ├── evals/
│   │   ├── orchestration-evals.json      # repeatable live-eval manifest; references existing invariant/scenario IDs
│   │   └── fixtures/                     # clean consumer-project seeds; skill is installed into a fresh copy per repetition
│   │       ├── orchestration-basic/
│   │       ├── multi-scope/
│   │       └── candidate-review/
│   ├── test_instruction_architecture.py
│   ├── test_context_budget.py
│   ├── test_repository_hygiene.py        # if a separate hygiene test is justified
│   └── <contract tests named by invariant, never phase>
│
├── maintenance/
│   ├── assignments-and-evidence.md
│   └── orchestration-invariant-coverage.md
│
└── scripts/
    ├── context_budget.py
    ├── render_coverage.py
    └── run_evals.py                      # dev/test-only real-Herdr eval runner; not runtime/control-plane code
```

**There is no `plugin/` in the default target tree.** If the evidence gate in §1.3 triggers and Human/Lead accepts an expanded architecture, a plugin or other component is designed in a bounded follow-up change with a name based on its final responsibility.

## 3.1 Files expected to disappear

When migration is complete and callers/tests/docs have moved to the target architecture:

```text
skills/herdr-orchestrator/scripts/herdr_runtime.py
```

`herdr_balanced_split.py` must also be deleted **if** an audit shows that it only duplicates generic pane balancing already covered by the official Herdr skill. Do not delete it if a clearly evidenced SLP-specific responsibility remains; if retained, its name/responsibility must be canonical, not a compatibility shim.

## 3.2 `herdr_orchestrator.py` after the refactor

It is no longer a runtime/control-plane manager.

Keep only responsibilities that truly belong to the skill, for example:

- parse/validate project config;
- validate `WORKSPACE_PROTOCOL.md`;
- recipe/model capability discovery that Herdr does not provide;
- setup/update validation;
- pure Assignment/contract rendering or validation if actually needed.

Commands/logic belonging to the old architecture must disappear:

```text
init-run
run tree
stage-assets if it only serves transport/run pack
pack
deliver
receipt
old semantic lifecycle ledger
duplicate lifecycle state machine
```

Do not replace them with commands that have the same semantics but new names.

# 4. Gap inventory

## P0 — must be resolved in the core refactor

### GAP-01 — Two runtime architectures are overlapping

The repo simultaneously says thin Herdr-native runtime/no run directory while still containing code/tests/maintenance for `init-run`, run tree, pack/deliver, receipt/ledger.

**Impact:** two control-plane/evidence truths; maintenance and tests may prove an architecture that is no longer shipped.

**Target:** Herdr is the runtime truth; delete the retired run/transport/lifecycle architecture instead of replacing it with a new semantic runtime.

---

### GAP-02 — `herdr_runtime.py` duplicates the official Herdr Agent Skill

The current helper hard-codes binary lookup, pane layout/balancing, pane env, agent start/prompt/wait/read, focus handling, and startup inspection.

**Target:** Launcher/Lead/Supervisor use the official Herdr skill + installed Herdr binary; do not maintain a custom generic Herdr runtime wrapper. Task/Assignment submission must preserve text according to the contract and avoid shell interpolation; this is an invocation constraint, not a new runtime wrapper.

---

### GAP-19 — Startup/prompt failure ownership must belong to the launch contract

The phase that changes the launch path must also preserve important failure semantics; do not defer cleanup policy to “later”.

**Target core:**

- new split/pane is created but process is not yet established → only clean up the newly owned pane when provably safe;
- agent/process already exists but is blocked → preserve the agent/pane and expose blocked evidence; do not treat it as a failed launch to destroy;
- prompt delivery is ambiguous/times out → inspect the current agent/output before an explicit follow-up; do not blind retry and do not destroy the pane merely because acknowledgement is ambiguous;
- do not touch pre-existing topology during cleanup.

---

### GAP-03 — SLP identity/parentage is not explicit in the orchestration contract

A Herdr pane/agent alias is a runtime handle, not an SLP authority relationship.

The core refactor needs enough information for an active orchestration to distinguish:

```text
role
parent/owner relationship
assignment
current Herdr target/binding when needed
```

**Target:** identity/parentage is carried explicitly in role env + Assignment/launch context; do not infer parent from same workspace, pane adjacency, or cwd.

**Not a core requirement:** a persistent cross-session/global SLP agent database. Native provider/session restore must not be treated as evidence that the SLP orchestration relationship has recovered. Only add a durable registry if live dogfood proves that resume/rebind actually loses an important invariant and native/session context is insufficient.

---

### GAP-04 — Assignment is not yet a first-class contract

Currently objective/scope/authority/disposition/verification mostly live in the prose prompt.

**Target:** Assignment has a canonical structured representation/rendering sufficient to inspect/test; the prompt is generated from Assignment, not parsed backward from prose into Assignment. The representation may be bounded data/template in the Lead flow; a database is not required by default.

---

### GAP-05 — Disposition is lost at runtime

The current Peer prompt hard-codes `Disposition: Peer`, while SLP requires a base Peer profile + assignment-level disposition such as Engineer/Architect/Reviewer/Scout.

**Target:** disposition is an Assignment field independent of recipe/profile.

---

### GAP-06 — One-writer ownership is only prose

Worktree isolation does not itself ensure that logical moving scopes do not overlap.

**Target core:** Lead must explicitly assign one writer for each moving scope, maintain an **explicit active delegation map in the Lead's own reasoning/Assignment flow**, check overlap before delegating another writer, and reconcile boundaries when scopes intersect. This map is orchestration context/contract, **not a mandatory file/database/service**. Worktree isolation supports valid concurrent writers but does not replace the ownership rule.

The core claim here is **contractual enforcement + observable dogfood behavior**, not transactional machine enforcement. If implementation has no shared state, tests/docs must not claim cross-Lead atomic exclusion.

**Escalation gate:** a shared/atomic ownership registry is needed only if dogfood reveals real ownership collisions caused by concurrency/context loss outside one Lead context that the rule above cannot reliably prevent.

---

### GAP-07 — Stable candidate is not yet first-class

Reviewer may be assigned a moving target; a worktree does not imply an immutable review candidate.

**Target:** prefer an exact Git commit. If the repo cannot commit, use an explicitly frozen reproducible snapshot with a clear contract; Reviewer Assignment binds the exact candidate; mutation creates a new candidate.

---

### GAP-08 — Peer semantic outcome is not yet first-class

Herdr `done/idle/blocked` is not equivalent to:

```text
COMPLETE
REOPEN_REQUEST
DEPENDENCY_REQUEST
BLOCKED
```

**Target:** Peer handback has a structured outcome + evidence + exact `assignment_id`; Herdr lifecycle is only a synchronization/observation signal. The core refactor does not need to persist the outcome in a database if the handback/evidence contract is sufficiently inspectable during active orchestration. Do not use the word `lossless` to implicitly claim durability across restart/reconnect if evidence only lives in temp/terminal transport.

---

### GAP-09 — Supervisor feedback loop has the wrong role model

The current Supervisor attachment says the Supervisor is invisible to the Lead and the Launcher does not notify/modify the Lead.

SLP requires the Supervisor to be able to observe, pose an evidence-backed open question to the Lead, relay a Human decision, and escalate an owner-only matter, without becoming project authority.

**Target core:** sanctioned Supervisor → Lead channel + native Herdr observation primitives when useful. Supervisor is attached by Human/Launcher governance setup; Lead/Peer do not activate, wake, or maintain Supervisor. Core does not require an automatic Attention Router component and does not claim that a Herdr event itself creates a Supervisor inference turn.

---

### GAP-10 — Lead operating cards exist but are not wired into runtime context

`references/lead/topology.md`, `peer-lifecycle.md`, `candidate-and-verdict.md`, and anti-pattern cards contain important semantics, but the current runtime Lead prompt does not load them.

**Target:** Lead receives the right knowledge through a concise profile + selective/on-demand reference contract; do not dump the whole manual.

---

### GAP-21 — Prompt delivery and assignment completion have mixed semantics (HD-004)

Official Herdr specifies that `agent prompt --wait` does not track individual turns; active turn completion may satisfy the wait.

**Target:** `prompt submitted` and `assignment completed` are two different facts. Prompt/follow-up carries the exact `assignment_id`; completion is confirmed only by matching Peer handback/outcome/evidence. Timeout/stall does not automatically permit blind resend. Core active orchestration may use `agent wait/read/inspect` to collect handback; if the Lead has idled/detached, Peer completion must not be claimed to automatically wake the Lead.

---

## P1 — must be resolved for stable operation

### GAP-11 — Fixed `120` terminal lines may truncate handoff

**Target:** remove the fixed-window result contract. Use appropriate official Herdr read behavior and structured handback; terminal history is an observation surface, not an arbitrary 120-line protocol. The structured outcome must be bounded; large evidence may be written to a task-owned/project-approved artifact or temp Markdown path, with the handback carrying only the reference/path. An evidence reference/path is valid only after the collector can resolve/read the target. Temp-path fallback guarantees transport only during the active orchestration lifetime and must not be claimed durable across restart/reconnect. This is a transport fallback, not a semantic journal.

---

### GAP-24 — Detached Peer handback does not automatically wake Lead

Herdr `agent.wait`/`agent.read` is sufficient for **active synchronous collection**, but a Peer lifecycle/event transition does not itself create a Lead inference turn when the Lead has idled/detached.

**Target core:** clearly support and dogfood the mode `Lead active → wait/read/inspect → matching assignment handback`. Do not claim detached/asynchronous `Peer outcome → automatic Lead wake` without an explicit wake mechanism. If a product requirement needs fan-out followed by the Lead sleeping/idling and being called back automatically when any Peer handback arrives, open the §1.3 evidence gate for the smallest wake bridge instead of assuming native Herdr already does this.

---

### GAP-12 — “verbatim Human task” but `_safe_text()` calls `.strip()`

**Target:** preserve task text according to the contract; validation must not normalize content beyond what is necessary to reject invalid input.

---

### GAP-13 — Language contract is not reliably propagated to every role

**Target:** live/artifact language is explicit project/Assignment context and is delivered according to role disclosure rules.

---

### GAP-14 — Authority enforcement is inconsistent

If raw Herdr CLI/official skill is exposed globally, Peer may technically orchestrate even though the role contract forbids it.

**Target core:** capability/context disclosure must match the role; Lead has orchestration knowledge, Supervisor has observation/attention knowledge, Peer **has no SLP authority** and must not load/use the orchestration skill for generic subagent control. If the raw Herdr binary remains globally reachable, this is a behavioral/authority boundary, not yet a technical ACL.

**Escalation gate:** only add semantic action/wrapper enforcement if dogfood proves role/profile/tool exposure is insufficient. If a wrapper exists, it only enforces caller role/assignment; it does not manage lifecycle.

---

### GAP-15 — Supervisor observation, activation, and event wake must have separate semantics

SLP prefers event-driven attention, but the native Herdr event substrate only emits signals; `events.subscribe` does not itself create a Supervisor inference turn.

**Target core:** Supervisor is attached by Human/Launcher governance setup and uses official/native Herdr read/wait/event observation while active. Lead/Peer have no responsibility to wake/maintain Supervisor. Avoid polling loops.

**Automatic wake is a separate capability:** it may only be claimed when a real Supervisor-side bridge exists: `Herdr event → filter → agent.prompt Supervisor`. If present, the bridge must not reason/issue verdicts or own lifecycle/Assignment/acceptance.

**Do not build by default:** Herdr plugin, persistent Attention Router, long-lived event daemon. Reopen only if dogfood/product requirement proves on-demand Supervisor is insufficient.

---

### GAP-25 — “Route to the correct Lead” requires an explicit source; it cannot be inferred from a Herdr event

A Herdr event has runtime identifiers/provenance, but does not make SLP parentage first-class. An event such as `pane.agent_status_changed` does not itself say “which Lead this Peer belongs to”.

**Target core:** Supervisor attachment is scoped to **one active Lead** or carries explicit supervised-Lead/topology context at attach time; Supervisor uses that source to route attention. Do not infer Lead from pane adjacency, same workspace, or cwd. Multi-Lead/cross-reconnect automatic routing is not a core capability without explicit mapping; if that requirement appears, trigger §1.3 instead of assuming the event substrate provides semantic parentage.

---

### GAP-16 — Provider/model discovery is not equivalent to Paseo yet

**Target:** keep `herdr_harnesses` only for capability/model/config validation that is actually needed; never let an adapter manage process/session/lifecycle.

---

### GAP-22 — Recipe approval policy may disable a capability that requires approval (HD-003)

**Target:** recipe/config validation treats approval policy as a capability constraint; do not hard-code an incompatible policy; smoke the correct approval path when the project actually requires that capability.

---

### GAP-23 — Lead is not yet required to evaluate decomposition/topology before multi-scope delegation (HD-005)

**Target:** Lead records bounded outcomes, coupling/dependencies, and topology rationale before delegation. Splitting is optional; one Peer may receive multiple scopes only when they are sufficiently coupled into one bounded assignment.

---

### GAP-17 — Maintenance evidence is stale/split

**Target:** maintenance docs keep only the canonical contract/coverage knowledge still needed. Actionable live failures go into the project issue tracker; reproducible failures become regression scenarios/evals. Delete the checked-in `dogfood-issues.md` ledger if it only duplicates issue history/eval evidence; stale tests/docs/history do not define runtime.

---

### GAP-18 — CI creates false confidence for runtime invariants

**Target:** static tests prove contract/static behavior; live Herdr dogfood proves runtime behavior. Do not claim a mock/static test provides live confidence.

---

### GAP-26 — A recorded dogfood pass is not yet a repeatable eval

A real dogfood run is valuable for discovery but may still be one-off, operator/context-dependent, and does not show reliability across repeated runs.

**Target:** keep three evidence layers separate:

```text
deterministic unit/static contract test
    = code/schema/instruction contract

real Herdr dogfood
    = exploratory/live discovery on a real workflow

repeatable live eval
    = reproducible setup + real Herdr/agent + explicit invariant
      + defined grader + repeated runs + machine-readable result
```

A dogfood failure should be converted into a repeatable eval once the scenario is stable enough to reproduce. P0 orchestration behavior that depends on a real agent must not be considered regression-protected merely because there was one recorded dogfood pass. The eval runner is a dev/test harness, not production orchestration runtime, a semantic registry, or a lifecycle manager.

---

## P2 — open only when evidence requires it

### OPTIONAL-01 — Durable cross-session SLP registry

Implement only if recorded dogfood proves that active-task identity/parentage cannot be reliably recovered from current launch/Assignment/session context after resume/rebind. Native Herdr/provider session restore is only a runtime/conversation restore substrate; it does not itself restore SLP Assignment/parentage/ownership/candidate/attention semantics.

---

### OPTIONAL-02 — Automatic Supervisor wake / Attention Router

Implement only if a product requirement or recorded dogfood needs unattended supervision and on-demand Supervisor is insufficient. The minimal capability is Supervisor-side `Herdr event → filter → agent.prompt Supervisor`; Lead/Peer do not participate.

If correct-Lead routing exceeds the one-Supervisor↔one-active-Lead attachment scope, the bridge needs explicit topology mapping; do not infer SLP parentage from pane/workspace layout.

If this component is needed, **a raw socket subscriber or plugin event hook are both candidate implementations**, not a default conclusion.

---

### OPTIONAL-03 — Semantic journal

A full transcript DB is not required. Add a bounded semantic journal only if audit/recovery dogfood reveals a specific failure that existing Assignment/candidate/evidence artifacts cannot explain.

---

### OPTIONAL-04 — Detached Lead wake / async fan-in

Implement only if the product workflow truly needs the Lead to launch multiple Peers, then idle/detach and automatically be called back when an exact Assignment handback appears. Native `agent.wait/read` is sufficient for active collection but does not itself create a detached Lead inference turn. The smallest fix must separate delivery/wake from semantic verdict and must not become a lifecycle manager.

---

### OPTIONAL-05 — Silence/heartbeat safety net

Event-driven wake cannot detect “no event”. Add heartbeat/schedule only when a recorded failure shows that a stalled agent, forgotten follow-up, or review-queue silence requires periodic attention. Heartbeat must not become a polling “done yet?” loop and is not core DoD.

---

# 5. Execution protocol for the agent implementing the plan

Each phase must follow the same sequence:

- [x] Re-read **Non-negotiable implementation rules**.
- [x] Inspect `git status`, current tree, and relevant callers before editing.
- [x] Run relevant baseline checks before changes.
- [x] Read only the sources of truth needed for the phase; do not pull all docs into the prompt if unnecessary.
- [x] Modify canonical files; do not create parallel milestone/version implementation.
- [x] Add/change tests by invariant/behavior, not by phase.
- [x] Run focused tests first, full CI-equivalent checks afterward.
- [x] Delete temporary files/shims that are no longer needed before marking the phase complete.
- [x] Inspect `git diff --check` and `git diff --stat`.
- [x] Run the naming/hygiene gate on changed files/symbols.
- [x] Mark the checklist in **this plan file** if the workflow allows; do not create a separate progress artifact.
- [x] If a premise does not hold, return `REOPEN_REQUEST` with evidence instead of silently creating a workaround.

---

# 6. Phase 0 — Establish baseline and guard against artifact pollution

**Goal:** create safety rails before changing the architecture; do not materially change runtime behavior.

## Checklist

- [x] Record current `git status`; preserve unrelated changes.
- [x] Run all current checks:
  - [x] `python3 -m unittest discover -s tests -v`
  - [x] `python3 scripts/render_coverage.py --check`
  - [x] `python3 scripts/context_budget.py --check`
- [x] Audit current tests to determine which tests verify the current architecture and which verify legacy run/pack/deliver behavior.
- [x] Add/extend a repository hygiene test to forbid milestone/version naming in new/changed source/test artifacts and Python symbols, with clear exceptions for external schema/version literals.
- [x] Add an architecture assertion that two generic Herdr runtime seams must not exist after migration.
- [x] State clearly in maintainer docs that phase naming exists only in the plan, not in the architecture.
- [x] Do not create new implementation in this phase beyond genuinely needed safety/test guards.

## Acceptance

- [x] Baseline failures (if pre-existing) are clearly recorded and not hidden by the refactor.
- [x] The hygiene test catches at least bad fixture/example names such as `phase1_test.py`, `runtime_v2.py`, `build_assignment_v2` without forbidding legitimate schema version literals.
- [x] Full CI-equivalent checks have no regressions beyond expected test updates.

---

# 7. Phase 1 — Make official Herdr skill the only generic agent-operation contract

**Goal:** migrate Launcher/Lead/Supervisor to the official Herdr operating path, prove focused smoke, then **retire the generic `herdr_runtime.py` seam in this phase** so later phases no longer have two runtime paths in parallel.

## Checklist

### Setup / prerequisite

- [x] Update setup/preflight to verify `HERDR_ENV=1` in the appropriate Launcher/role context.
- [x] Verify the installed Herdr binary supports the official skill (`herdr --skill`) and required CLI commands.
- [x] Document the official Herdr Agent Skill as the canonical Herdr operating reference for Launcher/Lead/Supervisor.
- [x] Do not vendor a stale copy of the official `herdr` skill if the release-matched `herdr --skill` can be used; if the environment requires installation, setup must clearly guide/verify installation.
- [x] Treat provider approval policy as a recipe capability: validate configured native args instead of defaulting to `--ask-for-approval never`.
- [x] For a recipe/tool surface that needs an approval-gated MCP/tool, prove compatible policy through smoke/preflight; if policy is fixed at process startup, a config change requires recreating the agent session.
- [x] Do not treat MCP startup failure as discovery/credential failure before checking approval-policy compatibility.

### Task launch

- [x] Rewrite `references/launcher/task-launch.md` so the Launcher uses official Herdr operating primitives instead of `python3 scripts/herdr_runtime.py start`.
- [x] Launch Lead using the exact configured recipe/kind/native args from project config.
- [x] A new pane must be assigned at least:
  - [x] canonical project root;
  - [x] `HERDR_ORCHESTRATOR_ROLE=lead`;
  - [x] required project-root context;
  - [x] no-focus default.
- [x] The Human task must be passed verbatim in semantics/text; do not `.strip()` or remove `$herdr-orchestrator` from the task for routing.
- [x] Task/Assignment submission must avoid shell interpolation. Use direct argv invocation or the official socket/API equivalent; do not construct a shell command from task text.
- [x] If a small helper is necessary to render Assignment → prompt text and submit safely, place it in the existing canonical owner (prefer `herdr_orchestrator.py`) and limit its responsibility to **render/submit + delivery result/Herdr IDs**; the helper must not wait/manage lifecycle/session/pane.
- [x] Re-entry guard continues to rely on role environment, not scanning task text.
- [x] Failure ownership:
  - [x] new split/pane but process not established → clean up only the newly owned pane when provably safe;
  - [x] agent/process exists but is blocked → preserve it and expose blocked evidence;
  - [x] prompt delivery ambiguous/times out → inspect before explicit follow-up, do not blind retry, do not destroy the pane merely because acknowledgement is ambiguous;
  - [x] do not touch existing topology.

### Lead operation

- [x] Update the Lead profile to use the official Herdr skill for pane/agent operations.
- [x] Remove “provided runtime operation” references pointing to `herdr_runtime.py`.
- [x] Lead must still choose the configured recipe from SLP project config; the official Herdr skill must not replace recipe/model policy on its own.
- [x] Lead must not create another Lead/Supervisor.

### Supervisor launch

- [x] Rewrite the **Human/Launcher governance attachment path** to launch the configured Supervisor using Herdr native/official skill primitives.
- [x] Attachment carries explicit supervised Lead/scope for the core topology; do not infer target Lead from pane/workspace layout.
- [x] Lead/Peer must not be responsible for creating/activating/waking/maintaining Supervisor.
- [x] Preserve the read-only/project authority envelope from SLP policy.

### Peer capability boundary

- [x] Peer profile must not load/use the official Herdr orchestration skill as a generic subagent launcher.
- [x] Peer receives only bounded assignment + task-local technical skills/capabilities.
- [x] If the agent platform globally exposes `$herdr`, the role profile must explicitly deny orchestration and later dogfood must check whether stronger enforcement is needed.

### Retire generic runtime seam immediately after smoke

- [x] After focused Launcher/Lead/Supervisor smoke of the official path passes, migrate/remove remaining callers to `scripts/herdr_runtime.py`.
- [x] Delete `skills/herdr-orchestrator/scripts/herdr_runtime.py` in the same bounded change; do not let this file survive through Phase 2–4 as an alternate runtime path.
- [x] Rewrite/delete tests that assert `herdr_runtime.py` is the canonical runtime seam.
- [x] Keep unrelated legacy `init-run/pack/deliver/ledger` cleanup for Phase 5 only if it cannot be deleted in the same change; those paths must not call the generic Herdr runtime wrapper again.

## Acceptance

- [x] A fresh Launcher can start Lead through the official Herdr operating path.
- [x] Lead can start/prompt/wait/read Peer through the official Herdr operating path + configured recipe.
- [x] Supervisor can be started separately with the configured recipe.
- [x] A recipe requiring approval-gated capability is not launched with incompatible `never` policy; an approval-capable smoke path is proven when that capability is in project requirements.
- [x] A task containing literal `$herdr-orchestrator` at the beginning/middle/end does not cause the spawned Lead to re-enter the Launcher route.
- [x] Task preservation test covers at minimum single/double quotes, backtick, literal `$()`, backslash, multiline, and leading/trailing whitespace without shell-evaluating the content.
- [x] No-focus behavior remains correct.
- [x] Blocked-agent/startup/prompt-ambiguity cases preserve the ownership/cleanup semantics above.
- [x] `herdr_runtime.py` has been deleted and no caller/test treats it as the canonical runtime seam before Phase 2 begins.
- [x] No new generic operation is hard-coded merely to rename `herdr_runtime.py`.

---

# 8. Phase 2 — Formalize SLP contracts without new runtime infrastructure

**Goal:** formalize the semantics Herdr does not own at the smallest contract level; do not build a new database/plugin/control-plane.

## Required contract concepts

At minimum, it must be possible to represent/render/verify:

```text
Role + authority
Assignment
Parent/owner relationship
Disposition
Moving-scope ownership
SemanticOutcome
Candidate
Supervisor attention/escalation contract
```

It is not required that each concept = one file/class. Prefer the smallest cohesive data/template/reference.

## Checklist

### No-infrastructure guard

- [x] Do not add a Herdr plugin in the core refactor.
- [x] Do not add a durable SLP registry/database, semantic journal service, or event daemon.
- [x] Do not create a repo-local run tree/receipt/transport tree under a new name.
- [x] If implementation appears to need persistent/shared semantic state, stop and use the §1.3 evidence gate instead of adding it speculatively.

### Identity / parentage in active orchestration

- [x] Launcher/Lead role context is explicit enough to distinguish the current Lead/Supervisor/Peer relationship.
- [x] Human/Launcher Supervisor attachment carries explicit supervised Lead/scope for the core one-active-Lead supervision topology.
- [x] Lead-created Peer Assignment/launch context records parent/owner relationship explicitly.
- [x] Do not infer parent from same workspace, pane adjacency, or cwd.
- [x] Moving the pane does not itself change the semantic role/assignment relationship in the active task.
- [x] Native Herdr/provider session restore must not be used as proof that Assignment/parentage/ownership/candidate/attention semantics have recovered.
- [x] Durable identity/orchestration recovery across arbitrary future session/restart **is not Definition of Done** unless an observed failure requires it.

### Assignment

- [x] Assignment has a stable ID within the task/project orchestration scope.
- [x] Assignment contains at minimum:
  - [x] objective;
  - [x] owned scope;
  - [x] exclusions;
  - [x] authority/write boundary;
  - [x] disposition;
  - [x] selected recipe/profile;
  - [x] verification direction;
  - [x] relevant dependencies;
  - [x] relevant language constraints;
  - [x] candidate binding when it is a review assignment;
  - [x] topology/decomposition rationale reference when the assignment is created from a multi-scope request.
- [x] Prompt is rendered from Assignment + Role Profile + allowed Workspace Protocol context.
- [x] Do not parse a prose prompt backward to construct an Assignment.
- [x] Assignment representation is inspectable/testable without a persistent database.

### Disposition

- [x] `role=peer` and `disposition` are two different fields.
- [x] Reviewer/Architect/Engineer use the same thin Peer invariant profile; disposition comes from Assignment.
- [x] Recipe selection is independent of disposition.

### Language

- [x] Live orchestration language and artifact language resolve deterministically from project config/protocol.
- [x] Lead/Supervisor receive the full policy when within their mandate.
- [x] Peer receives only applicable constraints but does not lose the language requirement needed for output.

## Acceptance

- [x] Lead → Peer delegation carries explicit parent/owner + assignment identity independent of pane adjacency.
- [x] Assignment is inspectable/testable outside the terminal transcript.
- [x] Engineer/Architect/Reviewer differ by disposition, not by copied profiles.
- [x] No plugin/new daemon/durable registry/run directory appears.
- [x] If a contract cannot be achieved without persistent infrastructure, there is `REOPEN_REQUEST` + dogfood evidence instead of speculative implementation.

---

# 9. Phase 3 — Operationalize ownership, candidate, semantic outcome, and acceptance chain

**Goal:** move important invariants from prose-only into operational/inspectable contracts and observable behavior without requiring a semantic runtime service.

## Checklist

### One writer per moving scope

- [x] Define a canonical logical scope representation sufficient for one Lead orchestration; do not use fuzzy/NLP overlap guessing.
- [x] Every write Assignment must declare explicit `owned_scope`; Lead maintains the active delegation map in its own orchestration reasoning/context and checks overlap before delegation.
- [x] Overlap must reject delegation or require Lead to explicitly reconcile/integrate the boundary.
- [x] Reviewer/read-only work does not claim writer ownership.
- [x] Worktree isolation is used when concurrent writers are valid but does not replace the logical ownership contract.
- [x] Core tests/dogfood prove **Lead behavior** blocks overlap within one active orchestration; do not claim atomic/cross-Lead enforcement without shared state.
- [x] Do not create an OS-temp/shared lock/ownership database merely to machine-enforce the invariant; only open infrastructure when live collision evidence triggers §1.3.

### Stable candidate

- [x] Candidate has a stable ID in the review flow.
- [x] Prefer an exact Git commit.
- [x] If not using a commit, the snapshot must be explicitly frozen + reproducible; a digest of a mutable worktree is insufficient.
- [x] Reviewer Assignment must bind the exact candidate.
- [x] Engineer changes after review → old candidate remains immutable; create a new candidate.
- [x] Lead does not accept a review of candidate A for an artifact that has mutated into B.

### Semantic Peer outcome

- [x] Formalize exact outcomes: `COMPLETE`, `REOPEN_REQUEST`, `DEPENDENCY_REQUEST`, `BLOCKED`.
- [x] Handback must carry the exact `assignment_id` + appropriate evidence/impact/need.
- [x] Do not automatically map Herdr `done` to `COMPLETE`.
- [x] Do not automatically map Herdr `blocked` to SLP `BLOCKED` if Peer has not provided semantic evidence.
- [x] Default outcome transport is structured Peer handback through the normal agent communication/read path; no persistent outcome database is required.
- [x] Distinguish collection mode: an active Lead may `wait/read/inspect` handback; a detached Lead must not be assumed to wake automatically when Peer lifecycle/outcome changes.

### Prompt delivery vs assignment completion

- [x] Define `prompt submitted` and `assignment completed` as two different facts.
- [x] Do not use `herdr agent prompt --wait` as acknowledgement for a specific assignment/turn.
- [x] Prompt/follow-up carries the exact `assignment_id`.
- [x] Assignment completion comes only from matching structured handback/evidence for `assignment_id`; lifecycle settle only triggers inspect.
- [x] Timeout/stall after submission does not automatically authorize resend; caller inspects current output/state before explicit follow-up.
- [x] If the agent is working when it receives the prompt, active-turn completion must not be mistaken for completion of the newly submitted prompt.

### Lossless handoff

- [x] Remove dependency on a fixed 120 terminal lines.
- [x] Use appropriate official Herdr read behavior + structured handback contract.
- [x] Inline handback must be bounded; large evidence must not be stuffed entirely into the terminal result contract. If full evidence cannot be read reliably through the normal read path, Peer writes Markdown/artifact to a task-owned/project-approved or temp path and the handback returns the reference/path.
- [x] File/path fallback is only evidence transport; it does not become a semantic journal/run tree.
- [x] Continuation routes back to the same Engineer when the correction belongs to the same ownership.

### Lead operating knowledge

- [x] Wire `references/lead/topology.md`, `peer-lifecycle.md`, `candidate-and-verdict.md`, and relevant anti-pattern cards through a selective/on-demand contract.
- [x] Critical invariant is reachable from Lead context.
- [x] Do not dump the entire reference library into every Lead prompt.

### Acceptance chain

- [x] Engineer proof, Reviewer falsification, Lead verdict, and Human-only decision remain distinct.
- [x] Lead verdict binds the exact candidate + actual verification evidence + unresolved findings/residual risk.
- [x] Herdr lifecycle state is not used as project acceptance.

## Acceptance

- [x] Two overlapping write assignments in the same Lead orchestration are blocked/reconciled by the Lead before concurrent mutation, including after bounded context growth/handbacks/corrections according to the dogfood scenario; this acceptance does not claim cross-Lead atomic exclusion.
- [x] Reviewer reviews only the exact immutable candidate.
- [x] Mutation after review invalidates the applicability of the old review.
- [x] Peer can REOPEN the premise and the **active Lead collection flow** receives the correct matching `assignment_id`; detached automatic Lead wake is not claimed without a wake mechanism.
- [x] Prompt timeout/stall does not create blind duplicate instruction.
- [x] A multi-scope request has topology rationale and bounded Peer Assignment.
- [x] `done`, tests pass, Reviewer approve do not automatically become project acceptance.
- [x] A persistent semantic service is not required to pass the scenarios above; if required, trigger §1.3.

---

# 10. Phase 4 — Connect Supervisor using native Herdr observation first

**Goal:** correct Supervisor to the proper role model and prove **on-demand/native observation** is the core path. Continuous event-driven supervision (`event → automatic wake`) is a separate capability, added only when scope/evidence truly requires a wake bridge.

## Checklist

### Supervisor behavior

- [x] Remove rule “Supervisor remains invisible to Lead”.
- [x] Supervisor has a sanctioned channel to send an evidence-backed open question to the **correct Lead**.
- [x] Supervisor may relay an explicit Human decision to Lead.
- [x] Owner-only issue routes to Human.
- [x] Supervisor does not directly modify project code, claim moving scope, spawn Peer, issue a binding architecture verdict, or provide project acceptance.

### Core A — Human/governance-attached on-demand Supervisor

- [x] Supervisor is attached by the **Human/Launcher governance path**; Lead/Peer do not activate, wake, or maintain Supervisor and do not need to know whether Supervisor is running.
- [x] Attachment carries explicit supervised Lead/scope; core routing to the “correct Lead” is based on attachment context, not inferred from Herdr event/pane adjacency/workspace/cwd.
- [x] Supervisor uses the official Herdr Agent Skill to inspect relevant Lead/Peer output and workspace evidence while Supervisor is active.
- [x] Core observation path uses bounded `wait/read/inspect`. Native event primitives are used in active observation only when an appropriate caller/integration already exists; core does not require the coding agent to build an `events.subscribe` subscriber merely to satisfy observation wording. Do not poll all agents in a default loop.
- [x] Event/lifecycle signal only triggers attention/inspect; it does not itself create an SLP verdict.
- [x] Context sent to Lead must be bounded, evidence-backed, and must not dump transcript.
- [x] Core refactor **does not claim** that raw `events.subscribe` itself creates a Supervisor inference turn.

### Core B — Continuous automatic wake is optional

- [x] If the product requirement is truly unattended/continuous supervision, model the flow explicitly as `Herdr event → Supervisor-side thin wake bridge → agent.prompt Supervisor → Supervisor reasoning`.
- [x] Lead/Peer do not publish/wake/notify Supervisor; the bridge observes Herdr independently from the governance side.
- [x] Wake bridge only filters/routes/wakes; it does not issue verdicts or own lifecycle, Assignment, or acceptance.
- [x] Correct-Lead routing beyond one attached Lead requires explicit topology mapping; event runtime IDs must not be treated as SLP parentage.
- [x] Do not add a plugin/socket daemon/wake bridge in the core phase merely to satisfy abstract “event-driven” wording.
- [x] Open this component only through §1.3 when dogfood/requirement proves on-demand Supervisor is insufficient or there is evidence of a missed-attention failure.
- [x] Event wake and heartbeat are two different capabilities; do not add a heartbeat scheduler or semantic journal without independent failure evidence.

## Acceptance

- [x] Human/governance-attached Supervisor can inspect relevant active Lead/Peer through the official/native Herdr path without Lead/Peer needing to wake or maintain it.
- [x] Within the core one-active-Lead attachment scope, Supervisor resolves the target Lead from explicit attachment context and can ask Lead directly without manual Human relay.
- [x] Supervisor question is provisional/evidence-backed, not a disguised correction order.
- [x] Supervisor has no project acceptance path.
- [x] No polling loop becomes the primary monitoring mechanism.
- [x] Core acceptance passes **without plugin, persistent Attention Router, or automatic wake bridge**; continuous unattended supervision must not be claimed implemented if the bridge does not exist.

---

# 11. Phase 5 — Retire duplicated/legacy runtime architecture

**Goal:** after the target path has been proven, delete old architecture code/docs/tests instead of preserving compatibility indefinitely.

## Checklist

### Verify generic runtime seam was already retired

- [x] Phase 1 already deleted `scripts/herdr_runtime.py`; Phase 5 only audits `git grep` to ensure no caller/reference survives.
- [x] Do not create a replacement file named like `slp_runtime.py`, `runtime_new.py`, `herdr_runtime_v2.py` if the responsibility is effectively still generic Herdr control.

### Simplify orchestrator helper

- [x] Audit `herdr_orchestrator.py` function-by-function.
- [x] Keep project config/protocol validation and provider capability discovery that are still needed.
- [x] Delete `init-run`.
- [x] Delete run tree creation.
- [x] Delete pack/deliver/receipt transport.
- [x] Delete stage-assets if it no longer has a target responsibility.
- [x] Delete the semantic ledger implementation tied to the old architecture.
- [x] Delete duplicate process/workspace/session lifecycle code.
- [x] Do not keep compatibility commands unless Human explicitly requests backward compatibility; if needed, compatibility must have a removal criterion and must not become a second runtime.

### Other scripts

- [x] Audit `herdr_balanced_split.py`; delete it if the official Herdr skill has fully replaced its responsibility.
- [x] Keep `herdr_harnesses/**` primarily for model/recipe/config discovery-validation. Following the accepted §1.3 live-evidence gate, it may also contain a verified harness-specific runtime-compatibility projection; that projection carries execution facts only and does not own orchestration lifecycle.
- [x] Harness adapter must not start/manage persistent process/session outside Herdr.

### Accepted evidence-triggered compatibility deviations

The following narrow deviations were Human-accepted after observed live
failures. They are not a general runtime/control-plane design and must not be
extended without new §1.3 evidence:

- `start-peer` is the canonical safe-invocation exception for a configured Peer
  recipe after a live argv-fidelity failure. It validates and passes one native
  `herdr agent start` argv unchanged; it does not own pane creation, wait,
  read, session identity, or lifecycle.
- A runtime binding carries one role's already-observed execution context and
  pane identity when a harness loses ambient Herdr/helper context in native
  subprocesses. It is not a registry, control plane, authority source, or
  lifecycle manager.
- A selected adapter may render the binding only when that harness-specific
  compatibility requirement has been verified. The generic role contract
  references the adapter requirement rather than duplicating a Codex sandbox or
  IPC detail.

### Context-budget / coverage migration after retiring `pack`

- [x] Audit `scripts/context_budget.py` for `PACK_LAYERS`, `render == "pack"`, and `_validate_pack_route()` assumptions; move measurement to the canonical Assignment/prompt renderer that remains after the refactor.
- [x] Rewrite `tests/test_context_budget.py` for parity with the new canonical renderer; remove assertions that depend on `herdr_orchestrator.py pack`.
- [x] Audit `scripts/render_coverage.py`, `tests/test_coverage_manifest.py`, and coverage selectors/manifests to remove retired run/pack/deliver/ledger routes.
- [x] Do not keep the `pack` command merely so old context-budget/coverage tests stay green.

### Documentation

- [x] Update `SKILL.md`: remove “Use packaged `scripts/herdr_runtime.py`...”.
- [x] Update task launch docs to the official Herdr skill/native runtime boundary.
- [x] Update Supervisor attachment according to the connected model + native Herdr observation/event path; do not default to plugin/router.
- [x] Update Lead profile from “provided runtime operation” to SLP assignment + official Herdr operations.
- [x] Update the authoritative ownership/contract map in `maintenance/assignments-and-evidence.md`.
- [x] Delete `maintenance/dogfood-issues.md` from the target tree after transferring still-useful knowledge: actionable unresolved failures → project issue tracker; reproducible regression knowledge → scenario/eval/coverage; historical run-tree-only entries → Git history/closed issues. Do not create a checked-in replacement ledger such as `known-failures.md` if the issue tracker is already the backlog truth.
- [x] Remove stale references to run receipt/pack/ledger from README/tests/maintenance.

## Acceptance

- [x] `git grep` has no valid runtime caller/reference to `herdr_runtime.py`.
- [x] No current docs say run directory/receipt/pack/ledger is runtime truth.
- [x] No `init-run`, `pack`, `deliver` commands remain if they belong only to the retired architecture.
- [x] Only one runtime/control-plane truth remains: Herdr.
- [x] SLP contracts exist in role/protocol/Assignment/handback/evidence; a persistent semantic runtime is not required for the core flow to operate.

---

# 12. Phase 6 — Convert critical invariants into executable dogfood and repeatable live evals

**Goal:** reduce the gap between “static docs/tests are green” and “orchestration actually works”, while converting stable behaviors into repeatable live evals to measure regression/reliability instead of keeping only recorded one-off dogfood evidence.

> **Evidence status (2026-08-28):** runner/manifest was redesigned so it does not leak
> the rubric into the evaluated agent and must observe real topology. Claims requiring a new
> Luna live run or the `5/5` threshold are still **unverified**; static/dry-run
> checks must not be used to tick them.

## Checklist

### Coverage model

- [x] Reclassify `maintenance/orchestration-invariant-coverage.md` according to the target architecture.
- [x] Do not claim that static tests prove live behavior.
- [x] Keep the separation:
  - [x] deterministic unit/static contract tests;
  - [x] real Herdr dogfood scenarios;
  - [x] model/provider-dependent smoke where necessary.
- [x] Formalize the failure lifecycle: `dogfood/live use → issue tracker → reproducible regression scenario/eval → fix → eval pass → close issue`.
- [x] Do not use `maintenance/dogfood-issues.md` or an equivalent Markdown ledger as a failure database parallel to issue tracker/eval results.
- [x] Add a separate **repeatable live eval** layer; do not relabel one-off dogfood as an eval merely because it runs a real agent.
- [x] Document taxonomy in coverage/maintainer docs:
  - [x] `static/contract`: deterministic, does not claim live agent behavior;
  - [x] `dogfood`: exploratory or real workflow used to discover failure/gap;
  - [x] `live-eval`: reproducible setup, real Herdr/agent, explicit invariant, defined grader, repetitions, and machine-readable result.
- [x] When dogfood finds a reproducible failure, convert that failure into a live eval regression case instead of merely appending a maintenance note.

### P0 dogfood scenarios

At minimum, executable scenarios must exist for:

- [x] **Binding:** active Lead → Peer relationship and `assignment_id` remain explicit when pane movement/normal Herdr observation changes; do not infer from layout.
- [x] **Parentage:** Lead → Peer cross-worktree carries explicit parent/owner relationship in Assignment/launch context.
- [x] **Assignment:** Peer receives the correct objective/scope/exclusion/authority/disposition/language.
- [x] **Independence:** Peer can issue `REOPEN_REQUEST` with evidence.
- [x] **Ownership:** within one active Lead orchestration, overlapping explicit owned scopes are blocked/reconciled by Lead; the scenario does not claim cross-Lead atomic exclusion.
  - [x] Stress context retention: after Lead assigns scope A, interleave unrelated investigation, one or more Peer handbacks/corrections/follow-ups, and context growth/compaction if the environment supports it; Lead must still recognize that a new assignment overlaps A and reject/reconcile it.
  - [x] If ownership is lost through context growth/compaction, record the observed context-loss failure and trigger §1.3 `REOPEN_REQUEST`; do not silently add a store/registry in the same change.
- [x] **Candidate:** Reviewer reviews the exact immutable candidate; mutation creates a new candidate.
- [x] **Lead handback collection:** active Lead uses native `wait/read/inspect` to trigger/collect observation; Assignment is only considered handed back/completed when structured outcome contains matching `assignment_id`. A separate scenario confirms Peer settle/event does not automatically wake a detached Lead and core does not claim that capability.
- [x] **Large handback:** bounded outcome remains recoverable when evidence exceeds terminal-friendly size through an artifact/temp Markdown reference; collector must resolve/read the reference before evidence is considered valid. Temp-path fallback must not be claimed durable across restart/reconnect; do not create journal/run tree.
- [x] **Supervisor attachment/routing:** Supervisor is attached by the Human/Launcher governance path, Lead/Peer do not wake/maintain it; in core topology, attachment carries explicit supervised Lead to route evidence/question to the correct Lead without inferring from event/layout.
- [x] **Supervisor wake claim:** core does not claim automatic event wake; if a bridge exists in a follow-up, the bridge must be on the governance side and Lead/Peer do not participate.
- [x] **Authority:** Peer has no SLP authority/operating instruction to generically orchestrate; if raw Herdr is globally reachable, the scenario must not call this a technical ACL. Supervisor does not accept the project.
- [x] **Acceptance:** Herdr `done` does not automatically become SLP acceptance.
- [x] **Task text:** literal `$herdr-orchestrator` in any position does not trigger spawned-role re-entry; quotes/backticks/`$()`/backslash/multiline/leading-trailing whitespace are preserved according to the contract without shell evaluation.
- [x] **No semantic infrastructure dependency:** restricted/workspace-write Lead can still orchestrate without Git-common-dir permission or plugin state for bookkeeping.
- [x] **Approval capability:** approval-gated MCP/tool runs under a compatible recipe policy; incompatible `never` policy is rejected by preflight or flagged before launch.
- [x] **Prompt correlation:** submitting a prompt to a working/near-settled agent must not treat active-turn settle as completion of the new assignment; timeout does not cause blind resend.
- [x] **Decomposition:** multi-scope request requires Lead to record coupling/dependency/topology rationale; Peer receives a bounded assignment rather than an unexplained raw bundle.

### Repeatable live eval layer

Eval is a **dev/test evidence layer**, not SLP runtime infrastructure. Because the shipped artifact is a reusable skill, live eval must measure the behavior of the **skill after it is installed into a clean consumer project**, not run source-tree code directly and call that skill confidence.

#### System under test and install isolation

- [x] Define the live-eval system under test (SUT) as a tuple recorded in the result: current `herdr-orchestrator` skill build/checkout + installed Herdr version + release-matched official Herdr Agent Skill + agent kind/model/recipe + clean consumer project fixture + project config/`WORKSPACE_PROTOCOL.md`.
- [x] Each repetition starts from **fresh temp HOME/user scope + fresh copy of the project fixture**; do not reuse pane/worktree/project/evidence from the previous repetition.
- [x] Install current `herdr-orchestrator` into the consumer project using the **canonical project-local install path real users use**. Eval must not import/read the skill directly from the source repo as a shortcut.
- [x] When installing from current checkout/local path, materialize/copy the skill payload into the consumer project/user scope instead of symlinking to the source tree if the installer supports it; the goal is to catch real packaging/missing-file/reference-resolution regression.
- [x] Install the release-matched official Herdr Agent Skill from the installed Herdr contract (`herdr --skill` or canonical release-matched install path) in the same isolated eval environment; do not mix an arbitrary HEAD skill with a different Herdr binary version.
- [x] The eval environment must avoid contamination from global/user skills, global project config, or unrelated developer state; if full isolation is not feasible, the runner must detect/report external skill roots/config and the case must not be called hermetic.
- [x] Grader-only expectations/rubrics must not exist in project context that Lead/Peer/Supervisor can read unless they are themselves public task requirements; do not leak the expected answer/invariant trigger through fixture files.
- [x] Each repetition cleans up only eval-owned pane/process/worktree/temp HOME/project/result staging; do not `clean/reset` unrelated Human state.

#### Eval suite classes

- [x] Separate evidence classes to avoid using one score for every purpose:
  - [x] `install-materialization`: the skill can be installed project-locally, references/config resolve, and isolation is verified; do not overclaim runtime activation;
  - [x] `regression-orchestration`: known SLP invariants must have high reliability and are used as a release gate;
  - [x] `contract-evidence`: helper/artifact contracts are useful but have not yet proven the correct live decision point, so they are not a release gate;
  - [x] `capability-generalization`: new or difficult task/project used to find headroom/gap, report trend but not a hard release gate by default.
- [x] The initial suite in this plan separates materialization, contract evidence, and `regression-orchestration`; capability suite expands after the regression harness stabilizes.
- [x] Dogfood remains the source of discovery: a reproducible real failure → add/adjust regression eval; do not turn every exploratory dogfood task into a permanent eval.

#### Manifest and runner

- [x] Create `tests/evals/orchestration-evals.json` as the canonical live-eval manifest.
- [x] Eval manifest **references existing invariant/scenario IDs** from `tests/orchestration-scenarios.json` or the coverage manifest when appropriate; do not copy a second set of orchestration semantics merely for eval.
- [x] Each eval case declares at minimum:
  - [x] stable eval ID by behavior/invariant;
  - [x] suite class (`install-materialization`, `regression-orchestration`, `contract-evidence`, `capability-generalization`);
  - [x] invariant/scenario reference;
  - [x] fixture ID + clean-project seed requirements;
  - [x] user-visible task/input;
  - [x] agent kind/recipe requirements;
  - [x] install requirements/version metadata that must be captured;
  - [x] repetitions;
  - [x] functional grader;
  - [x] hard SLP grader(s);
  - [x] optional semantic/quality grader rubric;
  - [x] mechanism/evidence semantics clearly stating what will fail if the helper is correct but orchestration is wrong;
  - [x] pass threshold/release-gate status.
- [x] Create `scripts/run_evals.py` as a thin dev/test runner:
  - [x] create isolated temp HOME + fresh fixture project per repetition;
  - [x] install current skill payload into the project using the canonical project-local install path;
  - [x] install/verify release-matched official Herdr skill + installed Herdr version;
  - [x] prepare fixture Git history/config/`WORKSPACE_PROTOCOL.md` deterministically;
  - [x] invoke the skill through the **real consumer entry path** (`$herdr-orchestrator`/agent skill activation path), not by calling a private helper as a replacement for actual skill activation;
  - [x] use a real supported Herdr agent for cases marked `live`;
  - [x] collect bounded observation/Assignment/handback/candidate/Git evidence;
  - [x] invoke graders outside agent context;
  - [x] clean up only resources owned by the eval run and preserve unrelated topology/state.
- [x] Runner must not own production pane/session/lifecycle semantics, must not maintain an SLP registry, and must not be imported/called from the normal `$herdr-orchestrator` runtime path.
- [x] Mock/fake Herdr may only be used for unit tests of runner/parser/grader; such a case must not be reported as `live-eval`.

#### Fixture strategy

- [x] Create at least three bounded consumer-project seeds, each repetition copied fresh before install/run:
  - [x] `orchestration-basic` — small deterministic project for activation, Assignment propagation, REOPEN, and prompt-correlation;
  - [x] `multi-scope` — independent + nested/coupled scopes to grade ownership/decomposition for both positive and negative cases;
  - [x] `candidate-review` — deterministic Git history/candidate mutations for Reviewer/candidate binding.
- [x] Fixture is a **consumer project**, not a mirror of the skill repo; it contains only the code/tests/config needed for the scenario.
- [x] Functional expected outcome must be graded from project-owned truth (tests/files/Git state), not transcript fluency.
- [x] Do not reuse mutable fixture output between repetitions; the seed must be reproducible or regenerated deterministically.

#### Grading contract

- [x] A trial only PASSes when **install/activation gate (if applicable) + functional task outcome + all hard SLP invariants of the case** all PASS. Quality score must not rescue a hard failure.
- [x] Prefer a deterministic grader when the invariant is observable through structured Assignment/handback, Git/filesystem, project tests, or Herdr state.
- [x] Functional grader prefers a deterministic project command/assertion (tests, expected files/diff/Git object) and runs from a clean consumer project.
- [x] Hard SLP grader covers at minimum the facts required by the case, for example exact `assignment_id`, role/parentage, ownership overlap, candidate identity, prohibited acceptance/authority behavior, and target Lead attachment.
- [x] LLM grader is used only for semantic judgment that cannot be reliably graded by a deterministic rule (for example quality of decomposition rationale or Supervisor open-question vs binding order); if used, it must have an explicit rubric, bounded grader input, and must not override deterministic hard FAIL.
- [x] Do not grade exact tool-call sequence when multiple valid paths can satisfy the invariant; grade observable contract/outcome unless the tool sequence itself is the invariant being checked.
- [x] A lifecycle settle, test pass, Reviewer approve, or fluent transcript must not itself make the grader PASS if the exact invariant has not been achieved.
- [x] Do not use one global aggregate score to hide regression. Report result/pass rate **per eval and per invariant**; a summary dashboard/text may exist, but the hard gate still evaluates each critical eval.

#### Reliability, positive/negative pairs, and thresholds

- [x] Regression eval must have a positive/negative pair when a one-sided grader can easily create extreme behavior. For example:
  - [x] nested/overlapping writer scopes → reject/reconcile; independent scopes → allow concurrent bounded writers;
  - [x] wrong premise → `REOPEN_REQUEST`; valid premise → do not REOPEN without reason;
  - [x] unrelated scopes → decompose; tightly-coupled bounded scopes → one Peer may be valid when rationale is clear.
- [x] Do not use `pass@k` where “one success is enough” for orchestration reliability. Critical P0 regression runs **5 repetitions and requires 5/5 (`pass^5`)** by default unless a different Human-approved threshold is recorded in the manifest with rationale.
- [x] A hard authority/ownership/candidate/correlation violation makes the repetition FAIL even if the final functional output is correct.
- [x] Capability/generalization suite reports pass rate/distribution and remains difficult enough to preserve improvement signal; do not force it to reach 100% like the regression suite.

#### Initial live eval suite

At minimum, add the following cases, reusing existing scenario/invariant setup instead of duplicating semantics:

- [x] `install-materialization-basic` — fresh consumer project installs current skill + release-matched Herdr skill, references resolve, and isolation does not use a source-tree shortcut; does not claim activation.
- [x] `assignment-propagation` — external grader binds the Herdr-observed Peer to the exact Assignment hash/owner and matching handback.
- [x] `ownership-*-contract`, `candidate-binding-contract`, `reopen-*-contract` — contract controls are named correctly and do not overclaim the live Lead decision point.
- [x] `prompt-correlation` — runner induces an old settled Peer then a newer Lead follow-up and grades exact old/new binding; timeout is not induced, so no retry claim is made.
- [x] `supervisor-routing` — after Lead/Peer evidence exists, Human-attached Supervisor inspects it and writes a bounded open question to the explicitly attached Lead; layout/event IDs are not evidence.
- [x] `decomposition-independent` and `decomposition-coupled` — independent requires two observed non-overlapping Peer Assignments; coupled requires exactly one observed Peer Assignment covering both scopes.

#### Baseline / control strategy

- [x] Runner supports an optional **previous released skill baseline** with the same Herdr version, agent recipe, fixture, task, and grader to detect regression caused by the refactor; baseline does not replace the absolute release threshold.
- [x] Runner supports an optional **ablation/control** (`official Herdr skill only` vs `official Herdr + herdr-orchestrator`) for selected capability cases to measure the SLP skill's value-add; ablation does not need to run on every PR/release.
- [x] Baseline/control result must record exact skill revision/version and environment metadata; do not compare runs with material model/Herdr/fixture differences without flagging the comparison as non-equivalent.

#### Secondary metrics

- [x] In addition to correctness, record bounded efficiency/operational metrics when actually measured: duration, observed Peer/Supervisor count, and runner prompt/follow-up count. Model usage, review cycles, candidate count, and max concurrency are `null` when unavailable, never misleading zeroes.
- [x] Efficiency regression is initially a warning/trend and must not override correctness; after the baseline stabilizes, Human may promote selected limits into a separate gate.

#### Result artifacts

- [x] Each run writes a machine-readable result under `.eval-results/` (gitignored), including at minimum eval ID, suite class, repetition, fixture, current skill revision/install mode, Herdr version, official-skill provenance, agent kind/recipe, functional result, hard-grader results, optional quality result, final PASS/FAIL, reason, duration, and bounded evidence references.
- [x] `.eval-results/` is ephemeral dev/test evidence; it must not be used as a runtime registry, semantic journal, agent database, or source of truth for active orchestration.
- [x] Do not persist full transcripts by default; retain only bounded evidence needed to reproduce/grade failure.
- [x] A failure must be traceable to the exact eval ID + invariant + repetition + fixture + installed skill revision + related Assignment/candidate/evidence.

### Test naming

- [x] Scenario/test names describe the invariant, not the phase.
- [x] If a dogfood runner is needed, use a canonical responsibility name such as `dogfood.py` / `orchestration-scenarios.json`, not `phase6-dogfood.py`.
- [x] Eval IDs/file/function names describe the invariant or eval responsibility; do not use `phase6-*`, `eval-v2`, `new-eval-runner`, or milestone naming.

### CI

- [x] Keep current deterministic checks:
  - [x] `python3 -m unittest discover -s tests -v`
  - [x] `python3 scripts/render_coverage.py --check`
  - [x] `python3 scripts/context_budget.py --check`
- [x] Do not add a plugin/schema CI path if the core refactor has no evidence-gated plugin implementation.
- [x] Real-agent dogfood must not be faked with a mock and then called live confidence.
- [x] If live dogfood cannot run in CI frequently, maintain an explicit command + evidence procedure, and CI only verifies scenario definitions/harness integrity.
- [x] Deterministic CI must validate eval manifest/schema/reference integrity and runner unit tests **without** calling those results live eval confidence.
- [x] Document the canonical real-eval command, for example `python3 scripts/run_evals.py --suite tests/evals/orchestration-evals.json`; exact CLI may be smaller if implementation proves sufficient responsibility.
- [x] Full live eval does not have to run on every PR if provider/time/cost is unsuitable, but there must be an explicit pre-release/refactor-completion procedure and bounded machine-readable result must be retained.
- [x] A provider-specific live-eval claim may only be recorded PASS when repetitions actually ran with the corresponding provider/recipe.

## Acceptance

- [x] Every P0 semantic invariant has a deterministic test or a clearly recorded live dogfood route.
- [x] Coverage manifest no longer references retired runtime architecture.
- [x] Dogfood failure can be traced to exact invariant/assignment/candidate/evidence, not only raw pane transcript.
- [x] P0 orchestration behavior that depends on a real agent has repeatable live eval; a recorded dogfood PASS is no longer the sole regression proof.
- [x] The initial live eval suite above exists with explicit grader/repetitions/threshold and can run through a canonical runner.
- [ ] On at least one supported agent kind, the initial P0 live eval suite reaches the manifest threshold; critical cases default to 5/5.
- [x] Machine-readable eval result can trace a failure to exact eval/invariant/repetition/evidence without requiring a runtime journal/database.

---

# 13. Phase 7 — Final architecture audit and cleanup

**Goal:** prove the refactor is complete as a coherent system, not a collection of patches.

## Checklist

### Runtime/control-plane audit

- [x] Herdr is the sole process/workspace/pane/session/lifecycle truth.
- [x] Official Herdr Agent Skill is the canonical generic Herdr operating instruction.
- [x] The repo does not duplicate a generic start/prompt/wait/read orchestration wrapper.
- [x] There is no mandatory plugin/durable semantic runtime in the core architecture.

### SLP semantic audit

- [x] Active orchestration identity/parentage is explicit, not inferred from layout.
- [x] Parent/owner relationship is first-class in the launch/Assignment contract.
- [x] Assignment is first-class.
- [x] Disposition is independent of recipe.
- [x] One-writer ownership is explicit and dogfood-observable in active Lead orchestration; do not claim shared atomic enforcement without shared state.
- [x] Semantic outcomes are executable.
- [x] Stable candidate is executable.
- [x] Acceptance chain preserves authority separation.
- [x] Human/governance-attached on-demand Supervisor native observation/attention path routes to the correct explicitly attached Lead/Human without overreach; Lead/Peer do not wake/maintain Supervisor; automatic wake is only claimed if an evidence-gated governance-side bridge actually exists.
- [x] Active Lead uses native `wait/read/inspect` to trigger/collect observation; exact Assignment correlation/completion comes only from matching structured `assignment_id`. Detached automatic Lead wake is not claimed without an explicit mechanism.

### Instruction architecture audit

- [x] Launcher only routes/setups/launches; it does not become Lead.
- [x] Lead receives sufficient critical operating knowledge but is not dumped the entire manual.
- [x] Peer context is bounded and does not load organization/control-plane noise.
- [x] Supervisor role does not overreach.
- [x] `WORKSPACE_PROTOCOL.md` remains the repo-specific strategy layer.
- [x] Initial task prompt remains the assignment-specific layer.

### Naming/artifact audit

- [x] No new production/test file is named `phase*`, `step*`, `*_v2`, `*-v2`, `new_*`, `*_new`, `*_final`, `*_refactored` merely because of the refactor.
- [x] No new function/class has a milestone/version suffix to distinguish old/new implementation.
- [x] No parallel old/new implementation remains alive because of migration.
- [x] No temporary migration/progress files remain in the repo.
- [x] Tests are named by behavior/invariant.

### Maintenance audit

- [x] README matches the target architecture.
- [x] `maintenance/dogfood-issues.md` has been deleted after moving actionable failures to the issue tracker and reproducible failures to scenario/eval/coverage; no replacement Markdown ledger is created.
- [x] `assignments-and-evidence.md` points to the correct authoritative sources.
- [x] `orchestration-invariant-coverage.md` matches the target scenarios.
- [x] Context budgets are updated intentionally; they do not increase merely because of prompt duplication.

### Eval audit

- [x] Coverage docs clearly distinguish `static/contract`, `dogfood`, `live-eval`; do not use one evidence type to overclaim another.
- [x] `tests/evals/orchestration-evals.json` does not duplicate existing SLP semantics; references resolve to the canonical invariant/scenario source.
- [x] `scripts/run_evals.py` is only a dev/test harness and does not create a second runtime/control plane.
- [x] Deterministic graders are preferred; an LLM grader, if present, must be explicit/rubric-bound.
- [x] `.eval-results/` is gitignored and is not used as active orchestration state.
- [x] P0 live eval reports pass rate per invariant, not only one aggregate score.

### Final verification

- [x] `python3 -m unittest discover -s tests -v`
- [x] `python3 scripts/render_coverage.py --check`
- [x] `python3 scripts/context_budget.py --check`
- [x] `git diff --check`
- [x] Naming/hygiene check passes.
- [ ] Focused live Herdr dogfood P0 passes on at least one supported agent kind.
- [x] Provider-specific claims are only recorded pass when smoke-tested with the corresponding provider.
- [x] Inspect final diff to ensure no unrelated Human changes were accidentally deleted.
- [x] Eval manifest/reference integrity checks pass.
- [ ] Canonical repeatable live eval command runs the initial suite on at least one supported agent kind and reaches manifest thresholds.
- [x] Eval cleanup leaves no orphan pane/process/worktree/temp artifact beyond owned eval resources.
- [ ] Live-eval run proves current skill is installed into a fresh consumer project/user scope and does not execute/import directly from the source tree.
- [x] Eval result captures minimum SUT provenance: skill revision/install mode, Herdr version, official Herdr skill provenance, agent kind/recipe, and fixture ID.

---

# 14. File-by-file migration map

| Current path | Target action | Reason |
|---|---|---|
| `skills/herdr-orchestrator/SKILL.md` | **Modify** | Route SLP; use official Herdr skill instead of packaged runtime; preserve re-entry/instruction layering |
| `references/launcher/preflight.md` | **Modify** | Verify Herdr/official skill/config prerequisites; remove assumptions from the old run runtime |
| `references/launcher/setup.md` | **Modify** | Setup project + role capability; preserve valuable model/envelope discovery |
| `references/launcher/task-launch.md` | **Rewrite in place** | Native/official Herdr launch path; no `herdr_runtime.py` |
| `references/launcher/supervisor-attachment.md` | **Rewrite in place** | Human/Launcher governance-attached Supervisor + explicit supervised-Lead scope + native observation; Lead/Peer do not wake/maintain |
| `references/launcher/workspace-protocol-authoring.md` | **Keep + adjust** | Repo-specific strategy still matches the boundary |
| `references/roles/lead.md` | **Modify** | Assignment/ownership/candidate contracts + official Herdr operations + selective references |
| `references/roles/peer.md` | **Modify** | Thin invariant + typed outcome + no orchestration authority |
| `references/roles/supervisor.md` | **Modify** | Native Herdr observation + sanctioned Lead attention channel |
| `references/lead/topology.md` | **Keep/wire** | Critical Lead operating knowledge |
| `references/lead/peer-lifecycle.md` | **Keep/wire** | Correction/review/lifecycle semantics |
| `references/lead/candidate-and-verdict.md` | **Keep/wire** | Stable candidate + acceptance semantics |
| `references/anti-patterns/**` | **Keep/wire selectively** | Preserve anti-pattern reasoning without dumping every card by default |
| `assets/config.toml` | **Modify if needed** | Keep recipe/model policy; add only truly semantic config fields, not runtime duplication |
| `assets/workspace-protocol-template.md` | **Modify if needed** | Keep 12-section strategy contract aligned with target semantics |
| `scripts/herdr_runtime.py` | **Delete in Phase 1 immediately after official-path focused smoke** | Do not let an alternate generic runtime seam exist through Phase 2–4 |
| `scripts/herdr_balanced_split.py` | **Audit; likely delete** | Generic pane balancing belongs to official Herdr operation knowledge |
| `scripts/herdr_orchestrator.py` | **Heavily simplify in place** | Keep project/config/model semantic helpers; delete run/pack/deliver/lifecycle duplication |
| `scripts/herdr_harnesses/**` | **Keep + narrow** | Provider/model/capability discovery, plus a verified harness-specific runtime-compatibility projection only when the §1.3 evidence gate has triggered |
| `scripts/context_budget.py` | **Modify** | Remove `pack` renderer assumptions; measure canonical Assignment/prompt renderer |
| `tests/test_context_budget.py` | **Modify** | Remove parity with retired `pack`; test canonical renderer |
| `scripts/render_coverage.py` | **Modify if selectors reference retired routes** | Remove run/pack/deliver/ledger coverage selectors |
| `tests/test_coverage_manifest.py` | **Modify if tied to retired routes** | Align coverage validation with target architecture |
| `plugin/**` | **Do not add by default** | Follow up only if the §1.3 evidence gate proves a persistent semantic/event component is truly needed; plugin is only one candidate |
| `maintenance/dogfood-issues.md` | **Delete** | Dogfood is discovery activity, not a checked-in failure DB; actionable failures live in the issue tracker, reproducible failures in scenario/eval/coverage, historical-only entries in Git/closed issues |
| `maintenance/assignments-and-evidence.md` | **Update** | Rebind authoritative ownership/evidence to Herdr runtime + SLP contracts |
| `maintenance/orchestration-invariant-coverage.md` | **Regenerate/update manifest** | Reflect executable target invariants |
| `tests/test_runtime.py` | **Remove/replace behavior coverage** | Do not preserve tests for the deleted custom runtime wrapper |
| `tests/test_herdr_orchestrator.py` | **Refocus** | Test remaining config/semantic helper responsibilities, not retired commands |
| `tests/test_instruction_architecture.py` | **Strengthen** | Verify official-skill boundary, role disclosure, no duplicate runtime seam |
| `tests/test_package_flow.py` | **Refocus or delete stale cases** | Must test target install/setup flow only |
| `tests/orchestration-scenarios.json` | **Update** | Source of truth for target invariant/dogfood scenarios; live eval manifest references these IDs when applicable |
| `tests/evals/orchestration-evals.json` | **Create** | Declarative repeatable live-eval manifest with scenario/invariant refs, clean-install requirements, repetitions, graders and thresholds; no duplicate runtime semantics |
| `tests/evals/fixtures/**` | **Create** | Small deterministic consumer-project seeds copied fresh per repetition; current skill is installed into each fresh project before live execution |
| `scripts/run_evals.py` | **Create** | Thin dev/test-only real-Herdr eval runner; creates isolated HOME/project, installs current skill + release-matched Herdr skill, runs/grades/cleans eval without becoming production control plane |
| `.gitignore` | **Modify** | Ignore `.eval-results/` ephemeral machine-readable eval evidence |
| `tests/context-budgets.json` | **Update only if justified** | Keep prompt/context discipline after new wiring |

---

# 15. Explicit non-goals

Do not do these in this refactor unless evidence requires them:

- [x] Do not build a Herdr plugin merely to have somewhere to store SLP semantics.
- [x] Do not build a durable SLP agent registry/database in the core refactor.
- [x] Do not build a persistent Attention Router/event daemon in the core refactor.
- [x] Do not build a semantic journal service when Assignment/candidate/evidence artifacts are already sufficient for audit.
- [x] Do not create an ephemeral/OS-temp ownership registry merely to machine-enforce one-writer when the single-Lead contract + dogfood have not failed.
- [x] Do not turn safe prompt invocation into a generic submission/transport subsystem; a helper, if needed, must be bounded and must not own lifecycle.
- [x] Do not fork the Herdr daemon.
- [x] Do not clone the Paseo agent database/timeline.
- [x] Do not create a custom terminal multiplexer abstraction.
- [x] Do not create a process lifecycle manager.
- [x] Do not create a custom worktree manager when Herdr/Git is sufficient.
- [x] Do not persist full transcripts.
- [x] Do not create a generic message bus between agents.
- [x] Do not create a mandatory council framework for every task.
- [x] Do not hard-code every anti-pattern into a runtime state machine.
- [x] Do not build a dashboard/topology UI before core contracts are stable in dogfood.
- [x] Do not add a backward-compatibility layer for retired run/pack/deliver unless Human requests it.
- [x] Do not change architecture merely to keep old tests green; stale tests must be deleted/rewritten according to target invariants.
- [x] Do not build an eval database/service/dashboard merely to run this suite; local manifest + runner + machine-readable result is the default boundary.
- [x] Do not use the eval runner/result store as a production orchestration registry, message bus, semantic journal, or lifecycle manager.
- [x] Do not add an LLM grader for an invariant with a sufficiently clear deterministic grader merely to make the eval “AI-native”.
- [x] Do not call a source-tree helper directly and then claim it is a reusable-skill live eval; a live trial must go through consumer-project installation + real skill activation path.
- [x] Do not symlink the current source repo into the fixture to bypass packaging/install verification if the canonical installer can copy/materialize the skill payload.
- [x] Do not place eval expectation/rubric/hidden grader data in project context that evaluated agents can read.
- [x] Do not create a new checked-in failure ledger (`known-failures.md`, `dogfood-log.md`, etc.) if the project issue tracker is already the actionable failure backlog truth.

---

# 16. Definition of Done

The refactor is considered complete only when **all** of the following are true:

- [x] Core refactor is complete without requiring a Herdr plugin/durable semantic service; if an evidence-gated follow-up exists, it is separately scoped and does not block core DoD.
- [x] `herdr_runtime.py` no longer exists/has callers.
- [x] Generic Herdr operations rely on installed Herdr + official Herdr Agent Skill.
- [x] `herdr_orchestrator.py` no longer contains a run/pack/deliver/lifecycle control-plane clone.
- [x] There is no current run directory/receipt/semantic lifecycle ledger architecture.
- [x] Active SLP identity/parent/assignment relationship is explicit and not inferred from pane adjacency/cwd.
- [x] Parent/owner relationship is first-class in the active orchestration contract, not inferred from layout.
- [x] Assignment is first-class.
- [x] Peer disposition is first-class and independent of recipe.
- [x] Lead-level moving-scope ownership is explicit; overlap/reconciliation remains contract evidence until a focused live decision-point run proves it. Do not claim cross-Lead atomic enforcement without shared state.
- [x] Stable candidate binds the exact immutable target.
- [x] `COMPLETE`, `REOPEN_REQUEST`, `DEPENDENCY_REQUEST`, `BLOCKED` are real semantic outcomes.
- [x] Lead critical operating cards are not orphaned.
- [x] Human task is not semantically normalized/trimmed contrary to the contract and the submission path does not shell-evaluate task text.
- [x] Language constraints propagate to the correct role.
- [x] On-demand Supervisor is attached by the Human/Launcher governance path, uses native Herdr observation primitives when needed, and routes to the explicitly attached Lead; Lead/Peer have no responsibility to wake/maintain Supervisor; continuous automatic wake is not core DoD.
- [x] There is no mandatory Attention Router component; if one is later added, the router is on the governance side, must not issue verdicts, and must not infer SLP parentage from runtime layout.
- [x] Active Lead collection flow uses native `wait/read/inspect` to trigger/collect observation; exact Assignment handback/completion is only claimed when structured outcome has matching `assignment_id`. Detached automatic Lead wake is not core DoD.
- [x] Structured handback is bounded; large evidence has artifact/temp-path fallback without creating journal/run tree. Evidence path is valid only after collector can resolve/read it; temp fallback is scoped only to active orchestration, not a durable recovery mechanism.
- [x] Peer has no generic orchestration **authority/instruction**; do not claim technical ACL if raw Herdr remains globally reachable.
- [x] Supervisor has no project acceptance authority.
- [x] Herdr `done/idle/blocked` is not equated with SLP semantic outcome/acceptance.
- [x] Prompt submission/wait semantics are not equated with completion of the exact assignment; timeout does not trigger blind duplicate instruction.
- [x] Recipe approval policy is compatible with configured approval-gated capabilities and is smoke-tested when the project needs them.
- [x] Multi-scope delegation has recorded decomposition/topology rationale and bounded Assignment.
- [x] Core orchestration does not depend on plugin semantic state or Git-common-dir permission for bookkeeping.
- [x] P0 invariants have an executable dogfood path.
- [x] P0 orchestration behavior that depends on a real agent has repeatable live eval with explicit consumer-project install setup, grader, repetitions, threshold, and machine-readable result; a recorded one-off dogfood PASS is not the only regression proof.
- [x] Each live repetition runs from a fresh consumer-project fixture + appropriately isolated user/HOME scope, installs current `herdr-orchestrator` through the canonical project-local install path, and verifies the release-matched official Herdr skill; do not use source-tree execution/symlink shortcuts to claim skill confidence.
- [ ] Focused live smoke proves participant provenance and eval-owned Peer cleanup; then `supervisor-routing` and `prompt-correlation` prove their explicit interactions; only then run the full release-gate threshold suite.
- [x] Each critical regression trial only PASSes when functional task outcome + all hard SLP graders of the case PASS; a hard failure is not hidden by average/quality score.
- [ ] Initial critical live eval cases reach the manifest threshold on at least one supported agent kind; P0 defaults to 5/5 (`pass^5`) unless there is a different Human-approved rationale.
- [x] Positive/negative control pairs exist for invariants prone to one-sided overfitting such as ownership, REOPEN, and decomposition.
- [x] Eval result captures enough SUT provenance to reproduce/compare: installed skill revision/mode, Herdr version, official Herdr skill provenance, agent recipe/model scope, and fixture ID.
- [x] Eval runner supports previous-release baseline and optional Herdr-only ablation without using comparative score to lower the absolute P0 gate.
- [x] Eval runner/manifest/result artifacts do not create a second runtime/control-plane/semantic state; `.eval-results/` is only gitignored dev/test evidence.
- [x] `context_budget.py`/`test_context_budget.py` and coverage tooling no longer depend on retired `pack`/run routes.
- [x] Maintenance docs reflect the current architecture.
- [x] `maintenance/dogfood-issues.md` is no longer in the target tree; there is no replacement Markdown failure ledger duplicating issue tracker/eval evidence.
- [x] Full CI-equivalent checks pass.
- [x] Naming/artifact hygiene gate passes.
- [x] No new file/function/class has a phase/migration/version name merely to distinguish new implementation.
- [x] No parallel old/new implementation remains.
- [x] Final diff preserves unrelated Human changes.

---

# 17. Expected end-state in one sentence

> **Herdr runs and observes agents; the official Herdr skill teaches authorized roles how to operate Herdr; `herdr-orchestrator` defines SLP roles, authority, Assignment, ownership, candidate, handback, and acceptance contracts. Supervisor is attached by the Human/governance side independently of Lead/Peer; an event does not itself wake an agent, active wait/read does not imply detached wake, and runtime event IDs do not themselves create SLP parentage. Safe submission is only an invocation constraint, one-writer core is a Lead contract; dogfood is only a discovery activity; actionable live failures go into the issue tracker, reproducible failures become regression evals, while repeatable live eval installs the current skill into a fresh consumer project and measures functional outcome + hard SLP invariants through real Herdr/agent; no parallel checked-in dogfood failure ledger is maintained, and new infrastructure is added only when live evidence proves native Herdr + skill contracts are insufficient.**
