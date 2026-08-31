# Role runtime context

Runtime context is a temporary machine-compiled artifact. It carries exact
Herdr executable, socket, pane, helper, project, role, and adapter projection;
it carries no profile, credential, authority, topology inference, or lifecycle
state.

After native Herdr returns an exact pane ID, compile the role context:

```text
python3 <canonical-helper> compile-runtime --project-root <root> \
  --kind <configured-kind> --role <role> --pane-id <returned-pane-id> \
  --output <runtime-context.json>
```

The compiler resolves and validates Herdr/socket/helper facts. Pass explicit
`--herdr-program` or `--socket-endpoint` only when the managed environment does
not expose them. A failure requires setup doctor; never guess or borrow another
adapter.

For another role in the same session, pass `--source-context
<current-runtime.json>` to reuse verified Herdr/socket facts while selecting
that role's adapter. Native path overrides are then rejected.

Before a Peer/Reviewer split, compile from the bound Lead pane with
`--target-role peer --assignment <assignment.json>`. Use the returned
`pane_launch.source_pane_id` and literal `pane_environment`; Herdr itself adds
managed pane/socket/workspace identity. After split, compile a fresh Peer
context from the returned pane ID and the Lead `--source-context`.

Prompts consume `runtime_projection` through the canonical renderer. Guarded
helper calls use the exact command form inside it, which binds
`HERDR_ORCHESTRATOR_PANE_ID` to native `HERDR_PANE_ID`.
