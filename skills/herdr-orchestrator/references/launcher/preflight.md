# Shared Launcher preflight

Read this procedure completely before either a task launch or Supervisor
attachment. It prepares facts only; the selected branch owns all durable work
and its completion gate.

## 1. Prove the control and evidence boundaries

Require `HERDR_ENV=1` and Python 3.11+. Run these canaries first:

```text
herdr agent list
herdr pane current --current
```

Stop on either exact error before reading project configuration or probing a
harness. A managed pane whose native boundary blocks the Herdr socket is not
launch-ready.

Resolve the repository root and absolute Git common directory. Prove common-
directory write access with one exclusive collision-free file created,
written, fsynced, and removed in a single bounded operation. Stop on any exact
failure and require no leftover. Permission bits alone are not evidence.

Resolve packaged `scripts/herdr_orchestrator.py` and
`scripts/herdr_balanced_split.py` relative to this skill. Require each helper's
`--help` to pass. Read only the relevant targeted Herdr `--help` pages and each
configured harness's native help; bulk runtime instruction dumps are not
command authority.

## 2. Validate the project and recipes

Invoke the orchestration helper's `validate-project` operation with the
repository and resolved `--git-common-dir`. Consume only its compact JSON
result and retain its exact canonical project root, Git common directory,
config path/digest, and protocol path/digest as the preflight binding; do not
recompute or substitute them. Require:

- `.orchestration/herdr-orchestrator.toml` at schema `version = 2` with exactly
  one `[roles.lead]`, optional `[roles.supervisor]`, and one or more uniquely
  named `[peer_recipes.<name>]` entries;
- only `kind` and `args` in fixed roles, and nonempty `description`, `kind`, and
  `args` in each Peer recipe;
- only options registered in the helper's strict per-kind argument schema, with
  no placeholders, credentials, indirection, unknown keys, or legacy schema;
- all twelve Workspace Protocol sections and explicit non-placeholder live and
  durable languages, with its canonical absolute Repository root equal to the
  validated project root.

Validate the recipes the selected branch can start against live local
capabilities: Lead and all Peer recipes for task launch; only the exact host
Supervisor recipe for Supervisor attachment. Require an installed executable,
supported Herdr kind, accepted native arguments, selectable configured model,
disabled native spawning, Herdr reachability for control roles, and the exact
read/write envelope for the role. Use the helper's compact catalog operation
advertised by its current `--help`; keep raw model catalogs out of the Launcher
context and logs. A Lead needs run-evidence writes. Each task-launch Peer recipe
needs a lossless exclusive report-return boundary; project-read-only Peers keep
checkout and Git metadata read-only. A Supervisor is project-read-only and
notebook-write-only. Report the exact failing element; no recipe substitution
or fallback is valid.

Read both communication languages before generating prose or delivering a
pack. Durable evidence uses the artifact language. Live status and transport
envelopes use the orchestration language. Source bytes, identifiers, schemas,
commands, output, and quoted Human wording remain exact.

## 3. Preserve before-state

Capture:

```text
git status --short --branch
git worktree list --porcelain
herdr agent list
herdr pane list
```

Inspect repository authority needed to bind the Human request, including
applicable `AGENTS.md`, domain documents, issue, or specification pointers.
Existing agents, panes, worktrees, branches, untracked files, and working-tree
changes are Human-owned. Keep them in place and unchanged.

Preflight is complete only when the repository, Git common directory, project
files, live recipes, selected branch input, applicable authority, and preserved
before-state are unambiguous; both helpers pass their own checks; and all access
canaries pass without fallback. The retained project root, paths, and digests
remain the sole authority for any task-run initialization.
