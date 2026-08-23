# Assignment and evidence ownership map

This file is a maintenance index, not a runtime route. Each contract has one
authoritative home and is disclosed at the action that consumes it:

| Contract | Authoritative source | Runtime trigger |
| --- | --- | --- |
| Three-layer pack and language ordering | `SKILL.md` | Every delivery |
| Run initialization, initial `launch`, and handoff | `references/launch.md` | Task launch |
| Peer Assignment fields, disposition, exact report schema, delivery, promotion, and `assignment`/`report` evidence | `references/lead/peer-lifecycle.md` | Before first Peer lifecycle action |
| Stable candidate, verification, review, Human request, verdict, ledger, and terminal `finish` | `references/lead/candidate-and-verdict.md` | Before the first corresponding milestone |
| Supervisor binding, notebook receipts, and authority | `references/supervisor-attachment.md` | Explicit Supervisor attachment |

The orchestration helper stages Lead cards and opaque Peer role bytes under the
run, records their SHA-256 digests, assembles sources in role/protocol/assignment
order, and delivers exact saved context. The Launcher consumes compact metadata
rather than loading runtime role/card bodies. A Lead verifies and reads one
card completely when its fixed trigger fires; the Peer profile is passed back
to `pack --role peer` without being read by the Lead.
