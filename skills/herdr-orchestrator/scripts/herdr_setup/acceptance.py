"""Digest-bound setup acceptance and atomic generation activation."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from .candidate import (
    ACTIVATION_PATH,
    DiscoveryFailure,
    DiscoverySnapshot,
    FileObservation,
    FreshnessStatus,
    SetupCandidate,
    check_candidate_freshness,
    discover_setup,
    render_setup_candidate,
)
from .runtime_proof import (
    RuntimeProofReceipt,
    RuntimeProofStatus,
    digest_native_launch_spec,
    render_runtime_proof,
)


PUBLICATION_SCHEMA = "herdr.setup-publication"
ACCEPTANCE_SCHEMA = "herdr.setup-acceptance"
ACTIVATION_SCHEMA = "herdr.setup-activation"
SETUP_ROOT = ".orchestration/setup"
GENERATIONS_ROOT = f"{SETUP_ROOT}/generations"
LOCK_PATH = f"{SETUP_ROOT}/publish.lock"
PRIMARY_ARTIFACT_PATHS = (
    "herdr-orchestrator.toml",
    "runtime-proof.json",
    "setup-plan.json",
    "workspace-protocol.md",
)
def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(label: str, value: object) -> str:
    return hashlib.sha256(
        label.encode("ascii") + b"\0" + _canonical_bytes(value)
    ).hexdigest()


def _validate_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_relative_path(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value != Path(value).as_posix():
        raise ValueError(f"{label} must be a canonical relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {".", ".."}:
        raise ValueError(f"{label} escapes its root")


def _artifact_projection(artifact: PublicationArtifact) -> dict[str, object]:
    return {
        "path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size": artifact.size,
    }


@dataclass(frozen=True, order=True)
class PublicationArtifact:
    relative_path: str
    content: bytes = field(compare=False, repr=False)
    sha256: str = field(init=False)
    size: int = field(init=False)

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path, "publication artifact path")
        if not isinstance(self.content, bytes):
            raise TypeError("publication artifact content must be bytes")
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())
        object.__setattr__(self, "size", len(self.content))


class PublicationCompileStatus(str, Enum):
    PREPARED = "PREPARED"
    STALE = "STALE"
    SMOKE_FAILED = "SMOKE_FAILED"
    STATIC_INVALID = "STATIC_INVALID"


class PublicationRejectionCode(str, Enum):
    PROOF_NOT_PROVEN = "PROOF_NOT_PROVEN"
    PROOF_CANDIDATE_MISMATCH = "PROOF_CANDIDATE_MISMATCH"
    PROOF_DISCOVERY_MISMATCH = "PROOF_DISCOVERY_MISMATCH"
    PROOF_ROLE_SET_MISMATCH = "PROOF_ROLE_SET_MISMATCH"
    PROOF_LAUNCH_MISMATCH = "PROOF_LAUNCH_MISMATCH"


@dataclass(frozen=True, order=True)
class PublicationRejection:
    code: PublicationRejectionCode
    role: str | None = None


@dataclass(frozen=True)
class SetupPublication:
    candidate: SetupCandidate
    runtime_proof: RuntimeProofReceipt
    artifacts: tuple[PublicationArtifact, ...]
    publication_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, SetupCandidate):
            raise TypeError("publication candidate must be a SetupCandidate")
        if not isinstance(self.runtime_proof, RuntimeProofReceipt):
            raise TypeError("publication proof must be a RuntimeProofReceipt")
        artifacts = tuple(sorted(self.artifacts, key=lambda item: item.relative_path))
        if any(not isinstance(item, PublicationArtifact) for item in artifacts):
            raise TypeError("publication contains an invalid artifact")
        paths = tuple(item.relative_path for item in artifacts)
        if paths != PRIMARY_ARTIFACT_PATHS:
            raise ValueError("publication must contain the exact artifact set")
        if _publication_rejections(self.candidate, self.runtime_proof):
            raise ValueError("publication candidate and runtime proof do not match")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "publication_digest",
            _digest("herdr-setup-publication", _publication_projection(self)),
        )

    @property
    def candidate_digest(self) -> str:
        return self.candidate.candidate_digest

    @property
    def discovery_digest(self) -> str:
        return self.candidate.discovery_digest

    @property
    def runtime_proof_digest(self) -> str:
        return self.runtime_proof.receipt_digest


@dataclass(frozen=True)
class PublicationCompileResult:
    status: PublicationCompileStatus
    publication: SetupPublication | None
    rejections: tuple[PublicationRejection, ...]


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _capability_label(name: str, resource: str | None) -> str:
    return name if resource is None else f"{name}({resource})"


def _render_config(candidate: SetupCandidate) -> bytes:
    policy_answers = {
        answer.identifier: answer.value
        for answer in candidate.compiled_policy.policy_answers
    }
    live_language = policy_answers.get("policy.live_language")
    artifact_language = policy_answers.get("policy.artifact_language")
    if not isinstance(live_language, str) or not isinstance(artifact_language, str):
        raise ValueError("runtime publication requires both Human-selected languages")
    repository_paths = {
        rule.resource: rule.path
        for plan in candidate.role_plans
        for rule in plan.launch_spec.filesystem_rules
        if rule.resource in {"project:assigned", "git-common:assigned"}
    }
    repository_root = repository_paths.get("project:assigned")
    git_common_dir = repository_paths.get("git-common:assigned")
    if repository_root is None or git_common_dir is None:
        raise ValueError("runtime publication requires repository and Git-common bindings")
    lines = [
        f"schema = {_toml_string(PUBLICATION_SCHEMA)}",
        f"candidate_digest = {_toml_string(candidate.candidate_digest)}",
        f"discovery_digest = {_toml_string(candidate.discovery_digest)}",
        f"project_root = {_toml_string(candidate.discovery.project_root)}",
        f"repository_root = {_toml_string(repository_root)}",
        f"git_common_dir = {_toml_string(git_common_dir)}",
        f"live_orchestration_language = {_toml_string(live_language)}",
        f"durable_artifact_language = {_toml_string(artifact_language)}",
        (
            "native_agent_policy = "
            f"{_toml_string(candidate.compiled_policy.native_agent_policy.value)}"
        ),
    ]
    for plan in candidate.role_plans:
        launch = plan.launch_spec
        lines.extend(
            (
                "",
                f"[roles.{plan.role}]",
                f"adapter_kind = {_toml_string(launch.adapter_kind)}",
                f"executable = {_toml_string(launch.executable)}",
                f"runtime_root = {_toml_string(next(rule.path for rule in launch.filesystem_rules if rule.resource == 'runtime:codex'))}",
                f"model = {_toml_string(launch.model)}",
                f"reasoning_effort = {_toml_string(launch.reasoning_effort)}",
                f"selected_binding_id = {_toml_string(launch.selected_binding_id)}",
                f"native_agents_enabled = {str(launch.native_agents_enabled).lower()}",
                f"network_enabled = {str(launch.network_enabled).lower()}",
                f"proof_launch_spec_digest = {_toml_string(digest_native_launch_spec(launch))}",
            )
        )
        access_by_resource: dict[str, str] = {}
        for capability in launch.effective_envelope.effective:
            if capability.name not in {"fs.read", "fs.write"} or capability.resource is None:
                continue
            access = "write" if capability.name == "fs.write" else "read"
            if access_by_resource.get(capability.resource) != "write":
                access_by_resource[capability.resource] = access
        binding_sources = {
            "runtime:codex": "runtime",
            "project:assigned": "workspace",
            "git-common:assigned": "git_common",
            "orchestration:control": "orchestration",
            "control:run": "evidence",
            "evidence:assignment": "evidence",
            "notebook:session": "notebook",
        }
        for resource, access in sorted(access_by_resource.items()):
            binding_source = binding_sources.get(resource)
            if binding_source is None:
                raise ValueError(f"runtime publication has no binding source for {resource}")
            lines.extend(("", f"[[roles.{plan.role}.filesystem]]"))
            lines.extend(
                (
                    f"resource = {_toml_string(resource)}",
                    f"binding = {_toml_string(binding_source)}",
                    f"access = {_toml_string(access)}",
                )
            )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _markdown_capabilities(values: Iterable[object]) -> str:
    labels = [
        _capability_label(capability.name, capability.resource)
        for capability in sorted(values)
    ]
    return ", ".join(f"`{label}`" for label in labels) if labels else "none"


def _render_protocol(candidate: SetupCandidate) -> bytes:
    policy_by_role = {
        decision.role: decision.policy
        for decision in candidate.compiled_policy.role_authority
    }
    lines = [
        "# Workspace Protocol",
        "",
        "This is a deterministic projection of a Human-decision-bound setup candidate.",
        "",
        "## Identity",
        "",
        f"- Candidate digest: `{candidate.candidate_digest}`",
        f"- Discovery digest: `{candidate.discovery_digest}`",
        f"- Human decisions digest: `{candidate.human_decisions_digest}`",
        (
            "- Native agent policy: "
            f"`{candidate.compiled_policy.native_agent_policy.value}`"
        ),
        (
            "- Live orchestration language: `"
            f"{next(answer.value for answer in candidate.compiled_policy.policy_answers if answer.identifier == 'policy.live_language')}`"
        ),
        (
            "- Durable artifact language: `"
            f"{next(answer.value for answer in candidate.compiled_policy.policy_answers if answer.identifier == 'policy.artifact_language')}`"
        ),
        "",
        "## Repositories",
        "",
    ]
    for repository in candidate.discovery.repositories:
        lines.append(
            f"- `{repository.identifier}`: `{repository.relative_path}` "
            f"(Git common: `{repository.git_common_dir}`)"
        )
    lines.extend(("", "## Human-approved policy answers", ""))
    if candidate.compiled_policy.policy_answers:
        for answer in candidate.compiled_policy.policy_answers:
            value = json.dumps(answer.value, ensure_ascii=True)
            lines.append(f"- `{answer.identifier}` ({answer.kind.value}): `{value}`")
    else:
        lines.append("- none")
    lines.extend(("", "## Role authority", ""))
    for plan in candidate.role_plans:
        requirement = plan.requirement
        policy = policy_by_role[plan.role]
        launch = plan.launch_spec
        lines.extend(
            (
                f"### {plan.role}",
                "",
                f"- Must have: {_markdown_capabilities(requirement.must_have)}",
                f"- May have ceiling: {_markdown_capabilities(requirement.may_have)}",
                f"- Role forbidden: {_markdown_capabilities(requirement.must_not_have)}",
                f"- Human permitted: {_markdown_capabilities(policy.permitted)}",
                f"- Policy forbidden: {_markdown_capabilities(policy.must_not_have)}",
                (
                    "- Effective: "
                    f"{_markdown_capabilities(launch.effective_envelope.effective)}"
                ),
                f"- Selected binding: `{launch.selected_binding_id}`",
                (
                    f"- Human-selected model: `{launch.adapter_kind}` / "
                    f"`{launch.model}` / `{launch.reasoning_effort}`"
                ),
                "",
            )
        )
    lines.extend(("## Provenance", ""))
    for record in candidate.provenance:
        digest = f" (`{record.source_digest}`)" if record.source_digest else ""
        lines.append(
            f"- `{record.subject}`: {record.kind.value} from "
            f"`{record.source}`{digest}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _publication_projection(publication: SetupPublication) -> dict[str, object]:
    return {
        "schema": PUBLICATION_SCHEMA,
        "candidate_digest": publication.candidate_digest,
        "discovery_digest": publication.discovery_digest,
        "runtime_proof_digest": publication.runtime_proof_digest,
        "artifacts": [_artifact_projection(item) for item in publication.artifacts],
    }


def _publication_rejections(
    candidate: SetupCandidate,
    proof: RuntimeProofReceipt,
) -> tuple[PublicationRejection, ...]:
    rejections: list[PublicationRejection] = []
    if proof.candidate_digest != candidate.candidate_digest:
        rejections.append(
            PublicationRejection(PublicationRejectionCode.PROOF_CANDIDATE_MISMATCH)
        )
    if (
        proof.discovery_digest != candidate.discovery_digest
        or proof.current_discovery_digest != candidate.discovery_digest
    ):
        rejections.append(
            PublicationRejection(PublicationRejectionCode.PROOF_DISCOVERY_MISMATCH)
        )
    plan_by_role = {plan.role: plan for plan in candidate.role_plans}
    proof_by_role = {role.role: role for role in proof.roles}
    if set(plan_by_role) != set(proof_by_role):
        rejections.append(
            PublicationRejection(PublicationRejectionCode.PROOF_ROLE_SET_MISMATCH)
        )
    else:
        for role, plan in plan_by_role.items():
            if (
                proof_by_role[role].candidate_digest != candidate.candidate_digest
                or proof_by_role[role].launch_spec_digest
                != digest_native_launch_spec(plan.launch_spec)
            ):
                rejections.append(
                    PublicationRejection(
                        PublicationRejectionCode.PROOF_LAUNCH_MISMATCH,
                        role,
                    )
                )
    if proof.status is not RuntimeProofStatus.PROVEN:
        rejections.append(
            PublicationRejection(PublicationRejectionCode.PROOF_NOT_PROVEN)
        )
    return tuple(rejections)


def compile_setup_publication(
    candidate: SetupCandidate,
    runtime_proof: RuntimeProofReceipt,
) -> PublicationCompileResult:
    """Compile exact candidate artifacts only after complete bound runtime proof."""

    if not isinstance(candidate, SetupCandidate):
        raise TypeError("candidate must be a SetupCandidate")
    if not isinstance(runtime_proof, RuntimeProofReceipt):
        raise TypeError("runtime proof must be a RuntimeProofReceipt")
    rejections = _publication_rejections(candidate, runtime_proof)
    if rejections:
        if runtime_proof.status is RuntimeProofStatus.STALE:
            status = PublicationCompileStatus.STALE
        elif any(
            rejection.code is not PublicationRejectionCode.PROOF_NOT_PROVEN
            for rejection in rejections
        ):
            status = PublicationCompileStatus.STATIC_INVALID
        else:
            status = PublicationCompileStatus.SMOKE_FAILED
        return PublicationCompileResult(status, None, rejections)
    publication = SetupPublication(
        candidate,
        runtime_proof,
        (
            PublicationArtifact("herdr-orchestrator.toml", _render_config(candidate)),
            PublicationArtifact("runtime-proof.json", render_runtime_proof(runtime_proof)),
            PublicationArtifact("setup-plan.json", render_setup_candidate(candidate)),
            PublicationArtifact("workspace-protocol.md", _render_protocol(candidate)),
        ),
    )
    return PublicationCompileResult(PublicationCompileStatus.PREPARED, publication, ())


class AcceptanceStatus(str, Enum):
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    STALE = "STALE"
    SMOKE_FAILED = "SMOKE_FAILED"
    STATIC_INVALID = "STATIC_INVALID"
    ACCEPTED = "ACCEPTED"


class AcceptanceRejectionCode(str, Enum):
    CANDIDATE_DIGEST_MISMATCH = "CANDIDATE_DIGEST_MISMATCH"
    DISCOVERY_STALE = "DISCOVERY_STALE"
    CURRENT_STATE_CHANGED = "CURRENT_STATE_CHANGED"
    PUBLISH_TARGET_UNSAFE = "PUBLISH_TARGET_UNSAFE"
    GENERATION_CONFLICT = "GENERATION_CONFLICT"
    PUBLICATION_IO_FAILED = "PUBLICATION_IO_FAILED"


@dataclass(frozen=True)
class AcceptanceRejection:
    code: AcceptanceRejectionCode
    detail: str | None = None


@dataclass(frozen=True)
class AcceptanceReceipt:
    candidate_digest: str
    discovery_digest: str
    runtime_proof_digest: str
    publication_digest: str
    prior_activation_digest: str | None
    generation: str
    artifacts: tuple[tuple[str, str], ...]
    receipt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.candidate_digest, "accepted candidate digest"),
            (self.discovery_digest, "accepted discovery digest"),
            (self.runtime_proof_digest, "accepted runtime proof digest"),
            (self.publication_digest, "accepted publication digest"),
        ):
            _validate_digest(value, label)
        if self.prior_activation_digest is not None:
            _validate_digest(self.prior_activation_digest, "prior activation digest")
        _validate_relative_path(self.generation, "accepted generation")
        artifacts = tuple(sorted(self.artifacts))
        if tuple(path for path, _ in artifacts) != PRIMARY_ARTIFACT_PATHS:
            raise ValueError("acceptance receipt has the wrong artifact set")
        for path, digest in artifacts:
            _validate_relative_path(path, "accepted artifact path")
            _validate_digest(digest, "accepted artifact digest")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "receipt_digest",
            _digest("herdr-setup-acceptance", _acceptance_projection(self)),
        )


@dataclass(frozen=True)
class AcceptanceResult:
    status: AcceptanceStatus
    receipt: AcceptanceReceipt | None
    rejections: tuple[AcceptanceRejection, ...]


def _acceptance_projection(receipt: AcceptanceReceipt) -> dict[str, object]:
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "status": AcceptanceStatus.ACCEPTED.value,
        "candidate_digest": receipt.candidate_digest,
        "discovery_digest": receipt.discovery_digest,
        "runtime_proof_digest": receipt.runtime_proof_digest,
        "publication_digest": receipt.publication_digest,
        "prior_activation_digest": receipt.prior_activation_digest,
        "generation": receipt.generation,
        "artifacts": [
            {"path": path, "sha256": digest} for path, digest in receipt.artifacts
        ],
    }


def render_acceptance_receipt(receipt: AcceptanceReceipt) -> bytes:
    """Render the immutable Human acceptance receipt as canonical JSON."""

    if not isinstance(receipt, AcceptanceReceipt):
        raise TypeError("receipt must be an AcceptanceReceipt")
    document = _acceptance_projection(receipt)
    document["receipt_digest"] = receipt.receipt_digest
    return _canonical_bytes(document) + b"\n"


def parse_acceptance_receipt(payload: bytes) -> AcceptanceReceipt:
    """Load and revalidate one canonical Human acceptance receipt."""

    if not isinstance(payload, bytes):
        raise TypeError("acceptance receipt payload must be bytes")
    if len(payload) > 1024 * 1024:
        raise ValueError("acceptance receipt payload exceeds the bounded size")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("acceptance receipt payload is not valid JSON") from exc
    expected = {
        "schema",
        "status",
        "candidate_digest",
        "discovery_digest",
        "runtime_proof_digest",
        "publication_digest",
        "prior_activation_digest",
        "generation",
        "artifacts",
        "receipt_digest",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise ValueError("acceptance receipt payload has the wrong fields")
    if (
        document["schema"] != ACCEPTANCE_SCHEMA
        or document["status"] != AcceptanceStatus.ACCEPTED.value
        or not isinstance(document["artifacts"], list)
    ):
        raise ValueError("acceptance receipt payload has invalid metadata")
    artifacts: list[tuple[str, str]] = []
    for artifact in document["artifacts"]:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise ValueError("acceptance receipt artifact has the wrong fields")
        artifacts.append((artifact["path"], artifact["sha256"]))
    try:
        receipt = AcceptanceReceipt(
            candidate_digest=document["candidate_digest"],
            discovery_digest=document["discovery_digest"],
            runtime_proof_digest=document["runtime_proof_digest"],
            publication_digest=document["publication_digest"],
            prior_activation_digest=document["prior_activation_digest"],
            generation=document["generation"],
            artifacts=tuple(artifacts),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("acceptance receipt payload contains invalid values") from exc
    if receipt.receipt_digest != document["receipt_digest"]:
        raise ValueError("acceptance receipt digest does not match its content")
    if render_acceptance_receipt(receipt) != payload:
        raise ValueError("acceptance receipt payload is not canonical")
    return receipt


def _publication_manifest(publication: SetupPublication) -> bytes:
    document = _publication_projection(publication)
    document["publication_digest"] = publication.publication_digest
    return _canonical_bytes(document) + b"\n"


def _activation_document(
    publication: SetupPublication,
    receipt: AcceptanceReceipt,
) -> bytes:
    return _canonical_bytes(
        {
            "schema": ACTIVATION_SCHEMA,
            "status": AcceptanceStatus.ACCEPTED.value,
            "candidate_digest": publication.candidate_digest,
            "discovery_digest": publication.discovery_digest,
            "runtime_proof_digest": publication.runtime_proof_digest,
            "publication_digest": publication.publication_digest,
            "acceptance_receipt_digest": receipt.receipt_digest,
            "generation": receipt.generation,
            "artifacts": [
                _artifact_projection(artifact) for artifact in publication.artifacts
            ],
        }
    ) + b"\n"


def _make_receipt(publication: SetupPublication) -> AcceptanceReceipt:
    activation = publication.candidate.discovery.existing_activation
    return AcceptanceReceipt(
        publication.candidate_digest,
        publication.discovery_digest,
        publication.runtime_proof_digest,
        publication.publication_digest,
        activation.sha256,
        f"generations/{publication.publication_digest}",
        tuple(
            (artifact.relative_path, artifact.sha256)
            for artifact in publication.artifacts
        ),
    )


class _UnsafeTarget(RuntimeError):
    pass


class _GenerationConflict(RuntimeError):
    pass


def _ensure_directory(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        path.mkdir(mode=0o700)
        metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise _UnsafeTarget(f"{path} is not a real directory")


def _safe_roots(project_root: Path) -> tuple[Path, Path]:
    orchestration = project_root / ".orchestration"
    setup_root = project_root / SETUP_ROOT
    generations = project_root / GENERATIONS_ROOT
    for path in (orchestration, setup_root, generations):
        _ensure_directory(path)
    return setup_root, generations


def _existing_safe_roots(project_root: Path) -> tuple[Path, Path]:
    orchestration = project_root / ".orchestration"
    setup_root = project_root / SETUP_ROOT
    generations = project_root / GENERATIONS_ROOT
    for path in (orchestration, setup_root, generations):
        metadata = os.lstat(path)
        if not stat.S_ISDIR(metadata.st_mode):
            raise _UnsafeTarget(f"{path} is not a real directory")
    return setup_root, generations


def _open_lock(path: Path, *, create: bool) -> int:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if not create:
            raise
    else:
        if not stat.S_ISREG(metadata.st_mode):
            raise _UnsafeTarget(f"{path} is not a regular lock file")
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise _UnsafeTarget(f"{path} is not a regular lock file")
    return descriptor


def _stable_regular_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _UnsafeTarget(f"{path} is not a regular file")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or len(data) != after.st_size
        ):
            raise _UnsafeTarget(f"{path} changed while it was read")
        return data
    finally:
        os.close(descriptor)


def _matches_observation(project_root: Path, observation: FileObservation) -> bool:
    path = project_root / observation.relative_path
    try:
        data = _stable_regular_bytes(path)
    except FileNotFoundError:
        return not observation.exists
    except OSError:
        return False
    if not observation.exists:
        return False
    return (
        len(data) == observation.size
        and hashlib.sha256(data).hexdigest() == observation.sha256
    )


def _input_observations(snapshot: DiscoverySnapshot) -> tuple[FileObservation, ...]:
    return (
        *snapshot.policy_sources,
        snapshot.existing_activation,
    )


def _inputs_are_current(snapshot: DiscoverySnapshot) -> bool:
    root = Path(snapshot.project_root)
    return all(
        _matches_observation(root, observation)
        for observation in _input_observations(snapshot)
    )


def _snapshot_is_live(snapshot: DiscoverySnapshot) -> bool:
    if not _inputs_are_current(snapshot):
        return False
    try:
        observed = discover_setup(
            snapshot.project_root,
            harnesses=snapshot.harnesses,
            adapters=snapshot.adapters,
        )
    except (DiscoveryFailure, OSError):
        return False
    return observed.discovery_digest == snapshot.discovery_digest


def _write_new_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short publication write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _expected_generation_files(
    publication: SetupPublication,
    receipt: AcceptanceReceipt,
) -> dict[str, bytes]:
    files = {
        artifact.relative_path: artifact.content for artifact in publication.artifacts
    }
    files["publication-manifest.json"] = _publication_manifest(publication)
    files["acceptance-receipt.json"] = render_acceptance_receipt(receipt)
    return files


def _verify_generation(path: Path, expected: dict[str, bytes]) -> None:
    metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise _GenerationConflict(f"{path} is not an immutable generation directory")
    actual_names = tuple(sorted(item.name for item in path.iterdir()))
    expected_names = tuple(sorted(expected))
    if actual_names != expected_names:
        raise _GenerationConflict(f"{path} contains an unexpected artifact set")
    for name, content in expected.items():
        if _stable_regular_bytes(path / name) != content:
            raise _GenerationConflict(f"{path / name} conflicts with publication")


def _remove_staging(path: Path, names: Iterable[str]) -> None:
    for name in names:
        try:
            (path / name).unlink()
        except FileNotFoundError:
            pass
    try:
        path.rmdir()
    except FileNotFoundError:
        pass


def _materialize_generation(
    generations: Path,
    publication: SetupPublication,
    receipt: AcceptanceReceipt,
) -> Path:
    expected = _expected_generation_files(publication, receipt)
    final = generations / publication.publication_digest
    try:
        _verify_generation(final, expected)
        return final
    except FileNotFoundError:
        pass
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=generations))
    try:
        for name in sorted(expected):
            _write_new_file(staging / name, expected[name])
        _fsync_directory(staging)
        try:
            os.rename(staging, final)
        except FileExistsError:
            _verify_generation(final, expected)
        _fsync_directory(generations)
    finally:
        if staging.exists():
            _remove_staging(staging, expected)
    _verify_generation(final, expected)
    return final


def _read_current_activation(project_root: Path) -> bytes | None:
    path = project_root / ACTIVATION_PATH
    try:
        return _stable_regular_bytes(path)
    except FileNotFoundError:
        return None


def _generation_path(project_root: Path, receipt: AcceptanceReceipt) -> Path:
    return project_root / SETUP_ROOT / receipt.generation


def _already_active(
    project_root: Path,
    publication: SetupPublication,
    receipt: AcceptanceReceipt,
    activation: bytes,
) -> bool:
    _existing_safe_roots(project_root)
    lock_descriptor = _open_lock(project_root / LOCK_PATH, create=False)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        if _read_current_activation(project_root) != activation:
            return False
        _verify_generation(
            _generation_path(project_root, receipt),
            _expected_generation_files(publication, receipt),
        )
        return True
    finally:
        os.close(lock_descriptor)


def _activate(setup_root: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".current-",
        suffix=".tmp",
        dir=setup_root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, setup_root / "current.json")
        _fsync_directory(setup_root)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _result(
    status: AcceptanceStatus,
    code: AcceptanceRejectionCode,
    detail: str | None = None,
) -> AcceptanceResult:
    return AcceptanceResult(status, None, (AcceptanceRejection(code, detail),))


def accept_setup_publication(
    publication: SetupPublication,
    current_discovery: DiscoverySnapshot,
    accepted_candidate_digest: str,
) -> AcceptanceResult:
    """Accept one exact candidate and atomically activate its immutable generation."""

    if not isinstance(publication, SetupPublication):
        raise TypeError("publication must be a SetupPublication")
    if not isinstance(current_discovery, DiscoverySnapshot):
        raise TypeError("current discovery must be a DiscoverySnapshot")
    if accepted_candidate_digest != publication.candidate_digest:
        return _result(
            AcceptanceStatus.AWAITING_ACCEPTANCE,
            AcceptanceRejectionCode.CANDIDATE_DIGEST_MISMATCH,
        )
    receipt = _make_receipt(publication)
    activation = _activation_document(publication, receipt)
    candidate = publication.candidate
    root = Path(candidate.discovery.project_root)
    if current_discovery.project_root != str(root):
        return _result(
            AcceptanceStatus.STALE,
            AcceptanceRejectionCode.DISCOVERY_STALE,
        )
    freshness = check_candidate_freshness(candidate, current_discovery)
    if freshness.status is FreshnessStatus.STALE:
        try:
            if _already_active(root, publication, receipt, activation):
                return AcceptanceResult(AcceptanceStatus.ACCEPTED, receipt, ())
        except (FileNotFoundError, _UnsafeTarget, _GenerationConflict, OSError):
            pass
        return _result(
            AcceptanceStatus.STALE,
            AcceptanceRejectionCode.DISCOVERY_STALE,
        )
    if not _snapshot_is_live(current_discovery):
        return _result(
            AcceptanceStatus.STALE,
            AcceptanceRejectionCode.CURRENT_STATE_CHANGED,
        )
    try:
        setup_root, generations = _safe_roots(root)
        lock_descriptor = _open_lock(root / LOCK_PATH, create=True)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            current_activation = _read_current_activation(root)
            if current_activation == activation:
                _verify_generation(
                    _generation_path(root, receipt),
                    _expected_generation_files(publication, receipt),
                )
                return AcceptanceResult(AcceptanceStatus.ACCEPTED, receipt, ())
            if not _snapshot_is_live(current_discovery):
                return _result(
                    AcceptanceStatus.STALE,
                    AcceptanceRejectionCode.CURRENT_STATE_CHANGED,
                )
            _materialize_generation(generations, publication, receipt)
            if not _snapshot_is_live(current_discovery):
                return _result(
                    AcceptanceStatus.STALE,
                    AcceptanceRejectionCode.CURRENT_STATE_CHANGED,
                )
            _activate(setup_root, activation)
            return AcceptanceResult(AcceptanceStatus.ACCEPTED, receipt, ())
        finally:
            os.close(lock_descriptor)
    except _UnsafeTarget as exc:
        return _result(
            AcceptanceStatus.STATIC_INVALID,
            AcceptanceRejectionCode.PUBLISH_TARGET_UNSAFE,
            str(exc),
        )
    except _GenerationConflict as exc:
        return _result(
            AcceptanceStatus.STATIC_INVALID,
            AcceptanceRejectionCode.GENERATION_CONFLICT,
            str(exc),
        )
    except OSError as exc:
        return _result(
            AcceptanceStatus.STATIC_INVALID,
            AcceptanceRejectionCode.PUBLICATION_IO_FAILED,
            f"{type(exc).__name__}:{exc.errno}",
        )
