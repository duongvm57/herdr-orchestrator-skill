# Herdr Orchestrator

An explicit-only Agent Skill that turns the invoking session into a short-lived
Launcher, creates a fresh Project Lead through
[Herdr](https://herdr.dev), and transfers the Human to that Lead.

The package is static instruction and templates. It adds no daemon, CLI,
plugin, scheduler, or orchestration runtime. Herdr remains the agent lifecycle
control plane; Git and the filesystem remain artifact truth.

## Install and invoke

Install with an Agent Skills-compatible installer, for example:

```bash
npx skills add duongvm57/herdr-orchestrator --agent codex --agent pi
```

The skill never runs implicitly. Invoke it by name:

```text
$herdr-orchestrator set up this repository
$herdr-orchestrator implement the cancellation fix described in issue 42
```

Setup creates two tracked files in the consuming repository:

```text
.orchestration/
├── herdr-orchestrator.toml
└── workspace-protocol.md
```

The config contains complete native Herdr launch recipes for one Lead, optional
Supervisor, and project-defined Peer routes. There are no shared profiles,
normalized effort names, credentials, or fallback routes. Setup discovers the
installed Herdr and harness command shapes before writing native arguments.

## Runtime model

The three instruction layers are Role Profile, repository Workspace Protocol,
and one concrete Assignment. The Lead receives macro project context. A Peer
receives its thin role profile, one disposition, one assignment, and only the
protocol constraints relevant to that work. A Supervisor receives governance
context only when the Human explicitly requests one.

Run evidence lives outside the checkout under the repository's Git common
directory:

```text
<git-common-dir>/herdr-orchestrator/runs/<run-id>/
├── context/
├── assignments/
├── reports/
├── supervisor/
└── events.jsonl
```

Context packs, assignments, and reports are preserved verbatim. `events.jsonl`
records semantic milestones, not live lifecycle state or autonomous acceptance.

## Package layout

```text
SKILL.md
README.md
agents/openai.yaml
assets/
  config.toml
  workspace-protocol.md
references/
  setup.md
  launcher.md
  roles/{lead,peer,supervisor}.md
  topology.md
  anti-patterns.md
  assignments-and-evidence.md
  workspace-protocol.md
  orchestration-invariant-coverage.md
```

`SKILL.md` is the router and invariant set. Detailed Herdr commands, topology,
role manuals, evidence schemas, and protocol authoring guidance load only for
the branch or role that needs them.

## Validate

```bash
python3 -c 'import tomllib; tomllib.load(open("assets/config.toml", "rb"))'
python3 /path/to/skill-creator/scripts/quick_validate.py .
git diff --check
```

Maintainers also audit `references/orchestration-invariant-coverage.md`; every
orchestration invariant must have one authoritative owner, one reader/injection
point, and a forward behavioral test.
