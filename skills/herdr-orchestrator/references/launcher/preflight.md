# Shared Launcher preflight

Read this procedure completely before task launch or Supervisor attachment. It
prepares facts only; the selected branch owns durable mutation and completion.

## 1. Prove control and evidence access

Require `HERDR_ENV=1` and Python 3.11+. Run:

```text
herdr agent list
herdr pane current --current
```

Stop on either error. Resolve packaged `scripts/herdr_orchestrator.py` and
`scripts/herdr_balanced_split.py` relative to this skill, and require both
helpers' `--help` operations to pass. Read only targeted current Herdr and Codex
help needed by the selected branch.

## 2. Load the accepted setup

Invoke:

```text
python3 <helper> validate-project \
  --project-root <canonical-project-root>
```

This command is the only project-configuration reader. It verifies the accepted
Activation Manifest, immutable generation, publication manifest, Acceptance
Receipt, every artifact digest, the closed-world authority templates, both
Human-selected languages, tracked root Workspace Protocol, repository
inventory, model inventory, and profile routes.
Direct mutable config or protocol files are not launch authority.

Retain the returned exact:

```text
project_root
repositories
activation.path and sha256
generation_root
publication_digest
acceptance_receipt_digest
config.path and sha256
protocol.path and sha256
languages
routes
authority_templates and each template's required_bindings
```

Require the `lead`, `peer_writable`, `peer_readonly`, and `supervisor` authority
templates and the `lead`, `peer`, `supervisor`, and `fallback` routes. Profiles,
dispositions, authority, and model routing remain separate. A missing compatible
template or inventory route stops the branch; fallback routing never grants
writable authority.

Require the configured Codex executable and model launch surface to remain
available. Preserve the exact model and reasoning binding.

## 3. Preserve before-state

After the Lead selects task topology, prove create/write/fsync/remove access
with one collision-free file under every selected Git common directory, leaving
no residue. Then capture:

```text
git status --short --branch
git worktree list --porcelain
herdr agent list
herdr pane list
```

Inspect repository authority applicable to the Human request, including scoped
`AGENTS.md` or equivalent policy sources. Existing agents, panes, worktrees,
branches, untracked files, and working-tree changes are Human-owned and remain
unchanged.

Preflight is complete only when the accepted generation and receipts verify,
the Lead-selected repository/worktree scopes resolve to accepted Git common
inventory, required templates/routes and languages are present, live control
canaries pass, and before-state is saved.
Forward the retained paths and digests unchanged; later steps do not recompute
or substitute them.
