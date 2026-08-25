# Task launch

Read `references/launcher/preflight.md` completely and pass its gate first.
This branch creates one run and hands the task to one fresh Project Lead. It
does not coordinate Peers after handoff.

## 1. Initialize the run

Save the Human task verbatim and capture the before-state requested by
preflight. Invoke packaged `scripts/herdr_orchestrator.py init-run` according to
its current `--help`, passing the retained canonical project root, Git common
directory, config/protocol paths and digests, task file, before-state file, and
a collision-free run ID.

`init-run` atomically stages the accepted config and protocol, concise Lead and
Peer profiles, layout/orchestration helpers, `herdr_lead_ops.py` and
`herdr_peer_ops.py`, and harness adapters outside the tracked checkout. Consume
only its compact JSON. Do not stage or load Lead lifecycle manuals.

Initialization is complete when the returned run directory and manifest are
absolute, collision-free, digest-verified, and outside the checkout.

## 2. Start and hand off the Lead

Resolve the exact Herdr executable once. Invoke the run-local helper:

```text
python3 <run>/tools/herdr_orchestrator.py start-lead \
  --run-dir <run> \
  --anchor-pane <launcher-pane-id> \
  --herdr <absolute-herdr-executable> \
  [--repository-authority-file <applicable-repository-directives>]
```

The helper performs the runtime mechanics as one transaction:

```text
discover repository inventory
→ create `runtime-manifest.json`
→ create the short three-layer Lead pack
→ split a balanced pane
→ start the configured Lead
→ record launch and handoff evidence
→ deliver the saved pack once
→ focus the Lead
```

The Lead pack contains only:

1. concise Lead profile;
2. accepted Workspace Protocol;
3. verbatim Human task, runtime manifest, and applicable repository authority.

It excludes setup docs, harness catalogs, Herdr CLI syntax, Peer lifecycle and
report mechanics, OCR internals, recovery procedures, and Supervisor context.
The runtime manifest is the Lead's infrastructure truth and includes exact
repositories, Human-approved Peer profiles, run binding, and one Lead
operations command.

Task launch is complete when `start-lead` returns an accepted delivery receipt
and exact Lead/run identities. Report those identities and the preserved
before-state to the Human, then cease acting as orchestration proxy.

If native startup pauses for a Human-owned prerequisite such as first-use trust,
resolve that prerequisite in the same pane and invoke the same command once with
`--resume`. Recovery reuses the prepared immutable Lead binding; it never creates
a replacement pane or agent. Do not use `--resume` after delivery or for an
unchanged startup failure.
