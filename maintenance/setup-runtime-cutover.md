# Setup runtime cutover evidence

Date: 2026-08-25

Status: implemented and regression-tested

## Sole runtime authority

Runtime loads only `.orchestration/setup/current.json`. The strict reader
checks the Activation Manifest, immutable generation name and artifact set,
Publication Manifest, Acceptance Receipt, every primary artifact byte/digest,
the Setup Candidate identity and role launch-spec identities, the complete
`PROVEN` Runtime Proof Receipt, and the closed-world runtime-template schema.
Any mismatch fails before a run or role receipt is created.

The previous direct config, protocol template, harness catalog, recipe parser,
and provider-specific runtime readers were removed. No migration or fallback
path remains.

## Exact runtime binding

The accepted TOML contains logical Runtime Role Templates, not proof-time paths
or raw recipe authority. `bind-launch` requires the exact snapshotted config
digest plus exactly the binding sources named by one role. It canonicalizes all
paths and compiles one Codex argument vector and permission profile for the
Assignment. Missing, extra, unavailable, or out-of-envelope paths fail closed.

`init-run` compares the retained Activation Manifest digest, snapshots the
accepted config/protocol/activation and both runtime helpers into immutable run
evidence, and records every byte in the run manifest. Lead, Peer, and Supervisor
launch procedures consume only those snapshots and bound launch receipts.

## Exercised boundaries

Automated tests cover accepted-chain loading, Setup Plan and Runtime Proof
identity projection, exact Lead/Reviewer binding, unknown and extra binding
rejection, generation tamper rejection, Activation Manifest compare-and-swap at
run initialization, deterministic run staging, and launcher instruction
architecture. The full setup authority, candidate, proof, acceptance, and
stateful presenter suites remain green after the cutover.
