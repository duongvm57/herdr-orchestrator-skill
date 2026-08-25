"""Stateful setup facade and pure Human-facing projection."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from .acceptance import (
    AcceptanceReceipt,
    AcceptanceStatus,
    SetupPublication,
    accept_setup_publication,
    compile_setup_publication,
    parse_acceptance_receipt,
    render_acceptance_receipt,
)
from .authority import (
    AuthorityEnvelope,
    AuthorityPolicy,
    Binding,
    Capability,
    EligibilityStatus,
    FeasibilityStatus,
    Requirement,
    SelectionStatus,
    evaluate_eligibility,
    select_binding,
    solve_feasibility,
)
from .candidate import (
    BindingChoice,
    CandidateCompileStatus,
    DecisionValueKind,
    DiscoverySnapshot,
    FileObservation,
    HarnessObservation,
    HarnessStatus,
    HumanDecisions,
    ModelBinding,
    NativeAgentPolicy,
    PolicyAnswer,
    RepositoryObservation,
    RoleAuthorityDecision,
    RoleCompilation,
    SetupCandidate,
    compile_setup_candidate,
    discover_setup,
    normalize_codex_harness,
    observe_codex_adapter,
)
from .codex_authority import (
    CodexObservation,
    CodexProbeResult,
    CodexProbeStatus,
    RuntimeBindingContext,
    RuntimePathBinding,
    compile_codex,
    probe_codex,
)
from .runtime_proof import (
    NativeCommandResult,
    RuntimeProofReceipt,
    RuntimeProofStatus,
    parse_runtime_proof,
    prove_candidate,
    render_runtime_proof,
)
from .harness_discovery import discover_unadapted_harnesses


SESSION_SCHEMA = "herdr.setup-session"
VIEW_SCHEMA = "herdr.setup-view"
SESSION_ROOT = ".orchestration/setup/sessions"
SESSION_MAX_BYTES = 8 * 1024 * 1024
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")

AUTHORITY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "lead": (
        "strong reasoning",
        "planning",
        "reliable tool use",
    ),
    "peer_writable": (
        "strong coding",
        "balanced reasoning",
        "assigned project write",
    ),
    "peer_readonly": (
        "strong critical reasoning",
        "code understanding",
        "project read and evidence write",
    ),
    "supervisor": (
        "strong observation",
        "strong reasoning",
    ),
}


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


def _validate_text(value: str, label: str, *, maximum: int = 4096) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be nonempty canonical text")
    if len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} is not bounded canonical text")


def _validate_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical identifier")


def _validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


class SetupStatus(str, Enum):
    UNSATISFIABLE = "UNSATISFIABLE"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    NEEDS_HUMAN_INPUT = "NEEDS_HUMAN_INPUT"
    STATIC_INVALID = "STATIC_INVALID"
    CAPABILITY_INVALID = "CAPABILITY_INVALID"
    SMOKE_FAILED = "SMOKE_FAILED"
    STALE = "STALE"
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"


class SetupAnswerKind(str, Enum):
    BOOLEAN = "BOOLEAN"
    CHOICE = "CHOICE"
    TEXT = "TEXT"


@dataclass(frozen=True)
class SetupOption:
    value: bool | str
    label: str
    facts: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if type(self.value) is not bool and not isinstance(self.value, str):
            raise TypeError("setup option value must be boolean or string")
        if isinstance(self.value, str):
            _validate_text(self.value, "setup option value", maximum=256)
        _validate_text(self.label, "setup option label", maximum=512)
        facts = tuple(sorted(self.facts))
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not all(isinstance(value, str) for value in item)
            for item in facts
        ):
            raise TypeError("setup option facts must be string pairs")
        if len(tuple(key for key, _ in facts)) != len({key for key, _ in facts}):
            raise ValueError("setup option repeats a fact")
        for key, value in facts:
            _validate_identifier(key, "setup option fact key")
            _validate_text(value, "setup option fact value", maximum=1024)
        object.__setattr__(self, "facts", facts)


@dataclass(frozen=True)
class SetupQuestion:
    identifier: str
    kind: SetupAnswerKind
    prompt: str
    reason: str
    options: tuple[SetupOption, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.identifier, "setup question identifier")
        if not isinstance(self.kind, SetupAnswerKind):
            raise TypeError("setup question kind is invalid")
        _validate_text(self.prompt, "setup question prompt", maximum=1024)
        _validate_text(self.reason, "setup question reason", maximum=2048)
        options = tuple(self.options)
        if any(not isinstance(option, SetupOption) for option in options):
            raise ValueError("setup question options are invalid")
        if self.kind is SetupAnswerKind.TEXT and options:
            raise ValueError("text setup question cannot prescribe options")
        if self.kind is not SetupAnswerKind.TEXT and not options:
            raise ValueError("boolean and choice setup questions require typed options")
        values = tuple(option.value for option in options)
        if len(values) != len(set(values)):
            raise ValueError("setup question repeats an option value")
        if self.kind is SetupAnswerKind.BOOLEAN and set(values) != {False, True}:
            raise ValueError("boolean setup question requires true and false options")
        if self.kind is SetupAnswerKind.CHOICE and any(
            not isinstance(value, str) for value in values
        ):
            raise ValueError("choice setup question requires string options")
        object.__setattr__(self, "options", options)


@dataclass(frozen=True, order=True)
class SetupTypedAnswer:
    identifier: str
    kind: SetupAnswerKind
    value: bool | str

    def __post_init__(self) -> None:
        _validate_identifier(self.identifier, "typed answer identifier")
        if not isinstance(self.kind, SetupAnswerKind):
            raise TypeError("typed answer kind is invalid")
        if self.kind is SetupAnswerKind.BOOLEAN:
            if type(self.value) is not bool:
                raise TypeError("boolean typed answer requires a boolean value")
        elif not isinstance(self.value, str):
            raise TypeError("textual typed answer requires a string value")
        else:
            _validate_text(self.value, "typed answer value", maximum=256)


@dataclass(frozen=True, order=True)
class SetupIssue:
    stage: str
    code: str
    role: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.stage, "setup issue stage")
        _validate_identifier(self.code.lower(), "setup issue code")
        if self.role is not None:
            _validate_identifier(self.role, "setup issue role")
        if self.detail is not None:
            _validate_text(self.detail, "setup issue detail", maximum=2048)


@dataclass(frozen=True, order=True)
class AuthorityRequirementView:
    template: str
    capability_profile: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.template, "authority requirement template")
        values = tuple(self.capability_profile)
        if not values or any(not isinstance(value, str) for value in values):
            raise ValueError("role requirement view requires capability labels")
        object.__setattr__(self, "capability_profile", values)


@dataclass(frozen=True, order=True)
class AuthorityBindingView:
    template: str
    harness: str
    model: str
    reasoning_effort: str
    cwd: str
    binding_id: str
    effective_authority: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.template, "authority binding template"),
            (self.harness, "role binding harness"),
            (self.reasoning_effort, "role binding effort"),
            (self.binding_id, "role binding identifier"),
        ):
            _validate_identifier(value, label)
        _validate_text(self.model, "role binding model", maximum=128)
        if not os.path.isabs(self.cwd) or os.path.normpath(self.cwd) != self.cwd:
            raise ValueError("role binding cwd must be an absolute normalized path")
        authority = tuple(sorted(self.effective_authority))
        if len(authority) != len(set(authority)):
            raise ValueError("role binding repeats effective authority")
        object.__setattr__(self, "effective_authority", authority)


@dataclass(frozen=True, order=True)
class HarnessInventoryView:
    kind: str
    status: str
    executable: str | None
    version: str | None
    models: tuple[str, ...]
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, order=True)
class RepositoryInventoryView:
    identifier: str
    relative_path: str
    path: str
    git_common_dir: str


@dataclass(frozen=True)
class SetupView:
    status: SetupStatus
    session_id: str
    revision: int
    project_root: str
    discovery_digest: str
    harnesses: tuple[HarnessInventoryView, ...]
    repositories: tuple[RepositoryInventoryView, ...]
    authority_requirements: tuple[AuthorityRequirementView, ...]
    questions: tuple[SetupQuestion, ...] = ()
    issues: tuple[SetupIssue, ...] = ()
    authority_bindings: tuple[AuthorityBindingView, ...] = ()
    candidate_digest: str | None = None
    runtime_proof_digest: str | None = None
    publication_digest: str | None = None
    acceptance_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SetupStatus):
            raise TypeError("setup view status is invalid")
        _validate_text(self.session_id, "setup view session identifier", maximum=8192)
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("setup view revision must be nonnegative")
        if not os.path.isabs(self.project_root):
            raise ValueError("setup view project root must be absolute")
        _validate_digest(self.discovery_digest, "setup view discovery digest")
        for value, label in (
            (self.candidate_digest, "setup view candidate digest"),
            (self.runtime_proof_digest, "setup view proof digest"),
            (self.publication_digest, "setup view publication digest"),
            (self.acceptance_receipt_digest, "setup view acceptance digest"),
        ):
            if value is not None:
                _validate_digest(value, label)
        if any(not isinstance(item, AuthorityRequirementView) for item in self.authority_requirements):
            raise TypeError("setup view authority requirements are invalid")
        if any(not isinstance(item, HarnessInventoryView) for item in self.harnesses):
            raise TypeError("setup view harness inventory is invalid")
        if any(not isinstance(item, RepositoryInventoryView) for item in self.repositories):
            raise TypeError("setup view repository inventory is invalid")
        if any(not isinstance(item, SetupQuestion) for item in self.questions):
            raise TypeError("setup view questions are invalid")
        if any(not isinstance(item, SetupIssue) for item in self.issues):
            raise TypeError("setup view issues are invalid")
        if any(not isinstance(item, AuthorityBindingView) for item in self.authority_bindings):
            raise TypeError("setup view authority bindings are invalid")


class SetupEngineError(RuntimeError):
    """Base class for bounded setup-engine failures."""


class SetupStateError(SetupEngineError):
    """The project-local session store is unsafe or malformed."""


class SetupRevisionConflict(SetupEngineError):
    def __init__(self, view: SetupView) -> None:
        self.view = view
        super().__init__("setup revision no longer matches")


class SetupAnswerError(SetupEngineError):
    def __init__(self, message: str, view: SetupView) -> None:
        self.view = view
        super().__init__(message)


class SetupTransitionError(SetupEngineError):
    def __init__(self, message: str, view: SetupView) -> None:
        self.view = view
        super().__init__(message)


@dataclass(frozen=True)
class _SessionState:
    session_id: str
    revision: int
    project_root: str
    discovery_digest: str
    initial_activation: FileObservation
    initial_workspace_protocol: FileObservation
    answers: tuple[SetupTypedAnswer, ...] = ()
    runtime_proof: bytes | None = field(default=None, repr=False)
    acceptance_receipt: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if _project_root_from_session_id(self.session_id) != self.project_root:
            raise ValueError("session identifier does not bind its project root")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("session revision must be nonnegative")
        _validate_digest(self.discovery_digest, "session discovery digest")
        if not isinstance(self.initial_activation, FileObservation):
            raise TypeError("session activation observation is invalid")
        if not isinstance(self.initial_workspace_protocol, FileObservation):
            raise TypeError("session Workspace Protocol observation is invalid")
        answers = tuple(sorted(self.answers, key=lambda answer: answer.identifier))
        if any(not isinstance(answer, SetupTypedAnswer) for answer in answers):
            raise TypeError("session answers are invalid")
        identifiers = tuple(answer.identifier for answer in answers)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("session repeats a typed answer")
        object.__setattr__(self, "answers", answers)
        if self.runtime_proof is not None:
            parse_runtime_proof(self.runtime_proof)
        if self.acceptance_receipt is not None:
            if self.runtime_proof is None:
                raise ValueError("accepted session requires runtime proof")
            parse_acceptance_receipt(self.acceptance_receipt)


@dataclass(frozen=True)
class _DiscoveryOutcome:
    snapshot: DiscoverySnapshot
    observations: tuple[CodexObservation, ...]
    status: SetupStatus | None
    issues: tuple[SetupIssue, ...]

    @property
    def observation_map(self) -> dict[str, CodexObservation]:
        return {observation.bound_cwd: observation for observation in self.observations}


@dataclass(frozen=True)
class _Evaluation:
    status: SetupStatus
    discovery: DiscoverySnapshot
    questions: tuple[SetupQuestion, ...]
    issues: tuple[SetupIssue, ...]
    candidate: SetupCandidate | None = None
    proof: RuntimeProofReceipt | None = None
    publication: SetupPublication | None = None
    acceptance: AcceptanceReceipt | None = None


def _session_id(project_root: str) -> str:
    encoded = base64.urlsafe_b64encode(project_root.encode("utf-8")).decode("ascii").rstrip("=")
    checksum = _digest("herdr-setup-session-root", project_root)
    return f"s1.{encoded}.{checksum[:24]}"


def _project_root_from_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or len(session_id) > 8192:
        raise ValueError("setup session identifier is invalid")
    parts = session_id.split(".")
    if len(parts) != 3 or parts[0] != "s1" or not parts[1]:
        raise ValueError("setup session identifier is invalid")
    try:
        padding = "=" * (-len(parts[1]) % 4)
        project_root = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("setup session identifier is invalid") from exc
    if (
        not os.path.isabs(project_root)
        or os.path.normpath(project_root) != project_root
        or _digest("herdr-setup-session-root", project_root)[:24] != parts[2]
    ):
        raise ValueError("setup session identifier checksum is invalid")
    return project_root


def _file_projection(observation: FileObservation) -> dict[str, object]:
    return {
        "relative_path": observation.relative_path,
        "exists": observation.exists,
        "size": observation.size,
        "sha256": observation.sha256,
    }


def _answer_projection(answer: SetupTypedAnswer) -> dict[str, object]:
    return {
        "identifier": answer.identifier,
        "kind": answer.kind.value,
        "value": answer.value,
    }


def _state_projection(state: _SessionState) -> dict[str, object]:
    return {
        "schema": SESSION_SCHEMA,
        "session_id": state.session_id,
        "revision": state.revision,
        "project_root": state.project_root,
        "discovery_digest": state.discovery_digest,
        "initial_activation": _file_projection(state.initial_activation),
        "initial_workspace_protocol": _file_projection(state.initial_workspace_protocol),
        "answers": [_answer_projection(answer) for answer in state.answers],
        "runtime_proof": (
            None if state.runtime_proof is None else json.loads(state.runtime_proof)
        ),
        "acceptance_receipt": (
            None
            if state.acceptance_receipt is None
            else json.loads(state.acceptance_receipt)
        ),
    }


def _render_state(state: _SessionState) -> bytes:
    document = _state_projection(state)
    document["session_digest"] = _digest("herdr-setup-session", document)
    return _canonical_bytes(document) + b"\n"


def _parse_state(payload: bytes) -> _SessionState:
    if len(payload) > SESSION_MAX_BYTES:
        raise SetupStateError("setup session exceeds the bounded size")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SetupStateError("setup session is not valid JSON") from exc
    expected = {
        "schema",
        "session_id",
        "revision",
        "project_root",
        "discovery_digest",
        "initial_activation",
        "initial_workspace_protocol",
        "answers",
        "runtime_proof",
        "acceptance_receipt",
        "session_digest",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise SetupStateError("setup session has the wrong fields")
    digest = document.pop("session_digest")
    if document.get("schema") != SESSION_SCHEMA or digest != _digest(
        "herdr-setup-session", document
    ):
        raise SetupStateError("setup session digest does not match its content")
    activation = document["initial_activation"]
    if not isinstance(activation, dict) or set(activation) != {
        "relative_path",
        "exists",
        "size",
        "sha256",
    }:
        raise SetupStateError("setup session activation observation is invalid")
    protocol = document["initial_workspace_protocol"]
    if not isinstance(protocol, dict) or set(protocol) != {
        "relative_path", "exists", "size", "sha256"
    }:
        raise SetupStateError("setup session Workspace Protocol observation is invalid")
    answers_document = document["answers"]
    if not isinstance(answers_document, list):
        raise SetupStateError("setup session answers are invalid")
    try:
        answers = tuple(
            SetupTypedAnswer(
                identifier=answer["identifier"],
                kind=SetupAnswerKind(answer["kind"]),
                value=answer["value"],
            )
            for answer in answers_document
            if isinstance(answer, dict)
            and set(answer) == {"identifier", "kind", "value"}
        )
        if len(answers) != len(answers_document):
            raise ValueError("answer fields")
        proof = (
            None
            if document["runtime_proof"] is None
            else _canonical_bytes(document["runtime_proof"]) + b"\n"
        )
        acceptance = (
            None
            if document["acceptance_receipt"] is None
            else _canonical_bytes(document["acceptance_receipt"]) + b"\n"
        )
        state = _SessionState(
            session_id=document["session_id"],
            revision=document["revision"],
            project_root=document["project_root"],
            discovery_digest=document["discovery_digest"],
            initial_activation=FileObservation(
                relative_path=activation["relative_path"],
                exists=activation["exists"],
                size=activation["size"],
                sha256=activation["sha256"],
            ),
            initial_workspace_protocol=FileObservation(
                relative_path=protocol["relative_path"],
                exists=protocol["exists"],
                size=protocol["size"],
                sha256=protocol["sha256"],
            ),
            answers=answers,
            runtime_proof=proof,
            acceptance_receipt=acceptance,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SetupStateError("setup session contains invalid values") from exc
    if _render_state(state) != payload:
        raise SetupStateError("setup session is not canonical")
    return state


def _safe_directory(root: Path, relative_parts: tuple[str, ...]) -> Path:
    current = root
    for part in relative_parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            try:
                os.mkdir(current, 0o700)
            except FileExistsError:
                metadata = os.lstat(current)
            else:
                metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SetupStateError(f"setup control path is not a safe directory: {current}")
    return current


def _session_paths(project_root: Path, session_id: str) -> tuple[Path, Path, Path]:
    sessions = _safe_directory(
        project_root,
        (".orchestration", "setup", "sessions"),
    )
    token = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return sessions, sessions / f"{token}.json", sessions / f"{token}.lock"


def _open_no_follow(path: Path, flags: int, mode: int = 0o600) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags | no_follow, mode)
    except OSError as exc:
        raise SetupStateError(f"cannot safely open setup session path: {path}") from exc


def _open_session_lock(path: Path) -> int:
    descriptor = _open_no_follow(path, os.O_RDWR | os.O_CREAT)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise SetupStateError("setup session lock is not a regular file")
    return descriptor


def _read_state(path: Path) -> _SessionState | None:
    try:
        descriptor = _open_no_follow(path, os.O_RDONLY)
    except SetupStateError as exc:
        if not path.exists() and not path.is_symlink():
            return None
        raise exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > SESSION_MAX_BYTES:
            raise SetupStateError("setup session is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = SESSION_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > SESSION_MAX_BYTES:
            raise SetupStateError("setup session exceeds the bounded size")
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(after) != identity(metadata):
            raise SetupStateError("setup session changed while being read")
    finally:
        os.close(descriptor)
    return _parse_state(payload)


def _write_state(sessions: Path, path: Path, state: _SessionState) -> None:
    payload = _render_state(state)
    if len(payload) > SESSION_MAX_BYTES:
        raise SetupStateError("setup session exceeds the bounded size")
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SetupStateError("setup session target is not a regular file")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".session-",
        suffix=".tmp",
        dir=sessions,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_descriptor = os.open(sessions, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise SetupStateError("failed to atomically persist setup session") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _option_projection(option: SetupOption) -> dict[str, object]:
    return {
        "value": option.value,
        "label": option.label,
        "facts": {key: value for key, value in option.facts},
    }


def _question_projection(question: SetupQuestion) -> dict[str, object]:
    return {
        "id": question.identifier,
        "kind": question.kind.value,
        "prompt": question.prompt,
        "reason": question.reason,
        "options": [_option_projection(option) for option in question.options],
    }


def _authority_binding_projection(binding: AuthorityBindingView) -> dict[str, object]:
    return {
        "template": binding.template,
        "harness": binding.harness,
        "model": binding.model,
        "reasoning_effort": binding.reasoning_effort,
        "cwd": binding.cwd,
        "binding_id": binding.binding_id,
        "effective_authority": list(binding.effective_authority),
    }


def _view_projection(view: SetupView) -> dict[str, object]:
    return {
        "schema": VIEW_SCHEMA,
        "status": view.status.value,
        "session_id": view.session_id,
        "revision": view.revision,
        "project_root": view.project_root,
        "discovery_digest": view.discovery_digest,
        "harnesses": [
            {
                "kind": item.kind,
                "status": item.status,
                "executable": item.executable,
                "version": item.version,
                "models": list(item.models),
                "issue_codes": list(item.issue_codes),
            }
            for item in view.harnesses
        ],
        "repositories": [
            {
                "identifier": item.identifier,
                "relative_path": item.relative_path,
                "path": item.path,
                "git_common_dir": item.git_common_dir,
            }
            for item in view.repositories
        ],
        "authority_requirements": [
            {
                "template": requirement.template,
                "capability_profile": list(requirement.capability_profile),
            }
            for requirement in view.authority_requirements
        ],
        "questions": [_question_projection(question) for question in view.questions],
        "issues": [
            {
                "stage": issue.stage,
                "code": issue.code,
                "role": issue.role,
                "detail": issue.detail,
            }
            for issue in view.issues
        ],
        "authority_bindings": [
            _authority_binding_projection(binding) for binding in view.authority_bindings
        ],
        "candidate_digest": view.candidate_digest,
        "runtime_proof_digest": view.runtime_proof_digest,
        "publication_digest": view.publication_digest,
        "acceptance_receipt_digest": view.acceptance_receipt_digest,
    }


def render_setup_view(view: SetupView) -> bytes:
    """Render the exact engine projection consumed by a thin presenter."""

    if not isinstance(view, SetupView):
        raise TypeError("setup view must be a SetupView")
    return _canonical_bytes(_view_projection(view)) + b"\n"


def _capability_label(capability: Capability) -> str:
    return (
        capability.name
        if capability.resource is None
        else f"{capability.name}({capability.resource})"
    )


def _project_setup_view(state: _SessionState, evaluation: _Evaluation) -> SetupView:
    """Purely project engine state; never discover, decide, prove, or write."""

    role_names = (
        tuple(plan.role for plan in evaluation.candidate.role_plans)
        if evaluation.candidate is not None
        else _selected_roles({answer.identifier: answer for answer in state.answers})
    )
    if not role_names:
        role_names = ("lead", "peer_writable", "peer_readonly", "supervisor")
    requirements = tuple(
        AuthorityRequirementView(role, AUTHORITY_TEMPLATES[role])
        for role in sorted(role_names)
    )
    bindings: tuple[AuthorityBindingView, ...] = ()
    if evaluation.candidate is not None:
        bindings = tuple(
            AuthorityBindingView(
                template=plan.role,
                harness=plan.launch_spec.adapter_kind,
                model=plan.launch_spec.model,
                reasoning_effort=plan.launch_spec.reasoning_effort,
                cwd=plan.launch_spec.cwd,
                binding_id=plan.launch_spec.selected_binding_id,
                effective_authority=tuple(
                    _capability_label(capability)
                    for capability in plan.launch_spec.effective_envelope.effective
                ),
            )
            for plan in evaluation.candidate.role_plans
        )
    return SetupView(
        status=evaluation.status,
        session_id=state.session_id,
        revision=state.revision,
        project_root=state.project_root,
        discovery_digest=state.discovery_digest,
        harnesses=tuple(
            HarnessInventoryView(
                item.kind,
                item.status.value,
                item.executable,
                item.version,
                tuple(model.identifier for model in item.models),
                item.issue_codes,
            )
            for item in evaluation.discovery.harnesses
        ),
        repositories=tuple(
            RepositoryInventoryView(
                item.identifier,
                item.relative_path,
                item.path,
                item.git_common_dir,
            )
            for item in evaluation.discovery.repositories
        ),
        authority_requirements=requirements,
        questions=evaluation.questions,
        issues=evaluation.issues,
        authority_bindings=bindings,
        candidate_digest=(
            None
            if evaluation.candidate is None
            else evaluation.candidate.candidate_digest
        ),
        runtime_proof_digest=(
            None if evaluation.proof is None else evaluation.proof.receipt_digest
        ),
        publication_digest=(
            None
            if evaluation.publication is None
            else evaluation.publication.publication_digest
        ),
        acceptance_receipt_digest=(
            None
            if evaluation.acceptance is None
            else evaluation.acceptance.receipt_digest
        ),
    )


def _answer_map(state: _SessionState) -> dict[str, SetupTypedAnswer]:
    return {answer.identifier: answer for answer in state.answers}


def _choice_question(
    identifier: str,
    prompt: str,
    reason: str,
    options: Iterable[SetupOption],
) -> SetupQuestion:
    return SetupQuestion(
        identifier,
        SetupAnswerKind.CHOICE,
        prompt,
        reason,
        tuple(options),
    )


def _boolean_question(
    identifier: str,
    prompt: str,
    reason: str,
) -> SetupQuestion:
    return SetupQuestion(
        identifier,
        SetupAnswerKind.BOOLEAN,
        prompt,
        reason,
        (
            SetupOption(False, "Deny"),
            SetupOption(True, "Grant"),
        ),
    )


def _text_question(
    identifier: str,
    prompt: str,
    reason: str,
) -> SetupQuestion:
    return SetupQuestion(
        identifier,
        SetupAnswerKind.TEXT,
        prompt,
        reason,
        (),
    )


def _model_option_value(harness: str, model: str, effort: str) -> str:
    return "binding-" + _digest(
        "herdr-setup-model-option",
        {"harness": harness, "model": model, "reasoning_effort": effort},
    )[:24]


def _model_options(snapshot: DiscoverySnapshot) -> tuple[SetupOption, ...]:
    return tuple(
        SetupOption(
            _model_option_value(harness.kind, model.identifier, effort),
            f"{harness.kind} / {model.identifier} / {effort}",
            (
                ("harness", harness.kind),
                ("model", model.identifier),
                ("reasoning_effort", effort),
            ),
        )
        for harness in snapshot.harnesses
        if harness.status is HarnessStatus.READY
        and harness.kind in snapshot.adapter_map
        for model in harness.models
        for effort in model.reasoning_efforts
    )


def _selected_roles(answers: dict[str, SetupTypedAnswer]) -> tuple[str, ...]:
    """Return proof templates once every project preference is resolved.

    These are authority templates, not durable orchestration roles. Both Peer
    templates share the one Human-selected Peer model binding.
    """

    required = {
        "binding.lead",
        "binding.peer",
        "binding.supervisor",
        "binding.fallback",
        "policy.live_language",
        "policy.artifact_language",
    }
    if not required <= set(answers):
        return ()
    return ("lead", "peer_writable", "peer_readonly", "supervisor")


def _setup_questions(
    snapshot: DiscoverySnapshot,
    answers: dict[str, SetupTypedAnswer],
) -> tuple[SetupQuestion, ...]:
    model_options = _model_options(snapshot)
    questions: list[SetupQuestion] = [
        _choice_question(
            "binding.lead",
            "Choose the default harness, model, and reasoning effort for Lead.",
            "Requirement: strong reasoning, planning, and reliable tool use. Options are observed, not ranked.",
            model_options,
        ),
        _choice_question(
            "binding.peer",
            "Choose the default harness, model, and reasoning effort for Peer.",
            "Lead may override this at runtime from the accepted live inventory. Options are observed, not ranked.",
            model_options,
        ),
        _choice_question(
            "binding.supervisor",
            "Choose the project default harness, model, and reasoning effort for Supervisor.",
            "This stores a project preference; setup does not create or attach a Supervisor. Options are observed, not ranked.",
            model_options,
        ),
        _choice_question(
            "binding.fallback",
            "Choose the global fallback harness, model, and reasoning effort.",
            "The fallback routes an ad-hoc Peer disposition only; it grants no authority. Options are observed, not ranked.",
            model_options,
        ),
        _text_question(
            "policy.live_language",
            "Which language should live orchestration messages use?",
            "The runtime delivery envelope uses this exact Human-selected language.",
        ),
        _text_question(
            "policy.artifact_language",
            "Which language should generated durable Markdown artifacts use?",
            "The runtime records this exact Human-selected artifact language.",
        ),
    ]
    return tuple(
        question for question in questions if question.identifier not in answers
    )


def _action_question(
    identifier: str,
    value: str,
    prompt: str,
    reason: str,
) -> SetupQuestion:
    return _choice_question(
        identifier,
        prompt,
        reason,
        (SetupOption(value, value.replace("_", " ").title()),),
    )


def _bounded_detail(value: str | None) -> str | None:
    if not value:
        return None
    return "detail_sha256=" + hashlib.sha256(
        value.encode("utf-8", errors="replace")
    ).hexdigest()


def _selected_repository(
    snapshot: DiscoverySnapshot,
    answers: dict[str, SetupTypedAnswer],
) -> RepositoryObservation:
    del answers
    return next(
        (repository for repository in snapshot.repositories if repository.relative_path == "."),
        snapshot.repositories[0],
    )


def _model_choice(
    snapshot: DiscoverySnapshot,
    role: str,
    answers: dict[str, SetupTypedAnswer],
) -> tuple[str, str, str]:
    answer_id = {
        "lead": "binding.lead",
        "peer_writable": "binding.peer",
        "peer_readonly": "binding.peer",
        "supervisor": "binding.supervisor",
    }[role]
    answer = answers.get(answer_id)
    if answer is None or not isinstance(answer.value, str):
        raise ValueError(f"model binding for {role} is unresolved")
    option = next(
        (
            option
            for option in _model_options(snapshot)
            if option.value == answer.value
        ),
        None,
    )
    if option is None:
        raise ValueError(f"model binding for {role} is no longer discovered")
    facts = dict(option.facts)
    return facts["harness"], facts["model"], facts["reasoning_effort"]


def _contains(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


def _role_authority(
    role: str,
    repository: RepositoryObservation,
    project_root: Path,
    answers: dict[str, SetupTypedAnswer],
) -> tuple[Requirement, AuthorityPolicy, tuple[RuntimePathBinding, ...]]:
    runtime = Capability("fs.read", "runtime:codex")
    read_project = Capability("fs.read", "project:assigned")
    write_project = Capability("fs.write", "project:assigned")
    read_git = Capability("fs.read", "git-common:assigned")
    write_git = Capability("fs.write", "git-common:assigned")
    native_spawn = Capability("native_spawn")
    network = Capability("network.egress")
    effective: set[Capability] = {runtime, read_project}
    forbidden: set[Capability] = {native_spawn, network}
    resources: list[RuntimePathBinding] = [
        RuntimePathBinding("project:assigned", repository.path),
    ]
    state_root = project_root / ".orchestration/setup/role-state"
    orchestration_root = project_root / ".orchestration"

    if role == "lead":
        effective.add(read_git)
        resources.append(
            RuntimePathBinding("git-common:assigned", repository.git_common_dir)
        )
        control = state_root / "lead"
        effective.update(
            {
                Capability("fs.read", "control:run"),
                Capability("fs.write", "control:run"),
            }
        )
        resources.append(RuntimePathBinding("control:run", str(control)))
        effective.update({write_project, write_git})
        if _contains(Path(repository.path), orchestration_root):
            effective.add(Capability("fs.read", "orchestration:control"))
            resources.append(RuntimePathBinding("orchestration:control", str(orchestration_root)))
    elif role == "peer_writable":
        evidence = state_root / "peer_writable"
        effective.update(
            {
                write_project,
                read_git,
                Capability("fs.read", "evidence:assignment"),
                Capability("fs.write", "evidence:assignment"),
            }
        )
        resources.append(
            RuntimePathBinding("git-common:assigned", repository.git_common_dir)
        )
        resources.append(RuntimePathBinding("evidence:assignment", str(evidence)))
        if _contains(Path(repository.path), orchestration_root):
            effective.add(Capability("fs.read", "orchestration:control"))
            resources.append(
                RuntimePathBinding(
                    "orchestration:control",
                    str(orchestration_root),
                )
            )
        effective.add(write_git)
    elif role == "peer_readonly":
        evidence = state_root / "peer_readonly"
        effective.update(
            {
                read_git,
                Capability("fs.read", "evidence:assignment"),
                Capability("fs.write", "evidence:assignment"),
            }
        )
        resources.append(
            RuntimePathBinding("git-common:assigned", repository.git_common_dir)
        )
        resources.append(RuntimePathBinding("evidence:assignment", str(evidence)))
        forbidden.add(write_project)
        forbidden.add(write_git)
    elif role == "supervisor":
        notebook = state_root / "supervisor"
        effective.update(
            {
                Capability("fs.read", "notebook:session"),
                Capability("fs.write", "notebook:session"),
            }
        )
        resources.append(RuntimePathBinding("notebook:session", str(notebook)))
        forbidden.add(write_project)
    else:
        raise ValueError(f"unsupported role: {role}")

    envelope = frozenset(effective)
    return (
        Requirement(
            role=role,
            must_have=envelope,
            must_not_have=frozenset(forbidden - effective),
            may_have=frozenset(),
        ),
        AuthorityPolicy(
            permitted=envelope,
            must_not_have=frozenset(forbidden - effective),
        ),
        tuple(resources),
    )


def _human_policy_answers(
    snapshot: DiscoverySnapshot,
    answers: dict[str, SetupTypedAnswer],
) -> tuple[PolicyAnswer, ...]:
    values: list[PolicyAnswer] = []
    for identifier in sorted(answers):
        if identifier.startswith("model."):
            continue
        answer = answers[identifier]
        values.append(
            PolicyAnswer(
                identifier=identifier,
                kind=DecisionValueKind(answer.kind.value),
                value=answer.value,
            )
        )
    for profile in ("lead", "peer", "supervisor", "fallback"):
        answer = answers.get(f"binding.{profile}")
        if answer is None or not isinstance(answer.value, str):
            continue
        option = next(
            (item for item in _model_options(snapshot) if item.value == answer.value),
            None,
        )
        if option is None:
            continue
        for key, value in option.facts:
            values.append(
                PolicyAnswer(
                    f"route.{profile}.{key}",
                    DecisionValueKind.CHOICE,
                    value,
                )
            )
    return tuple(values)


def _build_candidate(
    snapshot: DiscoverySnapshot,
    observations: dict[str, CodexObservation],
    project_root: Path,
    answers: dict[str, SetupTypedAnswer],
) -> tuple[SetupStatus, SetupCandidate | None, tuple[SetupIssue, ...]]:
    roles = _selected_roles(answers)
    if not roles:
        return (
            SetupStatus.STATIC_INVALID,
            None,
            (SetupIssue("candidate", "ROLE_PROFILE_INVALID"),),
        )
    repository = _selected_repository(snapshot, answers)
    observation = observations.get(repository.path)
    if observation is None:
        return (
            SetupStatus.CAPABILITY_INVALID,
            None,
            (
                SetupIssue(
                    "capability",
                    "RUNTIME_OBSERVATION_MISSING",
                    detail=repository.relative_path,
                ),
            ),
        )
    compilations: list[RoleCompilation] = []
    authority_decisions: list[RoleAuthorityDecision] = []
    model_bindings: list[ModelBinding] = []
    binding_choices: list[BindingChoice] = []
    for role in roles:
        requirement, policy, resources = _role_authority(
            role,
            repository,
            project_root,
            answers,
        )
        harness, model, effort = _model_choice(snapshot, role, answers)
        binding = Binding(
            "codex-" + role + "-" + _digest(
                "herdr-setup-role-binding",
                {"role": role, "repository": repository.identifier},
            )[:16],
            "codex",
            AuthorityEnvelope(requirement.must_have),
        )
        feasibility = solve_feasibility(requirement, (binding,))
        if feasibility.status is FeasibilityStatus.UNSATISFIABLE:
            return (
                SetupStatus.UNSATISFIABLE,
                None,
                (SetupIssue("feasibility", "NO_FEASIBLE_BINDING", role),),
            )
        eligibility = evaluate_eligibility(feasibility, policy)
        if eligibility.status is EligibilityStatus.POLICY_CONFLICT:
            return (
                SetupStatus.POLICY_CONFLICT,
                None,
                (SetupIssue("eligibility", "NO_ELIGIBLE_BINDING", role),),
            )
        selection = select_binding(eligibility)
        if selection.status is not SelectionStatus.SELECTED:
            return (
                (
                    SetupStatus.NEEDS_HUMAN_INPUT
                    if selection.status is SelectionStatus.NEEDS_HUMAN_INPUT
                    else SetupStatus.POLICY_CONFLICT
                ),
                None,
                (SetupIssue("selection", "BINDING_NOT_SELECTED", role),),
            )
        context = RuntimeBindingContext(
            cwd=repository.path,
            resources=resources,
            model=model,
            reasoning_effort=effort,
        )
        compiled = compile_codex(selection, context, observation)
        compilations.append(
            RoleCompilation(role, selection, context, observation, compiled)
        )
        authority_decisions.append(RoleAuthorityDecision(role, policy))
        model_bindings.append(ModelBinding(role, harness, model, effort))
        if (
            selection.selector_receipt is not None
            and selection.selector_receipt.selector == "explicit_binding"
        ):
            binding_choices.append(BindingChoice(role, binding.identifier))
    decisions = HumanDecisions(
        native_agent_policy=NativeAgentPolicy.DISABLED,
        role_authority=tuple(authority_decisions),
        model_bindings=tuple(model_bindings),
        binding_choices=tuple(binding_choices),
        policy_answers=_human_policy_answers(snapshot, answers),
    )
    result = compile_setup_candidate(snapshot, decisions, compilations)
    if result.status is CandidateCompileStatus.COMPILED:
        assert result.candidate is not None
        return SetupStatus.AWAITING_ACCEPTANCE, result.candidate, ()
    status = (
        SetupStatus.CAPABILITY_INVALID
        if result.status is CandidateCompileStatus.CAPABILITY_INVALID
        else SetupStatus.STATIC_INVALID
    )
    return (
        status,
        None,
        tuple(
            SetupIssue(
                "candidate",
                rejection.code.value,
                rejection.role,
                rejection.detail,
            )
            for rejection in result.rejections
        ),
    )


def _ensure_role_state(project_root: Path, roles: Iterable[str]) -> None:
    root = _safe_directory(
        project_root,
        (".orchestration", "setup", "role-state"),
    )
    for role in roles:
        if role in AUTHORITY_TEMPLATES:
            _safe_directory(root, (role,))


def _issue_from_probe(
    code: str,
    detail: str | None = None,
) -> SetupIssue:
    return SetupIssue("capability", code, detail=_bounded_detail(detail))


def _discovery_with_codex(
    project_root: str,
    executable: str | None,
    probe: Callable[..., CodexProbeResult],
) -> _DiscoveryOutcome:
    adapter = observe_codex_adapter()
    other_harnesses = discover_unadapted_harnesses(excluded=("codex",))
    preliminary = discover_setup(
        project_root,
        harnesses=(HarnessObservation("codex", HarnessStatus.NOT_INSTALLED), *other_harnesses),
        adapters=(adapter,),
    )
    if executable is None:
        harness = HarnessObservation("codex", HarnessStatus.NOT_INSTALLED)
        snapshot = discover_setup(
            project_root,
            harnesses=(harness, *other_harnesses),
            adapters=(adapter,),
        )
        return _DiscoveryOutcome(
            snapshot,
            (),
            SetupStatus.CAPABILITY_INVALID,
            (_issue_from_probe("EXECUTABLE_UNAVAILABLE"),),
        )
    executable_path = str(Path(executable).resolve())
    results = tuple(
        probe(executable_path, cwd=repository.path)
        for repository in preliminary.repositories
    )
    observations = tuple(
        result.observation
        for result in results
        if result.observation is not None
    )
    issues = tuple(
        _issue_from_probe(rejection.code.value, rejection.detail)
        for result in results
        for rejection in result.rejections
    )
    issue_codes = tuple(sorted({issue.code.lower() for issue in issues}))
    ready = bool(results) and all(
        result.status is CodexProbeStatus.READY and result.observation is not None
        for result in results
    )
    try:
        if len(observations) == len(results) and observations:
            normalized = normalize_codex_harness(observations)
            harness = (
                normalized
                if ready
                else replace(
                    normalized,
                    status=HarnessStatus.DETECTED_PARTIAL,
                    issue_codes=issue_codes or ("capability_invalid",),
                )
            )
        else:
            harness = HarnessObservation(
                "codex",
                HarnessStatus.UNUSABLE,
                executable=executable_path,
                issue_codes=issue_codes or ("probe_incomplete",),
            )
    except ValueError as exc:
        observations = ()
        issues = (*issues, _issue_from_probe("OBSERVATION_INCONSISTENT", str(exc)))
        harness = HarnessObservation(
            "codex",
            HarnessStatus.UNUSABLE,
            executable=executable_path,
            issue_codes=("observation_inconsistent",),
        )
        ready = False
    snapshot = discover_setup(
        project_root,
        harnesses=(harness, *other_harnesses),
        adapters=(adapter,),
    )
    return _DiscoveryOutcome(
        snapshot,
        observations,
        None if ready else SetupStatus.CAPABILITY_INVALID,
        issues,
    )


def _bound_discovery(
    state: _SessionState,
    current: DiscoverySnapshot,
) -> DiscoverySnapshot | None:
    if current.discovery_digest == state.discovery_digest:
        return current
    rebound = replace(
        current,
        existing_activation=state.initial_activation,
        workspace_protocol=state.initial_workspace_protocol,
    )
    return rebound if rebound.discovery_digest == state.discovery_digest else None


def _evaluate(
    state: _SessionState,
    outcome: _DiscoveryOutcome,
) -> _Evaluation:
    bound = _bound_discovery(state, outcome.snapshot)
    if bound is None:
        return _Evaluation(
            SetupStatus.STALE,
            outcome.snapshot,
            (
                _action_question(
                    "setup.restart",
                    "restart",
                    "Restart setup from the current Discovery Snapshot?",
                    "The previous snapshot changed; setup invalidates the whole "
                    "candidate and does not reuse prior Human answers automatically.",
                ),
            ),
            (
                SetupIssue(
                    "discovery",
                    "DISCOVERY_STALE",
                    detail=f"current={outcome.snapshot.discovery_digest}",
                ),
            ),
        )
    if outcome.status is SetupStatus.CAPABILITY_INVALID:
        return _Evaluation(
            SetupStatus.CAPABILITY_INVALID,
            bound,
            (
                _action_question(
                    "setup.retry_discovery",
                    "retry",
                    "Retry mechanical harness discovery?",
                    "The Codex adapter is not currently READY for every "
                    "discovered repository context.",
                ),
            ),
            outcome.issues,
        )
    answers = _answer_map(state)
    questions = _setup_questions(bound, answers)
    if questions:
        return _Evaluation(
            SetupStatus.NEEDS_HUMAN_INPUT,
            bound,
            questions,
            (),
        )
    try:
        status, candidate, issues = _build_candidate(
            bound,
            outcome.observation_map,
            Path(state.project_root),
            answers,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _Evaluation(
            SetupStatus.STATIC_INVALID,
            bound,
            (
                _action_question(
                    "setup.restart",
                    "restart",
                    "Restart setup from current facts?",
                    "The typed decisions cannot be compiled into a valid candidate.",
                ),
            ),
            (
                SetupIssue(
                    "candidate",
                    "CANDIDATE_INPUT_INVALID",
                    detail=_bounded_detail(str(exc)),
                ),
            ),
        )
    if candidate is None:
        return _Evaluation(
            status,
            bound,
            (
                _action_question(
                    "setup.restart",
                    "restart",
                    "Restart setup from current facts?",
                    "The current decisions did not compile into a candidate.",
                ),
            ),
            issues,
        )
    if state.runtime_proof is None:
        return _Evaluation(
            SetupStatus.SMOKE_FAILED,
            bound,
            (),
            (SetupIssue("smoke", "PROOF_PENDING"),),
            candidate=candidate,
        )
    proof = parse_runtime_proof(state.runtime_proof)
    if proof.status is RuntimeProofStatus.STALE:
        return _Evaluation(
            SetupStatus.STALE,
            bound,
            (
                _action_question(
                    "setup.restart",
                    "restart",
                    "Restart setup from current facts?",
                    "The stored runtime proof is bound to a stale Discovery Snapshot.",
                ),
            ),
            (SetupIssue("smoke", "PROOF_STALE"),),
            candidate=candidate,
            proof=proof,
        )
    if proof.status is RuntimeProofStatus.SMOKE_FAILED:
        return _Evaluation(
            SetupStatus.SMOKE_FAILED,
            bound,
            (
                _action_question(
                    "setup.retry_smoke",
                    "retry",
                    "Retry the deterministic native authority smoke?",
                    "At least one native allow/deny receipt did not match the compiled envelope.",
                ),
            ),
            (SetupIssue("smoke", "RUNTIME_PROOF_FAILED"),),
            candidate=candidate,
            proof=proof,
        )
    compiled = compile_setup_publication(candidate, proof)
    if compiled.publication is None:
        compile_status = {
            "STALE": SetupStatus.STALE,
            "SMOKE_FAILED": SetupStatus.SMOKE_FAILED,
            "STATIC_INVALID": SetupStatus.STATIC_INVALID,
        }.get(compiled.status.value, SetupStatus.STATIC_INVALID)
        return _Evaluation(
            compile_status,
            bound,
            (),
            tuple(
                SetupIssue(
                    "publication",
                    rejection.code.value,
                    rejection.role,
                )
                for rejection in compiled.rejections
            ),
            candidate=candidate,
            proof=proof,
        )
    acceptance = (
        None
        if state.acceptance_receipt is None
        else parse_acceptance_receipt(state.acceptance_receipt)
    )
    return _Evaluation(
        (
            SetupStatus.ACCEPTED
            if acceptance is not None
            else SetupStatus.AWAITING_ACCEPTANCE
        ),
        bound,
        (),
        (),
        candidate=candidate,
        proof=proof,
        publication=compiled.publication,
        acceptance=acceptance,
    )


CodexResolver = Callable[[], str | None]
ProofRunner = Callable[[tuple[str, ...], float], NativeCommandResult]


class SetupEngine:
    """Deep stateful interface: resume, typed answer CAS, and exact acceptance."""

    def __init__(
        self,
        *,
        codex_executable: str | None = None,
        executable_resolver: CodexResolver | None = None,
        codex_probe: Callable[..., CodexProbeResult] = probe_codex,
        proof_runner: ProofRunner | None = None,
    ) -> None:
        if codex_executable is not None and executable_resolver is not None:
            raise ValueError("choose an explicit Codex executable or a resolver")
        self._codex_executable = codex_executable
        self._executable_resolver = executable_resolver or (
            lambda: shutil.which("codex")
        )
        self._codex_probe = codex_probe
        self._proof_runner = proof_runner

    def _resolve_executable(self) -> str | None:
        value = self._codex_executable
        if value is None:
            value = self._executable_resolver()
        if value is None:
            return None
        path = Path(value).expanduser().resolve()
        return str(path)

    def _discover(self, project_root: str) -> _DiscoveryOutcome:
        return _discovery_with_codex(
            project_root,
            self._resolve_executable(),
            self._codex_probe,
        )

    def _advance(
        self,
        state: _SessionState,
        outcome: _DiscoveryOutcome,
    ) -> tuple[_SessionState, _Evaluation]:
        evaluation = _evaluate(state, outcome)
        if (
            evaluation.candidate is not None
            and state.runtime_proof is None
            and any(issue.code == "PROOF_PENDING" for issue in evaluation.issues)
        ):
            roles = tuple(plan.role for plan in evaluation.candidate.role_plans)
            _ensure_role_state(Path(state.project_root), roles)
            proof = prove_candidate(
                evaluation.candidate,
                evaluation.discovery,
                runner=self._proof_runner,
            )
            state = replace(state, runtime_proof=render_runtime_proof(proof))
            evaluation = _evaluate(state, outcome)
        if (
            evaluation.acceptance is not None
            and evaluation.publication is not None
            and evaluation.candidate is not None
        ):
            verified = accept_setup_publication(
                evaluation.publication,
                outcome.snapshot,
                evaluation.candidate.candidate_digest,
            )
            if verified.status is AcceptanceStatus.ACCEPTED:
                if verified.receipt != evaluation.acceptance:
                    evaluation = replace(
                        evaluation,
                        status=SetupStatus.STATIC_INVALID,
                        issues=(
                            SetupIssue(
                                "acceptance",
                                "ACCEPTANCE_RECEIPT_MISMATCH",
                            ),
                        ),
                    )
            else:
                mapped = (
                    SetupStatus.STALE
                    if verified.status is AcceptanceStatus.STALE
                    else SetupStatus.STATIC_INVALID
                )
                evaluation = replace(
                    evaluation,
                    status=mapped,
                    issues=tuple(
                        SetupIssue(
                            "acceptance",
                            rejection.code.value,
                            detail=rejection.detail,
                        )
                        for rejection in verified.rejections
                    ),
                )
        return state, evaluation

    def resume(self, project_root: str) -> SetupView:
        """Resume the stable project session or create its first discovery revision."""

        try:
            root = Path(project_root).expanduser().resolve(strict=True)
        except OSError as exc:
            raise SetupStateError("project root is not a readable directory") from exc
        if not root.is_dir() or str(root) != os.path.normpath(str(root)):
            raise SetupStateError("project root must be a canonical directory")
        canonical = str(root)
        session_id = _session_id(canonical)
        sessions, state_path, lock_path = _session_paths(root, session_id)
        lock_descriptor = _open_session_lock(lock_path)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            outcome = self._discover(canonical)
            state = _read_state(state_path)
            created = state is None
            if state is None:
                state = _SessionState(
                    session_id=session_id,
                    revision=0,
                    project_root=canonical,
                    discovery_digest=outcome.snapshot.discovery_digest,
                    initial_activation=outcome.snapshot.existing_activation,
                    initial_workspace_protocol=outcome.snapshot.workspace_protocol,
                )
            before = state
            state, evaluation = self._advance(state, outcome)
            if state != before and not created and state.revision == before.revision:
                state = replace(state, revision=state.revision + 1)
                evaluation = _evaluate(state, outcome)
            if created or state != before:
                _write_state(sessions, state_path, state)
            return _project_setup_view(state, evaluation)
        finally:
            os.close(lock_descriptor)

    def answer(
        self,
        session_id: str,
        revision: int,
        typed_answers: Iterable[SetupTypedAnswer],
    ) -> SetupView:
        """Apply exact open-question answers under revision compare-and-swap."""

        project_root = _project_root_from_session_id(session_id)
        root = Path(project_root)
        sessions, state_path, lock_path = _session_paths(root, session_id)
        lock_descriptor = _open_session_lock(lock_path)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            state = _read_state(state_path)
            if state is None or state.session_id != session_id:
                raise SetupStateError("setup session does not exist")
            outcome = self._discover(project_root)
            state, evaluation = self._advance(state, outcome)
            current_view = _project_setup_view(state, evaluation)
            if revision != state.revision:
                raise SetupRevisionConflict(current_view)
            values = tuple(typed_answers)
            if not values or any(
                not isinstance(value, SetupTypedAnswer) for value in values
            ):
                raise SetupAnswerError(
                    "typed answers must contain at least one SetupTypedAnswer",
                    current_view,
                )
            identifiers = tuple(value.identifier for value in values)
            if len(identifiers) != len(set(identifiers)):
                raise SetupAnswerError("typed answers repeat an identifier", current_view)

            action = {value.identifier: value for value in values}
            restart = action.get("setup.restart")
            if restart is not None:
                if (
                    len(action) != 1
                    or not any(
                        question.identifier == "setup.restart"
                        for question in evaluation.questions
                    )
                    or restart.kind is not SetupAnswerKind.CHOICE
                    or restart.value != "restart"
                ):
                    raise SetupAnswerError("setup.restart is not currently valid", current_view)
                state = _SessionState(
                    session_id=session_id,
                    revision=state.revision + 1,
                    project_root=project_root,
                    discovery_digest=outcome.snapshot.discovery_digest,
                    initial_activation=outcome.snapshot.existing_activation,
                    initial_workspace_protocol=outcome.snapshot.workspace_protocol,
                )
            elif evaluation.status is SetupStatus.STALE:
                expected = action.get("setup.restart")
                if (
                    len(action) != 1
                    or expected is None
                    or expected.kind is not SetupAnswerKind.CHOICE
                    or expected.value != "restart"
                ):
                    raise SetupAnswerError("stale setup requires setup.restart", current_view)
            elif evaluation.status is SetupStatus.SMOKE_FAILED:
                expected = action.get("setup.retry_smoke")
                if (
                    len(action) != 1
                    or expected is None
                    or expected.kind is not SetupAnswerKind.CHOICE
                    or expected.value != "retry"
                ):
                    raise SetupAnswerError(
                        "failed smoke requires setup.retry_smoke",
                        current_view,
                    )
                state = replace(
                    state,
                    revision=state.revision + 1,
                    runtime_proof=None,
                    acceptance_receipt=None,
                )
            elif evaluation.status is SetupStatus.CAPABILITY_INVALID:
                expected = action.get("setup.retry_discovery")
                if (
                    len(action) != 1
                    or expected is None
                    or expected.kind is not SetupAnswerKind.CHOICE
                    or expected.value != "retry"
                ):
                    raise SetupAnswerError(
                        "capability failure requires setup.retry_discovery",
                        current_view,
                    )
                state = replace(state, revision=state.revision + 1)
            else:
                open_questions = {
                    question.identifier: question for question in evaluation.questions
                }
                for answer in values:
                    question = open_questions.get(answer.identifier)
                    if question is None:
                        raise SetupAnswerError(
                            f"answer is not an open engine question: {answer.identifier}",
                            current_view,
                        )
                    if answer.kind is not question.kind or (
                        question.kind is not SetupAnswerKind.TEXT
                        and answer.value not in {
                            option.value for option in question.options
                        }
                    ):
                        raise SetupAnswerError(
                            f"answer does not match engine options: {answer.identifier}",
                            current_view,
                        )
                merged = _answer_map(state)
                merged.update(action)
                state = replace(
                    state,
                    revision=state.revision + 1,
                    answers=tuple(merged.values()),
                    runtime_proof=None,
                    acceptance_receipt=None,
                )
            state, evaluation = self._advance(state, outcome)
            _write_state(sessions, state_path, state)
            return _project_setup_view(state, evaluation)
        finally:
            os.close(lock_descriptor)

    def accept(
        self,
        session_id: str,
        candidate_digest: str,
    ) -> AcceptanceReceipt:
        """Accept one exact prepared candidate and atomically activate it."""

        project_root = _project_root_from_session_id(session_id)
        root = Path(project_root)
        sessions, state_path, lock_path = _session_paths(root, session_id)
        lock_descriptor = _open_session_lock(lock_path)
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            state = _read_state(state_path)
            if state is None or state.session_id != session_id:
                raise SetupStateError("setup session does not exist")
            outcome = self._discover(project_root)
            state, evaluation = self._advance(state, outcome)
            view = _project_setup_view(state, evaluation)
            if (
                evaluation.publication is None
                or evaluation.candidate is None
                or evaluation.status
                not in {SetupStatus.AWAITING_ACCEPTANCE, SetupStatus.ACCEPTED}
            ):
                raise SetupTransitionError(
                    "setup is not awaiting digest-bound acceptance",
                    view,
                )
            result = accept_setup_publication(
                evaluation.publication,
                outcome.snapshot,
                candidate_digest,
            )
            if result.status is not AcceptanceStatus.ACCEPTED or result.receipt is None:
                status = {
                    AcceptanceStatus.AWAITING_ACCEPTANCE: SetupStatus.AWAITING_ACCEPTANCE,
                    AcceptanceStatus.STALE: SetupStatus.STALE,
                    AcceptanceStatus.SMOKE_FAILED: SetupStatus.SMOKE_FAILED,
                    AcceptanceStatus.STATIC_INVALID: SetupStatus.STATIC_INVALID,
                }.get(result.status, SetupStatus.STATIC_INVALID)
                rejected = replace(
                    evaluation,
                    status=status,
                    issues=tuple(
                        SetupIssue(
                            "acceptance",
                            rejection.code.value,
                            detail=rejection.detail,
                        )
                        for rejection in result.rejections
                    ),
                )
                raise SetupTransitionError(
                    "candidate acceptance was rejected",
                    _project_setup_view(state, rejected),
                )
            state = replace(
                state,
                revision=state.revision + 1,
                acceptance_receipt=render_acceptance_receipt(result.receipt),
            )
            _write_state(sessions, state_path, state)
            return result.receipt
        finally:
            os.close(lock_descriptor)
