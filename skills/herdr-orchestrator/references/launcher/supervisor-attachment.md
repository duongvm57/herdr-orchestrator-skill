# Supervisor attachment

Read `references/launcher/preflight.md` completely first. Run this branch only
when the Human explicitly supplies the project/run bindings to observe. The
Supervisor remains invisible to every Lead and never participates in project
orchestration.

## 1. Bind observation authority

Choose one collision-free attachment ID matching `[a-z][a-z0-9_-]{0,31}`.
Resolve every run through its project and verify its launch evidence, protocol
snapshot, canonical project binding, and notebook boundary. For multiple
projects, the Human names one host run whose configured `[roles.supervisor]`
recipe supplies launch authority. The host recipe must keep every checkout and
Git common directory read-only and grant writes only to the bound `supervisor/`
notebooks. Stop on an absent recipe or mismatched boundary; runtime never
substitutes another harness or profile.

Reserve `<run>/supervisor/attachments/<attachment-id>/` in every bound run.
Under the host attachment root, atomically save `runtime-binding.json`:

```json
{
  "schema_version": 1,
  "attachment_id": "<id>",
  "supervisor": "<future-agent-name>",
  "projects": [
    {
      "project_id": "<project>",
      "run_id": "<run>",
      "evidence_root": "<absolute-run-root>"
    }
  ],
  "notebook_root": "<absolute-host-attachment-root>",
  "artifact_language": "<host-artifact-language>",
  "operations": ["python3", "<host-run>/tools/herdr_supervisor_ops.py"]
}
```

The Supervisor agent name is reserved before writing this binding. No Lead
identity or notification route appears in it.

## 2. Build the short Supervisor pack

Save `attachment-assignment.md` with the exact project/run/evidence bindings,
observation scope, Human-only boundaries, runtime-binding path, and the JSON
payload fields required by Supervisor operations:

```text
observation | evidence | suspected_mechanism | impact
question | recommendation | escalation | protocol_candidate
```

Invoke the host run's `tools/herdr_orchestrator.py pack --role supervisor` with:

1. run-local `context/supervisor-profile.md` as Role Profile;
2. each bound run's labelled `context/workspace-protocol.md` as Workspace
   Protocol; and
3. the attachment Assignment plus `runtime-binding.json` as Assignment.

The pack contains no Lead context, Peer lifecycle, Herdr CLI syntax, report
mechanics, or anti-pattern card. Save it as `<host-attachment>/context.md`.

## 3. Start and deliver

Use the host run's layout helper to create one fresh pane rooted at the host
attachment directory. Start the reserved Supervisor name with the exact host
Supervisor recipe and deliver the saved pack once through the run-local
orchestration helper. Use the host live language and save its delivery receipt
as `delivery-receipt.json` under the host attachment root. Focus the Supervisor
unless the Human requested another focus target.

Do not prompt, notify, or modify any Lead. Cross-project local receipts may
reference the shared Supervisor and observation root but copy no evidence.

Attachment is complete when all bindings, notebook boundaries, pack digest,
fresh agent identity, and delivery receipt agree. Observation records and
Human-attention/handoff recommendations remain notebook evidence; they never
become implementation, project acceptance, or protocol mutation.
