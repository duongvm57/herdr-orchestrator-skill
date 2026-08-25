# Setup specification

Status: frozen for v4-alpha implementation

Frozen: 2026-08-25

## Outcome

Setup v4-alpha is a deterministic, Human-in-the-loop policy compiler. The
engine discovers mechanical facts, solves logical authority, compiles one
Codex launch specification per selected binding, validates it, records native
runtime proof, and publishes only a digest-accepted candidate. The presenter
explains engine output and returns typed Human answers; it does not create
questions, bindings, policy, model rankings, native arguments, or completion
claims.

The alpha supports Codex; Lead, Engineer, Reviewer, and Supervisor roles; and
single or nested Git repositories. Fake binding sources exercise the authority
core without a Codex dependency. Other installed harnesses remain discoverable
but are not v4-feasible until their v4 adapters exist.

## Authority core

Every role `Requirement` has three disjoint capability sets:

- `must_have`: required functional authority;
- `must_not_have`: role-level security prohibitions; and
- `may_have`: authority the role tolerates when a binding needs it.

`may_have` is a ceiling, not a request. A compiler does not proactively grant
it. For requirement `R`, effective envelope `E`, and Human policy `P`, a
compatible binding satisfies all of:

```text
R.must_have ⊆ E
E ∩ R.must_not_have = ∅
E ⊆ R.must_have ∪ R.may_have
E ∩ P.must_not_have = ∅
E ⊆ P.permitted
```

The third rule makes role authority closed-world: an unlisted capability is an
error even when Human policy permits it. Role and policy prohibitions remain
separate in results so a caller can identify their source.

## Result pipeline

The engine preserves each decision stage as its own object:

```text
Requirement
    ↓
FeasibilityResult
    ↓
EligibilityResult
    ↓
SelectionResult
    ↓
NativeLaunchSpec
```

`FeasibilityResult` records technically feasible bindings, rejected bindings,
and per-binding rejection reasons. `EligibilityResult` records bindings allowed
by Human policy and per-binding policy conflicts. `SelectionResult` records one
selected binding and its selector receipt, or the exact unresolved selection
state. The Codex adapter introduced in Slice 2 alone produces
`NativeLaunchSpec` from a selected compatible binding and exact runtime context.

Technical feasibility, policy eligibility, and routing selection are distinct:

```text
zero feasible bindings              -> UNSATISFIABLE
feasible but zero eligible          -> POLICY_CONFLICT
one eligible binding                -> select it
multiple eligible, explicit match   -> select and receipt the selector
multiple eligible, no unique choice -> NEEDS_HUMAN_INPUT
```

Launch requires exactly one selected binding that remains compatible with the
current discovery snapshot. Multiple globally compatible bindings are valid.

## Least privilege selection

Authority comparison is a partial order only:

```text
Envelope A < Envelope B iff Effective(A) ⊂ Effective(B)
```

Without an explicit selector, the engine may select a binding only when it is
the unique minimum. Equal or incomparable minimal envelopes require Human
input. The engine does not break ties with model, provider, cost, quality,
speed, identifier order, or another heuristic. An explicit Human selector may
choose any eligible binding and receives a digest-bound receipt.

## Roles and runtime proof

The Codex alpha must compile and prove these policy-bound properties:

- Lead reads required project context and reads/writes its orchestration state;
  project mutation follows the exact Human policy, with direct native spawning
  denied while Herdr is the sole control plane.
- Engineer writes only its assigned workspace and the exact Git metadata or
  evidence roots required by its assigned authority.
- Reviewer reads project context, writes evidence, and cannot mutate project
  state.
- Supervisor reads project context, writes its notebook, and cannot mutate
  project state.

Runtime proof prefers deterministic native operations over model behavior. Its
assurance values are:

```text
STATIC_PROVEN
NATIVE_INTROSPECTED
RUNTIME_PROBED
MODEL_OBSERVED
UNVERIFIED
```

Filesystem probes use direct read/write operations inside the native runtime;
network and native-spawn checks use native introspection or primitives when
available. `MODEL_OBSERVED` is never the only proof of an authority constraint.

Slice 4 produces an immutable `RuntimeProofReceipt` bound to the exact
`candidate_digest`, `discovery_digest`, role, and structured native launch spec.
A changed Discovery Snapshot returns `STALE` before any command runs. Every
configured role must produce a passing role receipt; one missing, malformed,
unverified, or unexpected result makes the aggregate `SMOKE_FAILED`.

For each exact filesystem resource in the native launch spec, the proof matrix
checks read allow and checks write allow or deny according to the compiled
access. It also probes read and write denial outside every granted root. Before
entering the sandbox, the engine verifies that each target exists, is canonical,
and is host-readable; it creates and removes a bounded canary to prove host
write capability. This distinguishes sandbox denial from ordinary filesystem
permissions. A hidden sandbox path may report `ENOENT`, but that counts as deny
only after the host precondition proved the same path existed.

Network denial is probed with a socket primitive against an engine-owned local
listener. Native spawning is not delegated to model behavior: the alpha receipt
requires the structured launch setting and native `agents.enabled=false`
override, recorded as `STATIC_PROVEN`. Filesystem and network effects executed
through `codex sandbox --permission-profile` are `RUNTIME_PROBED`. The engine
records bounded error codes and detail digests rather than raw command output.

Receipt rendering is canonical JSON with domain-separated SHA-256 identity.
Slice 4 returns evidence only; Slice 5 consumes that receipt without weakening
its assurance.

## Acceptance and atomic publication

Slice 5 first compiles a `SetupPublication` from one exact Setup Candidate and
its complete `PROVEN` Runtime Proof Receipt. The compiler rejects a different
candidate, discovery, role set, or native launch-spec digest. Its primary
artifacts are deterministic projections, not LLM-authored files:

```text
herdr-orchestrator.toml
runtime-proof.json
setup-plan.json
workspace-protocol.md
```

The publication digest binds each artifact path, size, and content digest plus
the candidate, discovery, and runtime-proof digests. Human acceptance must name
the exact Candidate Digest. A mismatch leaves the engine in
`AWAITING_ACCEPTANCE` and writes nothing.

Multiple regular files cannot be atomically replaced as one portable filesystem
operation. Alpha therefore publishes an immutable generation under
`.orchestration/setup/generations/<publication_digest>/` and activates the
whole set by one atomic replacement of
`.orchestration/setup/current.json`. Runtime readers treat only that Activation
Manifest as current state and verify its generation/artifact digests. A crash
before the manifest swap can leave a complete inactive generation, never a
partially active setup.

The Discovery Snapshot observes the existing Activation Manifest. Acceptance
compares the current whole-snapshot digest, rechecks all observed policy-source
and activation bytes under an engine publication lock, and requires the
activation observation to match immediately before the swap. This is the alpha
compare-and-swap contract. A competing compliant publisher serializes on the
same lock; a changed activation fails `STALE` rather than overwriting it.

Publication rejects symlinked or non-directory control roots, symlinked control
files, conflicting generation contents, and incomplete artifact sets. Files and
directories are fsynced before activation. A retry of the same accepted
publication is idempotent only after the engine rechecks the exact Activation
Manifest and complete generation while holding the publication lock.

The generation also contains canonical publication and Acceptance Receipts.
The Acceptance Receipt binds candidate, discovery, runtime proof, publication,
prior activation, generation, and artifact digests. It contains no wall-clock
or model-generated claim.

The accepted generation is the sole runtime source. A strict reader verifies
the Activation Manifest, both receipts, every artifact digest, Candidate
identity and role launch-spec identities, the complete `PROVEN` Runtime Proof
Receipt, and the runtime template schema before a role can be bound.

## Codex alpha normalization

Codex permission profiles are the only alpha filesystem compiler target. The
compiler does not combine them with `--sandbox`, `sandbox_mode`, or
`sandbox_workspace_write`; a conflicting loaded legacy setting makes the
candidate capability-invalid. The probe is bound to the exact launch `cwd`,
and compilation requires that `cwd` be inside an explicitly selected read or
write resource.

Native `write` includes read access. A selected effective envelope therefore
contains both `fs.read(resource)` and `fs.write(resource)` for a writable
resource; omitting the implied read is an effective-envelope mismatch. Codex
also requires a coarse `fs.read(runtime:codex)` capability for `:minimal` and
the discovered installation root. Role policy may tolerate that capability,
but the compiler grants it only when the selected binding contains it.

The alpha compiles network denial and `agents.enabled=false`. A selected
`network.egress` or `native_spawn` grant is capability-invalid rather than
being approximated. Broader or domain-scoped network authority remains a later
vertical slice after its effective semantics can be normalized and probed.

These rules derive from the official OpenAI documentation for
[permission profiles](https://learn.chatgpt.com/docs/permissions), including
path precedence and the non-composition rule, and the
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
for `agents.enabled`. Provider documentation is provenance, not a substitute
for the bound native runtime probe.

## Discovery and candidate identity

The alpha discovery snapshot contains canonical repositories, harnesses,
adapter versions, policy sources, and the existing Activation Manifest
observation. Canonical serialization produces `discovery_digest`. Any snapshot
change invalidates the whole candidate; fine-grained stale dependency tracking
is deferred.

Slice 3 implements discovery as a read-only mechanical operation. Git roots
are found from their `.git` directory or worktree marker and verified with
`git rev-parse`; each repository records its exact worktree path, Git directory,
and Git common directory. Known agent-policy files and the one Activation
Manifest are content observations. Regular-file, bounded-size, stable-read
checks prevent a policy symlink or a concurrently changing file from becoming
ambiguous snapshot input. There are no direct mutable config/protocol inputs.

Harness inventory is normalized separately from adapter implementation
inventory. A Codex harness observation records only native facts: executable,
version, model identifiers and supported reasoning controls, exact probed
working directories, normalized controls, and assurance. The adapter record
binds its declared alpha version and implementation digest. Neither structure
contains model quality, price, speed, or preference metadata.

The immutable candidate binds at least:

```text
discovery_digest
human_decisions_digest
compiled_policy
model_bindings
```

The Slice 3 compiler additionally binds the Herdr role requirements, complete
selector receipts, effective envelopes, and structured native launch specs.
It accepts only matching role sets, requires Lead, validates every Human model
binding against the discovered catalog without ranking it, and requires each
Codex compilation observation to exist in the bound snapshot. An explicit
binding selector must have the matching typed Human binding choice; a sole or
least-privilege selector remains an engine inference.

Canonical JSON is a projection of typed engine state, not an LLM-authored
artifact. Domain-separated SHA-256 digests identify discovery, Human decisions,
and the whole candidate. Frozen values and tuple/frozenset collections keep the
in-memory candidate immutable. Slice 3 may render candidate JSON for inspection;
Slice 5 alone turns the candidate and proof into an accepted immutable
generation.

Candidate provenance uses `OBSERVED`, `INFERRED`, `HUMAN_APPROVED`, and
`DEFAULTED`. Discovery is observed; role requirements, deterministic selection,
and adapter compilation are inferred; authority/model choices and explicit
selection are Human-approved. Alpha defines the `DEFAULTED` category but does
not create implicit policy defaults.

Acceptance names the exact candidate digest. Only successful static,
capability, and runtime proof followed by digest-matching Human acceptance may
atomically publish canonical project artifacts.

Model selection is Human-owned. The engine verifies that the chosen model
exists, the harness accepts it, the requested reasoning control exists, and the
launch works. It makes no quality, price, speed, or cross-provider ranking
without provider- or Human-supplied metadata recorded with provenance.

## Setup interface and statuses

The external Setup Engine interface remains:

```text
resume(project_root) -> SetupView
answer(session_id, revision, typed_answers) -> SetupView
accept(session_id, candidate_digest) -> AcceptanceReceipt
```

`SetupView` is an engine-state projection. Questions and recommendations in it
come from engine facts and policy; a presenter may rephrase them but cannot add
decisions or unsupported trade-offs.

Slice 6 implements this as a project-local `SetupSession`. Its stable Session
ID binds the canonical project root; its monotonically increasing Setup Revision
is the compare-and-swap value for typed Human answers. The canonical session
record contains only the bound Discovery Digest, the pre-acceptance Activation
Manifest observation, typed answers, and canonical runtime-proof/acceptance
receipts. Candidate and publication objects are recompiled from those facts;
Python object serialization and conversation memory are not state authorities.

`resume` performs live mechanical discovery. A changed whole snapshot yields
`STALE` and one typed restart question; the engine never transfers old Human
answers into the new snapshot implicitly. A completed Runtime Proof Receipt is
reloaded and content/digest validated, so resuming a prepared candidate does
not repeat the authority smoke. `answer` accepts only identifiers, kinds, and
values present in the current Setup View revision. Unknown, stale-revision, or
out-of-option answers write nothing.

The alpha question compiler asks only policy unresolved by facts: enabled role
profile, Lead project-write authority, commit authority, irreversible
architecture boundary, explicit native-agent policy, an exact repository when
multiple Git roots exist, and one harness/model/reasoning binding per enabled
role. Model options are the mechanical Codex catalog cross-product with
supported reasoning controls, sorted without quality, price, speed, or fit
ranking. One-repository discovery is selected mechanically; multi-repository
alpha requires one explicit repository binding and defers cross-repository
routing.

The pure Setup View contains engine questions, issues, digest identities, and
the complete selected role bindings/effective envelopes. The Launcher procedure
is a thin presenter over the JSON commands `resume`, `answer`, and `accept`.
It may improve wording but preserves typed values and adds no option,
recommendation, retry, reset, model claim, policy, or completion claim.

Setup status values are:

```text
UNSATISFIABLE
POLICY_CONFLICT
NEEDS_HUMAN_INPUT
STATIC_INVALID
CAPABILITY_INVALID
SMOKE_FAILED
STALE
AWAITING_ACCEPTANCE
ACCEPTED
```

Setup does not reuse the task/Peer `BLOCKED` status.

## Delivery slices

1. Authority core: domain, closed-world algebra, solver, selector, and fake
   binding sources.
2. Codex authority: probe, normalize, compile, and exact repository/workspace/
   Git-common runtime binding.
3. Candidate compiler: discovery facts and typed Human decisions produce an
   immutable candidate.
4. Runtime proof: native introspection and deterministic probe receipts.
5. Acceptance: digest-bound Human acceptance and atomic publication.
6. Stateful facade and thin presenter: project-local CAS sessions expose only
   `resume`, `answer`, and `accept`; Setup View is a pure projection.
7. Runtime cutover: verify the active immutable generation and bind logical
   roles to exact workspace, Git-common, orchestration, evidence, and notebook
   paths; task launch and Supervisor attachment consume only those snapshots and
   bound launch receipts.

The alpha does not yet include additional production adapters, subjective model
ranking, a general routing language, fine-grained stale tracking, or
cross-repository candidate routing.
