# Launch preflight

Require `HERDR_ENV=1`; otherwise stop rather than controlling a session from
outside Herdr. Resolve the canonical project root and the exact absolute path
of `scripts/herdr_orchestrator.py` in this active installed skill. Call that
path `<canonical-helper>`; it is never a path guessed under the consumer
repository. Run:

```text
python3 <canonical-helper> validate-project --project-root <root>
```

Capture the installed-contract snapshot before launch:

```text
herdr --version
herdr --skill
herdr api schema --json
herdr status                 # only when a server is active
herdr agent start --help
```

Use the release-matched `herdr --skill` and the official [Herdr Agents
docs](https://herdr.dev/docs/agents/) to verify/install the official skill and
for lifecycle/detection semantics. Confirm the selected Launcher, Lead, or
Supervisor harness has that skill installed in its supported instruction
context. Only a harness that genuinely cannot install skills may use a
documented compatibility fallback that injects one fresh copy into its initial
prompt. CLI support alone does not prove the spawned agent received the skill.
The project config and Workspace Protocol are authoritative for recipe,
language, and SLP policy; Herdr is authoritative for pane, agent, and
lifecycle mechanics.

Read `references/launcher/runtime-binding.md` before starting a role. Resolve
the active session's exact Herdr executable and socket endpoint; after native
pane creation, read the returned exact pane ID before constructing that role's
fresh binding. Production roles retain the user's normal harness profile,
configuration, and authentication. The selected adapter, not this generic
route, decides how native execution consumes the bounded binding.

Stop on invalid configuration, unavailable skill/binary, or incompatible
approval policy. Do not substitute a harness, model, profile, or authority
envelope. A recipe requiring an approval-gated capability must not be launched
with an incompatible fixed approval policy; recreate the agent session after a
policy change when the provider fixes that policy at process start.
