# Supervisor identity and attachment

Read `references/launcher/preflight.md` completely and pass it before this
branch. A Supervisor is a durable Human-owned logical identity, not a Lead
child or a task role. Setup stores only each project's default Supervisor model
route and never creates or attaches an observer.

## 1. Create an identity only on explicit Human request

Create a new durable identity once, outside any run:

```text
python3 <helper> create-supervisor \
  --identity-dir <new-supervisor-identity-directory> \
  --name <stable-name> \
  --notebook-language <language>
```

Retain `identity.json` and `notebook/`. Reuse this identity across observation
sessions. An existing destination fails closed; attachment never replaces or
forks the identity.

## 2. Bind one Human-approved observation scope

Require the Human's exact Supervisor identity, accepted project, observed Lead
or run, and repository/worktree scope. Create a collision-free session folder
under the durable notebook, labelled by project and observation session. The
scope may contain one or multiple repositories whose Git common directories
belong to the accepted project inventory.

Bind the project Supervisor default with no model prompt:

```text
python3 <helper> bind-launch \
  --project-config-file <accepted-project-config> \
  --expected-project-config-sha256 <config-sha256> \
  --profile supervisor \
  --disposition observer \
  --authority project_readonly \
  --cwd <session-notebook-directory> \
  --repository <workspace-1>=<git-common-1> \
  [--repository <workspace-N>=<git-common-N>] \
  --notebook-root <session-notebook-directory> \
  --output <session-notebook-directory>/launch.json
```

Each project supplies its own accepted Supervisor default. Reusing one durable
identity across projects does not merge project authority, protocols, evidence,
or notebook records. A Human model override is explicit and must exist in the
target project's accepted inventory.

## 3. Assemble, start, and deliver

Save an Assignment containing the durable identity digest, project and Lead/run
identities, exact read scope, notebook boundary, evidence sources, language,
and Human-only decisions. Pack, in order:

1. packaged `references/roles/supervisor.md`, anti-pattern index, and verified
   disclosed-card manifest;
2. target project's accepted config and Workspace Protocol;
3. the scoped observation Assignment.

Start or resume the Herdr agent identity according to Herdr lifecycle truth,
then deliver the new scoped context once and record its receipt. Supervisor may
question the Lead with evidence, relay an exact Human decision, and report to
the Human. It never directs a Peer, mutates project files, changes protocol, or
accepts work. Completion requires the durable identity, scoped notebook,
launch receipt, context digest, delivery receipt, and project/run references to
agree.
