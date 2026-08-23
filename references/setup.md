# Project setup and update

Read this file only for setup or update. The result is exactly two tracked
project files: `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`.

## 1. Preserve and discover

Resolve the Git repository root and absolute Git common directory, then inspect
status, existing worktrees, current agents/panes, and both destination paths.
Preserve user-owned changes. If a destination already exists, treat it as user
data: propose a diff and update it in place only after understanding its current
intent.

Require `HERDR_ENV=1`, then read live command authority and prove that the
Launcher can reach the current Herdr control plane before doing slower
discovery:

```text
herdr agent list
herdr pane current --current
herdr --skill
herdr --help
herdr agent
herdr agent start --help
herdr integration status
```

If either of the first two canaries cannot reach the live server, stop
immediately with the exact OS/CLI error. A managed pane alone is insufficient:
the Launcher's native permission profile must permit the Herdr socket. Do not
run integration, version, or harness probes while this prerequisite is red.

Discovery has two depths. First build a shallow machine map from the live kind
set and integration status: supported kind, executable presence/path, bounded
version probe, and integration state. Show unavailable, broken, or outdated
entries rather than probing their model catalogs. Emit exactly one row per live
kind and compare the output set/count to the live kind set; an unknown
executable mapping is `unresolved`, never an omitted row. Then ask which
installed harnesses the Human wants to consider for the Lead, Peer recipe
catalog, and optional Supervisor. If the invocation already names those
candidates, use that answer without another question. During an update, every
existing recipe the Human wants to retain is also a selected candidate.

Only for the selected candidates, discover authentication readiness, current
native help, model catalog/list/picker, effort options, and
sandbox/tool/native-spawn controls. A failure in one selected harness is that
candidate's exact failure; it is not a reason to deep-probe unrelated
harnesses.

Use exact locally selectable model IDs from the native source. For current
Codex versions, inspect `codex debug models --help` and use `codex debug models`
when that command exists. Parse every visible `models[]` entry and its
`supported_reasoning_levels`; never infer the catalog from its first entry or a
configured default. If no catalog is enumerable, mark the selection
`unverified` and validate it through a documented local mechanism or a
Human-approved bounded smoke launch. Old config, marketing lists, guessed
aliases, and generic recommendations are not evidence. Show the
selected-candidate inventory and precise missing, unauthenticated, or
unverified states before asking the Human to choose exact recipes; never
silently repair machine-level integrations.

Then ask the Human in plain language for:

- the reasoning/cost preference for the Lead;
- which concrete harness/model/access recipes the Lead may use for Peers and a
  short capability/cost/access description for each;
- whether a Supervisor recipe should be configured;
- on first setup, when either stored language is missing/invalid, or when the
  Human explicitly requests a change, the resulting live orchestration and
  durable Markdown artifact language pair;
- project risk, costly reversals, review triggers, and minimum verdict evidence;
- edit, commit, push, deploy, publish, and other external-effect authority; and
- scope-expansion, reserved architecture, model-budget, and Human-only boundaries.

Translate those answers into each harness's current native arguments. Do not
invent a shared effort vocabulary. Do not store API keys, tokens, credential
paths, environment values, or secret-bearing arguments.

The Human must explicitly confirm both language settings during first setup.
On an unrelated update, preserve an existing valid pair without asking again.
If either value is missing or invalid, or the Human requests a language change,
show and obtain confirmation for the resulting pair before writing it. Store
nonempty language names or identifiers in both protocol fields; a blank,
placeholder, or inferred value is invalid. The invocation language may guide
the live conversation until first setup is complete, but it is not a stored
default and must not be inherited across repositories.

For every selected recipe, inspect native sandbox, approval, tool, and spawn
controls. The Lead needs bounded project plus run-evidence writes. Every Peer
needs one lossless report-return path in an assigned writable boundary;
writable Peer recipes otherwise need only their owned workspace. A
project-read-only recipe serves Architect, Reviewer, Scout, or other non-writing
assignments by making its exclusive report mailbox the pane cwd while keeping
the project and Git metadata outside every writable root. Supervisor is
project-read-only and notebook-write-only. Disable native agent spawning: the
Lead creates Peers through Herdr, and a native subagent tree would create a
second control plane. Validate installed controls rather than copying examples.
Do not configure a recipe whose required access envelope cannot be enforced,
and record any softer behavioral limitation honestly. Validate each role's
access envelope separately even when recipes share one harness and model.

The Lead and any configured Supervisor are control-plane roles. Prove that each
exact native permission recipe can run `herdr agent list` from inside its
harness boundary. Validate Git common-directory access per role: the Launcher
needs the run-evidence root; the Lead needs its run evidence plus Git metadata
allowed by its integration/commit authority; and a writable Peer needs Git
metadata only when its Assignment may commit. A project-read-only Peer gets only
its exclusive `reports/inbox/<agent-name>/` mailbox under the run, never
checkout or other Git common-directory writes. A Supervisor gets only its bound
run's `supervisor/` notebook directory, never the whole common directory. If a
configured harness
cannot express that dynamic notebook-only boundary, it is not a valid
Supervisor recipe. When static inspection is insufficient, use a Human-approved
bounded smoke session launched through Herdr: create, read, and remove one
collision-free probe inside only the assigned scope, and require no leftover.
For Codex `workspace-write`, current installations require native network access
for the Herdr Unix socket. Launcher/Lead or commit-capable Peer recipes may also
need an explicit writable root for the absolute Git common directory; that
broadens network and Git-metadata access, so show the trade-off rather than
hiding it. For a Codex project-read-only Peer, use `workspace-write` with the
mailbox as cwd and no project/common-directory `--add-dir`; `read-only` cannot
return the report. Do not copy a broad writable root into that Peer or a
notebook-only Supervisor recipe. Starting the configured model without the
relevant role canaries is not sufficient validation.

Discovery is complete when the shallow machine map and deep selected-candidate
inventory have been shown; every selected recipe names an installed Herdr kind,
an installed executable, native arguments accepted by current help, and a model
proven available on this machine; and the Lead recipe has proven live Herdr
control plus run-evidence access. Every Peer recipe has proven a lossless report
return path; a project-read-only smoke can read the candidate and write its
mailbox while checkout and non-mailbox common-directory writes fail. Any
configured Supervisor and writable Peer recipe has separately proven its
required control/evidence/commit boundary.

## 2. Write the config

Copy the authoritative table-shape template at `assets/config.toml` to
`.orchestration/herdr-orchestrator.toml`, then replace every example and
placeholder.

`[roles.lead]` and optional `[roles.supervisor]` are fixed-role recipes. Peer has
one durable Role Profile; each `[peer_recipes.<name>]` is instead a complete
launch recipe with a nonempty capability `description`. Add any number, using
capability labels rather than disposition names. The Lead may create any number
of Peers, reuse a recipe, or mix recipes; topology and Assignment determine
count and disposition.

`kind` and every `args` element are passed unchanged to `herdr agent start`.
There is no adapter, profile lookup, effort translation, fallback, inheritance,
or Lead-authored native argument. A missing recipe requires an explicit setup
update.

Require `version = 2`, exactly one `[roles.lead]`, optional
`[roles.supervisor]`, and one or more uniquely named
`[peer_recipes.<name>]` tables. A role recipe contains exactly `kind` and
`args`; a Peer recipe also contains `description`. Reject every other top-level
key, unknown recipe field, and indirection from any recipe to another table or
file. Create this schema from live answers rather than translating an older
project configuration. Package-level legacy files are not project inputs.

Config writing is complete when TOML parsing and strict schema checks succeed,
all placeholders are gone, and each recipe independently passes discovery.

## 3. Write the protocol

Read `references/workspace-protocol.md`, copy
`assets/workspace-protocol.md`, and interview the Human only for project facts
that cannot be discovered. Fill all twelve numbered sections. Describe how the
Lead chooses among configured Peer recipes for each Assignment's risk,
independence, access, and cost needs; keep model IDs and native flags in TOML.
The protocol contains tactics and decision boundaries, never secrets,
task-specific file lists, or global role manuals.

Protocol writing is complete when every section has a concrete project answer,
every recipe has decidable selection criteria, independent-review triggers are
decidable, one-writer and stable-candidate rules are explicit, and the
Human-only boundary plus live/artifact languages are clear.

## 4. Validate and review

Parse TOML with the standard library or equivalent and check the schema, not
only syntax. Re-run live availability checks for every final entry. Check that
changes attributable to setup touch only the intended two files and contain no
credential-like value; preserve unrelated Human changes. Present the scoped
diff and unresolved assumptions to the Human.

Do not start a Lead as a side effect of setup unless the same explicit Human
request also includes a task to launch. Setup/update completes at the gate in
`SKILL.md`.
