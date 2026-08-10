# Explicit parallel workflow

Read this branch only when the user explicitly requests concurrent work. The
parent [`SKILL.md`](../SKILL.md) still owns routing, context packs, HANDOFF, and
acceptance.

## Entry gate

Split only at independent ownership and evidence boundaries. Each unit needs one
outcome, one edit scope, explicit dependencies, exclusive resources, and its own
acceptance evidence. Keep dependent work serial. Keep overlapping writers
serial unless one unit owns the shared files completely.

Dispatch is ready when every unit is independently unblocked and each file or
exclusive resource has exactly one owner.

## Isolate writers

Record the accepted base commit. Root creates one Git branch and worktree per
writer before opening its Herdr session. Validate repository-relative authority
paths from each worker cwd. Read-only sessions may share a checkout.

Assign each writer:

- an exclusive file scope;
- unique ports, databases, locks, servers, and test directories when relevant;
- a dedicated `.pi/herdr/<unit>/` artifact directory; and
- the condition that next requires Root attention.

Use repository-native worktree naming and integration conventions. Otherwise
use a short `herdr/<unit>` branch and sibling worktree. Root alone creates and
removes worktrees.

## Dispatch and decisions

For up to four synchronous agents, keep Root and workers in the current tab.
Create each pane with the parent skill's balanced `pane_split` and set `cwd` to
its checkout. Use dedicated tabs for detached or long-running units, larger
groups, or an explicit user layout request.

Give each unit a named session and a context pack containing the accepted base,
branch and worktree, ownership, resources, dependencies, relevant peers, and
required evidence.

Root owns decisions. Workers may exchange scoped facts through an existing
direct channel. Return product, ownership, resource, dependency, and evidence
changes to Root. Record material peer facts in the receiving worker's artifact
or HANDOFF.

## Attention

With several sessions, use Attention Broker or optional intercom when available.
Otherwise poll `herdr_agent` action `list` and read settled sessions without
blocking on one target. First unblock the unit holding an exclusive resource;
otherwise handle the oldest attention event.

A worker needing a decision returns `HANDOFF state: blocked` and settles. Root
answers by prompting that same session with `wait: false`.

## Accept and integrate

Review and validate each branch independently against its recorded base.
Integrate accepted branches one at a time in dependency order using repository
conventions. If an earlier integration changes a later branch's base, update
that branch, rerun its evidence, and review its new diff.

After integration or abandonment, preserve the useful HANDOFF, confirm no
valuable uncommitted work remains, release resources, close the Root-created
pane, and remove the worktree safely.

Parallel work is complete when every unit is accepted or abandoned, integrated
state passes combined evidence, and every temporary worktree and exclusive
resource is accounted for.
