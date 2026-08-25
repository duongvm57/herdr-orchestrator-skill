# Assignment and evidence ownership map

This file is a maintenance index, not a runtime route. Each contract has one
authoritative home and is disclosed at the action that consumes it:

| Contract | Authoritative source | Runtime trigger |
| --- | --- | --- |
| Three-layer pack and language ordering | `skills/herdr-orchestrator/SKILL.md` | Every delivery |
| Lead launch and handoff | `skills/herdr-orchestrator/references/launcher/task-launch.md` | Task launch |
| Agent start, prompt, wait, and read | `skills/herdr-orchestrator/scripts/herdr_runtime.py` | Runtime operation call |
| Lead topology, independent review, correction, Human boundaries, and verdict judgment | `skills/herdr-orchestrator/references/roles/lead.md` | Lead project judgment |
| Supervisor mandate and protocol disclosure | `skills/herdr-orchestrator/references/launcher/supervisor-attachment.md` | Explicit Supervisor attachment |

The runtime assembles role/protocol/assignment layers in memory and delivers
them through Herdr. Lead, Peer, and Supervisor return ordinary agent responses;
durable evidence remains an explicit task artifact.
