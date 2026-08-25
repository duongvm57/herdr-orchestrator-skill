# Herdr Skills

This multi-skill repository contains composable Agent Skills for governed
repository work:

| Skill | Purpose | Required? |
|---|---|---|
| `herdr-orchestrator` | Launch a Human-led Project Lead and bounded independent Peers on [Herdr](https://herdr.dev). | Yes, for orchestration |
| `ocr-peer-reviewer` | Let an independent Reviewer use [OpenCodeReview](https://github.com/alibaba/open-code-review) for file selection and rule resolution. | No; direct Peer review remains available |

Herdr Orchestrator is explicit-only. For a project-task invocation, the current
session is only a short-lived **Launcher**: it checks the repository and live
tooling, prepares role-specific context, starts a fresh **Project Lead**, and
transfers the Human to that Lead. The Launcher does not remain an invisible
orchestration proxy.

`ocr-peer-reviewer` is model-invoked only when installed and applicable. Its
absence is not an orchestration error: a Reviewer uses direct exact-candidate
review.

## Orchestration mindset

The goal is not more agents. It is better ownership, independent judgment, and
evidence.

- The **Human** owns intent, cost/risk boundaries, irreversible choices,
  publication, external effects, and project-reserved trade-offs.
- The **Lead** holds macro context, chooses the smallest useful topology,
  assigns one owner per moving scope, resolves dependencies, and issues the
  project verdict.
- A **Peer** owns one bounded outcome. It may confirm, challenge, request a
  dependency, reopen a failed premise, or report `BLOCKED` with evidence.
- A **Supervisor** is optional fresh governance requested by the Human. It
  observes and asks questions without becoming a second Lead or accepting work.

Every agent receives only three ordered instruction layers:

```text
Role Profile → Workspace Protocol → Assignment
```

The Lead receives its thin role, full protocol, verbatim task, and a runtime
manifest containing exact repositories, approved Peer profiles, and one
operations command. A Peer receives its thin role, only relevant project
constraints, and one assignment. Independent
judgment uses a fresh session; correction returns to the same Engineer that owns
the write.

Every moving write scope has one writer. Review binds to an exact stable
candidate: a commit or deterministic base/diff/artifact digest. `done`, an idle
agent, a successful exit, or passing tests are attention signals—not acceptance.

## What constrains a run

Markdown cannot guarantee model obedience.

- Herdr supplies agent and pane lifecycle truth.
- Git and worktrees provide inspectable artifact and workspace identity.
- Harness-native sandbox, approval, and tool controls constrain capabilities.
- Herdr terminal output plus explicit task artifacts make decisions auditable.
- Fresh review and Human gates test claims prompts cannot enforce.

The skill provides no daemon, queue, retry engine, semantic parentage,
authorization, tamper-proof evidence, or automatic acceptance. Behavioral
confidence requires repeated real runs against the supported harness/model
versions.

OpenAI package metadata marks the skill explicit-only, and its entrypoint
requires explicit Human invocation.

## Install

You need Git, Python 3.11+, a running Herdr server, a Launcher session inside a
Herdr-managed pane, and every configured harness/model installed and
authenticated. The Launcher's native permission profile must allow the Herdr
socket. Each configured profile selects its own harness and native argument
vector; its harness adapter validates those flags without translating them into
a shared sandbox or effort vocabulary. Verify broadened network, filesystem,
and Git-metadata access with bounded canaries.

Use the standard multi-skill installer:

```bash
npx skills@latest add duongvm57/herdr-orchestrator
```

Choose `herdr-orchestrator`, and optionally choose `ocr-peer-reviewer`. The
installer also asks which supported agents receive each selected skill. Install
the orchestrator into the Launcher harness; install the OCR add-on into any
Peer-capable harness where you want OCR-backed review.

Leads, Peers, and Supervisors do not need `herdr-orchestrator` installed; their
role-specific context is sent directly when they are created. A Reviewer that
does not discover `ocr-peer-reviewer` continues with direct review. Every
Reviewer report records the procedure actually used and an OCR status. An
OCR-backed review preserves raw `preview.json` and `rules.json` beside its inbox
report and records both SHA-256 digests.

The optional OCR path also needs the `ocr` CLI. Delegation mode uses the host
Peer for reasoning and needs no OCR-side LLM provider:

```bash
npm install -g @alibaba-group/open-code-review
# or: brew install open-code-review
ocr version
```

See OpenCodeReview's [installation](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/installation.md)
and [delegation-mode](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/integrations/delegate.md)
documentation for other platforms and current CLI details.

## Set up a repository

From the repository, invoke:

```text
$herdr-orchestrator set up orchestration for this repository
```

Setup first intersects the orchestrator's verified adapter registry with
Herdr-supported, installed local harnesses. Herdr kinds without a verified
adapter are shown as unavailable rather than accepted through a generic
fallback. Setup then performs deeper model, effort, access, and native-spawn
discovery only for the harnesses you select. It shows exact native choices before asking which recipes are
permitted, then asks about cost, authority, review gates, expensive reversals,
and Human-only decisions and creates two tracked files:

Bounded native catalog discovery uses the common `harness-models --kind ...`
interface; Codex, Grok CLI, Pi, OpenCode, and OMP each implement their parser in
a separate adapter module. OMP exposes models from its current authenticated
providers. A harness without a verified adapter cannot be configured. Pi exposes only the effective
`enabledModels` scope; an absent or stale scope stops discovery instead of
falling back to its full authenticated-provider catalog.

- `.orchestration/herdr-orchestrator.toml` — complete native launch recipes for
  the Lead, a project-defined catalog of reusable Peer recipes, and an optional
  Supervisor;
- `.orchestration/workspace-protocol.md` — repository-specific authority,
  routing, ownership, topology, evidence, escalation, and evolution policy.

The protocol also separates live orchestration language from durable artifact
language. First setup asks the Human to confirm two nonempty values for that
repository; unrelated updates preserve a valid pair unless the Human requests a
change. The package has no language default. Authoritative embedded skill text
and technical literals remain unchanged. Selected Lead and Supervisor recipes
must prove local Herdr control access, and each recipe must prove only its
assigned evidence/commit boundary, before setup writes config.

Review the generated diff. Re-run setup after changing machine, harness, model,
or permission policy. Legacy `routes.toml` and `workers.*.toml` are unsupported.

## Run a task

```text
$herdr-orchestrator implement issue #42 and preserve my uncommitted changes
```

The Launcher cheaply validates accepted project inputs and existing state, then
uses one runtime helper to split a background pane, start the exact configured
Lead recipe, and deliver the task. Missing capability stops launch without
runtime substitution. Focus changes only when explicitly requested.

The Lead receives the full Workspace Protocol, the Human task, available Peer
profiles, and three operations: start an agent, wait for and read its result, or
send a continuation. These operations use Herdr's native agent lifecycle; they
do not create a second mailbox or lifecycle state machine.

After handoff, work with the Lead. A tiny task may need zero or one Peer.
Architecture-sensitive work may use a fresh Architect, one Engineer, and a fresh
Reviewer. The Lead decides the number and dispositions per task and may reuse or
mix approved harness/model recipes. A Peer launch names an exact configured
profile; runtime never falls through to a more permissive recipe. Recipes are
capabilities, not a fixed list of Peer types.

## Request a Supervisor

A configured Supervisor is never started automatically:

```text
$herdr-orchestrator attach a Supervisor to this project
```

Refocus an installed Launcher session before invoking that command; the fresh
Lead does not need or invoke the skill.

The Launcher starts the exact configured Supervisor recipe with a bounded
observation mandate. It is not exposed to a Lead and never creates Peers, edits
project code, or issues a project verdict. Full protocol context is supplied
only when the Human mandate requires protocol audit or update judgment.

## Evidence and verdicts

Herdr provides live agent state and terminal output. Git, verification commands,
and task artifacts provide technical evidence. The runtime creates no run
directory, mailbox, delivery receipt, or event ledger. A Peer or Supervisor
writes a durable report only when its Assignment requires one or terminal output
cannot carry the result reliably.

```text
Engineer proves writes
→ Reviewer falsifies the exact candidate when required
→ Lead inspects the complete evidence chain and issues the project verdict
→ Human resolves owner-only decisions
```

## Update project policy

```text
$herdr-orchestrator update this repository's orchestration protocol
```

A Supervisor observation remains evidence. It becomes policy only through an
explicit update invocation and a Human-reviewed tracked diff.

## License

Herdr Orchestrator and the repository-maintained support code are released
under the [MIT License](LICENSE). The adapted `ocr-peer-reviewer` skill is
released under [Apache-2.0](skills/ocr-peer-reviewer/LICENSE); its upstream
attribution and modification notice are in
[skills/ocr-peer-reviewer/NOTICE](skills/ocr-peer-reviewer/NOTICE).
