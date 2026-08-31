# Launch preflight

Require `HERDR_ENV=1`; otherwise stop rather than controlling a session from
outside Herdr. Resolve the canonical project root and the exact absolute path
of `scripts/herdr_orchestrator.py` in this active installed skill. Call that
path `<canonical-helper>`; it is never a path guessed under the consumer
repository.

Task launch consumes the config and Workspace Protocol accepted during setup.
Do not rerun setup discovery: no `doctor`, `validate-project`, Herdr
version/skill/status/help, integration inspection, harness version, or model
catalog call belongs on this hot path. The later control-role cost check parses
and validates the configured recipes before native start. If an actual native
operation exposes environment drift, stop with its bounded diagnostic and ask
the Human to rerun setup doctor; never substitute a harness or guess a repair.

Setup already verified the release-matched official Herdr Agent Skill and the
selected harness instruction context. The project config and Workspace
Protocol remain authoritative for recipe, language, and SLP policy; Herdr is
authoritative for pane, agent, and lifecycle mechanics.

Read `references/launcher/runtime-binding.md` before starting a role. Resolve
the returned exact pane ID after native creation; the compiler resolves and
validates executable, socket, helper, and adapter facts. Production roles keep
the user's normal harness profile, configuration, and authentication.

Pane projections set `PYTHONDONTWRITEBYTECODE=1`. Do not override it: Python
cache must not become untracked candidate input. Candidate freeze also excludes
any `__pycache__`, `.pyc`, or `.pyo` path as defence in depth.

Stop on invalid configuration, a native capability failure, or incompatible
approval policy. Do not substitute a harness, model, profile, or authority
envelope. Before launch, show the selected recipe,
harness/model/effort, native priority flags, and `cost_class`. An `elevated`
recipe requires Human approval; copy the exact decision into
`Assignment.cost_approval`, which is rendered verbatim to the Lead.
