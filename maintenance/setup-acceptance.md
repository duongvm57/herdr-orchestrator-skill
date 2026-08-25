# Setup acceptance evidence

Date: 2026-08-25

Status: implemented and regression-tested

## Implemented seam

Slice 5 adds two deterministic operations:

```text
compile_setup_publication(candidate, runtime_proof)
    -> PublicationCompileResult

accept_setup_publication(publication, current_discovery, candidate_digest)
    -> AcceptanceResult
```

The first operation is pure. It requires a complete proof bound to every exact
candidate role and native launch specification, then creates four immutable
primary artifacts and their publication digest. The second operation performs
the bounded filesystem transaction only after the Human-supplied Candidate
Digest matches.

## Atomicity model

The engine writes a complete generation under:

```text
.orchestration/setup/generations/<publication_digest>/
```

It then activates that generation with one atomic replacement of:

```text
.orchestration/setup/current.json
```

The Activation Manifest is the only current-state record. A failure before
that replacement may leave an inactive immutable generation, but cannot expose
a partially published setup. Every artifact and receipt is fsynced before the
manifest replacement, followed by a directory fsync.

The publisher serializes on `publish.lock`. Discovery observes the previous
Activation Manifest, and the publisher rechecks all observed policy-source and
activation bytes before and after generation materialization. A changed current
state returns `STALE`.

## Bound identities

The publication digest binds:

- Candidate Digest;
- Discovery Digest;
- Runtime Proof Receipt digest; and
- every primary artifact path, size, and SHA-256 digest.

The Acceptance Receipt additionally binds the prior Activation Manifest digest,
generation path, and exact Human-confirmed Candidate Digest. The Activation
Manifest binds the Acceptance Receipt digest.

## Failure receipts exercised

Focused tests prove that:

- a wrong Candidate Digest writes nothing;
- failed runtime proof cannot create a publication;
- changed discovery and a concurrently created activation return `STALE`;
- symlinked control roots and conflicting generations fail closed;
- an injected failure at the activation replacement leaves no current manifest
  and only one complete inactive generation; and
- retrying the exact already-active publication is idempotent after locked
  manifest and generation verification.

The generated TOML parses with Python `tomllib`; setup plan and proof artifacts
carry the exact candidate identity; and the four alpha roles are present.

## Runtime publication boundary

The setup files live only inside the accepted generation. Runtime resolves the
Activation Manifest, verifies the complete receipt/digest chain, and binds
logical role templates to exact Assignment paths. No mutable direct-launch
config is published.
