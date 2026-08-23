# Supervisor attachment

Read `references/launcher.md` completely and pass its preflight gate before
this branch. Run it only when the Human explicitly supplies exact project root,
run ID, and live Lead name bindings. It creates one fresh observer, not a run or
replacement Lead.

## 1. Bind existing evidence and authority

Choose one collision-free attachment ID absent from every bound run. Require it
to match `[a-z][a-z0-9_-]{0,31}` exactly before any path operation; separators,
dot segments, and all other forms are invalid. Its host root is
`<host-run>/supervisor/attachments/<attachment-id>/`; every selection,
Assignment, context, and delivery receipt for this attachment uses a new file
under that root. A later attachment uses another ID and never replaces these
bytes.

Resolve every run through its project's absolute Git common directory. Require
the run's launch event, Lead context digest, `launcher-handoff.md`, saved full
Workspace Protocol snapshot and manifest digest, canonical project-source
binding, and one live unique Lead to agree with the Human's exact binding. Use
the saved snapshot for the run, never the project's mutable current protocol.
Preserve project-local evidence; references may cross projects, bytes may not.

For one project, use its unchanged configured `[roles.supervisor]` recipe. For
multiple projects, require the Human to name one host project whose recipe is
launch authority. Each bound protocol must permit observation, and the exact
host recipe must enforce read-only access to every checkout and Git common
directory plus write access only to each bound run's `supervisor/` notebook.
Stop when any protocol, binding, recipe, live identity, or access boundary
disagrees. Recipes are neither merged nor substituted.

Before starting anything, prove Launcher create/write/fsync/remove access with
one collision-free probe under every bound run's `supervisor/` directory.
Require no residue and stop if any host or non-host boundary fails. Then reserve
the ID by exclusively creating
`<run>/supervisor/attachments/<attachment-id>/` in every bound run; if any
reservation fails, remove only still-empty roots created by this attempt and
stop before packing.

Binding is complete when each project, run, Lead, protocol, notebook root,
context digest, host authority, and attachment ID has one exact verified
identity and every access probe and exclusive root reservation passed.

## 2. Assemble the Supervisor pack opaquely

First invoke the host run helper's `stage-assets` operation with
`--run-dir <absolute-host-run>` and
`--asset anti-pattern-details=references/anti-patterns.md`, requesting a new
filtered selection through `--selection-output` at
`<host-attachment-root>/card-manifest.json`. Require byte-for-byte staging and
a digest-only selection containing exactly `anti-pattern-details`; do not
inline the Lead's five-card manifest. Then invoke
`tools/herdr_orchestrator.py pack --role supervisor` and pass sources in this
exact layer order:

Resolve packaged sources relative to the installed skill root and pass absolute
source, run, manifest, and output paths; project cwd is not a package resolver.

Before packing, atomically save
`<host-attachment-root>/attachment-assignment.md` in the host project's artifact
language. It contains the attachment ID, exact project/Lead/run/context
bindings, notebook roots, host recipe authority, observation scope, Human-only
boundaries, and notebook Assignment.

1. `--role-source`: `references/roles/supervisor.md`, then
   `references/anti-pattern-index.md`, then the filtered selection manifest;
2. `--protocol-source`: every bound run's full
   `context/workspace-protocol.md` snapshot under a unique labelled project/run
   boundary; and
3. `--assignment-source`: the saved attachment Assignment.

The Supervisor profile maps `anti-pattern-details` to its signal trigger and
requires complete, digest-verified reading only when a supplied signal appears.

The Launcher passes source paths without reading role or card bodies. Consume
only the helper's compact JSON metadata. Save the exact pack and digest inside
the host attachment root as `context.md`; use
`delivery-receipt.json` there for the helper's transport receipt. Generated
shared durable prose uses the host project's artifact language.

Packing is complete when ordered sources appear once, every bound protocol is
the bound run's full labelled snapshot, the anti-pattern detail card is staged
and digest-bound by the one-card selection, the exact bindings are inline, no
project evidence was copied across runs, and the Launcher transcript contains
no opaque body or delivery payload.

## 3. Start, deliver, and notify

Use the bound host run's layout helper and shared state to create a fresh no-
focus pane whose cwd is the host `supervisor/` directory. Accept only its
`new_pane_id`. Choose a unique name absent from the live agent inventory and
start the exact host Supervisor recipe with no initial prompt. Never resume,
fork, or replace an existing session.

Invoke the run-local orchestration helper's `deliver` operation once with the
fresh Supervisor name, saved context path, host project's live language,
`delivery-receipt.json`, and localized one-line opening/closing files that use
and contain that exact host live-language value. It sends that envelope plus
the exact saved bytes through a safe argument vector without `--wait`, stores
context and full-payload digests, and keeps payload bytes out of stdout and
logs.

After accepted delivery, atomically write a local attachment receipt in every
bound run at
`supervisor/attachments/<attachment-id>/local-receipt.md`, using that project's
artifact language. It contains only the attachment ID, now-confirmed shared
Supervisor identity, host context identity/digest, local binding, and local
notebook boundary; never copy another project's evidence. Then prompt each
bound Lead once with only its local receipt path and digest, using that
project's live language. Use a safe argument vector without `--wait`; atomically
save the immediate result, exact target, and message digest as
`lead-notification-receipt.json` under that project-local attachment root. That
Lead remains its project's ledger writer and acceptance authority. Focus the
Supervisor unless the Human requested another focus target.

A start, delivery, or receipt failure preserves the pane and evidence, reports
the exact error, and stops without unchanged retry. A Supervisor recommendation
is notebook evidence, never project acceptance or protocol mutation.

Attachment is complete only when preflight, bindings, access boundaries, pack,
fresh agent, attachment ID/root, notebook roots, context digest, all local
and Lead-notification receipts agree; host and per-project languages were used
at their named boundaries; Supervisor and Lead prompt deliveries each occurred
once without waiting; the selected focus is active; no replacement Lead exists;
and the Supervisor has observation but no implementation or acceptance
authority.
