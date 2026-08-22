# Anti-pattern catalog

The Lead and Supervisor receive this catalog in full. Treat every match as a
hypothesis, gather the stated evidence, and use the response; names alone are
not verdicts.

## 1. Sheep / authority-gradient compliance

- **Signal:** A Peer repeats the Lead's premise, skips foundation checks, and
  agrees without independent evidence.
- **Mechanism:** The brief embeds a verdict, so the Peer optimizes for authority.
- **Response:** Restate evidence and an open question; invite `CONFIRM`,
  `PARTIAL`, `CHALLENGE`, or `BLOCKED`. Reject evidence-free contrarianism too.

## 2. Pre-solving / perfect-plan trap

- **Signal:** The plan fixes every file, API, lifecycle, and solution before
  discovery; the Peer only executes PASS/FAIL steps.
- **Mechanism:** Unverified assumptions have become implementation constraints.
- **Response:** Reduce it to a provisional outcome/boundary/risk map and restore
  the Peer’s right to reopen premises.

## 3. Parachute optimization instead of brakes

- **Signal:** A third correction patches the same symptom while complexity rises.
- **Mechanism:** Local optimization protects a shared failed foundation.
- **Response:** Stop patches and ask which root mechanism creates the entire
  failure sequence.

## 4. Architecture lock-in

- **Signal:** Each feature requires another adapter or exception but the original
  architecture is treated as immutable.
- **Mechanism:** Strong implementation delays visible failure of a weak base.
- **Response:** Commission fresh architecture review of alternatives, strongest
  counterargument, and reversal conditions; double-check irreversible choices.

## 5. Architecture fog

- **Signal:** Abstractions and terms multiply while no one can name state owner,
  transitions, or failure semantics in one sentence.
- **Mechanism:** Wrappers postpone the missing ownership decision.
- **Response:** Name concrete owner/transition/failure semantics and apply the
  deletion test: what behavior disappears if the abstraction is removed?

## 6. Moving-scope collision

- **Signal:** Two Engineers edit one subsystem or review reads while it changes.
- **Mechanism:** Ownership and candidate identity are ambiguous.
- **Response:** Assign one writer, isolate concurrent writers, require explicit
  handback, and review an exact stable candidate.

## 7. Self-benchmark / self-acceptance

- **Signal:** One agent defines the metric, implements, measures, and declares
  success.
- **Mechanism:** Metric and implementation share a blind spot.
- **Response:** Human/Lead fixes the success boundary; use independent review for
  consequential decisions while the Engineer still proves its writes.

## 8. Test-shaped proof

- **Signal:** Tests mirror implementation, mock away real failure, or pass
  without proving the Human outcome.
- **Mechanism:** Verification checks the chosen shape rather than the mechanism.
- **Response:** Ask which wrong mechanism makes the test fail; add appropriate
  integration, migration, cancellation, or Human evidence.

## 9. Overengineering an edge case

- **Signal:** Large infrastructure protects a rare, low-impact edge case.
- **Mechanism:** Completeness is mistaken for proportional risk reduction.
- **Response:** Quantify frequency, impact, simpler fallback, maintenance cost,
  and reversal cost before continuing.

## 10. Polling / loop debt

- **Signal:** Status is reread continuously or the same failed call repeats with
  unchanged prerequisites.
- **Mechanism:** Activity substitutes for new information and dilutes attention.
- **Response:** Wait on events; after two identical failures inspect prerequisite,
  quota, authentication, authority, and shared mechanism.

## 11. Ceremony capture

- **Signal:** Every task gets a council, votes, and multiple reports regardless
  of risk.
- **Mechanism:** Agent count creates false confidence and process eclipses proof.
- **Response:** Return to the smallest useful topology; retain only independent,
  decision-changing seats.

## 12. Debate framing capture

- **Signal:** Every proposed option stays inside the Lead's possibly false frame.
- **Mechanism:** Challengers inherit the preferred solution before reconstructing
  the problem.
- **Response:** Give a fresh Architect a neutral problem first; seal reports when
  genuine divergence matters.

## 13. Forked independence

- **Signal:** A fork of Lead/Engineer is labeled an independent Reviewer.
- **Mechanism:** The fork retains premise, framing, and bias.
- **Response:** Start a fresh session with a neutral brief and exact candidate.

## 14. Lead attention dilution

- **Signal:** Human Q&A consumes the Lead's dependency, topology, and acceptance
  attention.
- **Mechanism:** The Lead shifts from coordination to explanation/defense.
- **Response:** Use an explicitly requested Supervisor or ordinary advisory
  session for broad Q&A, then relay compact owner decisions.

## 15. Skill pollution

- **Signal:** Peers orchestrate, Leads dive into framework minutiae, or roles load
  unrelated manuals.
- **Mechanism:** Available instructions redirect role attention.
- **Response:** Keep macro context with Lead, governance context with Supervisor,
  and only bounded technical context with Peer.

## 16. Status as acceptance

- **Signal:** `done`, `finished`, exit success, or passing tests becomes the final
  outcome without inspecting scope and exact artifact.
- **Mechanism:** Lifecycle attention is confused with evidence and authority.
- **Response:** Wake the owner, then inspect candidate, diff/artifact,
  verification, review, unresolved risk, and acceptance authority.

## 17. Supervisor overreach

- **Signal:** Supervisor edits code, issues architecture verdicts, or directs
  Peers without a bounded recovery mandate.
- **Mechanism:** Governance becomes a competing Project Lead.
- **Response:** Return to evidence-backed questions, owner-decision relay, or a
  proposed fresh-Lead handoff; require explicit Human authority for intervention.
