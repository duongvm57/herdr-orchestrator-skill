"""Load one accepted setup and bind its logical roles to exact runtime paths."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PUBLICATION_SCHEMA = "herdr.setup-publication"
ACCEPTANCE_SCHEMA = "herdr.setup-acceptance"
ACTIVATION_SCHEMA = "herdr.setup-activation"
CANDIDATE_SCHEMA = "herdr.setup-candidate"
ACCEPTED_STATUS = "ACCEPTED"
PROVEN_STATUS = "PROVEN"
CURRENT_PATH = ".orchestration/setup/current.json"
PRIMARY_ARTIFACT_PATHS = (
    "herdr-orchestrator.toml",
    "runtime-proof.json",
    "setup-plan.json",
    "workspace-protocol.md",
)
GENERATION_FILE_PATHS = (
    "acceptance-receipt.json",
    "herdr-orchestrator.toml",
    "publication-manifest.json",
    "runtime-proof.json",
    "setup-plan.json",
    "workspace-protocol.md",
)
MAX_CONTROL_FILE_BYTES = 16 * 1024 * 1024
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")
RESOURCE_BINDINGS = {
    "runtime:codex": "runtime",
    "project:assigned": "workspace",
    "git-common:assigned": "git_common",
    "orchestration:control": "orchestration",
    "control:run": "evidence",
    "evidence:assignment": "evidence",
    "notebook:session": "notebook",
}


class RuntimeConfigError(RuntimeError):
    """An accepted setup or exact role binding failed closed."""


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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise RuntimeConfigError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_text(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeConfigError(f"{label} must be bounded canonical text")
    return value


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        raise RuntimeConfigError(f"{label} must be a canonical identifier")
    return value


def _canonical_directory(value: object, label: str) -> Path:
    text = _require_text(value, label)
    path = Path(text)
    if not path.is_absolute() or os.path.normpath(text) != text or path.is_symlink():
        raise RuntimeConfigError(f"{label} must be a canonical absolute directory")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeConfigError(f"{label} is not an accessible directory") from exc
    if not resolved.is_dir() or str(resolved) != text:
        raise RuntimeConfigError(f"{label} must be a canonical absolute directory")
    return resolved


def _canonical_file(value: object, label: str) -> Path:
    text = _require_text(value, label)
    path = Path(text)
    if not path.is_absolute() or os.path.normpath(text) != text or path.is_symlink():
        raise RuntimeConfigError(f"{label} must be a canonical absolute file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeConfigError(f"{label} is not an accessible file") from exc
    if not resolved.is_file() or str(resolved) != text:
        raise RuntimeConfigError(f"{label} must be a canonical absolute file")
    return resolved


def _stable_regular_bytes(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeConfigError(f"{label} is not a readable regular file") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_CONTROL_FILE_BYTES:
            raise RuntimeConfigError(f"{label} is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        after = os.fstat(descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(value) != after.st_size:
            raise RuntimeConfigError(f"{label} changed while it was read")
        return value
    finally:
        os.close(descriptor)


def _canonical_json(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeConfigError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict) or _canonical_bytes(value) + b"\n" != payload:
        raise RuntimeConfigError(f"{label} is not canonical JSON")
    return value


@dataclass(frozen=True, order=True)
class RuntimeFilesystemGrant:
    resource: str
    binding: str
    access: str


@dataclass(frozen=True)
class RuntimeRoleTemplate:
    role: str
    adapter_kind: str
    executable: str
    runtime_root: str
    model: str
    reasoning_effort: str
    selected_binding_id: str
    proof_launch_spec_digest: str
    filesystem: tuple[RuntimeFilesystemGrant, ...]


@dataclass(frozen=True)
class RuntimeProjectConfig:
    candidate_digest: str
    discovery_digest: str
    project_root: str
    repository_root: str
    git_common_dir: str
    live_language: str
    artifact_language: str
    roles: tuple[RuntimeRoleTemplate, ...]

    @property
    def role_map(self) -> dict[str, RuntimeRoleTemplate]:
        return {role.role: role for role in self.roles}


@dataclass(frozen=True)
class AcceptedArtifact:
    path: str
    absolute_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class AcceptedProject:
    project_root: str
    activation_path: str
    activation_sha256: str
    generation_root: str
    publication_digest: str
    acceptance_receipt_digest: str
    config: RuntimeProjectConfig
    artifacts: tuple[AcceptedArtifact, ...]

    @property
    def artifact_map(self) -> dict[str, AcceptedArtifact]:
        return {artifact.path: artifact for artifact in self.artifacts}


@dataclass(frozen=True)
class BoundRoleLaunch:
    role: str
    kind: str
    executable: str
    cwd: str
    model: str
    reasoning_effort: str
    selected_binding_id: str
    arguments: tuple[str, ...]
    filesystem: tuple[tuple[str, str, str], ...]
    launch_digest: str


def _parse_artifacts(value: object, *, sizes: bool) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise RuntimeConfigError("accepted artifact manifest must be an array")
    expected_fields = {"path", "sha256", "size"} if sizes else {"path", "sha256"}
    result: list[dict[str, object]] = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise RuntimeConfigError("accepted artifact entry has the wrong fields")
        path = entry["path"]
        if path not in PRIMARY_ARTIFACT_PATHS:
            raise RuntimeConfigError("accepted artifact entry has an unsupported path")
        _require_digest(entry["sha256"], "accepted artifact digest")
        if sizes and (
            type(entry["size"]) is not int or entry["size"] < 0
        ):
            raise RuntimeConfigError("accepted artifact size is invalid")
        result.append(entry)
    if tuple(entry["path"] for entry in result) != PRIMARY_ARTIFACT_PATHS:
        raise RuntimeConfigError("accepted artifact manifest is incomplete or unordered")
    return tuple(result)


def _validate_role_shape(role: str, grants: tuple[RuntimeFilesystemGrant, ...]) -> None:
    access = {grant.resource: grant.access for grant in grants}
    required = {"runtime:codex": "read", "project:assigned": "read"}
    allowed: dict[str, set[str]] = {
        "lead": {
            "runtime:codex",
            "project:assigned",
            "git-common:assigned",
            "orchestration:control",
            "control:run",
        },
        "engineer": {
            "runtime:codex",
            "project:assigned",
            "git-common:assigned",
            "orchestration:control",
            "evidence:assignment",
        },
        "reviewer": {
            "runtime:codex",
            "project:assigned",
            "git-common:assigned",
            "evidence:assignment",
        },
        "supervisor": {
            "runtime:codex",
            "project:assigned",
            "notebook:session",
        },
    }
    required_by_role: dict[str, dict[str, str]] = {
        "lead": {"git-common:assigned": "read", "control:run": "write"},
        "engineer": {
            "project:assigned": "write",
            "evidence:assignment": "write",
        },
        "reviewer": {
            "git-common:assigned": "read",
            "evidence:assignment": "write",
        },
        "supervisor": {"notebook:session": "write"},
    }
    expected = {**required, **required_by_role[role]}
    if any(access.get(resource) != expected_access for resource, expected_access in expected.items()):
        raise RuntimeConfigError(f"role {role} is missing required closed-world authority")
    if set(access) - allowed[role]:
        raise RuntimeConfigError(f"role {role} has unsupported authority")
    if role in {"reviewer", "supervisor"} and access["project:assigned"] != "read":
        raise RuntimeConfigError(f"role {role} must keep project mutation denied")
    if role == "lead" and access.get("git-common:assigned") != "read":
        raise RuntimeConfigError("Lead Git metadata must remain read-only")
    if role == "engineer" and access.get("git-common:assigned") not in {"read", "write"}:
        raise RuntimeConfigError("Engineer Git metadata authority is invalid")


def parse_runtime_config(payload: bytes) -> RuntimeProjectConfig:
    """Parse the deterministic runtime-template artifact through one strict interface."""

    try:
        document = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeConfigError("accepted project config is not valid TOML") from exc
    expected = {
        "schema",
        "candidate_digest",
        "discovery_digest",
        "project_root",
        "repository_root",
        "git_common_dir",
        "live_orchestration_language",
        "durable_artifact_language",
        "native_agent_policy",
        "roles",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise RuntimeConfigError("accepted project config has the wrong top-level fields")
    if document["schema"] != PUBLICATION_SCHEMA:
        raise RuntimeConfigError("accepted project config has an unsupported schema")
    if document["native_agent_policy"] != "disabled":
        raise RuntimeConfigError("accepted project config must disable native agents")
    project_root = _canonical_directory(document["project_root"], "configured project root")
    repository_root = _canonical_directory(
        document["repository_root"], "configured repository root"
    )
    git_common_dir = _canonical_directory(
        document["git_common_dir"], "configured Git common directory"
    )
    if not repository_root.is_relative_to(project_root):
        raise RuntimeConfigError("configured repository root escapes the project root")
    raw_roles = document["roles"]
    if not isinstance(raw_roles, dict) or set(raw_roles) not in (
        {"lead", "engineer", "reviewer"},
        {"lead", "engineer", "reviewer", "supervisor"},
    ):
        raise RuntimeConfigError("accepted project config has an unsupported role set")
    roles: list[RuntimeRoleTemplate] = []
    role_fields = {
        "adapter_kind",
        "executable",
        "runtime_root",
        "model",
        "reasoning_effort",
        "selected_binding_id",
        "native_agents_enabled",
        "network_enabled",
        "proof_launch_spec_digest",
        "filesystem",
    }
    for role in sorted(raw_roles):
        raw = raw_roles[role]
        if not isinstance(raw, dict) or set(raw) != role_fields:
            raise RuntimeConfigError(f"role {role} has the wrong fields")
        if (
            raw["adapter_kind"] != "codex"
            or raw["native_agents_enabled"] is not False
            or raw["network_enabled"] is not False
        ):
            raise RuntimeConfigError(f"role {role} has unsupported runtime controls")
        executable = _canonical_file(raw["executable"], f"role {role} executable")
        runtime_root = _canonical_directory(
            raw["runtime_root"], f"role {role} runtime root"
        )
        raw_grants = raw["filesystem"]
        if not isinstance(raw_grants, list) or not raw_grants:
            raise RuntimeConfigError(f"role {role} requires filesystem authority")
        grants: list[RuntimeFilesystemGrant] = []
        for entry in raw_grants:
            if not isinstance(entry, dict) or set(entry) != {"resource", "binding", "access"}:
                raise RuntimeConfigError(f"role {role} filesystem entry has the wrong fields")
            resource = _require_text(entry["resource"], f"role {role} resource", maximum=128)
            binding = _require_identifier(entry["binding"], f"role {role} binding source")
            access = entry["access"]
            if RESOURCE_BINDINGS.get(resource) != binding or access not in {"read", "write"}:
                raise RuntimeConfigError(f"role {role} filesystem entry is unsupported")
            grants.append(RuntimeFilesystemGrant(resource, binding, access))
        grants_tuple = tuple(sorted(grants))
        if len({grant.resource for grant in grants_tuple}) != len(grants_tuple):
            raise RuntimeConfigError(f"role {role} repeats a filesystem resource")
        _validate_role_shape(role, grants_tuple)
        roles.append(
            RuntimeRoleTemplate(
                role=role,
                adapter_kind="codex",
                executable=str(executable),
                runtime_root=str(runtime_root),
                model=_require_text(raw["model"], f"role {role} model", maximum=128),
                reasoning_effort=_require_identifier(
                    raw["reasoning_effort"], f"role {role} reasoning effort"
                ),
                selected_binding_id=_require_identifier(
                    raw["selected_binding_id"], f"role {role} selected binding"
                ),
                proof_launch_spec_digest=_require_digest(
                    raw["proof_launch_spec_digest"], f"role {role} proof launch digest"
                ),
                filesystem=grants_tuple,
            )
        )
    return RuntimeProjectConfig(
        candidate_digest=_require_digest(document["candidate_digest"], "candidate digest"),
        discovery_digest=_require_digest(document["discovery_digest"], "discovery digest"),
        project_root=str(project_root),
        repository_root=str(repository_root),
        git_common_dir=str(git_common_dir),
        live_language=_require_text(
            document["live_orchestration_language"], "live orchestration language", maximum=128
        ),
        artifact_language=_require_text(
            document["durable_artifact_language"], "durable artifact language", maximum=128
        ),
        roles=tuple(roles),
    )


def _validate_setup_plan(
    payload: bytes,
    *,
    candidate_digest: str,
    discovery_digest: str,
    config: RuntimeProjectConfig,
) -> None:
    document = _canonical_json(payload, "Setup Plan")
    fields = {
        "schema_version",
        "discovery",
        "discovery_digest",
        "human_decisions",
        "human_decisions_digest",
        "compiled_policy",
        "model_bindings",
        "roles",
        "provenance",
        "candidate_digest",
    }
    if set(document) != fields or document["schema_version"] != CANDIDATE_SCHEMA:
        raise RuntimeConfigError("Setup Plan has an unsupported schema")
    projection = {key: document[key] for key in fields - {"candidate_digest"}}
    if (
        document["candidate_digest"] != candidate_digest
        or document["discovery_digest"] != discovery_digest
        or _digest("herdr-setup-candidate", projection) != candidate_digest
    ):
        raise RuntimeConfigError("Setup Plan identity does not match activation")
    roles = document["roles"]
    if not isinstance(roles, list):
        raise RuntimeConfigError("Setup Plan roles must be an array")
    expected_role_fields = {
        "role",
        "requirement",
        "selector_receipt",
        "native_launch_spec",
    }
    role_names: list[str] = []
    launch_by_role: dict[str, dict[str, object]] = {}
    for role_plan in roles:
        if not isinstance(role_plan, dict) or set(role_plan) != expected_role_fields:
            raise RuntimeConfigError("Setup Plan role has the wrong fields")
        role = role_plan["role"]
        launch = role_plan["native_launch_spec"]
        if not isinstance(role, str) or not isinstance(launch, dict):
            raise RuntimeConfigError("Setup Plan role launch is invalid")
        role_names.append(role)
        launch_by_role[role] = launch
    configured_roles = tuple(role.role for role in config.roles)
    if tuple(role_names) != configured_roles or len(launch_by_role) != len(role_names):
        raise RuntimeConfigError("Setup Plan role set does not match runtime config")
    for template in config.roles:
        launch = launch_by_role[template.role]
        required_launch_fields = {
            "adapter_kind",
            "executable",
            "cwd",
            "arguments",
            "permission_profile",
            "config_overrides",
            "filesystem_rules",
            "model",
            "reasoning_effort",
            "native_agents_enabled",
            "network_enabled",
            "selected_binding_id",
            "effective_envelope",
        }
        if set(launch) != required_launch_fields:
            raise RuntimeConfigError(
                f"Setup Plan launch has the wrong fields: {template.role}"
            )
        if (
            launch["adapter_kind"] != template.adapter_kind
            or launch["executable"] != template.executable
            or launch["model"] != template.model
            or launch["reasoning_effort"] != template.reasoning_effort
            or launch["selected_binding_id"] != template.selected_binding_id
            or launch["native_agents_enabled"] is not False
            or launch["network_enabled"] is not False
            or _digest("herdr-native-launch", launch)
            != template.proof_launch_spec_digest
        ):
            raise RuntimeConfigError(
                f"Setup Plan launch does not match runtime template: {template.role}"
            )
        rules = launch["filesystem_rules"]
        if not isinstance(rules, list):
            raise RuntimeConfigError("Setup Plan filesystem rules must be an array")
        rule_access: dict[str, str] = {}
        runtime_path: str | None = None
        minimal_seen = False
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {"resource", "path", "access"}:
                raise RuntimeConfigError("Setup Plan filesystem rule has the wrong fields")
            resource = rule["resource"]
            access = rule["access"]
            path = rule["path"]
            if resource is None:
                if minimal_seen or path != ":minimal" or access != "read":
                    raise RuntimeConfigError("Setup Plan minimal filesystem rule is invalid")
                minimal_seen = True
                continue
            if (
                not isinstance(resource, str)
                or not isinstance(path, str)
                or access not in {"read", "write"}
                or resource in rule_access
            ):
                raise RuntimeConfigError("Setup Plan filesystem rule is invalid")
            rule_access[resource] = access
            if resource == "runtime:codex":
                runtime_path = path
        template_access = {
            grant.resource: grant.access for grant in template.filesystem
        }
        if (
            not minimal_seen
            or rule_access != template_access
            or runtime_path != template.runtime_root
        ):
            raise RuntimeConfigError(
                f"Setup Plan filesystem authority does not match runtime template: {template.role}"
            )


def _validate_runtime_proof(
    payload: bytes,
    *,
    proof_digest: str,
    candidate_digest: str,
    discovery_digest: str,
    config: RuntimeProjectConfig,
) -> None:
    document = _canonical_json(payload, "Runtime Proof")
    fields = {
        "status",
        "candidate_digest",
        "discovery_digest",
        "current_discovery_digest",
        "roles",
        "receipt_digest",
    }
    if set(document) != fields:
        raise RuntimeConfigError("Runtime Proof has the wrong fields")
    if (
        document["status"] != PROVEN_STATUS
        or document["candidate_digest"] != candidate_digest
        or document["discovery_digest"] != discovery_digest
        or document["current_discovery_digest"] != discovery_digest
        or document["receipt_digest"] != proof_digest
    ):
        raise RuntimeConfigError("Runtime Proof does not prove the accepted candidate")
    roles = document["roles"]
    if not isinstance(roles, list):
        raise RuntimeConfigError("Runtime Proof roles must be an array")
    role_fields = {
        "role",
        "candidate_digest",
        "launch_spec_digest",
        "status",
        "checks",
        "receipt_digest",
    }
    check_fields = {
        "identifier",
        "operation",
        "resource",
        "target",
        "expected",
        "observed",
        "assurance",
        "error_code",
        "detail_digest",
    }
    proof_roles: list[str] = []
    template_by_role = config.role_map
    for role_receipt in roles:
        if not isinstance(role_receipt, dict) or set(role_receipt) != role_fields:
            raise RuntimeConfigError("Runtime Proof role receipt has the wrong fields")
        role = role_receipt["role"]
        template = template_by_role.get(role) if isinstance(role, str) else None
        checks = role_receipt["checks"]
        if (
            template is None
            or role_receipt["candidate_digest"] != candidate_digest
            or role_receipt["launch_spec_digest"] != template.proof_launch_spec_digest
            or role_receipt["status"] != PROVEN_STATUS
            or not isinstance(checks, list)
            or not checks
        ):
            raise RuntimeConfigError("Runtime Proof role does not prove its launch")
        for check in checks:
            if not isinstance(check, dict) or set(check) != check_fields:
                raise RuntimeConfigError("Runtime Proof check has the wrong fields")
            if (
                check["expected"] not in {"ALLOW", "DENY"}
                or check["observed"] != check["expected"]
                or check["assurance"]
                not in {"STATIC_PROVEN", "NATIVE_INTROSPECTED", "RUNTIME_PROBED"}
            ):
                raise RuntimeConfigError("Runtime Proof check is not authoritative")
            if (
                check["assurance"] == "RUNTIME_PROBED"
                and check["observed"] == "DENY"
                and check["error_code"] not in {1, 2, 13, 30}
            ):
                raise RuntimeConfigError("Runtime Proof denial lacks a sandbox error")
        role_projection = {
            key: role_receipt[key] for key in role_fields - {"receipt_digest"}
        }
        if (
            role_receipt["receipt_digest"]
            != _digest("herdr-role-proof", role_projection)
        ):
            raise RuntimeConfigError("Runtime Proof role digest does not match its content")
        proof_roles.append(role)
    configured_roles = tuple(role.role for role in config.roles)
    if tuple(proof_roles) != configured_roles or len(set(proof_roles)) != len(proof_roles):
        raise RuntimeConfigError("Runtime Proof role set does not match runtime config")
    projection = {key: document[key] for key in fields - {"receipt_digest"}}
    if _digest("herdr-runtime-proof", projection) != proof_digest:
        raise RuntimeConfigError("Runtime Proof digest does not match its content")


def load_accepted_project(project_root: str) -> AcceptedProject:
    """Resolve and cryptographically verify the one active immutable generation."""

    root = _canonical_directory(project_root, "project root")
    current = root / CURRENT_PATH
    activation_payload = _stable_regular_bytes(current, "Activation Manifest")
    activation = _canonical_json(activation_payload, "Activation Manifest")
    activation_fields = {
        "schema",
        "status",
        "candidate_digest",
        "discovery_digest",
        "runtime_proof_digest",
        "publication_digest",
        "acceptance_receipt_digest",
        "generation",
        "artifacts",
    }
    if set(activation) != activation_fields:
        raise RuntimeConfigError("Activation Manifest has the wrong fields")
    if activation["schema"] != ACTIVATION_SCHEMA or activation["status"] != ACCEPTED_STATUS:
        raise RuntimeConfigError("Activation Manifest is not an accepted setup")
    candidate_digest = _require_digest(activation["candidate_digest"], "candidate digest")
    discovery_digest = _require_digest(activation["discovery_digest"], "discovery digest")
    proof_digest = _require_digest(activation["runtime_proof_digest"], "runtime proof digest")
    publication_digest = _require_digest(activation["publication_digest"], "publication digest")
    acceptance_digest = _require_digest(
        activation["acceptance_receipt_digest"], "acceptance receipt digest"
    )
    generation_value = activation["generation"]
    expected_generation = f"generations/{publication_digest}"
    if generation_value != expected_generation:
        raise RuntimeConfigError("Activation Manifest generation is not publication-bound")
    generation = root / ".orchestration/setup" / expected_generation
    if generation.is_symlink():
        raise RuntimeConfigError("accepted generation must not be a symlink")
    try:
        metadata = os.lstat(generation)
    except OSError as exc:
        raise RuntimeConfigError("accepted generation is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeConfigError("accepted generation is not a real directory")
    if tuple(sorted(path.name for path in generation.iterdir())) != GENERATION_FILE_PATHS:
        raise RuntimeConfigError("accepted generation has an unsupported artifact set")

    activation_artifacts = _parse_artifacts(activation["artifacts"], sizes=True)
    artifacts: list[AcceptedArtifact] = []
    artifact_payloads: dict[str, bytes] = {}
    for entry in activation_artifacts:
        relative = str(entry["path"])
        path = generation / relative
        payload = _stable_regular_bytes(path, f"accepted artifact {relative}")
        if len(payload) != entry["size"] or _sha256(payload) != entry["sha256"]:
            raise RuntimeConfigError(f"accepted artifact does not match activation: {relative}")
        artifacts.append(
            AcceptedArtifact(relative, str(path), len(payload), str(entry["sha256"]))
        )
        artifact_payloads[relative] = payload

    publication_payload = _stable_regular_bytes(
        generation / "publication-manifest.json", "Publication Manifest"
    )
    publication = _canonical_json(publication_payload, "Publication Manifest")
    publication_fields = {
        "schema",
        "candidate_digest",
        "discovery_digest",
        "runtime_proof_digest",
        "artifacts",
        "publication_digest",
    }
    if set(publication) != publication_fields:
        raise RuntimeConfigError("Publication Manifest has the wrong fields")
    publication_projection = {key: publication[key] for key in publication_fields - {"publication_digest"}}
    if (
        publication["schema"] != PUBLICATION_SCHEMA
        or publication["candidate_digest"] != candidate_digest
        or publication["discovery_digest"] != discovery_digest
        or publication["runtime_proof_digest"] != proof_digest
        or publication["artifacts"] != list(activation_artifacts)
        or publication["publication_digest"] != publication_digest
        or _digest("herdr-setup-publication", publication_projection) != publication_digest
    ):
        raise RuntimeConfigError("Publication Manifest does not match activation")

    receipt_payload = _stable_regular_bytes(
        generation / "acceptance-receipt.json", "Acceptance Receipt"
    )
    receipt = _canonical_json(receipt_payload, "Acceptance Receipt")
    receipt_fields = {
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
    if set(receipt) != receipt_fields:
        raise RuntimeConfigError("Acceptance Receipt has the wrong fields")
    receipt_artifacts = _parse_artifacts(receipt["artifacts"], sizes=False)
    expected_receipt_artifacts = [
        {"path": entry["path"], "sha256": entry["sha256"]}
        for entry in activation_artifacts
    ]
    receipt_projection = {key: receipt[key] for key in receipt_fields - {"receipt_digest"}}
    if (
        receipt["schema"] != ACCEPTANCE_SCHEMA
        or receipt["status"] != ACCEPTED_STATUS
        or receipt["candidate_digest"] != candidate_digest
        or receipt["discovery_digest"] != discovery_digest
        or receipt["runtime_proof_digest"] != proof_digest
        or receipt["publication_digest"] != publication_digest
        or receipt["generation"] != expected_generation
        or list(receipt_artifacts) != expected_receipt_artifacts
        or receipt["receipt_digest"] != acceptance_digest
        or _digest("herdr-setup-acceptance", receipt_projection) != acceptance_digest
    ):
        raise RuntimeConfigError("Acceptance Receipt does not match activation")

    config = parse_runtime_config(artifact_payloads["herdr-orchestrator.toml"])
    if (
        config.project_root != str(root)
        or config.candidate_digest != candidate_digest
        or config.discovery_digest != discovery_digest
    ):
        raise RuntimeConfigError("accepted project config does not match activation")
    _validate_setup_plan(
        artifact_payloads["setup-plan.json"],
        candidate_digest=candidate_digest,
        discovery_digest=discovery_digest,
        config=config,
    )
    _validate_runtime_proof(
        artifact_payloads["runtime-proof.json"],
        proof_digest=proof_digest,
        candidate_digest=candidate_digest,
        discovery_digest=discovery_digest,
        config=config,
    )
    return AcceptedProject(
        project_root=str(root),
        activation_path=str(current),
        activation_sha256=_sha256(activation_payload),
        generation_root=str(generation),
        publication_digest=publication_digest,
        acceptance_receipt_digest=acceptance_digest,
        config=config,
        artifacts=tuple(artifacts),
    )


def _contains(root: str, candidate: str) -> bool:
    try:
        return os.path.commonpath((root, candidate)) == root
    except ValueError:
        return False


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _permission_override(filesystem: tuple[tuple[str, str, str], ...]) -> str:
    rules = ", ".join(
        f"{_toml_string(path)} = {_toml_string(access)}"
        for _resource, path, access in filesystem
    )
    return (
        'permissions={ "herdr_runtime" = { filesystem = { '
        + rules
        + " }, network = { enabled = false } } }"
    )


def bind_role_launch(
    config: RuntimeProjectConfig,
    role: str,
    *,
    cwd: str,
    bindings: Mapping[str, str],
) -> BoundRoleLaunch:
    """Compile one role template with exact Assignment paths; grant no unused root."""

    template = config.role_map.get(role)
    if template is None:
        raise RuntimeConfigError(f"role is not enabled by the accepted setup: {role}")
    canonical_cwd = _canonical_directory(cwd, "role cwd")
    supplied = dict(bindings)
    if set(supplied) - {"workspace", "git_common", "orchestration", "evidence", "notebook"}:
        raise RuntimeConfigError("role binding contains an unsupported source")
    fixed = {"runtime": template.runtime_root}
    required_sources = {
        grant.binding for grant in template.filesystem if grant.binding != "runtime"
    }
    if set(supplied) != required_sources:
        missing = sorted(required_sources - set(supplied))
        extra = sorted(set(supplied) - required_sources)
        detail = []
        if missing:
            detail.append("missing " + ",".join(missing))
        if extra:
            detail.append("extra " + ",".join(extra))
        raise RuntimeConfigError("role binding source mismatch: " + "; ".join(detail))
    paths = {
        source: str(_canonical_directory(value, f"role {source} binding"))
        for source, value in supplied.items()
    }
    paths.update(fixed)
    filesystem = tuple(
        sorted(
            (
                grant.resource,
                paths[grant.binding],
                grant.access,
            )
            for grant in template.filesystem
        )
    )
    accessible = tuple(
        path for _resource, path, access in filesystem if access in {"read", "write"}
    )
    if not any(_contains(path, str(canonical_cwd)) for path in accessible):
        raise RuntimeConfigError("role cwd is outside its effective filesystem authority")
    path_access: dict[str, str] = {":minimal": "read"}
    for _resource, path, access in filesystem:
        if path_access.get(path) != "write":
            path_access[path] = access
    normalized_filesystem = tuple(
        (resource, path, access) for resource, path, access in filesystem
    )
    overrides = (
        'default_permissions="herdr_runtime"',
        _permission_override(
            tuple(("", path, access) for path, access in sorted(path_access.items()))
        ),
        "agents.enabled=false",
        f"model_reasoning_effort={_toml_string(template.reasoning_effort)}",
    )
    arguments = (
        "--strict-config",
        "--model",
        template.model,
        "--ask-for-approval",
        "never",
        "--config",
        overrides[0],
        "--config",
        overrides[1],
        "--config",
        overrides[2],
        "--config",
        overrides[3],
        "--cd",
        str(canonical_cwd),
    )
    projection = {
        "candidate_digest": config.candidate_digest,
        "role": role,
        "kind": template.adapter_kind,
        "executable": template.executable,
        "cwd": str(canonical_cwd),
        "model": template.model,
        "reasoning_effort": template.reasoning_effort,
        "selected_binding_id": template.selected_binding_id,
        "arguments": list(arguments),
        "filesystem": [
            {"resource": resource, "path": path, "access": access}
            for resource, path, access in normalized_filesystem
        ],
    }
    return BoundRoleLaunch(
        role=role,
        kind=template.adapter_kind,
        executable=template.executable,
        cwd=str(canonical_cwd),
        model=template.model,
        reasoning_effort=template.reasoning_effort,
        selected_binding_id=template.selected_binding_id,
        arguments=arguments,
        filesystem=normalized_filesystem,
        launch_digest=_digest("herdr-runtime-bound-launch", projection),
    )
