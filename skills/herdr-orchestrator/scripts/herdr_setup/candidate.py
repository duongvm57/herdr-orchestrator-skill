"""Mechanical discovery and immutable setup-candidate compilation."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from .authority import (
    AuthorityPolicy,
    Capability,
    Requirement,
    SelectionResult,
    SelectionStatus,
    SelectorReceipt,
)
from .codex_authority import (
    AssuranceLevel,
    CodexCompileResult,
    CodexCompileStatus,
    CodexObservation,
    NativeLaunchSpec,
    RuntimeBindingContext,
)


CANDIDATE_SCHEMA = "herdr.setup-candidate"
CODEX_ADAPTER_CONTRACT = "codex-permission-profile"
MAX_DISCOVERED_FILE_BYTES = 16 * 1024 * 1024
POLICY_FILENAMES = frozenset({"AGENTS.md", "CLAUDE.md"})
COPILOT_POLICY_PATH = ".github/copilot-instructions.md"
ACTIVATION_PATH = ".orchestration/setup/current.json"
SUPPORTED_ROLES = frozenset({"lead", "engineer", "reviewer", "supervisor"})
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


def _validate_text(value: str, label: str, *, maximum: int = 4096) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty canonical string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds the bounded length")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} contains a control character")


def _validate_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical identifier")


def _validate_absolute_path(value: str, label: str) -> None:
    _validate_text(value, label)
    if not os.path.isabs(value) or os.path.normpath(value) != value:
        raise ValueError(f"{label} must be an absolute normalized path")


def _validate_relative_path(value: str, label: str) -> None:
    _validate_text(value, label)
    candidate = Path(value)
    if candidate.is_absolute() or value == ".." or value.startswith("../"):
        raise ValueError(f"{label} must stay relative to the project root")
    if (
        value != "."
        and (candidate.as_posix() != value or posixpath.normpath(value) != value)
    ):
        raise ValueError(f"{label} must use canonical POSIX separators")


def _validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(label: str, value: object) -> str:
    payload = label.encode("ascii") + b"\0" + _canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _ordered_unique(
    values: Iterable[object],
    *,
    expected_type: type,
    key,
    label: str,
) -> tuple[object, ...]:
    result = tuple(values)
    if any(not isinstance(value, expected_type) for value in result):
        raise TypeError(f"{label} contains an invalid value")
    ordered = tuple(sorted(result, key=key))
    keys = tuple(key(value) for value in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} repeats an identifier")
    return ordered


class ProvenanceKind(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    DEFAULTED = "DEFAULTED"


class HarnessStatus(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    DETECTED = "DETECTED"
    DETECTED_PARTIAL = "DETECTED_PARTIAL"
    SUPPORTED = "SUPPORTED"
    READY = "READY"
    UNUSABLE = "UNUSABLE"


@dataclass(frozen=True, order=True)
class DiscoveredModel:
    identifier: str
    reasoning_efforts: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_text(self.identifier, "model identifier", maximum=128)
        efforts = tuple(sorted(self.reasoning_efforts))
        if any(
            not isinstance(effort, str) or IDENTIFIER_RE.fullmatch(effort) is None
            for effort in efforts
        ):
            raise ValueError("reasoning efforts must be canonical identifiers")
        if len(efforts) != len(set(efforts)):
            raise ValueError("model repeats a reasoning effort")
        object.__setattr__(self, "reasoning_efforts", efforts)


@dataclass(frozen=True, order=True)
class CapabilityObservation:
    name: str
    available: bool
    assurance: AssuranceLevel

    def __post_init__(self) -> None:
        _validate_identifier(self.name, "capability observation name")
        if not isinstance(self.available, bool):
            raise TypeError("capability availability must be boolean")
        if not isinstance(self.assurance, AssuranceLevel):
            raise TypeError("capability assurance must be an AssuranceLevel")


@dataclass(frozen=True, order=True)
class HarnessRuntimeObservation:
    cwd: str
    runtime_root: str
    capabilities: tuple[CapabilityObservation, ...]

    def __post_init__(self) -> None:
        _validate_absolute_path(self.cwd, "harness runtime cwd")
        _validate_absolute_path(self.runtime_root, "harness runtime root")
        ordered = _ordered_unique(
            self.capabilities,
            expected_type=CapabilityObservation,
            key=lambda item: item.name,
            label="harness runtime capabilities",
        )
        object.__setattr__(self, "capabilities", ordered)


@dataclass(frozen=True)
class HarnessObservation:
    kind: str
    status: HarnessStatus
    executable: str | None = None
    version: str | None = None
    models: tuple[DiscoveredModel, ...] = ()
    runtimes: tuple[HarnessRuntimeObservation, ...] = ()
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(self.kind, "harness kind")
        if not isinstance(self.status, HarnessStatus):
            raise TypeError("harness status must be a HarnessStatus")
        if self.executable is not None:
            _validate_absolute_path(self.executable, "harness executable")
        if self.version is not None:
            _validate_text(self.version, "harness version", maximum=128)
        models = _ordered_unique(
            self.models,
            expected_type=DiscoveredModel,
            key=lambda item: item.identifier,
            label="harness models",
        )
        runtimes = _ordered_unique(
            self.runtimes,
            expected_type=HarnessRuntimeObservation,
            key=lambda item: item.cwd,
            label="harness runtime observations",
        )
        issues = tuple(sorted(self.issue_codes))
        if any(
            not isinstance(issue, str) or IDENTIFIER_RE.fullmatch(issue) is None
            for issue in issues
        ):
            raise ValueError("harness issue codes must be canonical identifiers")
        if len(issues) != len(set(issues)):
            raise ValueError("harness repeats an issue code")
        if self.status is HarnessStatus.NOT_INSTALLED and any(
            value for value in (self.executable, self.version, models, runtimes)
        ):
            raise ValueError("not-installed harness cannot claim discovered facts")
        if self.status is HarnessStatus.READY and (
            self.executable is None
            or self.version is None
            or not models
            or not runtimes
            or issues
        ):
            raise ValueError("ready harness requires a complete issue-free observation")
        object.__setattr__(self, "models", models)
        object.__setattr__(self, "runtimes", runtimes)
        object.__setattr__(self, "issue_codes", issues)

    @property
    def model_map(self) -> dict[str, DiscoveredModel]:
        return {model.identifier: model for model in self.models}

    @property
    def runtime_map(self) -> dict[str, HarnessRuntimeObservation]:
        return {runtime.cwd: runtime for runtime in self.runtimes}


@dataclass(frozen=True, order=True)
class AdapterObservation:
    kind: str
    version: str
    implementation_digest: str

    def __post_init__(self) -> None:
        _validate_identifier(self.kind, "adapter kind")
        _validate_text(self.version, "adapter version", maximum=128)
        _validate_digest(self.implementation_digest, "adapter implementation digest")


@dataclass(frozen=True, order=True)
class RepositoryObservation:
    identifier: str
    relative_path: str
    path: str
    git_dir: str
    git_common_dir: str

    def __post_init__(self) -> None:
        _validate_text(self.identifier, "repository identifier", maximum=512)
        _validate_relative_path(self.relative_path, "repository relative path")
        for value, label in (
            (self.path, "repository path"),
            (self.git_dir, "repository Git directory"),
            (self.git_common_dir, "repository Git common directory"),
        ):
            _validate_absolute_path(value, label)


@dataclass(frozen=True, order=True)
class FileObservation:
    relative_path: str
    exists: bool
    size: int | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path, "observed file path")
        if not isinstance(self.exists, bool):
            raise TypeError("observed file existence must be boolean")
        if self.exists:
            if (
                not isinstance(self.size, int)
                or isinstance(self.size, bool)
                or self.size < 0
                or self.sha256 is None
            ):
                raise ValueError("existing file requires size and digest")
            _validate_digest(self.sha256, "observed file digest")
        elif self.size is not None or self.sha256 is not None:
            raise ValueError("missing file cannot have size or digest")


@dataclass(frozen=True)
class DiscoverySnapshot:
    project_root: str
    repositories: tuple[RepositoryObservation, ...]
    harnesses: tuple[HarnessObservation, ...]
    adapters: tuple[AdapterObservation, ...]
    policy_sources: tuple[FileObservation, ...]
    existing_activation: FileObservation
    discovery_digest: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_absolute_path(self.project_root, "discovery project root")
        repositories = _ordered_unique(
            self.repositories,
            expected_type=RepositoryObservation,
            key=lambda item: item.relative_path,
            label="discovered repositories",
        )
        if not repositories:
            raise ValueError("discovery requires at least one Git repository")
        identifiers = tuple(repository.identifier for repository in repositories)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("discovered repositories repeat an identifier")
        harnesses = _ordered_unique(
            self.harnesses,
            expected_type=HarnessObservation,
            key=lambda item: item.kind,
            label="discovered harnesses",
        )
        adapters = _ordered_unique(
            self.adapters,
            expected_type=AdapterObservation,
            key=lambda item: item.kind,
            label="discovered adapters",
        )
        policy_sources = _ordered_unique(
            self.policy_sources,
            expected_type=FileObservation,
            key=lambda item: item.relative_path,
            label="policy sources",
        )
        if any(not source.exists for source in policy_sources):
            raise ValueError("policy source observations must exist")
        if not isinstance(self.existing_activation, FileObservation):
            raise TypeError("existing activation must be a FileObservation")
        if self.existing_activation.relative_path != ACTIVATION_PATH:
            raise ValueError("existing activation observation has the wrong canonical path")
        object.__setattr__(self, "repositories", repositories)
        object.__setattr__(self, "harnesses", harnesses)
        object.__setattr__(self, "adapters", adapters)
        object.__setattr__(self, "policy_sources", policy_sources)
        root = Path(self.project_root)
        for repository in repositories:
            expected_path = (
                root
                if repository.relative_path == "."
                else root / repository.relative_path
            )
            if repository.path != str(expected_path):
                raise ValueError(
                    "repository path does not match its project-relative path"
                )
        object.__setattr__(
            self,
            "discovery_digest",
            _digest("herdr-discovery", _discovery_projection(self)),
        )

    @property
    def harness_map(self) -> dict[str, HarnessObservation]:
        return {harness.kind: harness for harness in self.harnesses}

    @property
    def adapter_map(self) -> dict[str, AdapterObservation]:
        return {adapter.kind: adapter for adapter in self.adapters}


class DiscoveryFailureCode(str, Enum):
    PROJECT_ROOT_INVALID = "PROJECT_ROOT_INVALID"
    NO_GIT_REPOSITORY = "NO_GIT_REPOSITORY"
    GIT_PROBE_FAILED = "GIT_PROBE_FAILED"
    GIT_ROOT_MISMATCH = "GIT_ROOT_MISMATCH"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_CHANGED_DURING_DISCOVERY = "FILE_CHANGED_DURING_DISCOVERY"


class DiscoveryFailure(RuntimeError):
    def __init__(
        self,
        code: DiscoveryFailureCode,
        path: str,
        detail: str | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        message = f"{code.value}: {path}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


def _relative(project_root: Path, path: Path) -> str:
    relative = path.relative_to(project_root)
    return "." if relative == Path(".") else relative.as_posix()


def _observe_file(project_root: Path, path: Path, *, optional: bool) -> FileObservation:
    relative = _relative(project_root, path)
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        if optional:
            return FileObservation(relative, False)
        raise DiscoveryFailure(DiscoveryFailureCode.UNSUPPORTED_FILE, str(path), "missing")
    if not stat.S_ISREG(before.st_mode):
        raise DiscoveryFailure(
            DiscoveryFailureCode.UNSUPPORTED_FILE,
            str(path),
            "policy inputs must be regular files, not symlinks or directories",
        )
    if before.st_size > MAX_DISCOVERED_FILE_BYTES:
        raise DiscoveryFailure(
            DiscoveryFailureCode.FILE_TOO_LARGE,
            str(path),
            f"{before.st_size} bytes",
        )
    data = path.read_bytes()
    after = os.lstat(path)
    stable = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) and len(data) == after.st_size
    if not stable:
        raise DiscoveryFailure(
            DiscoveryFailureCode.FILE_CHANGED_DURING_DISCOVERY,
            str(path),
        )
    return FileObservation(
        relative_path=relative,
        exists=True,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _git(repo: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", *arguments],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoveryFailure(
            DiscoveryFailureCode.GIT_PROBE_FAILED,
            str(repo),
            str(exc),
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:1000]
        raise DiscoveryFailure(
            DiscoveryFailureCode.GIT_PROBE_FAILED,
            str(repo),
            detail or f"exit {completed.returncode}",
        )
    value = completed.stdout.strip()
    if not value:
        raise DiscoveryFailure(
            DiscoveryFailureCode.GIT_PROBE_FAILED,
            str(repo),
            "empty rev-parse output",
        )
    return value


def _observe_repository(project_root: Path, candidate: Path) -> RepositoryObservation:
    top_level = Path(_git(candidate, "--show-toplevel")).resolve(strict=True)
    if top_level != candidate:
        raise DiscoveryFailure(
            DiscoveryFailureCode.GIT_ROOT_MISMATCH,
            str(candidate),
            f"Git reports {top_level}",
        )
    if _git(candidate, "--is-inside-work-tree") != "true":
        raise DiscoveryFailure(
            DiscoveryFailureCode.GIT_PROBE_FAILED,
            str(candidate),
            "setup requires a Git worktree",
        )
    git_dir = Path(_git(candidate, "--absolute-git-dir")).resolve(strict=True)
    common_raw = Path(_git(candidate, "--git-common-dir"))
    git_common = (
        common_raw if common_raw.is_absolute() else candidate / common_raw
    ).resolve(strict=True)
    relative = _relative(project_root, candidate)
    return RepositoryObservation(
        identifier="root" if relative == "." else relative,
        relative_path=relative,
        path=str(candidate),
        git_dir=str(git_dir),
        git_common_dir=str(git_common),
    )


def _scan_project(project_root: Path) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    repository_roots: list[Path] = []
    policy_sources: list[Path] = []
    for directory, child_directories, filenames in os.walk(project_root):
        current = Path(directory)
        child_directories[:] = sorted(
            child
            for child in child_directories
            if child != ".git" and not (current / child).is_symlink()
        )
        names = set(filenames)
        if ".git" in names or (current / ".git").is_dir():
            repository_roots.append(current.resolve(strict=True))
        for name in sorted(names & POLICY_FILENAMES):
            policy_sources.append(current / name)
        copilot = current / "copilot-instructions.md"
        if _relative(project_root, copilot) == COPILOT_POLICY_PATH and copilot.is_file():
            policy_sources.append(copilot)
    return tuple(sorted(set(repository_roots))), tuple(sorted(set(policy_sources)))


def discover_setup(
    project_root: str,
    *,
    harnesses: Iterable[HarnessObservation],
    adapters: Iterable[AdapterObservation],
) -> DiscoverySnapshot:
    """Discover canonical project facts without asking the Human or writing files."""

    _validate_absolute_path(project_root, "project root")
    try:
        root = Path(project_root).resolve(strict=True)
    except OSError as exc:
        raise DiscoveryFailure(
            DiscoveryFailureCode.PROJECT_ROOT_INVALID,
            project_root,
            str(exc),
        ) from exc
    if not root.is_dir() or str(root) != project_root:
        raise DiscoveryFailure(
            DiscoveryFailureCode.PROJECT_ROOT_INVALID,
            project_root,
            "project root must be a canonical directory",
        )
    repository_paths, policy_paths = _scan_project(root)
    if not repository_paths:
        raise DiscoveryFailure(DiscoveryFailureCode.NO_GIT_REPOSITORY, project_root)
    repositories = tuple(
        _observe_repository(root, repository) for repository in repository_paths
    )
    policy_sources = tuple(
        _observe_file(root, source, optional=False) for source in policy_paths
    )
    return DiscoverySnapshot(
        project_root=project_root,
        repositories=repositories,
        harnesses=tuple(harnesses),
        adapters=tuple(adapters),
        policy_sources=policy_sources,
        existing_activation=_observe_file(root, root / ACTIVATION_PATH, optional=True),
    )


def normalize_codex_harness(
    observations: Iterable[CodexObservation],
) -> HarnessObservation:
    """Normalize one Codex installation and its exact probed cwd contexts."""

    values = tuple(observations)
    if not values or any(not isinstance(value, CodexObservation) for value in values):
        raise ValueError("Codex harness normalization requires observations")
    first = values[0]
    discovered_models = tuple(
        sorted(
            (
                DiscoveredModel(model.identifier, model.reasoning_efforts)
                for model in first.models
            ),
            key=lambda model: model.identifier,
        )
    )
    if any(
        value.executable != first.executable
        or value.version != first.version
        or tuple(
            sorted(
                (
                    DiscoveredModel(model.identifier, model.reasoning_efforts)
                    for model in value.models
                ),
                key=lambda model: model.identifier,
            )
        )
        != discovered_models
        for value in values[1:]
    ):
        raise ValueError("Codex observations do not describe one installation")
    runtimes = tuple(
        HarnessRuntimeObservation(
            cwd=value.bound_cwd,
            runtime_root=value.runtime_root,
            capabilities=(
                CapabilityObservation(
                    "filesystem.permission_profiles",
                    value.permission_profiles,
                    value.permission_profile_assurance,
                ),
                CapabilityObservation(
                    "native_spawn.control",
                    value.native_spawn_control,
                    value.native_spawn_assurance,
                ),
                CapabilityObservation(
                    "network.control",
                    value.network_control,
                    value.network_assurance,
                ),
                CapabilityObservation(
                    "legacy_sandbox.absent",
                    not value.legacy_sandbox_settings,
                    AssuranceLevel.NATIVE_INTROSPECTED,
                ),
            ),
        )
        for value in values
    )
    return HarnessObservation(
        kind="codex",
        status=HarnessStatus.READY,
        executable=first.executable,
        version=str(first.version),
        models=discovered_models,
        runtimes=runtimes,
    )


def observe_codex_adapter() -> AdapterObservation:
    """Observe the Codex adapter contract and exact implementation bytes."""

    implementation = Path(__file__).with_name("codex_authority.py").read_bytes()
    return AdapterObservation(
        kind="codex",
        version=CODEX_ADAPTER_CONTRACT,
        implementation_digest=hashlib.sha256(implementation).hexdigest(),
    )


class DecisionValueKind(str, Enum):
    BOOLEAN = "BOOLEAN"
    CHOICE = "CHOICE"
    TEXT = "TEXT"


@dataclass(frozen=True, order=True)
class PolicyAnswer:
    identifier: str
    kind: DecisionValueKind
    value: bool | str

    def __post_init__(self) -> None:
        _validate_identifier(self.identifier, "policy answer identifier")
        if not isinstance(self.kind, DecisionValueKind):
            raise TypeError("policy answer kind must be a DecisionValueKind")
        if self.kind is DecisionValueKind.BOOLEAN:
            if type(self.value) is not bool:
                raise TypeError("boolean policy answer requires a boolean value")
        elif not isinstance(self.value, str):
            raise TypeError("textual policy answer requires a string value")
        else:
            _validate_text(self.value, "choice policy answer", maximum=256)


class NativeAgentPolicy(str, Enum):
    DISABLED = "disabled"


@dataclass(frozen=True)
class RoleAuthorityDecision:
    role: str
    policy: AuthorityPolicy

    def __post_init__(self) -> None:
        _validate_identifier(self.role, "authority decision role")
        if not isinstance(self.policy, AuthorityPolicy):
            raise TypeError("authority decision policy must be an AuthorityPolicy")


@dataclass(frozen=True, order=True)
class ModelBinding:
    role: str
    harness: str
    model: str
    reasoning_effort: str

    def __post_init__(self) -> None:
        _validate_identifier(self.role, "model binding role")
        _validate_identifier(self.harness, "model binding harness")
        _validate_text(self.model, "model binding model", maximum=128)
        _validate_identifier(self.reasoning_effort, "model binding reasoning effort")


@dataclass(frozen=True, order=True)
class BindingChoice:
    role: str
    binding_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.role, "binding choice role")
        _validate_identifier(self.binding_id, "binding choice identifier")


@dataclass(frozen=True)
class HumanDecisions:
    native_agent_policy: NativeAgentPolicy
    role_authority: tuple[RoleAuthorityDecision, ...]
    model_bindings: tuple[ModelBinding, ...]
    binding_choices: tuple[BindingChoice, ...] = ()
    policy_answers: tuple[PolicyAnswer, ...] = ()
    human_decisions_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.native_agent_policy, NativeAgentPolicy):
            raise TypeError("native agent policy must be a NativeAgentPolicy")
        authority = _ordered_unique(
            self.role_authority,
            expected_type=RoleAuthorityDecision,
            key=lambda item: item.role,
            label="role authority decisions",
        )
        models = _ordered_unique(
            self.model_bindings,
            expected_type=ModelBinding,
            key=lambda item: item.role,
            label="model bindings",
        )
        choices = _ordered_unique(
            self.binding_choices,
            expected_type=BindingChoice,
            key=lambda item: item.role,
            label="binding choices",
        )
        answers = _ordered_unique(
            self.policy_answers,
            expected_type=PolicyAnswer,
            key=lambda item: item.identifier,
            label="policy answers",
        )
        object.__setattr__(self, "role_authority", authority)
        object.__setattr__(self, "model_bindings", models)
        object.__setattr__(self, "binding_choices", choices)
        object.__setattr__(self, "policy_answers", answers)
        object.__setattr__(
            self,
            "human_decisions_digest",
            _digest("herdr-human-decisions", _human_decisions_projection(self)),
        )


@dataclass(frozen=True)
class CompiledPolicy:
    native_agent_policy: NativeAgentPolicy
    role_authority: tuple[RoleAuthorityDecision, ...]
    policy_answers: tuple[PolicyAnswer, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.native_agent_policy, NativeAgentPolicy):
            raise TypeError("compiled native agent policy is invalid")
        authority = _ordered_unique(
            self.role_authority,
            expected_type=RoleAuthorityDecision,
            key=lambda item: item.role,
            label="compiled role authority",
        )
        answers = _ordered_unique(
            self.policy_answers,
            expected_type=PolicyAnswer,
            key=lambda item: item.identifier,
            label="compiled policy answers",
        )
        object.__setattr__(self, "role_authority", authority)
        object.__setattr__(self, "policy_answers", answers)


@dataclass(frozen=True)
class RoleCompilation:
    role: str
    selection: SelectionResult
    runtime_context: RuntimeBindingContext
    observation: CodexObservation
    compile_result: CodexCompileResult

    def __post_init__(self) -> None:
        _validate_identifier(self.role, "role compilation role")
        if not isinstance(self.selection, SelectionResult):
            raise TypeError("role compilation selection must be a SelectionResult")
        if not isinstance(self.runtime_context, RuntimeBindingContext):
            raise TypeError("role compilation context must be a RuntimeBindingContext")
        if not isinstance(self.observation, CodexObservation):
            raise TypeError("role compilation observation must be a CodexObservation")
        if not isinstance(self.compile_result, CodexCompileResult):
            raise TypeError("role compilation result must be a CodexCompileResult")


@dataclass(frozen=True)
class CandidateRolePlan:
    role: str
    requirement: Requirement
    selector_receipt: SelectorReceipt
    launch_spec: NativeLaunchSpec

    def __post_init__(self) -> None:
        _validate_identifier(self.role, "candidate role plan role")
        if not isinstance(self.requirement, Requirement):
            raise TypeError("candidate role plan requirement is invalid")
        if self.requirement.role != self.role:
            raise ValueError("candidate role plan requirement has the wrong role")
        if not isinstance(self.selector_receipt, SelectorReceipt):
            raise TypeError("candidate role plan selector receipt is invalid")
        if not isinstance(self.launch_spec, NativeLaunchSpec):
            raise TypeError("candidate role plan launch spec is invalid")
        if (
            self.selector_receipt.selected_binding_id
            != self.launch_spec.selected_binding_id
        ):
            raise ValueError("candidate selector and launch binding do not match")


@dataclass(frozen=True, order=True)
class ProvenanceRecord:
    subject: str
    kind: ProvenanceKind
    source: str
    source_digest: str | None = None

    def __post_init__(self) -> None:
        _validate_text(self.subject, "provenance subject", maximum=512)
        if not self.subject.startswith("/"):
            raise ValueError("provenance subject must be an absolute field pointer")
        if not isinstance(self.kind, ProvenanceKind):
            raise TypeError("provenance kind must be a ProvenanceKind")
        _validate_text(self.source, "provenance source", maximum=512)
        if self.source_digest is not None:
            _validate_digest(self.source_digest, "provenance source digest")


@dataclass(frozen=True)
class SetupCandidate:
    discovery: DiscoverySnapshot
    human_decisions: HumanDecisions
    compiled_policy: CompiledPolicy
    model_bindings: tuple[ModelBinding, ...]
    role_plans: tuple[CandidateRolePlan, ...]
    provenance: tuple[ProvenanceRecord, ...]
    candidate_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.discovery, DiscoverySnapshot):
            raise TypeError("candidate discovery must be a DiscoverySnapshot")
        if not isinstance(self.human_decisions, HumanDecisions):
            raise TypeError("candidate decisions must be HumanDecisions")
        if not isinstance(self.compiled_policy, CompiledPolicy):
            raise TypeError("candidate policy must be a CompiledPolicy")
        models = _ordered_unique(
            self.model_bindings,
            expected_type=ModelBinding,
            key=lambda item: item.role,
            label="candidate model bindings",
        )
        plans = _ordered_unique(
            self.role_plans,
            expected_type=CandidateRolePlan,
            key=lambda item: item.role,
            label="candidate role plans",
        )
        provenance = tuple(sorted(self.provenance, key=lambda item: item.subject))
        if any(not isinstance(item, ProvenanceRecord) for item in provenance):
            raise TypeError("candidate provenance contains an invalid value")
        subjects = tuple(item.subject for item in provenance)
        if len(subjects) != len(set(subjects)):
            raise ValueError("candidate provenance repeats a subject")
        object.__setattr__(self, "model_bindings", models)
        object.__setattr__(self, "role_plans", plans)
        object.__setattr__(self, "provenance", provenance)
        expected_policy = CompiledPolicy(
            native_agent_policy=self.human_decisions.native_agent_policy,
            role_authority=self.human_decisions.role_authority,
            policy_answers=self.human_decisions.policy_answers,
        )
        if self.compiled_policy != expected_policy:
            raise ValueError("candidate compiled policy does not match its decisions")
        if models != self.human_decisions.model_bindings:
            raise ValueError("candidate model bindings do not match its decisions")
        plan_roles = {plan.role for plan in plans}
        policy_by_role = {
            decision.role: decision.policy
            for decision in self.compiled_policy.role_authority
        }
        model_by_role = {binding.role: binding for binding in models}
        if plan_roles != set(policy_by_role) or plan_roles != set(model_by_role):
            raise ValueError("candidate role sets do not match")
        for plan in plans:
            effective = plan.launch_spec.effective_envelope.effective
            requirement = plan.requirement
            policy = policy_by_role[plan.role]
            model = model_by_role[plan.role]
            if (
                not requirement.must_have <= effective
                or effective & requirement.must_not_have
                or not effective <= requirement.ceiling
                or effective & policy.must_not_have
                or not effective <= policy.permitted
            ):
                raise ValueError("candidate role plan violates closed-world authority")
            if (
                plan.launch_spec.adapter_kind != model.harness
                or plan.launch_spec.model != model.model
                or plan.launch_spec.reasoning_effort != model.reasoning_effort
            ):
                raise ValueError("candidate role plan violates its model binding")
        object.__setattr__(
            self,
            "candidate_digest",
            _digest("herdr-setup-candidate", _candidate_projection(self)),
        )

    @property
    def discovery_digest(self) -> str:
        return self.discovery.discovery_digest

    @property
    def human_decisions_digest(self) -> str:
        return self.human_decisions.human_decisions_digest


class CandidateCompileStatus(str, Enum):
    COMPILED = "COMPILED"
    STATIC_INVALID = "STATIC_INVALID"
    CAPABILITY_INVALID = "CAPABILITY_INVALID"


class CandidateRejectionCode(str, Enum):
    LEAD_REQUIRED = "LEAD_REQUIRED"
    ROLE_SET_MISMATCH = "ROLE_SET_MISMATCH"
    ROLE_UNSUPPORTED = "ROLE_UNSUPPORTED"
    SELECTION_NOT_COMPLETE = "SELECTION_NOT_COMPLETE"
    REQUIREMENT_ROLE_MISMATCH = "REQUIREMENT_ROLE_MISMATCH"
    AUTHORITY_POLICY_MISMATCH = "AUTHORITY_POLICY_MISMATCH"
    BINDING_CHOICE_MISMATCH = "BINDING_CHOICE_MISMATCH"
    HARNESS_NOT_READY = "HARNESS_NOT_READY"
    ADAPTER_NOT_DISCOVERED = "ADAPTER_NOT_DISCOVERED"
    RUNTIME_OBSERVATION_STALE = "RUNTIME_OBSERVATION_STALE"
    MODEL_NOT_DISCOVERED = "MODEL_NOT_DISCOVERED"
    REASONING_EFFORT_UNSUPPORTED = "REASONING_EFFORT_UNSUPPORTED"
    MODEL_BINDING_MISMATCH = "MODEL_BINDING_MISMATCH"
    ROLE_COMPILE_NOT_COMPLETE = "ROLE_COMPILE_NOT_COMPLETE"
    ROLE_COMPILE_STATIC_INVALID = "ROLE_COMPILE_STATIC_INVALID"
    LAUNCH_SPEC_MISMATCH = "LAUNCH_SPEC_MISMATCH"
    NATIVE_AGENT_POLICY_UNSUPPORTED = "NATIVE_AGENT_POLICY_UNSUPPORTED"


@dataclass(frozen=True)
class CandidateRejection:
    code: CandidateRejectionCode
    role: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CandidateCompileResult:
    status: CandidateCompileStatus
    candidate: SetupCandidate | None
    rejections: tuple[CandidateRejection, ...]


def _candidate_status(rejections: Iterable[CandidateRejection]) -> CandidateCompileStatus:
    capability_codes = {
        CandidateRejectionCode.HARNESS_NOT_READY,
        CandidateRejectionCode.ADAPTER_NOT_DISCOVERED,
        CandidateRejectionCode.RUNTIME_OBSERVATION_STALE,
        CandidateRejectionCode.MODEL_NOT_DISCOVERED,
        CandidateRejectionCode.REASONING_EFFORT_UNSUPPORTED,
        CandidateRejectionCode.ROLE_COMPILE_NOT_COMPLETE,
        CandidateRejectionCode.NATIVE_AGENT_POLICY_UNSUPPORTED,
    }
    return (
        CandidateCompileStatus.CAPABILITY_INVALID
        if any(rejection.code in capability_codes for rejection in rejections)
        else CandidateCompileStatus.STATIC_INVALID
    )


def compile_setup_candidate(
    discovery: DiscoverySnapshot,
    human_decisions: HumanDecisions,
    role_compilations: Iterable[RoleCompilation],
) -> CandidateCompileResult:
    """Compile validated facts and Human choices into one immutable candidate."""

    if not isinstance(discovery, DiscoverySnapshot):
        raise TypeError("discovery must be a DiscoverySnapshot")
    if not isinstance(human_decisions, HumanDecisions):
        raise TypeError("human decisions must be HumanDecisions")
    compilations = _ordered_unique(
        role_compilations,
        expected_type=RoleCompilation,
        key=lambda item: item.role,
        label="role compilations",
    )
    authority_by_role = {
        decision.role: decision for decision in human_decisions.role_authority
    }
    model_by_role = {
        binding.role: binding for binding in human_decisions.model_bindings
    }
    choice_by_role = {
        choice.role: choice for choice in human_decisions.binding_choices
    }
    compilation_by_role = {item.role: item for item in compilations}
    role_sets = (
        set(authority_by_role),
        set(model_by_role),
        set(compilation_by_role),
    )
    rejections: list[CandidateRejection] = []
    all_roles = set().union(*role_sets)
    if "lead" not in all_roles:
        rejections.append(CandidateRejection(CandidateRejectionCode.LEAD_REQUIRED))
    if any(roles != all_roles for roles in role_sets):
        rejections.append(
            CandidateRejection(
                CandidateRejectionCode.ROLE_SET_MISMATCH,
                detail=",".join(sorted(all_roles)),
            )
        )
    for role in sorted(set(choice_by_role) - all_roles):
        rejections.append(
            CandidateRejection(
                CandidateRejectionCode.ROLE_SET_MISMATCH,
                role,
                "binding choice has no configured role",
            )
        )
    for role in sorted(all_roles - SUPPORTED_ROLES):
        rejections.append(
            CandidateRejection(CandidateRejectionCode.ROLE_UNSUPPORTED, role)
        )
    if human_decisions.native_agent_policy is not NativeAgentPolicy.DISABLED:
        rejections.append(
            CandidateRejection(CandidateRejectionCode.NATIVE_AGENT_POLICY_UNSUPPORTED)
        )
    if rejections:
        return CandidateCompileResult(_candidate_status(rejections), None, tuple(rejections))

    plans: list[CandidateRolePlan] = []
    harnesses = discovery.harness_map
    adapters = discovery.adapter_map
    for role in sorted(all_roles):
        authority = authority_by_role[role]
        model_binding = model_by_role[role]
        compilation = compilation_by_role[role]
        selection = compilation.selection
        if (
            selection.status is not SelectionStatus.SELECTED
            or selection.selected_binding is None
            or selection.selector_receipt is None
        ):
            rejections.append(
                CandidateRejection(CandidateRejectionCode.SELECTION_NOT_COMPLETE, role)
            )
            continue
        requirement = selection.eligibility.feasibility.requirement
        if requirement.role != role:
            rejections.append(
                CandidateRejection(CandidateRejectionCode.REQUIREMENT_ROLE_MISMATCH, role)
            )
        if selection.eligibility.policy != authority.policy:
            rejections.append(
                CandidateRejection(CandidateRejectionCode.AUTHORITY_POLICY_MISMATCH, role)
            )
        selected = selection.selected_binding
        if selected.adapter_kind != model_binding.harness:
            rejections.append(
                CandidateRejection(CandidateRejectionCode.MODEL_BINDING_MISMATCH, role)
            )
        choice = choice_by_role.get(role)
        selector = selection.selector_receipt.selector
        if (
            (selector == "explicit_binding" and (
                choice is None or choice.binding_id != selected.identifier
            ))
            or (selector != "explicit_binding" and choice is not None)
        ):
            rejections.append(
                CandidateRejection(CandidateRejectionCode.BINDING_CHOICE_MISMATCH, role)
            )

        harness = harnesses.get(model_binding.harness)
        if harness is None or harness.status is not HarnessStatus.READY:
            rejections.append(
                CandidateRejection(CandidateRejectionCode.HARNESS_NOT_READY, role)
            )
        if model_binding.harness not in adapters:
            rejections.append(
                CandidateRejection(CandidateRejectionCode.ADAPTER_NOT_DISCOVERED, role)
            )
        if harness is not None and harness.status is HarnessStatus.READY:
            discovered_model = harness.model_map.get(model_binding.model)
            if discovered_model is None:
                rejections.append(
                    CandidateRejection(CandidateRejectionCode.MODEL_NOT_DISCOVERED, role)
                )
            elif model_binding.reasoning_effort not in discovered_model.reasoning_efforts:
                rejections.append(
                    CandidateRejection(
                        CandidateRejectionCode.REASONING_EFFORT_UNSUPPORTED,
                        role,
                    )
                )
            normalized_observation = normalize_codex_harness(
                (compilation.observation,)
            )
            observed_runtime = harness.runtime_map.get(compilation.observation.bound_cwd)
            if (
                harness.executable != compilation.observation.executable
                or harness.version != str(compilation.observation.version)
                or harness.models != normalized_observation.models
                or observed_runtime != normalized_observation.runtimes[0]
            ):
                rejections.append(
                    CandidateRejection(
                        CandidateRejectionCode.RUNTIME_OBSERVATION_STALE,
                        role,
                    )
                )

        context = compilation.runtime_context
        if (
            context.model != model_binding.model
            or context.reasoning_effort != model_binding.reasoning_effort
            or context.cwd != compilation.observation.bound_cwd
        ):
            rejections.append(
                CandidateRejection(CandidateRejectionCode.MODEL_BINDING_MISMATCH, role)
            )
        compile_result = compilation.compile_result
        if (
            compile_result.status is not CodexCompileStatus.COMPILED
            or compile_result.launch_spec is None
        ):
            rejections.append(
                CandidateRejection(
                    (
                        CandidateRejectionCode.ROLE_COMPILE_STATIC_INVALID
                        if compile_result.status is CodexCompileStatus.STATIC_INVALID
                        else CandidateRejectionCode.ROLE_COMPILE_NOT_COMPLETE
                    ),
                    role,
                )
            )
            continue
        launch = compile_result.launch_spec
        if (
            launch.adapter_kind != model_binding.harness
            or launch.executable != compilation.observation.executable
            or launch.cwd != context.cwd
            or launch.model != model_binding.model
            or launch.reasoning_effort != model_binding.reasoning_effort
            or launch.native_agents_enabled
            or launch.network_enabled
            or launch.selected_binding_id != selected.identifier
            or launch.effective_envelope != selected.envelope
        ):
            rejections.append(
                CandidateRejection(CandidateRejectionCode.LAUNCH_SPEC_MISMATCH, role)
            )
            continue
        plans.append(
            CandidateRolePlan(
                role=role,
                requirement=requirement,
                selector_receipt=selection.selector_receipt,
                launch_spec=launch,
            )
        )

    if rejections:
        return CandidateCompileResult(_candidate_status(rejections), None, tuple(rejections))
    compiled_policy = CompiledPolicy(
        native_agent_policy=human_decisions.native_agent_policy,
        role_authority=human_decisions.role_authority,
        policy_answers=human_decisions.policy_answers,
    )
    provenance: list[ProvenanceRecord] = [
        ProvenanceRecord(
            "/discovery",
            ProvenanceKind.OBSERVED,
            discovery.project_root,
            discovery.discovery_digest,
        ),
        ProvenanceRecord(
            "/compiled_policy/native_agent_policy",
            ProvenanceKind.HUMAN_APPROVED,
            "human_decisions",
            human_decisions.human_decisions_digest,
        ),
    ]
    for index, repository in enumerate(discovery.repositories):
        provenance.append(
            ProvenanceRecord(
                f"/discovery/repositories/{index}",
                ProvenanceKind.OBSERVED,
                f"git:{repository.path}",
            )
        )
    for index, harness in enumerate(discovery.harnesses):
        provenance.append(
            ProvenanceRecord(
                f"/discovery/harnesses/{index}",
                ProvenanceKind.OBSERVED,
                harness.executable or f"harness_inventory:{harness.kind}",
            )
        )
    for index, adapter in enumerate(discovery.adapters):
        provenance.append(
            ProvenanceRecord(
                f"/discovery/adapters/{index}",
                ProvenanceKind.OBSERVED,
                f"adapter:{adapter.kind}",
                adapter.implementation_digest,
            )
        )
    for index, source in enumerate(discovery.policy_sources):
        provenance.append(
            ProvenanceRecord(
                f"/discovery/policy_sources/{index}",
                ProvenanceKind.OBSERVED,
                str(Path(discovery.project_root) / source.relative_path),
                source.sha256,
            )
        )
    for subject, observation in (
        ("existing_activation", discovery.existing_activation),
    ):
        provenance.append(
            ProvenanceRecord(
                f"/discovery/{subject}",
                ProvenanceKind.OBSERVED,
                str(Path(discovery.project_root) / observation.relative_path),
                observation.sha256,
            )
        )
    for answer in human_decisions.policy_answers:
        provenance.append(
            ProvenanceRecord(
                f"/compiled_policy/answers/{answer.identifier}",
                ProvenanceKind.HUMAN_APPROVED,
                "human_decisions",
                human_decisions.human_decisions_digest,
            )
        )
    for plan in plans:
        role = plan.role
        provenance.extend(
            (
                ProvenanceRecord(
                    f"/compiled_policy/roles/{role}",
                    ProvenanceKind.HUMAN_APPROVED,
                    "human_decisions",
                    human_decisions.human_decisions_digest,
                ),
                ProvenanceRecord(
                    f"/model_bindings/{role}",
                    ProvenanceKind.HUMAN_APPROVED,
                    "human_decisions",
                    human_decisions.human_decisions_digest,
                ),
                ProvenanceRecord(
                    f"/roles/{role}/requirement",
                    ProvenanceKind.INFERRED,
                    "herdr_role_requirement",
                ),
                ProvenanceRecord(
                    f"/roles/{role}/selected_binding",
                    (
                        ProvenanceKind.HUMAN_APPROVED
                        if plan.selector_receipt.selector == "explicit_binding"
                        else ProvenanceKind.INFERRED
                    ),
                    (
                        "human_decisions"
                        if plan.selector_receipt.selector == "explicit_binding"
                        else f"authority_solver:{plan.selector_receipt.selector}"
                    ),
                    (
                        human_decisions.human_decisions_digest
                        if plan.selector_receipt.selector == "explicit_binding"
                        else None
                    ),
                ),
                ProvenanceRecord(
                    f"/roles/{role}/native_launch_spec",
                    ProvenanceKind.INFERRED,
                    f"adapter:{plan.launch_spec.adapter_kind}",
                    adapters[plan.launch_spec.adapter_kind].implementation_digest,
                ),
            )
        )
    candidate = SetupCandidate(
        discovery=discovery,
        human_decisions=human_decisions,
        compiled_policy=compiled_policy,
        model_bindings=human_decisions.model_bindings,
        role_plans=tuple(plans),
        provenance=tuple(provenance),
    )
    return CandidateCompileResult(CandidateCompileStatus.COMPILED, candidate, ())


class FreshnessStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"


@dataclass(frozen=True)
class FreshnessReceipt:
    status: FreshnessStatus
    candidate_discovery_digest: str
    current_discovery_digest: str


def check_candidate_freshness(
    candidate: SetupCandidate,
    current_discovery: DiscoverySnapshot,
) -> FreshnessReceipt:
    """Invalidate the whole candidate when any discovery fact changes."""

    if not isinstance(candidate, SetupCandidate):
        raise TypeError("candidate must be a SetupCandidate")
    if not isinstance(current_discovery, DiscoverySnapshot):
        raise TypeError("current discovery must be a DiscoverySnapshot")
    status = (
        FreshnessStatus.CURRENT
        if candidate.discovery_digest == current_discovery.discovery_digest
        else FreshnessStatus.STALE
    )
    return FreshnessReceipt(
        status,
        candidate.discovery_digest,
        current_discovery.discovery_digest,
    )


def _capability_projection(capability: Capability) -> dict[str, object]:
    return {"name": capability.name, "resource": capability.resource}


def _authority_policy_projection(policy: AuthorityPolicy) -> dict[str, object]:
    return {
        "permitted": [
            _capability_projection(capability) for capability in sorted(policy.permitted)
        ],
        "must_not_have": [
            _capability_projection(capability)
            for capability in sorted(policy.must_not_have)
        ],
    }


def _requirement_projection(requirement: Requirement) -> dict[str, object]:
    def capabilities(values: Iterable[Capability]) -> list[dict[str, object]]:
        return [_capability_projection(capability) for capability in sorted(values)]

    return {
        "role": requirement.role,
        "must_have": capabilities(requirement.must_have),
        "must_not_have": capabilities(requirement.must_not_have),
        "may_have": capabilities(requirement.may_have),
    }


def _file_projection(observation: FileObservation) -> dict[str, object]:
    return {
        "relative_path": observation.relative_path,
        "exists": observation.exists,
        "size": observation.size,
        "sha256": observation.sha256,
    }


def _runtime_projection(runtime: HarnessRuntimeObservation) -> dict[str, object]:
    return {
        "cwd": runtime.cwd,
        "runtime_root": runtime.runtime_root,
        "capabilities": [
            {
                "name": capability.name,
                "available": capability.available,
                "assurance": capability.assurance.value,
            }
            for capability in runtime.capabilities
        ],
    }


def _harness_projection(harness: HarnessObservation) -> dict[str, object]:
    return {
        "kind": harness.kind,
        "status": harness.status.value,
        "executable": harness.executable,
        "version": harness.version,
        "models": [
            {
                "identifier": model.identifier,
                "reasoning_efforts": list(model.reasoning_efforts),
            }
            for model in harness.models
        ],
        "runtimes": [_runtime_projection(runtime) for runtime in harness.runtimes],
        "issue_codes": list(harness.issue_codes),
    }


def _discovery_projection(snapshot: DiscoverySnapshot) -> dict[str, object]:
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "project_root": snapshot.project_root,
        "repositories": [
            {
                "identifier": repository.identifier,
                "relative_path": repository.relative_path,
                "path": repository.path,
                "git_dir": repository.git_dir,
                "git_common_dir": repository.git_common_dir,
            }
            for repository in snapshot.repositories
        ],
        "harnesses": [_harness_projection(harness) for harness in snapshot.harnesses],
        "adapters": [
            {
                "kind": adapter.kind,
                "version": adapter.version,
                "implementation_digest": adapter.implementation_digest,
            }
            for adapter in snapshot.adapters
        ],
        "policy_sources": [
            _file_projection(source) for source in snapshot.policy_sources
        ],
        "existing_activation": _file_projection(snapshot.existing_activation),
    }


def _policy_answer_projection(answer: PolicyAnswer) -> dict[str, object]:
    return {
        "identifier": answer.identifier,
        "kind": answer.kind.value,
        "value": answer.value,
    }


def _model_binding_projection(binding: ModelBinding) -> dict[str, object]:
    return {
        "role": binding.role,
        "harness": binding.harness,
        "model": binding.model,
        "reasoning_effort": binding.reasoning_effort,
    }


def _human_decisions_projection(decisions: HumanDecisions) -> dict[str, object]:
    return {
        "native_agent_policy": decisions.native_agent_policy.value,
        "role_authority": [
            {
                "role": decision.role,
                "policy": _authority_policy_projection(decision.policy),
            }
            for decision in decisions.role_authority
        ],
        "model_bindings": [
            _model_binding_projection(binding) for binding in decisions.model_bindings
        ],
        "binding_choices": [
            {"role": choice.role, "binding_id": choice.binding_id}
            for choice in decisions.binding_choices
        ],
        "policy_answers": [
            _policy_answer_projection(answer) for answer in decisions.policy_answers
        ],
    }


def _launch_projection(launch: NativeLaunchSpec) -> dict[str, object]:
    return {
        "adapter_kind": launch.adapter_kind,
        "executable": launch.executable,
        "cwd": launch.cwd,
        "arguments": list(launch.arguments),
        "permission_profile": launch.permission_profile,
        "config_overrides": list(launch.config_overrides),
        "filesystem_rules": [
            {
                "resource": rule.resource,
                "path": rule.path,
                "access": rule.access,
            }
            for rule in launch.filesystem_rules
        ],
        "model": launch.model,
        "reasoning_effort": launch.reasoning_effort,
        "native_agents_enabled": launch.native_agents_enabled,
        "network_enabled": launch.network_enabled,
        "selected_binding_id": launch.selected_binding_id,
        "effective_envelope": [
            _capability_projection(capability)
            for capability in sorted(launch.effective_envelope.effective)
        ],
    }


def _compiled_policy_projection(policy: CompiledPolicy) -> dict[str, object]:
    return {
        "native_agent_policy": policy.native_agent_policy.value,
        "role_authority": [
            {
                "role": decision.role,
                "policy": _authority_policy_projection(decision.policy),
            }
            for decision in policy.role_authority
        ],
        "policy_answers": [
            _policy_answer_projection(answer) for answer in policy.policy_answers
        ],
    }


def _candidate_projection(candidate: SetupCandidate) -> dict[str, object]:
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "discovery": _discovery_projection(candidate.discovery),
        "discovery_digest": candidate.discovery_digest,
        "human_decisions": _human_decisions_projection(candidate.human_decisions),
        "human_decisions_digest": candidate.human_decisions_digest,
        "compiled_policy": _compiled_policy_projection(candidate.compiled_policy),
        "model_bindings": [
            _model_binding_projection(binding) for binding in candidate.model_bindings
        ],
        "roles": [
            {
                "role": plan.role,
                "requirement": _requirement_projection(plan.requirement),
                "selector_receipt": {
                    "selector": plan.selector_receipt.selector,
                    "selected_binding_id": plan.selector_receipt.selected_binding_id,
                    "considered_binding_ids": list(
                        plan.selector_receipt.considered_binding_ids
                    ),
                },
                "native_launch_spec": _launch_projection(plan.launch_spec),
            }
            for plan in candidate.role_plans
        ],
        "provenance": [
            {
                "subject": record.subject,
                "kind": record.kind.value,
                "source": record.source,
                "source_digest": record.source_digest,
            }
            for record in candidate.provenance
        ],
    }


def render_discovery_snapshot(snapshot: DiscoverySnapshot) -> bytes:
    """Render canonical snapshot JSON including its content-derived digest."""

    if not isinstance(snapshot, DiscoverySnapshot):
        raise TypeError("snapshot must be a DiscoverySnapshot")
    document = _discovery_projection(snapshot)
    document["discovery_digest"] = snapshot.discovery_digest
    return _canonical_bytes(document) + b"\n"


def render_setup_candidate(candidate: SetupCandidate) -> bytes:
    """Render canonical candidate JSON including its content-derived digest."""

    if not isinstance(candidate, SetupCandidate):
        raise TypeError("candidate must be a SetupCandidate")
    document = _candidate_projection(candidate)
    document["candidate_digest"] = candidate.candidate_digest
    return _canonical_bytes(document) + b"\n"
