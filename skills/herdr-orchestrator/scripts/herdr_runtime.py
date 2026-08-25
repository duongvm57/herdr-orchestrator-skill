"""Load one accepted setup and bind profiles to exact Assignment envelopes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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
    "control:run": "control",
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
class RuntimeAuthorityTemplate:
    name: str
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
    live_language: str
    artifact_language: str
    repositories: tuple["RuntimeRepository", ...]
    model_inventory: tuple["RuntimeModel", ...]
    routes: tuple["RuntimeRoute", ...]
    authority_templates: tuple[RuntimeAuthorityTemplate, ...]

    @property
    def authority_map(self) -> dict[str, RuntimeAuthorityTemplate]:
        return {template.name: template for template in self.authority_templates}

    @property
    def route_map(self) -> dict[str, "RuntimeRoute"]:
        return {route.profile: route for route in self.routes}


@dataclass(frozen=True, order=True)
class RuntimeRepository:
    identifier: str
    relative_path: str
    path: str
    git_common_dir: str


@dataclass(frozen=True, order=True)
class RuntimeModel:
    harness: str
    executable: str
    runtime_root: str
    model: str
    reasoning_effort: str


@dataclass(frozen=True, order=True)
class RuntimeRoute:
    profile: str
    harness: str
    model: str
    reasoning_effort: str


@dataclass(frozen=True, order=True)
class LaunchRepositoryBinding:
    workspace: str
    git_common_dir: str


@dataclass(frozen=True, order=True)
class ModelSelection:
    harness: str
    model: str
    reasoning_effort: str


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
class BoundLaunch:
    profile: str
    disposition: str
    authority_template: str
    route_source: str
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


def _validate_template_shape(name: str, grants: tuple[RuntimeFilesystemGrant, ...]) -> None:
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
        "peer_writable": {
            "runtime:codex",
            "project:assigned",
            "git-common:assigned",
            "orchestration:control",
            "evidence:assignment",
        },
        "peer_readonly": {
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
        "lead": {
            "project:assigned": "write",
            "git-common:assigned": "write",
            "control:run": "write",
        },
        "peer_writable": {
            "project:assigned": "write",
            "git-common:assigned": "write",
            "evidence:assignment": "write",
        },
        "peer_readonly": {
            "git-common:assigned": "read",
            "evidence:assignment": "write",
        },
        "supervisor": {"notebook:session": "write"},
    }
    if name not in allowed:
        raise RuntimeConfigError(f"unknown authority template: {name}")
    expected = {**required, **required_by_role[name]}
    if any(access.get(resource) != expected_access for resource, expected_access in expected.items()):
        raise RuntimeConfigError(f"template {name} is missing required closed-world authority")
    if set(access) - allowed[name]:
        raise RuntimeConfigError(f"template {name} has unsupported authority")
    if name in {"peer_readonly", "supervisor"} and access["project:assigned"] != "read":
        raise RuntimeConfigError(f"template {name} must keep project mutation denied")


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
        "live_orchestration_language",
        "durable_artifact_language",
        "native_agent_policy",
        "repositories",
        "model_inventory",
        "routes",
        "authority_templates",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise RuntimeConfigError("accepted project config has the wrong top-level fields")
    if document["schema"] != PUBLICATION_SCHEMA:
        raise RuntimeConfigError("accepted project config has an unsupported schema")
    if document["native_agent_policy"] != "disabled":
        raise RuntimeConfigError("accepted project config must disable native agents")
    project_root = _canonical_directory(document["project_root"], "configured project root")
    raw_repositories = document["repositories"]
    if not isinstance(raw_repositories, list) or not raw_repositories:
        raise RuntimeConfigError("accepted project config requires repository inventory")
    repositories: list[RuntimeRepository] = []
    for raw in raw_repositories:
        if not isinstance(raw, dict) or set(raw) != {"identifier", "relative_path", "path", "git_common_dir"}:
            raise RuntimeConfigError("repository inventory entry has the wrong fields")
        path = _canonical_directory(raw["path"], "inventory repository path")
        common = _canonical_directory(raw["git_common_dir"], "inventory Git common directory")
        repositories.append(RuntimeRepository(
            _require_text(raw["identifier"], "repository identifier", maximum=512),
            _require_text(raw["relative_path"], "repository relative path", maximum=4096),
            str(path),
            str(common),
        ))
    raw_models = document["model_inventory"]
    if not isinstance(raw_models, list) or not raw_models:
        raise RuntimeConfigError("accepted project config requires model inventory")
    models: list[RuntimeModel] = []
    for raw in raw_models:
        if not isinstance(raw, dict) or set(raw) != {"harness", "executable", "runtime_root", "model", "reasoning_effort"}:
            raise RuntimeConfigError("model inventory entry has the wrong fields")
        models.append(RuntimeModel(
            _require_identifier(raw["harness"], "model harness"),
            str(_canonical_file(raw["executable"], "model executable")),
            str(_canonical_directory(raw["runtime_root"], "model runtime root")),
            _require_text(raw["model"], "model identifier", maximum=128),
            _require_identifier(raw["reasoning_effort"], "model reasoning effort"),
        ))
    raw_routes = document["routes"]
    if not isinstance(raw_routes, dict) or set(raw_routes) != {"lead", "peer", "supervisor", "fallback"}:
        raise RuntimeConfigError("accepted project config has the wrong routes")
    routes: list[RuntimeRoute] = []
    for profile in sorted(raw_routes):
        raw = raw_routes[profile]
        if not isinstance(raw, dict) or set(raw) != {"harness", "model", "reasoning_effort"}:
            raise RuntimeConfigError(f"route {profile} has the wrong fields")
        route = RuntimeRoute(
            profile,
            _require_identifier(raw["harness"], f"route {profile} harness"),
            _require_text(raw["model"], f"route {profile} model", maximum=128),
            _require_identifier(raw["reasoning_effort"], f"route {profile} effort"),
        )
        if not any((item.harness, item.model, item.reasoning_effort) == (route.harness, route.model, route.reasoning_effort) for item in models):
            raise RuntimeConfigError(f"route {profile} is absent from accepted model inventory")
        routes.append(route)
    raw_roles = document["authority_templates"]
    if not isinstance(raw_roles, dict) or set(raw_roles) != {"lead", "peer_writable", "peer_readonly", "supervisor"}:
        raise RuntimeConfigError("accepted project config has an unsupported authority template set")
    templates: list[RuntimeAuthorityTemplate] = []
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
        _validate_template_shape(role, grants_tuple)
        templates.append(
            RuntimeAuthorityTemplate(
                name=role,
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
        live_language=_require_text(
            document["live_orchestration_language"], "live orchestration language", maximum=128
        ),
        artifact_language=_require_text(
            document["durable_artifact_language"], "durable artifact language", maximum=128
        ),
        repositories=tuple(sorted(repositories)),
        model_inventory=tuple(sorted(models)),
        routes=tuple(routes),
        authority_templates=tuple(templates),
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
        "authority_templates",
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
    roles = document["authority_templates"]
    if not isinstance(roles, list):
        raise RuntimeConfigError("Setup Plan roles must be an array")
    expected_role_fields = {
        "template",
        "requirement",
        "selector_receipt",
        "native_launch_spec",
    }
    role_names: list[str] = []
    launch_by_role: dict[str, dict[str, object]] = {}
    for role_plan in roles:
        if not isinstance(role_plan, dict) or set(role_plan) != expected_role_fields:
            raise RuntimeConfigError("Setup Plan role has the wrong fields")
        role = role_plan["template"]
        launch = role_plan["native_launch_spec"]
        if not isinstance(role, str) or not isinstance(launch, dict):
            raise RuntimeConfigError("Setup Plan role launch is invalid")
        role_names.append(role)
        launch_by_role[role] = launch
    configured_roles = tuple(template.name for template in config.authority_templates)
    if tuple(role_names) != configured_roles or len(launch_by_role) != len(role_names):
        raise RuntimeConfigError("Setup Plan role set does not match runtime config")
    for template in config.authority_templates:
        launch = launch_by_role[template.name]
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
                f"Setup Plan launch has the wrong fields: {template.name}"
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
                f"Setup Plan launch does not match runtime template: {template.name}"
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
                f"Setup Plan filesystem authority does not match runtime template: {template.name}"
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
        "authority_templates",
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
    roles = document["authority_templates"]
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
    template_by_role = config.authority_map
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
    configured_roles = tuple(template.name for template in config.authority_templates)
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
    protocol_snapshot = artifact_payloads["workspace-protocol.md"]
    if _stable_regular_bytes(root / "WORKSPACE_PROTOCOL.md", "Workspace Protocol") != protocol_snapshot:
        raise RuntimeConfigError("tracked Workspace Protocol does not match accepted setup")
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


def _verified_repository_binding(
    config: RuntimeProjectConfig,
    binding: LaunchRepositoryBinding,
) -> LaunchRepositoryBinding:
    workspace = _canonical_directory(binding.workspace, "launch repository workspace")
    common = _canonical_directory(binding.git_common_dir, "launch Git common directory")
    try:
        completed = subprocess.run(
            ("git", "-C", str(workspace), "rev-parse", "--git-common-dir"),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeConfigError("launch repository is not a usable Git worktree") from exc
    observed = Path(completed.stdout.strip())
    if not observed.is_absolute():
        observed = workspace / observed
    try:
        observed = observed.resolve(strict=True)
    except OSError as exc:
        raise RuntimeConfigError("launch Git common directory is unavailable") from exc
    accepted_commons = {repository.git_common_dir for repository in config.repositories}
    if str(observed) != str(common) or str(common) not in accepted_commons:
        raise RuntimeConfigError("launch repository is outside the accepted Git inventory")
    return LaunchRepositoryBinding(str(workspace), str(common))


def _select_model(
    config: RuntimeProjectConfig,
    profile: str,
    disposition: str,
    explicit: ModelSelection | None,
    runtime_route: ModelSelection | None,
) -> tuple[RuntimeModel, str]:
    if explicit is not None:
        desired, source = explicit, "human_override"
    elif runtime_route is not None:
        desired, source = runtime_route, "lead_runtime_route"
    else:
        route_name = (
            "fallback"
            if profile == "peer"
            and disposition not in {"engineer", "reviewer", "architect", "scout"}
            else profile
        )
        route = config.route_map[route_name]
        desired = ModelSelection(route.harness, route.model, route.reasoning_effort)
        source = "global_fallback" if route_name == "fallback" else "profile_default"
    match = next(
        (
            item
            for item in config.model_inventory
            if (item.harness, item.model, item.reasoning_effort)
            == (desired.harness, desired.model, desired.reasoning_effort)
        ),
        None,
    )
    if match is None:
        raise RuntimeConfigError("selected model route is absent from accepted inventory")
    return match, source


def bind_launch(
    config: RuntimeProjectConfig,
    *,
    profile: str,
    disposition: str,
    authority: str,
    cwd: str,
    repositories: Iterable[LaunchRepositoryBinding],
    evidence_root: str | None = None,
    notebook_root: str | None = None,
    control_root: str | None = None,
    model_override: ModelSelection | None = None,
    runtime_route: ModelSelection | None = None,
) -> BoundLaunch:
    """Compile one explicit Assignment envelope into an exact native launch."""

    if profile not in {"lead", "peer", "supervisor"}:
        raise RuntimeConfigError("launch profile must be lead, peer, or supervisor")
    _require_identifier(disposition, "launch disposition")
    expected_authority = {
        "lead": {"project_writable": "lead"},
        "peer": {
            "project_writable": "peer_writable",
            "project_readonly": "peer_readonly",
        },
        "supervisor": {"project_readonly": "supervisor"},
    }[profile]
    template_name = expected_authority.get(authority)
    if template_name is None:
        raise RuntimeConfigError("authority is incompatible with the selected profile")
    template = config.authority_map.get(template_name)
    if template is None:
        raise RuntimeConfigError("accepted setup lacks the selected authority template")
    bound_repositories = tuple(
        _verified_repository_binding(config, item) for item in repositories
    )
    if not bound_repositories:
        raise RuntimeConfigError("launch requires at least one exact repository binding")
    if len(set(bound_repositories)) != len(bound_repositories):
        raise RuntimeConfigError("launch repeats a repository binding")
    selected_model, route_source = _select_model(
        config, profile, disposition, model_override, runtime_route
    )
    if selected_model.harness != template.adapter_kind:
        raise RuntimeConfigError("selected model route has no compatible authority adapter")
    roots = {
        "runtime": selected_model.runtime_root,
        "orchestration": str(_canonical_directory(
            str(Path(config.project_root) / ".orchestration"),
            "orchestration control root",
        )),
    }
    optional = {
        "evidence": evidence_root,
        "notebook": notebook_root,
        "control": control_root,
    }
    for source, value in optional.items():
        if value is not None:
            roots[source] = str(_canonical_directory(value, f"launch {source} root"))
    required_single = {
        grant.binding
        for grant in template.filesystem
        if grant.binding not in {"runtime", "workspace", "git_common", "orchestration"}
    }
    if required_single != (set(roots) & required_single):
        raise RuntimeConfigError("launch is missing its evidence, notebook, or control root")
    filesystem_values: list[tuple[str, str, str]] = []
    for grant in template.filesystem:
        if grant.binding == "workspace":
            filesystem_values.extend(
                (f"{grant.resource}.{index}", item.workspace, grant.access)
                for index, item in enumerate(bound_repositories)
            )
        elif grant.binding == "git_common":
            filesystem_values.extend(
                (f"{grant.resource}.{index}", item.git_common_dir, grant.access)
                for index, item in enumerate(bound_repositories)
            )
        else:
            filesystem_values.append((grant.resource, roots[grant.binding], grant.access))
    filesystem = tuple(sorted(filesystem_values))
    canonical_cwd = _canonical_directory(cwd, "launch cwd")
    accessible = tuple(
        path for _resource, path, access in filesystem if access in {"read", "write"}
    )
    if not any(_contains(path, str(canonical_cwd)) for path in accessible):
        raise RuntimeConfigError("launch cwd is outside its effective filesystem authority")
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
        f"model_reasoning_effort={_toml_string(selected_model.reasoning_effort)}",
    )
    arguments = (
        "--strict-config",
        "--model",
        selected_model.model,
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
        "profile": profile,
        "disposition": disposition,
        "authority_template": template_name,
        "route_source": route_source,
        "kind": template.adapter_kind,
        "executable": selected_model.executable,
        "cwd": str(canonical_cwd),
        "model": selected_model.model,
        "reasoning_effort": selected_model.reasoning_effort,
        "selected_binding_id": template.selected_binding_id,
        "arguments": list(arguments),
        "filesystem": [
            {"resource": resource, "path": path, "access": access}
            for resource, path, access in normalized_filesystem
        ],
    }
    return BoundLaunch(
        profile=profile,
        disposition=disposition,
        authority_template=template_name,
        route_source=route_source,
        kind=template.adapter_kind,
        executable=selected_model.executable,
        cwd=str(canonical_cwd),
        model=selected_model.model,
        reasoning_effort=selected_model.reasoning_effort,
        selected_binding_id=template.selected_binding_id,
        arguments=arguments,
        filesystem=normalized_filesystem,
        launch_digest=_digest("herdr-runtime-bound-launch", projection),
    )
