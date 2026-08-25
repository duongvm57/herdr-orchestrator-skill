"""Deterministic native authority proof for immutable setup candidates."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable

from .candidate import (
    DiscoverySnapshot,
    FreshnessStatus,
    SetupCandidate,
    check_candidate_freshness,
)
from .codex_authority import AssuranceLevel, NativeFilesystemRule, NativeLaunchSpec


PROBE_TIMEOUT_SECONDS = 20.0
DENIAL_ERRNOS = frozenset({1, 2, 13, 30})  # EPERM, ENOENT, EACCES, EROFS


class ProofOperation(str, Enum):
    FILESYSTEM_READ = "FILESYSTEM_READ"
    FILESYSTEM_WRITE = "FILESYSTEM_WRITE"
    NETWORK_EGRESS = "NETWORK_EGRESS"
    NATIVE_SPAWN = "NATIVE_SPAWN"


class ExpectedEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class ObservedEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ERROR = "ERROR"


class RoleProofStatus(str, Enum):
    PROVEN = "PROVEN"
    SMOKE_FAILED = "SMOKE_FAILED"


class RuntimeProofStatus(str, Enum):
    PROVEN = "PROVEN"
    SMOKE_FAILED = "SMOKE_FAILED"
    STALE = "STALE"


def _validate_text(value: str, label: str, *, maximum: int = 4096) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty canonical string")
    if len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} is not bounded canonical text")


def _validate_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
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
    return hashlib.sha256(label.encode("ascii") + b"\0" + _canonical_bytes(value)).hexdigest()


def _detail_digest(value: str) -> str:
    return hashlib.sha256(value[:4000].encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class ProofCheck:
    identifier: str
    operation: ProofOperation
    resource: str | None
    target: str
    expected: ExpectedEffect
    observed: ObservedEffect
    assurance: AssuranceLevel
    error_code: int | None = None
    detail_digest: str | None = None

    def __post_init__(self) -> None:
        _validate_text(self.identifier, "proof check identifier", maximum=512)
        if not isinstance(self.operation, ProofOperation):
            raise TypeError("proof check operation is invalid")
        if self.resource is not None:
            _validate_text(self.resource, "proof check resource", maximum=512)
        _validate_text(self.target, "proof check target")
        if not isinstance(self.expected, ExpectedEffect):
            raise TypeError("proof check expectation is invalid")
        if not isinstance(self.observed, ObservedEffect):
            raise TypeError("proof check observation is invalid")
        if not isinstance(self.assurance, AssuranceLevel):
            raise TypeError("proof check assurance is invalid")
        if self.error_code is not None and (
            not isinstance(self.error_code, int) or isinstance(self.error_code, bool)
        ):
            raise TypeError("proof check error code must be an integer")
        if self.observed is ObservedEffect.ALLOW and self.error_code is not None:
            raise ValueError("allowed proof check cannot report an error code")
        if (
            self.observed is ObservedEffect.DENY
            and self.assurance is AssuranceLevel.RUNTIME_PROBED
            and self.error_code not in DENIAL_ERRNOS
        ):
            raise ValueError("runtime denial lacks a sandbox denial error code")
        if self.detail_digest is not None:
            _validate_digest(self.detail_digest, "proof check detail digest")

    @property
    def passed(self) -> bool:
        effect_matches = (
            self.expected is ExpectedEffect.ALLOW
            and self.observed is ObservedEffect.ALLOW
        ) or (
            self.expected is ExpectedEffect.DENY
            and self.observed is ObservedEffect.DENY
        )
        return effect_matches and self.assurance not in {
            AssuranceLevel.MODEL_OBSERVED,
            AssuranceLevel.UNVERIFIED,
        }


@dataclass(frozen=True)
class RoleProofReceipt:
    role: str
    candidate_digest: str
    launch_spec_digest: str
    status: RoleProofStatus
    checks: tuple[ProofCheck, ...]
    receipt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_text(self.role, "proof receipt role", maximum=128)
        _validate_digest(self.candidate_digest, "proof candidate digest")
        _validate_digest(self.launch_spec_digest, "proof launch digest")
        if not isinstance(self.status, RoleProofStatus):
            raise TypeError("role proof status is invalid")
        checks = tuple(self.checks)
        if not checks or any(not isinstance(check, ProofCheck) for check in checks):
            raise ValueError("role proof receipt requires checks")
        identifiers = tuple(check.identifier for check in checks)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("role proof receipt repeats a check")
        expected_status = (
            RoleProofStatus.PROVEN
            if all(check.passed for check in checks)
            else RoleProofStatus.SMOKE_FAILED
        )
        if self.status is not expected_status:
            raise ValueError("role proof status does not match its checks")
        object.__setattr__(self, "checks", checks)
        object.__setattr__(
            self,
            "receipt_digest",
            _digest("herdr-role-proof", _role_receipt_projection(self)),
        )


@dataclass(frozen=True)
class RuntimeProofReceipt:
    status: RuntimeProofStatus
    candidate_digest: str
    discovery_digest: str
    current_discovery_digest: str
    roles: tuple[RoleProofReceipt, ...]
    receipt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.status, RuntimeProofStatus):
            raise TypeError("runtime proof status is invalid")
        for value, label in (
            (self.candidate_digest, "runtime proof candidate digest"),
            (self.discovery_digest, "runtime proof discovery digest"),
            (self.current_discovery_digest, "runtime proof current discovery digest"),
        ):
            _validate_digest(value, label)
        roles = tuple(sorted(self.roles, key=lambda receipt: receipt.role))
        if any(not isinstance(receipt, RoleProofReceipt) for receipt in roles):
            raise TypeError("runtime proof roles contain an invalid receipt")
        role_names = tuple(receipt.role for receipt in roles)
        if len(role_names) != len(set(role_names)):
            raise ValueError("runtime proof repeats a role")
        if any(receipt.candidate_digest != self.candidate_digest for receipt in roles):
            raise ValueError("runtime proof role is bound to another candidate")
        if self.status is RuntimeProofStatus.STALE:
            if roles or self.discovery_digest == self.current_discovery_digest:
                raise ValueError("stale runtime proof has inconsistent discovery")
        else:
            expected = (
                RuntimeProofStatus.PROVEN
                if roles and all(
                    receipt.status is RoleProofStatus.PROVEN for receipt in roles
                )
                else RuntimeProofStatus.SMOKE_FAILED
            )
            if self.status is not expected:
                raise ValueError("runtime proof status does not match role receipts")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(
            self,
            "receipt_digest",
            _digest("herdr-runtime-proof", _runtime_receipt_projection(self)),
        )


@dataclass(frozen=True)
class _PlannedCheck:
    identifier: str
    operation: ProofOperation
    resource: str | None
    target: str
    expected: ExpectedEffect
    path: str | None = None
    canary: str | None = None
    network_host: str | None = None
    network_port: int | None = None


@dataclass(frozen=True)
class NativeCommandResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if not isinstance(self.returncode, int) or isinstance(self.returncode, bool):
            raise TypeError("native command return code must be an integer")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise TypeError("native command output must be text")


Runner = Callable[[tuple[str, ...], float], NativeCommandResult]


def _subprocess_runner(
    command: tuple[str, ...],
    timeout: float,
) -> NativeCommandResult:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return NativeCommandResult(127, "", str(exc))
    return NativeCommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


PROBE_SCRIPT = r'''
import errno
import json
import os
import socket
import sys

# A path hidden by the native sandbox can surface as ENOENT. Host preflight
# proves every probed target exists before that result is accepted as denial.
denials = {errno.EPERM, errno.EACCES, errno.EROFS, errno.ENOENT}
plan = json.loads(sys.argv[1])
results = []
for check in plan:
    observed = "ERROR"
    error_code = None
    try:
        if check["operation"] == "FILESYSTEM_READ":
            os.listdir(check["path"])
            observed = "ALLOW"
        elif check["operation"] == "FILESYSTEM_WRITE":
            descriptor = os.open(
                check["canary"],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                os.write(descriptor, b"herdr-runtime-proof\n")
            finally:
                os.close(descriptor)
            os.unlink(check["canary"])
            observed = "ALLOW"
        elif check["operation"] == "NETWORK_EGRESS":
            candidate = socket.socket()
            candidate.settimeout(2)
            try:
                candidate.connect((check["network_host"], check["network_port"]))
                observed = "ALLOW"
            finally:
                candidate.close()
    except OSError as error:
        error_code = error.errno
        observed = "DENY" if error.errno in denials else "ERROR"
    results.append(
        {
            "identifier": check["identifier"],
            "observed": observed,
            "error_code": error_code,
        }
    )
print(json.dumps(results, sort_keys=True, separators=(",", ":")))
'''.strip()


def _launch_projection(launch: NativeLaunchSpec) -> dict[str, object]:
    return {
        "adapter_kind": launch.adapter_kind,
        "executable": launch.executable,
        "cwd": launch.cwd,
        "arguments": list(launch.arguments),
        "permission_profile": launch.permission_profile,
        "config_overrides": list(launch.config_overrides),
        "filesystem_rules": [
            {"resource": rule.resource, "path": rule.path, "access": rule.access}
            for rule in launch.filesystem_rules
        ],
        "model": launch.model,
        "reasoning_effort": launch.reasoning_effort,
        "native_agents_enabled": launch.native_agents_enabled,
        "network_enabled": launch.network_enabled,
        "selected_binding_id": launch.selected_binding_id,
        "effective_envelope": [
            {"name": capability.name, "resource": capability.resource}
            for capability in sorted(launch.effective_envelope.effective)
        ],
    }


def digest_native_launch_spec(launch: NativeLaunchSpec) -> str:
    """Return the domain-separated identity used by role proof receipts."""

    if not isinstance(launch, NativeLaunchSpec):
        raise TypeError("launch must be a NativeLaunchSpec")
    return _digest("herdr-native-launch", _launch_projection(launch))


def _check_projection(check: ProofCheck) -> dict[str, object]:
    return {
        "identifier": check.identifier,
        "operation": check.operation.value,
        "resource": check.resource,
        "target": check.target,
        "expected": check.expected.value,
        "observed": check.observed.value,
        "assurance": check.assurance.value,
        "error_code": check.error_code,
        "detail_digest": check.detail_digest,
    }


def _role_receipt_projection(receipt: RoleProofReceipt) -> dict[str, object]:
    return {
        "role": receipt.role,
        "candidate_digest": receipt.candidate_digest,
        "launch_spec_digest": receipt.launch_spec_digest,
        "status": receipt.status.value,
        "checks": [_check_projection(check) for check in receipt.checks],
    }


def _runtime_receipt_projection(receipt: RuntimeProofReceipt) -> dict[str, object]:
    return {
        "status": receipt.status.value,
        "candidate_digest": receipt.candidate_digest,
        "discovery_digest": receipt.discovery_digest,
        "current_discovery_digest": receipt.current_discovery_digest,
        "roles": [
            {
                **_role_receipt_projection(role),
                "receipt_digest": role.receipt_digest,
            }
            for role in receipt.roles
        ],
    }


def _static_checks(launch: NativeLaunchSpec) -> tuple[ProofCheck, ...]:
    native_disabled = (
        launch.native_agents_enabled is False
        and "agents.enabled=false" in launch.config_overrides
    )
    network_disabled = launch.network_enabled is False and any(
        "network = { enabled = false }" in override
        for override in launch.config_overrides
    )
    return (
        ProofCheck(
            "native_spawn.config",
            ProofOperation.NATIVE_SPAWN,
            None,
            "agents.enabled",
            ExpectedEffect.DENY,
            ObservedEffect.DENY if native_disabled else ObservedEffect.ALLOW,
            AssuranceLevel.STATIC_PROVEN,
        ),
        ProofCheck(
            "network.config",
            ProofOperation.NETWORK_EGRESS,
            None,
            "permission_profile.network",
            ExpectedEffect.DENY,
            ObservedEffect.DENY if network_disabled else ObservedEffect.ALLOW,
            AssuranceLevel.STATIC_PROVEN,
        ),
    )


def _canary_name(candidate_digest: str, role: str, resource: str) -> str:
    token = hashlib.sha256(
        f"{candidate_digest}\0{role}\0{resource}".encode("utf-8")
    ).hexdigest()[:20]
    return f".herdr-runtime-proof-{token}"


def _plan_filesystem_checks(
    candidate_digest: str,
    role: str,
    rules: Iterable[NativeFilesystemRule],
    outside: Path,
) -> tuple[_PlannedCheck, ...]:
    planned: list[_PlannedCheck] = []
    for rule in rules:
        if rule.path == ":minimal":
            continue
        assert rule.resource is not None
        planned.append(
            _PlannedCheck(
                f"fs.read:{rule.resource}",
                ProofOperation.FILESYSTEM_READ,
                rule.resource,
                rule.path,
                ExpectedEffect.ALLOW,
                path=rule.path,
            )
        )
        if rule.resource == "runtime:codex":
            continue
        canary = str(
            Path(rule.path)
            / _canary_name(candidate_digest, role, rule.resource)
        )
        planned.append(
            _PlannedCheck(
                f"fs.write:{rule.resource}",
                ProofOperation.FILESYSTEM_WRITE,
                rule.resource,
                rule.path,
                (
                    ExpectedEffect.ALLOW
                    if rule.access == "write"
                    else ExpectedEffect.DENY
                ),
                path=rule.path,
                canary=canary,
            )
        )
    outside_canary = outside / _canary_name(candidate_digest, role, "outside")
    planned.extend(
        (
            _PlannedCheck(
                "fs.read:outside",
                ProofOperation.FILESYSTEM_READ,
                "outside:probe",
                "outside:probe",
                ExpectedEffect.DENY,
                path=str(outside),
            ),
            _PlannedCheck(
                "fs.write:outside",
                ProofOperation.FILESYSTEM_WRITE,
                "outside:probe",
                "outside:probe",
                ExpectedEffect.DENY,
                path=str(outside),
                canary=str(outside_canary),
            ),
        )
    )
    return tuple(planned)


def _preflight(
    launch: NativeLaunchSpec,
    planned: tuple[_PlannedCheck, ...],
) -> dict[str, str]:
    errors: dict[str, str] = {}
    cwd = Path(launch.cwd)
    try:
        if not cwd.is_dir() or cwd.resolve(strict=True) != cwd:
            raise OSError("cwd is absent or noncanonical")
    except OSError as exc:
        for check in planned:
            errors[check.identifier] = f"launch cwd unavailable: {exc}"
        return errors
    checked_reads: set[str] = set()
    checked_writes: set[str] = set()
    for check in planned:
        assert check.path is not None
        root = Path(check.path)
        try:
            if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
                raise OSError("target root is absent, symlinked, or noncanonical")
            if check.path not in checked_reads:
                os.listdir(root)
                checked_reads.add(check.path)
            if check.canary is not None and check.path not in checked_writes:
                canary = Path(check.canary)
                descriptor = os.open(
                    canary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    os.write(descriptor, b"herdr-host-preflight\n")
                finally:
                    os.close(descriptor)
                canary.unlink()
                checked_writes.add(check.path)
        except OSError as exc:
            errors[check.identifier] = str(exc)
    return errors


def _unverified_checks(
    planned: tuple[_PlannedCheck, ...],
    errors: dict[str, str],
) -> tuple[ProofCheck, ...]:
    result: list[ProofCheck] = []
    for check in planned:
        detail = errors.get(check.identifier, "role preflight aborted")
        result.append(
            ProofCheck(
                check.identifier,
                check.operation,
                check.resource,
                check.target,
                check.expected,
                ObservedEffect.ERROR,
                (
                    AssuranceLevel.NATIVE_INTROSPECTED
                    if check.identifier in errors
                    else AssuranceLevel.UNVERIFIED
                ),
                detail_digest=_detail_digest(detail),
            )
        )
    return tuple(result)


def _probe_command(
    launch: NativeLaunchSpec,
    planned: tuple[_PlannedCheck, ...],
) -> tuple[str, ...]:
    plan = [
        {
            "identifier": check.identifier,
            "operation": check.operation.value,
            "expected": check.expected.value,
            "path": check.path,
            "canary": check.canary,
            "network_host": check.network_host,
            "network_port": check.network_port,
        }
        for check in planned
    ]
    config_arguments = tuple(
        argument
        for override in launch.config_overrides
        for argument in ("--config", override)
    )
    return (
        launch.executable,
        "sandbox",
        "--permission-profile",
        launch.permission_profile,
        *config_arguments,
        "--cd",
        launch.cwd,
        "--",
        "python3",
        "-c",
        PROBE_SCRIPT,
        json.dumps(plan, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
    )


def _parse_native_checks(
    result: NativeCommandResult,
    planned: tuple[_PlannedCheck, ...],
) -> tuple[ProofCheck, ...]:
    if result.returncode != 0:
        digest = _detail_digest(result.stderr or result.stdout or "native probe failed")
        return tuple(
            ProofCheck(
                check.identifier,
                check.operation,
                check.resource,
                check.target,
                check.expected,
                ObservedEffect.ERROR,
                AssuranceLevel.UNVERIFIED,
                detail_digest=digest,
            )
            for check in planned
        )
    try:
        document = json.loads(result.stdout)
        if not isinstance(document, list):
            raise ValueError("native receipt is not an array")
        by_identifier: dict[str, dict[str, object]] = {}
        for entry in document:
            if not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str):
                raise ValueError("native receipt entry is malformed")
            identifier = entry["identifier"]
            if identifier in by_identifier:
                raise ValueError("native receipt repeats a check")
            by_identifier[identifier] = entry
        if set(by_identifier) != {check.identifier for check in planned}:
            raise ValueError("native receipt check set differs from the plan")
    except (json.JSONDecodeError, ValueError) as exc:
        digest = _detail_digest(f"{exc}\n{result.stdout}\n{result.stderr}")
        return tuple(
            ProofCheck(
                check.identifier,
                check.operation,
                check.resource,
                check.target,
                check.expected,
                ObservedEffect.ERROR,
                AssuranceLevel.UNVERIFIED,
                detail_digest=digest,
            )
            for check in planned
        )
    checks: list[ProofCheck] = []
    for planned_check in planned:
        entry = by_identifier[planned_check.identifier]
        try:
            observed = ObservedEffect(entry.get("observed"))
            error_code = entry.get("error_code")
            if error_code is not None and (
                not isinstance(error_code, int) or isinstance(error_code, bool)
            ):
                raise ValueError("native error code is invalid")
            if observed is ObservedEffect.ALLOW and error_code is not None:
                raise ValueError("allowed native operation reported an error")
            if (
                observed is ObservedEffect.DENY
                and error_code not in DENIAL_ERRNOS
            ):
                raise ValueError("native denial lacks a sandbox denial error")
        except (ValueError, TypeError) as exc:
            checks.append(
                ProofCheck(
                    planned_check.identifier,
                    planned_check.operation,
                    planned_check.resource,
                    planned_check.target,
                    planned_check.expected,
                    ObservedEffect.ERROR,
                    AssuranceLevel.UNVERIFIED,
                    detail_digest=_detail_digest(str(exc)),
                )
            )
            continue
        checks.append(
            ProofCheck(
                planned_check.identifier,
                planned_check.operation,
                planned_check.resource,
                planned_check.target,
                planned_check.expected,
                observed,
                AssuranceLevel.RUNTIME_PROBED,
                error_code=error_code,
            )
        )
    return tuple(checks)


def _execute_native_probe(
    runner: Runner,
    command: tuple[str, ...],
    timeout: float,
) -> NativeCommandResult:
    try:
        result = runner(command, timeout)
    except Exception as exc:
        return NativeCommandResult(
            127,
            "",
            f"{type(exc).__name__}: {exc}",
        )
    if not isinstance(result, NativeCommandResult):
        return NativeCommandResult(
            127,
            "",
            f"runner returned {type(result).__name__}, not NativeCommandResult",
        )
    return result


def _cleanup_canaries(planned: Iterable[_PlannedCheck]) -> None:
    for check in planned:
        if check.canary is None:
            continue
        canary = Path(check.canary)
        try:
            if canary.is_file() and not canary.is_symlink():
                canary.unlink()
        except OSError:
            pass


def _prove_role(
    candidate: SetupCandidate,
    role: str,
    launch: NativeLaunchSpec,
    runner: Runner,
    timeout: float,
) -> RoleProofReceipt:
    launch_digest = digest_native_launch_spec(launch)
    static = _static_checks(launch)
    with TemporaryDirectory(prefix="herdr-proof-outside-") as outside_raw:
        outside = Path(outside_raw).resolve(strict=True)
        planned = list(
            _plan_filesystem_checks(
                candidate.candidate_digest,
                role,
                launch.filesystem_rules,
                outside,
            )
        )
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(1)
        host, port = listener.getsockname()
        planned.append(
            _PlannedCheck(
                "network.egress",
                ProofOperation.NETWORK_EGRESS,
                None,
                "network:local-listener",
                ExpectedEffect.DENY,
                network_host=host,
                network_port=port,
            )
        )
        planned_tuple = tuple(planned)
        try:
            errors = _preflight(launch, planned_tuple[:-1])
            if errors:
                dynamic = _unverified_checks(planned_tuple, errors)
            else:
                result = _execute_native_probe(
                    runner,
                    _probe_command(launch, planned_tuple),
                    timeout,
                )
                dynamic = _parse_native_checks(result, planned_tuple)
        finally:
            listener.close()
            _cleanup_canaries(planned_tuple)
    checks = (*static, *dynamic)
    status = (
        RoleProofStatus.PROVEN
        if all(check.passed for check in checks)
        else RoleProofStatus.SMOKE_FAILED
    )
    return RoleProofReceipt(
        role,
        candidate.candidate_digest,
        launch_digest,
        status,
        checks,
    )


def prove_candidate(
    candidate: SetupCandidate,
    current_discovery: DiscoverySnapshot,
    *,
    runner: Runner | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> RuntimeProofReceipt:
    """Prove every candidate role with native commands, or fail closed."""

    if not isinstance(candidate, SetupCandidate):
        raise TypeError("candidate must be a SetupCandidate")
    if not isinstance(current_discovery, DiscoverySnapshot):
        raise TypeError("current discovery must be a DiscoverySnapshot")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("runtime proof timeout must be positive")
    freshness = check_candidate_freshness(candidate, current_discovery)
    if freshness.status is FreshnessStatus.STALE:
        return RuntimeProofReceipt(
            RuntimeProofStatus.STALE,
            candidate.candidate_digest,
            candidate.discovery_digest,
            current_discovery.discovery_digest,
            (),
        )
    execute = runner or _subprocess_runner
    role_receipts = tuple(
        _prove_role(
            candidate,
            plan.role,
            plan.launch_spec,
            execute,
            float(timeout),
        )
        for plan in candidate.role_plans
    )
    status = (
        RuntimeProofStatus.PROVEN
        if role_receipts
        and all(receipt.status is RoleProofStatus.PROVEN for receipt in role_receipts)
        else RuntimeProofStatus.SMOKE_FAILED
    )
    return RuntimeProofReceipt(
        status,
        candidate.candidate_digest,
        candidate.discovery_digest,
        current_discovery.discovery_digest,
        role_receipts,
    )


def render_runtime_proof(receipt: RuntimeProofReceipt) -> bytes:
    """Render a canonical digest-bound runtime proof receipt."""

    if not isinstance(receipt, RuntimeProofReceipt):
        raise TypeError("receipt must be a RuntimeProofReceipt")
    document = _runtime_receipt_projection(receipt)
    document["receipt_digest"] = receipt.receipt_digest
    return _canonical_bytes(document) + b"\n"


def parse_runtime_proof(payload: bytes) -> RuntimeProofReceipt:
    """Load and revalidate one canonical runtime-proof receipt."""

    if not isinstance(payload, bytes):
        raise TypeError("runtime proof payload must be bytes")
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("runtime proof payload exceeds the bounded size")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime proof payload is not valid JSON") from exc
    expected_root = {
        "status",
        "candidate_digest",
        "discovery_digest",
        "current_discovery_digest",
        "roles",
        "receipt_digest",
    }
    if not isinstance(document, dict) or set(document) != expected_root:
        raise ValueError("runtime proof payload has the wrong fields")
    roles_document = document["roles"]
    if not isinstance(roles_document, list):
        raise ValueError("runtime proof roles must be a list")
    roles: list[RoleProofReceipt] = []
    expected_role = {
        "role",
        "candidate_digest",
        "launch_spec_digest",
        "status",
        "checks",
        "receipt_digest",
    }
    expected_check = {
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
    try:
        for role_document in roles_document:
            if not isinstance(role_document, dict) or set(role_document) != expected_role:
                raise ValueError("runtime proof role has the wrong fields")
            checks_document = role_document["checks"]
            if not isinstance(checks_document, list):
                raise ValueError("runtime proof checks must be a list")
            checks: list[ProofCheck] = []
            for check_document in checks_document:
                if (
                    not isinstance(check_document, dict)
                    or set(check_document) != expected_check
                ):
                    raise ValueError("runtime proof check has the wrong fields")
                checks.append(
                    ProofCheck(
                        identifier=check_document["identifier"],
                        operation=ProofOperation(check_document["operation"]),
                        resource=check_document["resource"],
                        target=check_document["target"],
                        expected=ExpectedEffect(check_document["expected"]),
                        observed=ObservedEffect(check_document["observed"]),
                        assurance=AssuranceLevel(check_document["assurance"]),
                        error_code=check_document["error_code"],
                        detail_digest=check_document["detail_digest"],
                    )
                )
            role = RoleProofReceipt(
                role=role_document["role"],
                candidate_digest=role_document["candidate_digest"],
                launch_spec_digest=role_document["launch_spec_digest"],
                status=RoleProofStatus(role_document["status"]),
                checks=tuple(checks),
            )
            if role.receipt_digest != role_document["receipt_digest"]:
                raise ValueError("runtime proof role digest does not match its content")
            roles.append(role)
        receipt = RuntimeProofReceipt(
            status=RuntimeProofStatus(document["status"]),
            candidate_digest=document["candidate_digest"],
            discovery_digest=document["discovery_digest"],
            current_discovery_digest=document["current_discovery_digest"],
            roles=tuple(roles),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("runtime proof"):
            raise
        raise ValueError("runtime proof payload contains invalid values") from exc
    if receipt.receipt_digest != document["receipt_digest"]:
        raise ValueError("runtime proof digest does not match its content")
    if render_runtime_proof(receipt) != payload:
        raise ValueError("runtime proof payload is not canonical")
    return receipt
