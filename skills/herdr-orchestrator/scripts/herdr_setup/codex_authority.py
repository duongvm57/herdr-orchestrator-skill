"""Compile selected setup authority into an exact Codex launch specification."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from .authority import (
    AuthorityEnvelope,
    Binding,
    Capability,
    SelectionResult,
    SelectionStatus,
)


MINIMUM_PERMISSION_PROFILE_VERSION = (0, 138, 0)
PROFILE_NAME = "herdr_runtime"
RUNTIME_RESOURCE = "runtime:codex"
RESOURCE_ID_RE = re.compile(
    r"[a-z][a-z0-9._-]{0,63}:[a-z][a-z0-9._-]{0,63}\Z"
)
VERSION_RE = re.compile(r"(?:codex-cli\s+)?(\d+)\.(\d+)\.(\d+)\Z")
SUPPORTED_REASONING_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


def _validate_text(value: str, label: str, *, maximum: int = 512) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty canonical string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds the bounded length")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} contains a control character")


def _validate_path(value: str, label: str) -> None:
    _validate_text(value, label, maximum=4096)
    if not os.path.isabs(value):
        raise ValueError(f"{label} must be absolute")
    if os.path.normpath(value) != value:
        raise ValueError(f"{label} must be normalized")


def _ordered_capabilities(values: Iterable[Capability]) -> tuple[Capability, ...]:
    return tuple(sorted(values))


@dataclass(frozen=True, order=True)
class CodexVersion:
    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (self.major, self.minor, self.patch)
        ):
            raise ValueError("Codex version parts must be nonnegative integers")

    @classmethod
    def parse(cls, value: str) -> CodexVersion:
        _validate_text(value, "Codex version", maximum=64)
        match = VERSION_RE.fullmatch(value)
        if match is None:
            raise ValueError("Codex version is not a supported semantic version")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class AssuranceLevel(str, Enum):
    STATIC_PROVEN = "STATIC_PROVEN"
    NATIVE_INTROSPECTED = "NATIVE_INTROSPECTED"
    RUNTIME_PROBED = "RUNTIME_PROBED"
    MODEL_OBSERVED = "MODEL_OBSERVED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class CodexModelObservation:
    identifier: str
    reasoning_efforts: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_text(self.identifier, "Codex model identifier", maximum=128)
        efforts = tuple(self.reasoning_efforts)
        if any(
            not isinstance(effort, str)
            or SUPPORTED_REASONING_RE.fullmatch(effort) is None
            for effort in efforts
        ):
            raise ValueError("Codex reasoning efforts must be canonical identifiers")
        if len(efforts) != len(set(efforts)):
            raise ValueError("Codex model repeats a reasoning effort")
        object.__setattr__(self, "reasoning_efforts", efforts)


@dataclass(frozen=True)
class CodexObservation:
    """Machine observation that compilation relies on; no quality rankings."""

    executable: str
    version: CodexVersion
    runtime_root: str
    bound_cwd: str
    models: tuple[CodexModelObservation, ...]
    permission_profiles: bool
    permission_profile_assurance: AssuranceLevel
    native_spawn_control: bool
    native_spawn_assurance: AssuranceLevel
    network_control: bool
    network_assurance: AssuranceLevel
    legacy_sandbox_settings: bool

    def __post_init__(self) -> None:
        _validate_path(self.executable, "Codex executable")
        if not isinstance(self.version, CodexVersion):
            raise TypeError("Codex observation version must be a CodexVersion")
        _validate_path(self.runtime_root, "Codex runtime root")
        _validate_path(self.bound_cwd, "Codex observation cwd")
        models = tuple(self.models)
        if any(not isinstance(model, CodexModelObservation) for model in models):
            raise TypeError("Codex models must contain CodexModelObservation values")
        identifiers = [model.identifier for model in models]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Codex observation repeats a model identifier")
        object.__setattr__(self, "models", models)
        for label, value in (
            ("permission_profiles", self.permission_profiles),
            ("native_spawn_control", self.native_spawn_control),
            ("network_control", self.network_control),
            ("legacy_sandbox_settings", self.legacy_sandbox_settings),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{label} must be boolean")
        for label, value in (
            ("permission_profile_assurance", self.permission_profile_assurance),
            ("native_spawn_assurance", self.native_spawn_assurance),
            ("network_assurance", self.network_assurance),
        ):
            if not isinstance(value, AssuranceLevel):
                raise TypeError(f"{label} must be an AssuranceLevel")

    @property
    def model_map(self) -> dict[str, CodexModelObservation]:
        return {model.identifier: model for model in self.models}


@dataclass(frozen=True, order=True)
class RuntimePathBinding:
    resource: str
    path: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.resource, str)
            or RESOURCE_ID_RE.fullmatch(self.resource) is None
        ):
            raise ValueError("runtime resource must be a canonical scoped identifier")
        if self.resource == RUNTIME_RESOURCE:
            raise ValueError("runtime:codex is supplied by CodexObservation")
        _validate_path(self.path, "runtime resource path")


@dataclass(frozen=True)
class RuntimeBindingContext:
    """Exact launch-time resource paths and Human-selected model controls."""

    cwd: str
    resources: tuple[RuntimePathBinding, ...]
    model: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        _validate_path(self.cwd, "runtime cwd")
        resources = tuple(self.resources)
        if any(not isinstance(resource, RuntimePathBinding) for resource in resources):
            raise TypeError("runtime resources must contain RuntimePathBinding values")
        identifiers = [resource.resource for resource in resources]
        paths = [resource.path for resource in resources]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("runtime context repeats a resource identifier")
        if len(paths) != len(set(paths)):
            raise ValueError("runtime context binds multiple resources to one path")
        object.__setattr__(
            self,
            "resources",
            tuple(sorted(resources, key=lambda resource: resource.resource)),
        )
        _validate_text(self.model, "runtime model", maximum=128)
        if (
            not isinstance(self.reasoning_effort, str)
            or SUPPORTED_REASONING_RE.fullmatch(self.reasoning_effort) is None
        ):
            raise ValueError("runtime reasoning effort must be canonical")

    @property
    def resource_map(self) -> dict[str, str]:
        return {resource.resource: resource.path for resource in self.resources}


class CodexCompileStatus(str, Enum):
    COMPILED = "COMPILED"
    STATIC_INVALID = "STATIC_INVALID"
    CAPABILITY_INVALID = "CAPABILITY_INVALID"


class CodexCompileRejectionCode(str, Enum):
    SELECTION_NOT_COMPLETE = "SELECTION_NOT_COMPLETE"
    ADAPTER_KIND_MISMATCH = "ADAPTER_KIND_MISMATCH"
    VERSION_TOO_OLD = "VERSION_TOO_OLD"
    PERMISSION_PROFILES_UNAVAILABLE = "PERMISSION_PROFILES_UNAVAILABLE"
    PERMISSION_PROFILE_UNVERIFIED = "PERMISSION_PROFILE_UNVERIFIED"
    NATIVE_SPAWN_CONTROL_UNAVAILABLE = "NATIVE_SPAWN_CONTROL_UNAVAILABLE"
    NATIVE_SPAWN_CONTROL_UNVERIFIED = "NATIVE_SPAWN_CONTROL_UNVERIFIED"
    NETWORK_CONTROL_UNAVAILABLE = "NETWORK_CONTROL_UNAVAILABLE"
    NETWORK_CONTROL_UNVERIFIED = "NETWORK_CONTROL_UNVERIFIED"
    LEGACY_SANDBOX_CONFLICT = "LEGACY_SANDBOX_CONFLICT"
    OBSERVATION_CONTEXT_MISMATCH = "OBSERVATION_CONTEXT_MISMATCH"
    MODEL_NOT_OBSERVED = "MODEL_NOT_OBSERVED"
    REASONING_EFFORT_UNSUPPORTED = "REASONING_EFFORT_UNSUPPORTED"
    MISSING_RUNTIME_READ = "MISSING_RUNTIME_READ"
    UNBOUND_RESOURCE = "UNBOUND_RESOURCE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_CAPABILITY_SHAPE = "INVALID_CAPABILITY_SHAPE"
    EFFECTIVE_ENVELOPE_MISMATCH = "EFFECTIVE_ENVELOPE_MISMATCH"
    CWD_NOT_ACCESSIBLE = "CWD_NOT_ACCESSIBLE"
    NATIVE_SPAWN_UNSUPPORTED = "NATIVE_SPAWN_UNSUPPORTED"
    NETWORK_GRANT_UNSUPPORTED = "NETWORK_GRANT_UNSUPPORTED"


@dataclass(frozen=True)
class CodexCompileRejection:
    code: CodexCompileRejectionCode
    detail: str | None = None
    capabilities: tuple[Capability, ...] = ()


@dataclass(frozen=True)
class NativeFilesystemRule:
    resource: str | None
    path: str
    access: str

    def __post_init__(self) -> None:
        if self.path == ":minimal":
            if self.resource is not None:
                raise ValueError(":minimal cannot bind a logical resource")
        else:
            _validate_path(self.path, "Codex filesystem rule path")
            if (
                not isinstance(self.resource, str)
                or RESOURCE_ID_RE.fullmatch(self.resource) is None
            ):
                raise ValueError(
                    "Codex filesystem rule requires a canonical resource"
                )
        if self.access not in {"read", "write", "deny"}:
            raise ValueError("Codex filesystem rule access is invalid")


@dataclass(frozen=True)
class NativeLaunchSpec:
    adapter_kind: str
    executable: str
    cwd: str
    arguments: tuple[str, ...]
    permission_profile: str
    config_overrides: tuple[str, ...]
    filesystem_rules: tuple[NativeFilesystemRule, ...]
    model: str
    reasoning_effort: str
    native_agents_enabled: bool
    network_enabled: bool
    selected_binding_id: str
    effective_envelope: AuthorityEnvelope

    def __post_init__(self) -> None:
        if self.adapter_kind != "codex":
            raise ValueError("Codex launch adapter kind must be codex")
        if not isinstance(self.effective_envelope, AuthorityEnvelope):
            raise TypeError("Codex launch envelope must be an AuthorityEnvelope")
        _validate_path(self.executable, "Codex launch executable")
        _validate_path(self.cwd, "Codex launch cwd")
        arguments = tuple(self.arguments)
        if any(not isinstance(argument, str) for argument in arguments):
            raise TypeError("Codex launch arguments must be strings")
        object.__setattr__(self, "arguments", arguments)
        _validate_text(
            self.permission_profile,
            "Codex launch permission profile",
            maximum=128,
        )
        overrides = tuple(self.config_overrides)
        if any(not isinstance(override, str) for override in overrides):
            raise TypeError("Codex launch config overrides must be strings")
        object.__setattr__(self, "config_overrides", overrides)
        rules = tuple(self.filesystem_rules)
        if any(not isinstance(rule, NativeFilesystemRule) for rule in rules):
            raise TypeError("Codex launch filesystem rules are invalid")
        rules = tuple(sorted(rules, key=lambda rule: rule.path))
        paths = tuple(rule.path for rule in rules)
        resources = tuple(
            rule.resource for rule in rules if rule.resource is not None
        )
        if len(paths) != len(set(paths)) or len(resources) != len(set(resources)):
            raise ValueError("Codex launch filesystem rules repeat a binding")
        if not any(rule.path == ":minimal" for rule in rules):
            raise ValueError("Codex launch filesystem rules require :minimal")
        effective_access: dict[str, str] = {}
        for capability in self.effective_envelope.effective:
            if capability.name not in {"fs.read", "fs.write"}:
                continue
            if capability.resource is None:
                raise ValueError("Codex launch has an unscoped filesystem capability")
            desired = "write" if capability.name == "fs.write" else "read"
            if effective_access.get(capability.resource) != "write":
                effective_access[capability.resource] = desired
        rule_access = {
            rule.resource: rule.access
            for rule in rules
            if rule.resource is not None
        }
        if effective_access != rule_access:
            raise ValueError(
                "Codex launch filesystem rules do not match its effective envelope"
            )
        object.__setattr__(self, "filesystem_rules", rules)
        _validate_text(self.model, "Codex launch model", maximum=128)
        if SUPPORTED_REASONING_RE.fullmatch(self.reasoning_effort) is None:
            raise ValueError("Codex launch reasoning effort must be canonical")
        if self.native_agents_enabled is not False:
            raise ValueError("Codex launch must disable native agents")
        if self.network_enabled is not False:
            raise ValueError("Codex launch must disable network access")
        _validate_text(
            self.selected_binding_id,
            "Codex launch selected binding",
            maximum=128,
        )


@dataclass(frozen=True)
class CodexCompileResult:
    status: CodexCompileStatus
    launch_spec: NativeLaunchSpec | None
    rejections: tuple[CodexCompileRejection, ...]


class CodexProbeStatus(str, Enum):
    READY = "READY"
    CAPABILITY_INVALID = "CAPABILITY_INVALID"
    UNUSABLE = "UNUSABLE"


class CodexProbeRejectionCode(str, Enum):
    EXECUTABLE_UNAVAILABLE = "EXECUTABLE_UNAVAILABLE"
    VERSION_PROBE_FAILED = "VERSION_PROBE_FAILED"
    VERSION_INVALID = "VERSION_INVALID"
    VERSION_TOO_OLD = "VERSION_TOO_OLD"
    CLI_SURFACE_INCOMPLETE = "CLI_SURFACE_INCOMPLETE"
    MODEL_CATALOG_FAILED = "MODEL_CATALOG_FAILED"
    MODEL_CATALOG_INVALID = "MODEL_CATALOG_INVALID"
    PERMISSION_PROFILE_PROBE_FAILED = "PERMISSION_PROFILE_PROBE_FAILED"


@dataclass(frozen=True)
class CodexProbeRejection:
    code: CodexProbeRejectionCode
    detail: str | None = None


@dataclass(frozen=True)
class CodexProbeResult:
    status: CodexProbeStatus
    observation: CodexObservation | None
    rejections: tuple[CodexProbeRejection, ...]


def _rejected(
    status: CodexCompileStatus,
    *rejections: CodexCompileRejection,
) -> CodexCompileResult:
    return CodexCompileResult(status, None, tuple(rejections))


def _runtime_rejections(
    observation: CodexObservation,
    context: RuntimeBindingContext,
) -> tuple[CodexCompileRejection, ...]:
    rejections: list[CodexCompileRejection] = []
    if observation.version < CodexVersion(*MINIMUM_PERMISSION_PROFILE_VERSION):
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.VERSION_TOO_OLD,
                f"observed {observation.version}; need at least 0.138.0",
            )
        )
    if not observation.permission_profiles:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.PERMISSION_PROFILES_UNAVAILABLE
            )
        )
    elif observation.permission_profile_assurance is not AssuranceLevel.RUNTIME_PROBED:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.PERMISSION_PROFILE_UNVERIFIED
            )
        )
    if not observation.native_spawn_control:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.NATIVE_SPAWN_CONTROL_UNAVAILABLE
            )
        )
    elif observation.native_spawn_assurance not in {
        AssuranceLevel.STATIC_PROVEN,
        AssuranceLevel.NATIVE_INTROSPECTED,
        AssuranceLevel.RUNTIME_PROBED,
    }:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.NATIVE_SPAWN_CONTROL_UNVERIFIED
            )
        )
    if not observation.network_control:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.NETWORK_CONTROL_UNAVAILABLE
            )
        )
    elif observation.network_assurance is not AssuranceLevel.RUNTIME_PROBED:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.NETWORK_CONTROL_UNVERIFIED
            )
        )
    if observation.legacy_sandbox_settings:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.LEGACY_SANDBOX_CONFLICT
            )
        )
    if observation.bound_cwd != context.cwd:
        rejections.append(
            CodexCompileRejection(
                CodexCompileRejectionCode.OBSERVATION_CONTEXT_MISMATCH,
                f"observed {observation.bound_cwd}; compiling {context.cwd}",
            )
        )
    return tuple(rejections)


def _model_rejections(
    observation: CodexObservation,
    context: RuntimeBindingContext,
) -> tuple[CodexCompileRejection, ...]:
    model = observation.model_map.get(context.model)
    if model is None:
        return (
            CodexCompileRejection(
                CodexCompileRejectionCode.MODEL_NOT_OBSERVED,
                context.model,
            ),
        )
    if context.reasoning_effort not in model.reasoning_efforts:
        return (
            CodexCompileRejection(
                CodexCompileRejectionCode.REASONING_EFFORT_UNSUPPORTED,
                context.reasoning_effort,
            ),
        )
    return ()


def _compile_filesystem_rules(
    binding: Binding,
    context: RuntimeBindingContext,
    observation: CodexObservation,
) -> tuple[
    tuple[tuple[str, str], ...] | None,
    tuple[CodexCompileRejection, ...],
]:
    effective = binding.envelope.effective
    runtime_read = Capability("fs.read", RUNTIME_RESOURCE)
    if runtime_read not in effective:
        return None, (
            CodexCompileRejection(CodexCompileRejectionCode.MISSING_RUNTIME_READ),
        )

    access_by_resource: dict[str, str] = {}
    resource_paths = context.resource_map
    rejections: list[CodexCompileRejection] = []
    for capability in sorted(effective):
        if capability == runtime_read:
            continue
        if capability.name == "native_spawn":
            rejections.append(
                CodexCompileRejection(
                    CodexCompileRejectionCode.NATIVE_SPAWN_UNSUPPORTED,
                    capabilities=(capability,),
                )
            )
            continue
        if capability.name == "network.egress":
            rejections.append(
                CodexCompileRejection(
                    CodexCompileRejectionCode.NETWORK_GRANT_UNSUPPORTED,
                    capabilities=(capability,),
                )
            )
            continue
        if capability.name not in {"fs.read", "fs.write"}:
            rejections.append(
                CodexCompileRejection(
                    CodexCompileRejectionCode.UNSUPPORTED_CAPABILITY,
                    capabilities=(capability,),
                )
            )
            continue
        if capability.resource is None or capability.resource == RUNTIME_RESOURCE:
            rejections.append(
                CodexCompileRejection(
                    CodexCompileRejectionCode.INVALID_CAPABILITY_SHAPE,
                    capabilities=(capability,),
                )
            )
            continue
        if capability.resource not in resource_paths:
            rejections.append(
                CodexCompileRejection(
                    CodexCompileRejectionCode.UNBOUND_RESOURCE,
                    capability.resource,
                    (capability,),
                )
            )
            continue
        desired = "write" if capability.name == "fs.write" else "read"
        current = access_by_resource.get(capability.resource)
        if current != "write":
            access_by_resource[capability.resource] = desired

    if rejections:
        return None, tuple(rejections)

    normalized = {runtime_read}
    path_access: dict[str, str] = {
        ":minimal": "read",
        observation.runtime_root: "read",
    }
    for resource, access in access_by_resource.items():
        normalized.add(Capability("fs.read", resource))
        if access == "write":
            normalized.add(Capability("fs.write", resource))
        path_access[resource_paths[resource]] = access
    if frozenset(normalized) != effective:
        difference = normalized ^ set(effective)
        return None, (
            CodexCompileRejection(
                CodexCompileRejectionCode.EFFECTIVE_ENVELOPE_MISMATCH,
                capabilities=_ordered_capabilities(difference),
            ),
        )
    return tuple(sorted(path_access.items())), ()


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _render_inline_string_table(entries: tuple[tuple[str, str], ...]) -> str:
    body = ", ".join(
        f"{_toml_string(key)} = {_toml_string(value)}" for key, value in entries
    )
    return f"{{ {body} }}"


def _permission_override(filesystem: tuple[tuple[str, str], ...]) -> str:
    rules = _render_inline_string_table(filesystem)
    return (
        "permissions={ "
        f"{_toml_string(PROFILE_NAME)} = {{ "
        f"filesystem = {rules}, network = {{ enabled = false }} "
        "} }"
    )


def _path_contains(root: str, candidate: str) -> bool:
    try:
        return os.path.commonpath((root, candidate)) == root
    except ValueError:
        return False


def compile_codex(
    selection: SelectionResult,
    context: RuntimeBindingContext,
    observation: CodexObservation,
) -> CodexCompileResult:
    """Compile one selected compatible Codex binding; fail closed otherwise."""

    if not isinstance(selection, SelectionResult):
        raise TypeError("selection must be a SelectionResult")
    if not isinstance(context, RuntimeBindingContext):
        raise TypeError("context must be a RuntimeBindingContext")
    if not isinstance(observation, CodexObservation):
        raise TypeError("observation must be a CodexObservation")
    if (
        selection.status is not SelectionStatus.SELECTED
        or selection.selected_binding is None
        or selection.selector_receipt is None
    ):
        return _rejected(
            CodexCompileStatus.STATIC_INVALID,
            CodexCompileRejection(
                CodexCompileRejectionCode.SELECTION_NOT_COMPLETE
            ),
        )
    binding = selection.selected_binding
    if binding.adapter_kind != "codex":
        return _rejected(
            CodexCompileStatus.STATIC_INVALID,
            CodexCompileRejection(
                CodexCompileRejectionCode.ADAPTER_KIND_MISMATCH,
                binding.adapter_kind,
            ),
        )

    runtime_rejections = _runtime_rejections(observation, context)
    if runtime_rejections:
        return _rejected(CodexCompileStatus.CAPABILITY_INVALID, *runtime_rejections)
    model_rejections = _model_rejections(observation, context)
    if model_rejections:
        return _rejected(CodexCompileStatus.CAPABILITY_INVALID, *model_rejections)

    filesystem, authority_rejections = _compile_filesystem_rules(
        binding,
        context,
        observation,
    )
    if authority_rejections:
        capability_codes = {
            CodexCompileRejectionCode.NATIVE_SPAWN_UNSUPPORTED,
            CodexCompileRejectionCode.NETWORK_GRANT_UNSUPPORTED,
        }
        status = (
            CodexCompileStatus.CAPABILITY_INVALID
            if any(
                rejection.code in capability_codes
                for rejection in authority_rejections
            )
            else CodexCompileStatus.STATIC_INVALID
        )
        return _rejected(status, *authority_rejections)
    assert filesystem is not None
    accessible_roots = tuple(
        path
        for path, access in filesystem
        if access in {"read", "write"}
        and path not in {":minimal", observation.runtime_root}
    )
    if not any(_path_contains(root, context.cwd) for root in accessible_roots):
        return _rejected(
            CodexCompileStatus.STATIC_INVALID,
            CodexCompileRejection(CodexCompileRejectionCode.CWD_NOT_ACCESSIBLE),
        )

    config_overrides = (
        f"default_permissions={_toml_string(PROFILE_NAME)}",
        _permission_override(filesystem),
        "agents.enabled=false",
        f"model_reasoning_effort={_toml_string(context.reasoning_effort)}",
    )
    arguments = (
        "--strict-config",
        "--model",
        context.model,
        "--ask-for-approval",
        "never",
        "--config",
        config_overrides[0],
        "--config",
        config_overrides[1],
        "--config",
        config_overrides[2],
        "--config",
        config_overrides[3],
        "--cd",
        context.cwd,
    )
    return CodexCompileResult(
        status=CodexCompileStatus.COMPILED,
        launch_spec=NativeLaunchSpec(
            adapter_kind="codex",
            executable=observation.executable,
            cwd=context.cwd,
            arguments=arguments,
            permission_profile=PROFILE_NAME,
            config_overrides=config_overrides,
            filesystem_rules=tuple(
                NativeFilesystemRule(
                    (
                        None
                        if path == ":minimal"
                        else RUNTIME_RESOURCE
                        if path == observation.runtime_root
                        else next(
                            resource.resource
                            for resource in context.resources
                            if resource.path == path
                        )
                    ),
                    path,
                    access,
                )
                for path, access in filesystem
            ),
            model=context.model,
            reasoning_effort=context.reasoning_effort,
            native_agents_enabled=False,
            network_enabled=False,
            selected_binding_id=binding.identifier,
            effective_envelope=binding.envelope,
        ),
        rejections=(),
    )


def _run_codex(
    arguments: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _probe_detail(completed: subprocess.CompletedProcess[str]) -> str:
    output = (completed.stderr or completed.stdout).strip()
    return output[:1000] if output else f"exit {completed.returncode}"


def _parse_model_catalog(raw: str) -> tuple[CodexModelObservation, ...]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"catalog is not JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("models"), list):
        raise ValueError("catalog must contain a models array")
    models: list[CodexModelObservation] = []
    for index, entry in enumerate(document["models"]):
        if not isinstance(entry, dict):
            raise ValueError(f"catalog entry {index} must be an object")
        identifier = entry.get("slug")
        levels = entry.get("supported_reasoning_levels")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"catalog entry {index} has no model identifier")
        if not isinstance(levels, list):
            raise ValueError(f"catalog model {identifier} has no reasoning-level array")
        efforts: list[str] = []
        for level_index, level in enumerate(levels):
            effort = level.get("effort") if isinstance(level, dict) else level
            if not isinstance(effort, str) or not effort:
                raise ValueError(
                    f"catalog model {identifier} reasoning level {level_index} is invalid"
                )
            if effort in efforts:
                raise ValueError(
                    f"catalog model {identifier} repeats reasoning effort {effort}"
                )
            efforts.append(effort)
        models.append(CodexModelObservation(identifier, tuple(efforts)))
    if not models:
        raise ValueError("catalog contains no models")
    identifiers = [model.identifier for model in models]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("catalog repeats a model identifier")
    return tuple(models)


def _discover_runtime_root(executable: str) -> str:
    resolved = Path(executable).resolve(strict=True)
    if resolved.name == "codex.js" and resolved.parent.name == "bin":
        return str(resolved.parent.parent)
    return str(resolved.parent)


def _probe_permission_profile(
    executable: str,
    cwd: str,
    runtime_root: str,
) -> tuple[bool, str | None]:
    script = r'''
set +e
dd if="$1/readable" of=/dev/null bs=1 count=1 >/dev/null 2>&1
printf 'read_project=%s\n' "$?"
sh -c ': > "$1"' sh "$2/allowed" >/dev/null 2>&1
printf 'write_evidence=%s\n' "$?"
sh -c ': > "$1"' sh "$1/blocked" >/dev/null 2>&1
printf 'write_project=%s\n' "$?"
sh -c ': > "$1"' sh "$3/blocked" >/dev/null 2>&1
printf 'write_outside=%s\n' "$?"
ls "$3" >/dev/null 2>&1
printf 'read_outside=%s\n' "$?"
python3 -c 'import errno, socket, sys
try:
    candidate = socket.socket()
    candidate.settimeout(1)
    candidate.connect(("1.1.1.1", 80))
except OSError as error:
    sys.exit(0 if error.errno in (errno.EPERM, errno.EACCES) else 2)
sys.exit(3)' >/dev/null 2>&1
printf 'network_denied=%s\n' "$?"
'''.strip()
    with tempfile.TemporaryDirectory(prefix="herdr-codex-profile-") as temporary:
        probe_root = Path(temporary)
        project_root = probe_root / "project"
        evidence_root = probe_root / "evidence"
        outside_root = probe_root / "outside"
        project_root.mkdir()
        evidence_root.mkdir()
        outside_root.mkdir()
        (project_root / "readable").write_bytes(b"x")
        path_rules: dict[str, str] = {
            ":minimal": "read",
            runtime_root: "read",
            cwd: "read",
            str(project_root): "read",
            str(evidence_root): "write",
        }
        filesystem = tuple(sorted(path_rules.items()))
        try:
            completed = _run_codex(
                [
                    executable,
                    "sandbox",
                    "--permission-profile",
                    PROFILE_NAME,
                    "--config",
                    _permission_override(filesystem),
                    "--config",
                    "agents.enabled=false",
                    "--cd",
                    cwd,
                    "--",
                    "sh",
                    "-c",
                    script,
                    "sh",
                    str(project_root),
                    str(evidence_root),
                    str(outside_root),
                ],
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
    if completed.returncode != 0:
        return False, _probe_detail(completed)
    receipt: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and value.isdigit():
            receipt[key] = int(value)
    required = {
        "read_project",
        "write_evidence",
        "write_project",
        "write_outside",
        "read_outside",
        "network_denied",
    }
    if set(receipt) != required:
        return False, f"incomplete probe receipt: {completed.stdout[:1000]}"
    passed = (
        receipt["read_project"] == 0
        and receipt["write_evidence"] == 0
        and receipt["write_project"] != 0
        and receipt["write_outside"] != 0
        and receipt["read_outside"] != 0
        and receipt["network_denied"] == 0
    )
    if not passed:
        return False, f"unexpected probe receipt: {receipt}"
    return True, None


def probe_codex(executable: str, *, cwd: str) -> CodexProbeResult:
    """Mechanically probe one Codex installation for required authority controls."""

    _validate_path(executable, "Codex probe executable")
    _validate_path(cwd, "Codex probe cwd")
    if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.EXECUTABLE_UNAVAILABLE,
                    executable,
                ),
            ),
        )
    try:
        version_completed = _run_codex(
            [executable, "--version"],
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.VERSION_PROBE_FAILED,
                    str(exc),
                ),
            ),
        )
    if version_completed.returncode != 0:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.VERSION_PROBE_FAILED,
                    _probe_detail(version_completed),
                ),
            ),
        )
    try:
        version = CodexVersion.parse(version_completed.stdout.strip())
        runtime_root = _discover_runtime_root(executable)
    except (OSError, ValueError) as exc:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.VERSION_INVALID,
                    str(exc),
                ),
            ),
        )

    try:
        help_completed = _run_codex([executable, "--help"], timeout=5)
        sandbox_help = _run_codex(
            [executable, "sandbox", "--help"],
            timeout=5,
        )
        catalog_completed = _run_codex(
            [executable, "debug", "models", "--bundled"],
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.CLI_SURFACE_INCOMPLETE,
                    str(exc),
                ),
            ),
        )
    if catalog_completed.returncode != 0:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.MODEL_CATALOG_FAILED,
                    _probe_detail(catalog_completed),
                ),
            ),
        )
    try:
        models = _parse_model_catalog(catalog_completed.stdout)
    except ValueError as exc:
        return CodexProbeResult(
            CodexProbeStatus.UNUSABLE,
            None,
            (
                CodexProbeRejection(
                    CodexProbeRejectionCode.MODEL_CATALOG_INVALID,
                    str(exc),
                ),
            ),
        )

    rejections: list[CodexProbeRejection] = []
    current_enough = version >= CodexVersion(*MINIMUM_PERMISSION_PROFILE_VERSION)
    if not current_enough:
        rejections.append(
            CodexProbeRejection(
                CodexProbeRejectionCode.VERSION_TOO_OLD,
                f"observed {version}; need at least 0.138.0",
            )
        )
    top_help = help_completed.stdout if help_completed.returncode == 0 else ""
    profile_help = sandbox_help.stdout if sandbox_help.returncode == 0 else ""
    required_top = {
        "--config",
        "--strict-config",
        "--ask-for-approval",
        "--cd",
    }
    surface_ready = required_top.issubset(set(top_help.split())) and (
        "--permission-profile" in profile_help
    )
    if not surface_ready:
        rejections.append(
            CodexProbeRejection(
                CodexProbeRejectionCode.CLI_SURFACE_INCOMPLETE
            )
        )
    profile_passed = False
    if current_enough and surface_ready:
        profile_passed, detail = _probe_permission_profile(
            executable,
            cwd,
            runtime_root,
        )
        if not profile_passed:
            rejections.append(
                CodexProbeRejection(
                    CodexProbeRejectionCode.PERMISSION_PROFILE_PROBE_FAILED,
                    detail,
                )
            )

    control_available = current_enough and surface_ready
    observation = CodexObservation(
        executable=executable,
        version=version,
        runtime_root=runtime_root,
        bound_cwd=cwd,
        models=models,
        permission_profiles=profile_passed,
        permission_profile_assurance=(
            AssuranceLevel.RUNTIME_PROBED
            if profile_passed
            else AssuranceLevel.UNVERIFIED
        ),
        native_spawn_control=control_available,
        native_spawn_assurance=(
            AssuranceLevel.STATIC_PROVEN
            if control_available
            else AssuranceLevel.UNVERIFIED
        ),
        network_control=profile_passed,
        network_assurance=(
            AssuranceLevel.RUNTIME_PROBED
            if profile_passed
            else AssuranceLevel.UNVERIFIED
        ),
        legacy_sandbox_settings=False,
    )
    return CodexProbeResult(
        CodexProbeStatus.READY if not rejections else CodexProbeStatus.CAPABILITY_INVALID,
        observation,
        tuple(rejections),
    )
