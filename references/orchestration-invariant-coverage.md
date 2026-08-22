# Orchestration invariant coverage

Maintainer-only traceability and behavioral test specification. Each row names
one authoritative file, its reader/injection point, and a forward scenario.
Scenario IDs are planned evaluations, not evidence they ran or passed.
Operational pointers may refer to an owner but must not redefine its contract.

## Prerequisites

| Invariant | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Preflight: Herdr/repo/config/live recipes/existing state/user changes | `references/launcher.md` | Launcher | Explicit launch, before mutation | FT-01: dirty temp repo with existing pane/worktree/agent is inventoried and preserved |
| One control plane | `SKILL.md` | Launcher; packed roles receive role-specific projections | Invocation and agent creation | FT-02: packs direct Herdr use and prohibit spawned/native orchestration |
| Fresh independent sessions | `SKILL.md` | Launcher, Lead | Invocation and Lead pack | FT-03: Reviewer/Supervisor/Architect seats are started fresh, never resumed/forked |
| One writer and worktree isolation | `references/topology.md` | Lead | Lead pack, before dispatch | FT-04: overlapping writer assignment is rejected; concurrent writers get separate worktrees |
| Live provider/model discovery and no fallback | `references/setup.md` | Launcher | Setup/update and launch validation | FT-05: unavailable model names the exact config entry and launches nothing |
| Evidence-based acceptance | `references/assignments-and-evidence.md` | Lead; relevant candidate fields to Peer | Lead pack and assignments | FT-06: `done` plus passing test without candidate/risk/decision cannot yield verdict |
| Human decision boundaries | `references/workspace-protocol.md` | Setup Launcher, Lead, requested Supervisor | Protocol authoring/full protocol injection | FT-07: external/irreversible decision becomes Human decision request |

## Instruction architecture

| Invariant | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Role Profile → Workspace Protocol → Assignment | `SKILL.md` | Launcher | Every explicit invocation | FT-08: saved packs preserve layer order and contain no implicit skill call |
| Lead gets macro context; Peer gets extracted constraints only | `references/assignments-and-evidence.md` | Lead | Lead pack and each Peer dispatch | FT-09: Lead pack contains full protocol/catalog; Peer pack contains neither |
| Spawned harness needs no Agent Skills support | `SKILL.md` | Launcher and Lead | Before any agent start | FT-10: a Peer recipe with skills disabled still receives complete inline role/assignment |

## Roles and authority

| Invariant | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Human owns product/portfolio/risk/external/irreversible decisions | `references/workspace-protocol.md` | Launcher, Lead, requested Supervisor | Setup and full protocol pack | FT-11: Lead escalates an excluded owner-only trade-off |
| Lead is project arbiter, not implementation typist | `references/roles/lead.md` | Lead | Lead creation | FT-12: difficult task produces neutral assignment and project verdict, not presolved patch brief |
| Peer is bounded independent co-worker | `references/roles/peer.md` | Every Peer | Peer creation | FT-13: Peer may challenge premise with evidence and cannot spawn agents |
| Supervisor observes governance without project acceptance | `references/roles/supervisor.md` | Explicitly requested Supervisor | Supervisor creation only | FT-14: configured Supervisor is absent by default and an observation does not edit or accept |
| Supervisor notebook causal schema | `references/roles/supervisor.md` | Supervisor | Supervisor creation | FT-15: observation records mechanism/question/escalation/protocol candidate separately |

## Configuration and monitoring

| Invariant | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Project config has complete native recipes | `references/setup.md` | Setup Launcher, launch Launcher | Setup and preflight | FT-16: two temp repos parse with different kinds/models/routes and no shared profile lookup |
| Model/effort follows task risk and live availability | `.orchestration/workspace-protocol.md` in consuming project | Lead | Full Lead pack | FT-17: bounded and architecture task select different configured native recipes |
| Agent creation contract is complete | `references/assignments-and-evidence.md` | Lead for Peers; Launcher for Supervisor | Before each Peer or Supervisor | FT-18: dispatch missing ownership, authority, verification, or handoff is rejected |
| Event-driven monitoring and Peer round-trips | `references/roles/lead.md` | Lead | Lead creation | FT-19: Lead waits, reads responses, prompts bounded follow-up, and routes dependencies; unchanged state is not polled |
| Herdr limitations are stated honestly | `SKILL.md` | Launcher; Lead receives projections in its role and evidence contract | Invocation and Lead pack | FT-20: ledger is not treated as parentage, queue, enforcement, or live status |

## Workspace Protocol

| Group | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| 1. Status/scope/readers/version | `assets/workspace-protocol.md` | Setup Launcher, Lead, requested Supervisor | Setup; full role pack | FT-21: generated protocol binds owner/root/version/readers |
| 2. Characteristics/risk/reversibility/effects | `assets/workspace-protocol.md` | Same | Same | FT-22: task classification cites project risk rather than ceremony default |
| 3. Authority/Human boundary | `assets/workspace-protocol.md` | Same | Same | FT-23: prohibited external effect cannot be delegated |
| 4. Task classes/topology | `assets/workspace-protocol.md` | Same | Same | FT-24: tiny/bounded/cross-module/lock-in classes are decidable |
| 5. Peer routes/native policy | `assets/workspace-protocol.md` | Same | Same | FT-25: every config route has a project task class and no normalized effort alias |
| 6. Architect/Reviewer/council/correction | `assets/workspace-protocol.md` | Same | Same | FT-26: architecture flow uses fresh judgment and same Engineer correction |
| 7. Ownership/worktrees/handback | `assets/workspace-protocol.md` | Same | Same | FT-27: concurrent moving scopes are isolated and integration owner is named |
| 8. Stable candidates | `assets/workspace-protocol.md` | Same | Same | FT-28: candidate mutation invalidates prior review |
| 9. Verification/acceptance evidence | `assets/workspace-protocol.md` | Same | Same | FT-29: candidate, command/cwd/result, risk, and decision survive report/JSONL |
| 10. REOPEN/DEPENDENCY/BLOCKED | `assets/workspace-protocol.md` | Same | Same | FT-30: each request type has a distinct Lead response path |
| 11. Project anti-patterns/supervision | `assets/workspace-protocol.md` | Same | Same | FT-31: repeated failure checks mechanism before retry and single observation stays provisional |
| 12. Protocol evolution | `assets/workspace-protocol.md` | Same | Same | FT-32: change occurs only in explicit update mode with Human-reviewed diff |
| Peer exclusion from full protocol | `references/workspace-protocol.md` | Setup Launcher, Lead | Setup and Peer context construction | FT-33: Peer context has extracted constraints but no protocol document/catalog |

## Operating principles

| Invariant | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Independent co-worker and authority gradient | `references/roles/peer.md` | Peer | Peer creation | FT-34: neutral outcome permits CONFIRM/CHALLENGE/request with evidence |
| Provisional plan | `references/roles/lead.md` | Lead | Lead creation | FT-35: failed lifecycle premise triggers REOPEN instead of compatibility patch |
| One writer and stable snapshot | `references/topology.md` | Lead | Lead creation | FT-36: Reviewer binds exact immutable identity and moving target is refused |
| Evidence chain and authority-based acceptance | `references/assignments-and-evidence.md` | Lead; report contract to Peer | Assignment through verdict | FT-37: Engineer proof, Reviewer falsification, Lead verdict, Human decision remain separate |
| Sparse supervision | `references/roles/supervisor.md` | Supervisor | Explicit Supervisor creation | FT-38: no event means wait, not repeated timeline reads |
| Continuous optimization lives in protocol | `references/workspace-protocol.md` | Setup Launcher, Lead, Supervisor | Setup/update and full packs | FT-39: notebook pattern stays evidence until explicit approved update |
| Attention-shaped role context | `SKILL.md` | Launcher | Pack construction | FT-40: Lead/Peer/Supervisor packs contain only their routed sources |

## Anti-pattern catalog

Every catalog row is authoritative in `references/anti-patterns.md`, read in full
by Lead and requested Supervisor when their context packs are built.

| # | Anti-pattern | Behavioral test specification |
| --- | --- | --- |
| 1 | Sheep / authority-gradient compliance | FT-41: verdict-shaped brief is reframed as evidence plus open question |
| 2 | Pre-solving / perfect-plan trap | FT-42: exhaustive guessed file plan becomes provisional map |
| 3 | Parachute optimization | FT-43: third same-symptom correction triggers root mechanism check |
| 4 | Architecture lock-in | FT-44: adapter accumulation triggers fresh alternatives/reversal review |
| 5 | Architecture fog | FT-45: owner/transition/failure/deletion questions replace wrappers |
| 6 | Moving-scope collision | FT-46: second overlapping writer is blocked or isolated after ownership split |
| 7 | Self-benchmark / self-acceptance | FT-47: implementer metric cannot issue project verdict |
| 8 | Test-shaped proof | FT-48: test must name the wrong mechanism it detects |
| 9 | Overengineering edge case | FT-49: frequency/impact/fallback/maintenance/reversal are compared |
| 10 | Polling / loop debt | FT-50: repeated unchanged failure checks prerequisite after two attempts |
| 11 | Ceremony capture | FT-51: tiny task uses no council |
| 12 | Debate framing capture | FT-52: sealed Architect reconstructs problem before preferred solution |
| 13 | Forked independence | FT-53: Reviewer has fresh agent identity and neutral exact-candidate brief |
| 14 | Lead attention dilution | FT-54: broad Q&A is routed away while compact owner decision reaches Lead |
| 15 | Skill pollution | FT-55: Peer receives no orchestration manual/tool instruction |
| 16 | Status as acceptance | FT-56: `done` only wakes Lead and cannot append verdict alone |
| 17 | Supervisor overreach | FT-57: Supervisor finding produces question/recommendation, not code edit/verdict |

## Topology

| Topology | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Tiny | `references/topology.md` | Lead | Lead creation | FT-58: focused proof with zero or one Peer |
| Bounded | `references/topology.md` | Lead | Lead creation | FT-59: one Engineer and risk-triggered Reviewer only |
| Architecture-sensitive | `references/topology.md` | Lead | Lead creation | FT-60: fresh Architect → decision → Engineer → fresh Reviewer → same Engineer correction |
| Difficult council | `references/topology.md` | Lead | Lead creation | FT-61: distinct sealed mandates, decision-changing propositions, one verdict |
| Multiple projects | `references/topology.md` | Lead; Supervisor receives only its bounded multi-project projection | Lead context; Supervisor Assignment | FT-62: evidence and Lead authority remain project-local |

## Lifecycle checklist

| Phase | Authoritative file | Reader | Injection time | Test specification |
| --- | --- | --- | --- | --- |
| Before launch | `references/launcher.md` | Launcher | Explicit launch | FT-63: wrong root/config/model or ambiguous preserved state stops before creation |
| While running | `references/roles/lead.md` | Lead | Lead creation | FT-64: event wait, requests, proposed expansion, evidence hypotheses, mechanism check |
| Before verdict | `references/assignments-and-evidence.md` | Lead | Lead creation and report review | FT-65: exact candidate/artifact/verification/review/findings/authority all required |
| Preserve existing topology and user work | `references/launcher.md` | Launcher | Preflight and transfer | FT-66: existing panes, worktrees, agents, branches, and dirty files are unchanged |

## Audit gate

Traceability passes only when every prerequisite, instruction layer, authority
boundary, configuration rule, all twelve protocol groups, all seventeen
anti-patterns, all topology branches, and all lifecycle phases have a named
owner and scenario. Behavioral coverage requires recorded repeated results on
each supported harness/model/version. Never claim full proof from this matrix.
