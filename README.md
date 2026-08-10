# Herdr Orchestrator

An [Agent Skill](https://agentskills.io/) for continuing one repository work
unit in one named [Herdr](https://herdr.dev) session.

Root chooses the work, controls Herdr, resolves user decisions, and accepts the
result. The continuation worker performs the unit and returns a compact
`HANDOFF`. Default work-in-progress is one continuation and one writer;
parallel work requires an explicit user request.

## Supported runtimes

The skill has one portable `SKILL.md` and selects a runtime adapter after
activation:

| Root | Herdr control | Worker profiles | Worker isolation |
| --- | --- | --- | --- |
| Pi | Typed `herdr_layout`, `herdr_pane`, and `herdr_agent` tools | `workers.toml` | Excludes Herdr, interactive-question, and installed agent-spawn tools |
| Codex | Herdr CLI wrappers | `workers.codex.toml` | Launches every worker with `--disable multi_agent` |

Route names and selection conditions remain shared in `workers.toml`. Runtime
references contain only host-specific control and launch behavior.

## Install

Install with the open [`skills` CLI](https://github.com/vercel-labs/skills).
After this repository is published, replace `<owner>` with its GitHub owner:

```bash
npx skills add <owner>/herdr-orchestrator --agent pi --agent codex
```

Install globally with `--global`:

```bash
npx skills add <owner>/herdr-orchestrator \
  --agent pi --agent codex --global
```

For local development, run the command from a consuming project and pass the
skill repository as a local source:

```bash
npx skills add /path/to/herdr-orchestrator --agent pi --agent codex
```

The CLI discovers the root `SKILL.md` and installs the same skill package into
each agent's native location. No host-specific copy or nested skill package is
required.

## Requirements

All runs require:

- Herdr with a running server;
- Root running inside a Herdr-managed pane;
- Git; and
- the selected coding-agent CLI installed and authenticated.

### Pi Root

Pi requires the
[`@ogulcancelik/pi-herdr`](https://github.com/ogulcancelik/pi-extensions/tree/main/packages/pi-herdr)
extension. It provides the typed Herdr tools used by `references/pi.md`.

Confirm that Pi can see `herdr_layout`, `herdr_pane`, and `herdr_agent` before
invoking the skill.

### Codex Root

Codex controls Herdr through the installed `herdr` CLI. Install Herdr's Codex
integration when native session restore is required:

```bash
herdr integration install codex
herdr integration status
```

The integration and Root's Codex configuration remain user-owned. The skill
inspects them but does not install, update, or rewrite them.

## Use

Invoke the installed skill by name:

```text
$herdr-orchestrator continue the next unblocked unit of work
```

The skill then:

1. qualifies the Pi or Codex runtime branch;
2. reuses one live continuation or prepares one new session;
3. selects a route and resolves the runtime's model and effort;
4. sends one compact context pack;
5. waits for `HANDOFF`; and
6. independently verifies repository evidence before acceptance.

The run ends only after Root accepts or abandons the unit, preserves useful
handoff material, and safely releases topology it created.

### Parallel work

Ask for parallel work explicitly. Root then reads `references/parallel.md`,
assigns exclusive ownership, isolates writers in branches and worktrees, and
integrates accepted branches one at a time. Ordinary continuation requests stay
WIP-one.

## Routing

`workers.toml` owns:

- the default route;
- route names and selection conditions; and
- Pi profiles.

`workers.codex.toml` owns Codex profiles and effort aliases. Codex reuses every
route from `workers.toml`; only profile resolution changes. The current alias
maps the Pi effort name `off` to Codex `none`.

Every Codex worker launch must prove its model, effort, checkout, and
`--disable multi_agent` arguments before Root delivers work. This worker-level
override leaves Root's own `multi_agent` setting untouched.

## HANDOFF

Every final or blocking worker reply ends with at most 12 lines:

```text
HANDOFF
state: done | blocked
outcome: <completed result or decision needed>
evidence: <commands and paths, or none>
artifact: <.pi/herdr path, or none>
next: <next action, or numbered options with a recommendation>
```

Herdr lifecycle states request attention; they do not prove completion. Root
accepts work only when repository authority, changed state, and required
evidence agree.

## Package layout

```text
.
├── SKILL.md                 Portable workflow and runtime selection
├── agents/openai.yaml       Codex interface and invocation policy
├── workers.toml             Shared routes and Pi profiles
├── workers.codex.toml       Codex profiles and effort aliases
└── references/
    ├── pi.md                Pi control and worker adapter
    ├── codex.md             Codex control and worker adapter
    └── parallel.md          Explicit parallel branch
```

`SKILL.md` contains the core sequence. Runtime details load only after the
corresponding branch qualifies.

## Validate

Check Agent Skills discovery without installing:

```bash
npx skills add . --list
```

Validate the standard skill metadata when `skills-ref` is available:

```bash
skills-ref validate .
```

Check configuration and Markdown integrity:

```bash
python3 -c 'import tomllib; tomllib.load(open("workers.toml", "rb")); tomllib.load(open("workers.codex.toml", "rb"))'
git diff --check
```

Runtime validation is complete when the selected adapter qualifies, every
route resolves a host profile, and worker launch evidence matches the selected
model, effort, checkout, and isolation policy.

## Troubleshooting

### No skill found

Run `npx skills add . --list` from the repository root. The result must contain
`herdr-orchestrator`. Verify that `SKILL.md` has valid YAML frontmatter and that
the installed directory is named `herdr-orchestrator`.

### Codex Root is outside Herdr

The Codex adapter stops when `HERDR_ENV` is absent. Start Codex inside a
Herdr-managed pane; the skill does not control another focused Herdr session
from outside.

### Codex integration is missing or outdated

Screen-based state detection may still work, but native session restore is
degraded. Run `herdr integration install codex`, restart Codex, then check
`herdr integration status` again.

### HANDOFF is missing

Read more `recent-unwrapped` output. Ask the same worker once to resend only
`HANDOFF`. If terminal recovery still fails, have it write the full reply under
the repository's ignored `.pi/herdr/` directory and return the path.
