# Runtime preflight

Runtime consumes the setup-accepted project configuration. It performs a cheap
freshness and reachability check; harness discovery and model-catalog probing
belong to setup and are repeated only when accepted inputs are stale.

## 1. Resolve the fixed boundary

Require `HERDR_ENV=1`, Python 3.11+, and a Git repository. Resolve:

```text
canonical project root
absolute Herdr executable
current Launcher pane ID
packaged runtime helper
```

Run one bounded Herdr canary each for `agent list` and `pane current --current`.
Require the runtime helper's `--help` command to pass. Stop on an exact failure.

## 2. Check accepted inputs cheaply

Invoke packaged `scripts/herdr_orchestrator.py validate-project` with the
canonical project root and Git common directory. Retain its compact result:
project/config/protocol paths and digests, languages, Lead recipe, Peer profile
inventory, fallback profile, and optional Supervisor recipe.

Do not probe model catalogs, re-run setup discovery, compare model quality, or
reconstruct harness flags during task launch. A missing executable, changed or
invalid accepted file, unknown adapter, or unsatisfied configured access check
is `STALE`; stop and ask the Human to run setup/update. Runtime never substitutes
another harness, model, profile, or authority envelope.

For a control role, the native envelope must reach the Herdr control socket.
Codex `workspace-write` therefore requires its explicit native network-access
setting; `danger-full-access` also satisfies reachability. Treat this as control-
plane access, not permission for the Lead to perform arbitrary network work.

## 3. Preserve existing state

Inspect `git status --short --branch`, `git worktree list --porcelain`, `herdr
agent list`, and `herdr pane list`. Existing agents, panes, worktrees, branches,
untracked files, and working-tree changes are Human-owned and remain unchanged.

Inspect only repository authority needed to bind the Human task, such as an
applicable `AGENTS.md` or an explicitly referenced specification. Include the
applicable constraints in the task; do not create a runtime evidence directory.

Preflight is complete when accepted inputs, fixed paths, Herdr reachability,
applicable repository authority, and existing state are known and unchanged.
