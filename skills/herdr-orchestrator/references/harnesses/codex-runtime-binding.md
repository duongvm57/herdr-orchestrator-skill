# Codex runtime-binding projection

Codex is a verified harness adapter with one observed compatibility limit: its
tool subprocesses cannot be trusted to preserve the ambient role environment.
This is not a generic Herdr or role requirement.

For every Codex role recipe, retain the adapter-validated native configuration
in its exact recipe argv: `shell_environment_policy.inherit="all"`,
`shell_environment_policy.ignore_default_excludes=false`, and
`allow_login_shell=false`; plus separate `"include"` filters for `HOME`,
`CODEX_HOME`, `PATH`, `SHELL`, `USER`, `LOGNAME`, `PWD`, `TERM`, `TMPDIR`,
`LANG`, `LC_*`, `XDG_RUNTIME_DIR`, `HERDR_*`, and
`HERDR_ORCHESTRATOR_*` (`shell_environment_policy.filters.<key>`; quote
wildcard TOML keys). This preserves the bounded process-start policy and does
not replace the runtime-binding projection.

Codex Herdr observation requires `--sandbox workspace-write` together with
`--config sandbox_workspace_write.network_access=true` (or an explicitly
authorized broader envelope). This is a verified technical IPC compatibility
requirement for a Codex role, including a Supervisor; it does not grant SLP
authority or turn a governance-only Supervisor into a project writer.

For the active role, run `render-runtime-binding` with `--kind codex` and put
the emitted fragment in the initial prompt. That Codex adapter fragment renders
literal native Herdr and helper commands carrying the exact binding. Use those
literal forms for Codex tool operations because a bare command may lose the
role context. Do not copy this syntax into OMP, Pi, Claude, or another adapter.

For a Codex Peer or Reviewer, also run `render-runtime-binding-pane` with
`--kind codex` before `herdr pane split`. Use its complete returned
`pane_environment` list and `source_pane_id` as literal native split inputs.
The normal Codex projection does not override `HOME` or `CODEX_HOME`, copy
credentials, prepare login, or manage authentication; Codex uses the user's
normal process profile. The generic entries provide project, helper, and
`peer` role context. Do not add `HERDR_ENV`, socket, pane, tab, or workspace
values to that pane.
