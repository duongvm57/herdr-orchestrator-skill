---
name: herdr-orchestrator
description: Continue one repository work unit in one named Herdr session. Use when coordinating a continuation worker through Herdr from Pi or Codex Root.
---

# Herdr continuation

## Contract

**Root** is the current session. The **continuation** performs one next unit of
work. Root owns Herdr layout, user decisions, and acceptance.

Default WIP is one:

```text
active continuation sessions = 1
active writers = 1
```

Open or resume exactly one continuation in the current checkout. Reuse it for
questions and corrections until Root accepts or abandons the unit.

**Parallel branch.** When the user explicitly requests concurrent work, read
[`references/parallel.md`](references/parallel.md). That branch alone may raise
default WIP.

**Checkout.** Use the current checkout. Create a worktree only for the parallel
branch, an explicit user request, or an already-selected checkout.

**Runtime branch.** Select one branch before preparation:

- **Pi Root:** when typed `herdr_layout`, `herdr_pane`, and `herdr_agent` tools
  are available, read [`references/pi.md`](references/pi.md). Resolve routes
  from [`routes.toml`](routes.toml) and profiles from
  [`workers.pi.toml`](workers.pi.toml).
- **Codex Root:** when Codex runs inside a Herdr-managed pane with the `herdr`
  CLI available, read [`references/codex.md`](references/codex.md). Resolve
  selection and routes from `routes.toml`, profiles and effort aliases from
  [`workers.codex.toml`](workers.codex.toml). The Codex adapter replaces every
  typed Herdr operation named below and in the parallel branch with its CLI
  mapping.

Stop when neither branch qualifies. Runtime selection is complete when one
adapter, one route table, and one host profile table are fixed.

## Prepare the continuation

1. Call `herdr_agent` with `action: "list"`. Reuse the live continuation for
   this repository. If several candidates exist, ask the user which one to
   resume.
2. Select one unblocked next outcome from repository authority and current
   state. Fix its edit scope, constraints, open decisions, and acceptance
   evidence.
3. Read [`routes.toml`](routes.toml). Start with `selection.default`; select
   another route only when its `when` condition matches explicitly. Resolve the
   profile, runtime, model, and effort from that route.
4. Read the selected runtime adapter: Pi uses `references/pi.md`; Codex uses
   `references/codex.md`. A runtime without an accepted adapter requires a user
   decision; CLI defaults are not authority.
5. Build one compact context pack with:
   - outcome and current state;
   - primary authority paths;
   - accepted decisions and open questions;
   - edit scope and constraints;
   - required evidence; and
   - the HANDOFF format below.

Inline the pack. If it is too long, write it under `.pi/herdr/` only when that
path is Git-ignored, then pass its path and SHA-256. Use `.pi/herdr/`, not
`/tmp`, for continuation handoffs.

Preparation is complete when one route, checkout, outcome, and context pack are
fixed.

## Open the session

1. Name it `w-<unit>-continue`, lowercase and at most 32 characters.
2. For synchronous work, keep Root and the continuation in the current tab.
   Split Root's pane with `herdr_layout` action `pane_split`, set `cwd` to the
   selected checkout, and omit `direction` so Herdr chooses from the geometry.
3. Use a dedicated unfocused tab only for detached or long-running work, or an
   explicit user layout request.
4. Start the agent in the prepared pane with the adapter's explicit arguments.
   Restore Root focus if launch moved it, unless the user requested continuation
   focus.
5. Deliver the context pack with `herdr_agent` action `prompt` and
   `wait: false`.

The continuation becomes active when the prompt is delivered. Keep it as the
sole live continuation.

## Continue the conversation

Use the same session until Root accepts or abandons the unit:

```text
prompt -> wait -> read HANDOFF -> decide -> resume or accept
```

- **working:** wait on the continuation. A timeout triggers inspection.
- **blocked:** read the question, decide from accepted authority or ask the
  user, then prompt the same session with `wait: false`.
- **idle or done:** read the latest result. Settlement means ready for review.
- **error or stopped:** preserve the latest output and recover the same session.
  Replace it only after it is no longer live and its useful context is durable.

A complete HANDOFF received through an optional direct transport is canonical.
Otherwise read `recent-unwrapped` with enough lines to capture it. If HANDOFF is
missing, ask the same session once to resend only HANDOFF. If recovery still
fails, ask it to write the full reply under `.pi/herdr/` and return the path.

## HANDOFF

Require every final or blocking reply to end with at most 12 lines:

```text
HANDOFF
state: done | blocked
outcome: <completed result or decision needed>
evidence: <commands and paths, or none>
artifact: <.pi/herdr path, or none>
next: <next action, or numbered options with a recommendation>
```

HANDOFF stays self-contained; `artifact` carries overflow detail.

## Accept and clean up

Treat `state: done` as a proposal. Inspect changed files and run or observe the
required evidence. Send corrections to the same continuation. Accept only when
repository authority, changed state, and evidence agree.

After acceptance or abandonment:

1. preserve the useful HANDOFF or artifact durably;
2. confirm no uncommitted work would be lost;
3. release the continuation's edit scope and resources;
4. close only the pane Root created, when safe; and
5. report outcome, evidence, and remaining risk to the user.
