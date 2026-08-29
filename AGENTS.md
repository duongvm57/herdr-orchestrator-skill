# Core orchestration changes

Use this entrypoint when changing the orchestration core. Keep product policy
in the canonical sources rather than duplicating it here:

- `skills/herdr-orchestrator/SKILL.md` and
  `skills/herdr-orchestrator/references/` own the SLP role, authority, and
  instruction-layer contracts.
- `skills/herdr-orchestrator/scripts/herdr_orchestrator.py` owns bounded
  project/config and Assignment validation; `herdr_harnesses/` owns only
  harness capability discovery.
- Root `scripts/` own development validation and eval tooling, not Herdr
  lifecycle or orchestration runtime behavior.

Preserve the boundaries: the release-matched official Herdr Agent Skill is the
only generic agent-operation contract; each moving write scope has one owner;
review and acceptance bind an exact stable candidate and semantic handback;
static checks do not prove live behavior or project acceptance. Do not add a
generic runtime wrapper, lifecycle/state service, or an implied fallback
authority between Lead, Peer, Supervisor, and Human.

Before handing off a core change, run the focused contract tests relevant to
the edited path. The repository static gate is:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/render_coverage.py --check
python3 scripts/context_budget.py --check
```

Also inspect `git diff --check`. Run a live eval only when its explicit
acceptance contract requires it; a passing static suite is not a substitute.
