# Workspace Protocol

## 1. Status and scope

- Owner:
- Version: 1
- Last reviewed: YYYY-MM-DD
- Repository root:
- Readers: Project Lead; Supervisor only when explicitly assigned
- Live orchestration language:
- Durable Markdown artifact language:

## 2. Project characteristics and risk classes

- Criticality:
- Dominant risks:
- Expensive-to-reverse decisions:
- External side effects:
- Model/cost budget:

## 3. Authority and Human decision boundaries

- Lead may decide:
- Human must decide:
- Edit/commit/push/deploy/publish authority:
- Scope-expansion boundary:
- Architecture contracts reserved for Human review:
- Prohibited without explicit Human authority:

## 4. Task classes and smallest useful topology

- Tiny:
- Bounded implementation:
- Cross-module or lifecycle-sensitive:
- Architecture lock-in:
- Subjective/product evidence:

## 5. Peer recipe selection and native model/effort policy

- Configured recipe capabilities and access constraints:
- Selection by Assignment risk, independence, cost, and required access:
- Recipe reuse or mixing across dynamically created Peers:
- Specialized miss, configured fallback recipe, and out-of-envelope escalation:

## 6. Architect, Reviewer, and council triggers

- Fresh Architect required when:
- Fresh Reviewer required when:
- Sealed council allowed when:
- Same-Engineer correction rule:

## 7. Ownership, workspace isolation, and handback

- One writer per moving scope:
- Worktree rules for concurrent writers:
- Exclusive resources:
- Handback and integration owner:

## 8. Stable candidates

- Allowed identity forms (Git commit or Git tree with exact base commit):
- Candidate freeze and replacement rules:

## 9. Verification and acceptance evidence

- Checks by task class:
- Independent falsification expectations:
- Subjective/Human evidence:
- Minimum evidence required for Lead verdict:
- Residual risk reporting:

## 10. Escalation requests

- `REOPEN_REQUEST` for failed foundations or premises:
- `DEPENDENCY_REQUEST` for another owner, API, scope, or prerequisite:
- `BLOCKED` for missing authority, external state, or Human decision:

## 11. Project-specific anti-patterns and supervision

- Signal, evidence, suspected mechanism, open question, allowed response:
- Supervisor observation retention/export policy:
- Supervisor project-read/notebook-write boundary:
- Repeated-failure prerequisite check:

## 12. Protocol evolution

- Review trigger and date:
- Human approval required for material authority changes:
- Version-history practice:
- Repeated evidence required before promoting a protocol candidate:
