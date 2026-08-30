# Anti-pattern response card

This is the disclosed `anti-pattern-details` card. Its signals live in the
initial signal index. After a signal triggers this card, use the matching
mechanism as a hypothesis, gather evidence, and apply its response.

## 1. Authority-gradient compliance

**Mechanism:** A verdict-bearing brief makes the Peer optimize for authority.
**Response:** Restate evidence and an open question; invite `CONFIRM`, `PARTIAL`,
`CHALLENGE`, or `BLOCKED`. Require evidence from agreement and opposition.

## 2. Pre-solving / perfect-plan trap

**Mechanism:** Unverified assumptions became implementation constraints.
**Response:** Reduce the plan to a provisional outcome, boundary, and risk map;
restore the Peer's right to reopen premises.

## 3. Parachute optimization instead of brakes

**Mechanism:** Local optimization protects one failed shared foundation.
**Response:** Stop symptom patches and identify the root mechanism that creates
the whole failure sequence. Severity labels do not outrank dependency
structure: a lower-priority prerequisite or root mechanism can require repair
before a higher-priority symptom.

## 4. Architecture lock-in

**Mechanism:** Strong implementation delays visible failure of a weak base.
**Response:** Commission fresh architecture review of alternatives, strongest
counterargument, and reversal conditions; recheck irreversible choices.

## 5. Architecture fog

**Mechanism:** Wrappers postpone the missing ownership decision.
**Response:** Name owner, transition, and failure semantics concretely; apply the
deletion test: which behavior disappears with the abstraction?

## 6. Moving-scope collision

**Mechanism:** Ownership and candidate identity are ambiguous.
**Response:** Assign one writer, isolate concurrent writers, require explicit
handback, and review one exact stable candidate.

## 7. Self-benchmark / self-acceptance

**Mechanism:** Metric and implementation share a blind spot.
**Response:** Human or Lead fixes the success boundary; use independent review
for consequential decisions while the Engineer proves its writes.

## 8. Test-shaped proof

**Mechanism:** Verification checks the chosen shape rather than the mechanism.
**Response:** Identify which wrong mechanism must make the check fail; add the
needed integration, migration, cancellation, or Human evidence.

## 9. Overengineering an edge case

**Mechanism:** Completeness substitutes for proportional risk reduction.
**Response:** Compare frequency, impact, fallback, maintenance cost, and reversal
cost before continuing.

## 10. Polling / loop debt

**Mechanism:** Activity substitutes for new information.
**Response:** Wait on events. After two identical failures, inspect prerequisite,
quota, authentication, authority, and shared mechanism.

## 11. Ceremony capture

**Mechanism:** Agent count creates false confidence and process eclipses proof.
**Response:** Return to the smallest useful topology; retain only independent,
decision-changing seats.

## 12. Debate framing capture

**Mechanism:** Challengers inherit the preferred solution before reconstructing
the problem.
**Response:** Give a fresh Architect the neutral problem first; seal reports when
genuine divergence matters.

## 13. Forked independence

**Mechanism:** A fork retains premise, framing, and bias.
**Response:** Start a fresh session with a neutral brief and exact candidate.

## 14. Lead attention dilution

**Mechanism:** The Lead shifts from coordination to explanation and defense.
**Response:** Use an explicitly requested Supervisor or ordinary advisory
session for broad Q&A, then relay compact owner decisions.

## 15. Role pollution

**Mechanism:** Available unrelated instructions redirect role attention.
**Response:** Keep macro context with Lead, governance with Supervisor, and only
bounded technical context with Peer.

## 16. Status as acceptance

**Mechanism:** Lifecycle attention is confused with evidence and authority.
**Response:** Wake the owner, then inspect candidate, artifact, verification,
review, unresolved risk, and acceptance authority.

## 17. Supervisor overreach

**Mechanism:** Governance becomes a competing Project Lead.
**Response:** Return to evidence-backed questions, owner-decision relay, or a
proposed fresh-Lead handoff; intervention requires explicit Human authority.

## 18. Contract-minting red test

**Mechanism:** A new test, mock, or fixture invents an API, data shape, or
behavior that no contract owner authorized, then production is changed to obey
that assumption.
**Response:** Do not change production merely to satisfy the invented premise.
Resolve contract ownership; use `REOPEN_REQUEST` or `DEPENDENCY_REQUEST` until
the contract is stable, then freeze the agreed behavior as a test.

## 19. Foundation ballooning

**Mechanism:** A missing or weak foundation remains unexamined while wrappers,
compatibility layers, duplicate state, adapters, heuristics, or special cases
keep the feature locally alive.
**Response:** Group the symptoms by their shared mechanism and reopen the
foundation when needed. Retain a compatibility layer only for a clear boundary
or migration reason. Unlike architecture fog, the warning is that a known weak
base is still accumulating layers.

## 20. Review-loop non-convergence

**Mechanism:** Each review finding receives a local correction while related
findings are never grouped around their shared root mechanism.
**Response:** Stop the loop, group findings by mechanism, prioritize impact and
probability, make one coherent correction batch, then use independent review
or verification to test the evidence after correction.

## 21. Scout-as-Judge

**Mechanism:** A Peer assigned to discover files, evidence, APIs, or options has
its interpretation silently promoted to binding authority.
**Response:** Keep the Scout output to evidence and uncertainty. The Lead or
the role with the relevant authority makes the decision; obtain independent
review where the protocol requires it.

## 22. Nested orchestration ownership

**Mechanism:** Two control planes both manage spawn, parentage, retry, wait,
cleanup, or follow-up, leaving runtime truth non-deterministic.
**Response:** One control plane owns the runtime graph. Here Herdr is that
truth; the SLP layer retains semantic authority and contracts only. This does
not turn native-subagent configuration into a global SLP enforcement duty.

Response is complete only when the observed signal is recorded as evidence,
the suspected mechanism has been tested rather than assumed from its label, the
bounded response names its owner and authority, and the next decision or wait
condition is explicit. A label alone never changes topology, acceptance, or
protocol.
