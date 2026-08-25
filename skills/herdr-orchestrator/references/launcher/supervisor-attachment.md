# Supervisor attachment

Read `references/launcher/preflight.md` completely first. Run this branch only
when the Human explicitly asks for a Supervisor. The Supervisor remains
invisible to the Lead and never participates in Peer orchestration.

Invoke the packaged runtime directly:

```text
python3 scripts/herdr_runtime.py start \
  --role supervisor \
  --project-root <canonical-project-root> \
  --task <observation-mandate>
```

The configured Supervisor recipe is required; runtime substitution is not
allowed. The default prompt contains the Supervisor profile, bounded observation
scope, and only applicable read-only constraints. Pass
`--constraints full-protocol` only when the Human mandate explicitly requires a
protocol audit or update proposal.

Keep the Supervisor in the background unless the Human explicitly requests
focus. Retrieve observations with:

```text
python3 scripts/herdr_runtime.py result --agent <supervisor-name>
```

The normal result is the Herdr agent response. A notebook or report exists only
when the mandate explicitly requests a durable artifact. The Launcher does not
notify or modify any Lead.
