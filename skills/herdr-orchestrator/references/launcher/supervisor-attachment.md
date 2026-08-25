# Supervisor attachment

Read `references/launcher/preflight.md` completely and pass it before this
branch. The current setup attaches one fresh Supervisor to one exact accepted project
and run. Cross-project observation requires a later authority slice.

## 1. Bind existing evidence

Require the Human's exact project root, run ID, and live Lead name. Resolve the
run through the preflight Git common directory and verify its run manifest,
launch event, Lead context digest, `launcher-handoff.md`, saved Activation
Manifest/config/protocol, and one live unique Lead.

Choose an attachment ID matching `[a-z][a-z0-9_-]{0,31}` and absent from the
run. Reserve
`<run>/supervisor/attachments/<attachment-id>/` exclusively. Prove one
create/write/fsync/remove canary there with no residue. Existing attachments
and notebook bytes remain immutable.

Invoke the run-local helper's `bind-role --role supervisor` against the saved
config and `run-manifest.json.artifacts.project_config.sha256`. Supply exactly
its `required_bindings`:

```text
python3 <run>/tools/herdr_orchestrator.py bind-role \
  --project-config-file <run>/context/project-config.toml \
  --expected-project-config-sha256 <project_config.sha256> \
  --role supervisor \
  --cwd <attachment-root> \
  --bind workspace=<repository_root> \
  --bind notebook=<attachment-root> \
  --output <attachment-root>/launch.json
```

This receipt must show project read, attachment-notebook write, native agents
disabled, and network denied. A missing Supervisor role or any binding mismatch
stops the attachment.

## 2. Assemble the Supervisor pack opaquely

Invoke `stage-assets` with packaged
`references/anti-patterns/responses.md` as `anti-pattern-details` and
`--selection-output
supervisor/attachments/<attachment-id>/card-manifest.json` to create a
filtered selection manifest. Then atomically save
`<attachment-root>/attachment-assignment.md` in the configured artifact
language with the attachment, project/Lead/run/context, notebook, launch
digest, observation scope, and Human-only boundaries.

Invoke `pack --role supervisor` in this exact order:

1. `--role-source`: packaged `references/roles/supervisor.md`, packaged
   `references/anti-patterns/index.md`, then the filtered card manifest;
2. `--protocol-source`: the bound run's `context/project-config.toml`, then
   `context/workspace-protocol.md`;
3. `--assignment-source`: the saved attachment Assignment.

Pass absolute paths without opening opaque role/card bodies. Save exact bytes
as `<attachment-root>/context.md` and retain its digest.

## 3. Start, deliver, and notify

Use the run-local layout helper to create a fresh pane whose cwd is the
attachment root. Choose a unique Supervisor name and start the exact
`launch.json` kind and argument vector with no prompt. Never resume, fork, or
replace another agent.

Invoke `deliver` once with the saved context, configured live language,
`<attachment-root>/delivery-receipt.json`, and localized opening/closing files.
After accepted delivery, atomically write `local-receipt.md` containing the
attachment ID, Supervisor identity, context and launch digests, run binding,
and notebook boundary. Prompt the Lead once with only that receipt path and
digest; save the immediate result as `lead-notification-receipt.json`. The Lead
retains ledger and acceptance authority. Focus the Supervisor unless the Human
specified another target.

Completion requires the accepted setup, run binding, reserved attachment,
bound launch, pack, fresh agent, delivery, local receipt, and Lead notification
to agree. A failure preserves created evidence and reports the exact error. A
Supervisor recommendation remains notebook evidence, never project acceptance
or protocol mutation.
