# Assignment and evidence ownership map

This file is a maintenance index, not a runtime route. Each contract has one
authoritative home and is disclosed at the action that consumes it:

| Contract | Authoritative source | Runtime trigger |
| --- | --- | --- |
| Three-layer pack and language ordering | `skills/herdr-orchestrator/SKILL.md` | Every delivery |
| Run initialization, initial `launch`, and handoff | `skills/herdr-orchestrator/references/launcher/task-launch.md` | Task launch |
| Peer request, routing, pack, delivery, typed result, candidate verification, report promotion, and events | `skills/herdr-orchestrator/scripts/herdr_runtime_ops.py` | Lead/Peer operation wrapper call |
| Lead topology, independent review, correction, Human boundaries, and verdict judgment | `skills/herdr-orchestrator/references/roles/lead.md` | Lead project judgment |
| Supervisor binding and notebook authority | `skills/herdr-orchestrator/references/launcher/supervisor-attachment.md` | Explicit Supervisor attachment |
| Supervisor observation/Human-attention/handoff records | `skills/herdr-orchestrator/scripts/herdr_runtime_ops.py` | Supervisor operation wrapper call |

The orchestration helper stages concise role profiles and stable operation
wrappers under the run, assembles sources in role/protocol/assignment order, and
delivers exact saved context. The Launcher consumes compact metadata rather
than runtime role bodies. Lead, Peer, and Supervisor provide judgment payloads;
the wrappers perform deterministic lifecycle, evidence, and notebook mechanics.
