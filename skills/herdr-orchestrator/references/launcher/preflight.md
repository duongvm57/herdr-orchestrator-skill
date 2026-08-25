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
  --project-root <canonical-project-root> \
  --git-common-dir <canonical-selected-git-common-dir>
```

This command is the only project-configuration reader. It verifies the accepted
Activation Manifest, immutable generation, publication manifest, Acceptance
Receipt, every artifact digest, the closed-world role templates, both
Human-selected languages, and the selected repository/Git-common binding.
Direct mutable config or protocol files are not launch authority.

Retain the returned exact:

```text
project_root
repository_root
git_common_dir
activation.path and sha256
generation_root
publication_digest
acceptance_receipt_digest
config.path and sha256
protocol.path and sha256
languages
roles and each role's required_bindings
```

Require `lead`, `engineer`, and `reviewer`; require `supervisor` only for an
attachment. Every role is Codex-bound, has a Human-selected model
and reasoning effort, disables native agents and network, and exposes logical
filesystem bindings rather than proof-time paths. A missing role or incompatible
authority stops the branch; there is no writable fallback.

Require the configured Codex executable and model launch surface to remain
available. Preserve the exact model and reasoning binding.

## 3. Preserve before-state

Prove create/write/fsync/remove access with one collision-free file under the
exact returned Git common directory, leaving no residue. Then capture:

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
the selected repository and Git common directory agree, the required roles and
languages are present, live control canaries pass, and before-state is saved.
Forward the retained paths and digests unchanged; later steps do not recompute
or substitute them.
