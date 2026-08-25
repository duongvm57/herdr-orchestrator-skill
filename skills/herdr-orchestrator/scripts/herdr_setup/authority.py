"""Adapter-neutral closed-world authority solving for setup."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


CAPABILITY_NAME_RE = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")
MAX_RESOURCE_LENGTH = 512


def _validate_bounded_text(value: str, label: str, *, maximum: int) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty canonical string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds the bounded length")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} contains a control character")


def _capability_set(
    values: Iterable[Capability],
    label: str,
) -> frozenset[Capability]:
    result = frozenset(values)
    if any(not isinstance(value, Capability) for value in result):
        raise TypeError(f"{label} must contain only Capability values")
    return result


@dataclass(frozen=True, order=True)
class Capability:
    """One normalized authority atom understood by the setup solver."""

    name: str
    resource: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or CAPABILITY_NAME_RE.fullmatch(self.name) is None:
            raise ValueError("capability name must be a canonical identifier")
        if self.resource is not None:
            _validate_bounded_text(
                self.resource,
                "capability resource",
                maximum=MAX_RESOURCE_LENGTH,
            )


@dataclass(frozen=True)
class AuthorityEnvelope:
    """The complete normalized authority a binding would grant."""

    effective: frozenset[Capability]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "effective",
            _capability_set(self.effective, "authority envelope"),
        )


@dataclass(frozen=True)
class Requirement:
    """Closed-world role authority requirement."""

    role: str
    must_have: frozenset[Capability]
    must_not_have: frozenset[Capability]
    may_have: frozenset[Capability]

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or IDENTIFIER_RE.fullmatch(self.role) is None:
            raise ValueError("requirement role must be a canonical identifier")
        must_have = _capability_set(self.must_have, "must_have")
        must_not_have = _capability_set(self.must_not_have, "must_not_have")
        may_have = _capability_set(self.may_have, "may_have")
        object.__setattr__(self, "must_have", must_have)
        object.__setattr__(self, "must_not_have", must_not_have)
        object.__setattr__(self, "may_have", may_have)
        overlaps = (
            ("must_have and must_not_have", must_have & must_not_have),
            ("must_have and may_have", must_have & may_have),
            ("must_not_have and may_have", must_not_have & may_have),
        )
        for label, overlap in overlaps:
            if overlap:
                raise ValueError(f"requirement {label} must be disjoint")

    @property
    def ceiling(self) -> frozenset[Capability]:
        """Maximum authority tolerated by this role; not an authority request."""

        return self.must_have | self.may_have


@dataclass(frozen=True)
class AuthorityPolicy:
    """Human-permitted ceiling and project-level prohibitions."""

    permitted: frozenset[Capability]
    must_not_have: frozenset[Capability]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "permitted",
            _capability_set(self.permitted, "policy permitted"),
        )
        object.__setattr__(
            self,
            "must_not_have",
            _capability_set(self.must_not_have, "policy must_not_have"),
        )


@dataclass(frozen=True)
class Binding:
    """One adapter-neutral candidate and its complete effective envelope."""

    identifier: str
    adapter_kind: str
    envelope: AuthorityEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or IDENTIFIER_RE.fullmatch(self.identifier) is None:
            raise ValueError("binding identifier must be canonical")
        if (
            not isinstance(self.adapter_kind, str)
            or IDENTIFIER_RE.fullmatch(self.adapter_kind) is None
        ):
            raise ValueError("binding adapter kind must be canonical")
        if not isinstance(self.envelope, AuthorityEnvelope):
            raise TypeError("binding envelope must be an AuthorityEnvelope")


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    UNSATISFIABLE = "UNSATISFIABLE"


class FeasibilityRejectionCode(str, Enum):
    MISSING_MUST_HAVE = "MISSING_MUST_HAVE"
    GRANTS_ROLE_FORBIDDEN = "GRANTS_ROLE_FORBIDDEN"
    GRANTS_OUTSIDE_ROLE_CEILING = "GRANTS_OUTSIDE_ROLE_CEILING"


@dataclass(frozen=True)
class FeasibilityRejection:
    code: FeasibilityRejectionCode
    capabilities: tuple[Capability, ...]


@dataclass(frozen=True)
class BindingFeasibilityRejection:
    binding_id: str
    reasons: tuple[FeasibilityRejection, ...]


@dataclass(frozen=True)
class FeasibilityResult:
    requirement: Requirement
    status: FeasibilityStatus
    feasible_bindings: tuple[Binding, ...]
    rejected_bindings: tuple[Binding, ...]
    rejection_reasons: tuple[BindingFeasibilityRejection, ...]


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    POLICY_CONFLICT = "POLICY_CONFLICT"


class EligibilityRejectionCode(str, Enum):
    GRANTS_OUTSIDE_HUMAN_PERMISSION = "GRANTS_OUTSIDE_HUMAN_PERMISSION"
    GRANTS_POLICY_FORBIDDEN = "GRANTS_POLICY_FORBIDDEN"


@dataclass(frozen=True)
class EligibilityConflict:
    code: EligibilityRejectionCode
    capabilities: tuple[Capability, ...]


@dataclass(frozen=True)
class BindingPolicyConflict:
    binding_id: str
    conflicts: tuple[EligibilityConflict, ...]


@dataclass(frozen=True)
class EligibilityResult:
    feasibility: FeasibilityResult
    policy: AuthorityPolicy
    status: EligibilityStatus
    eligible_bindings: tuple[Binding, ...]
    policy_conflicts: tuple[BindingPolicyConflict, ...]


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    NEEDS_HUMAN_INPUT = "NEEDS_HUMAN_INPUT"
    POLICY_CONFLICT = "POLICY_CONFLICT"


class SelectionConflictCode(str, Enum):
    NO_ELIGIBLE_BINDINGS = "NO_ELIGIBLE_BINDINGS"
    EXPLICIT_BINDING_NOT_ELIGIBLE = "EXPLICIT_BINDING_NOT_ELIGIBLE"


@dataclass(frozen=True)
class SelectionConflict:
    code: SelectionConflictCode
    binding_id: str | None = None


@dataclass(frozen=True)
class SelectorReceipt:
    selector: str
    selected_binding_id: str
    considered_binding_ids: tuple[str, ...]


@dataclass(frozen=True)
class SelectionResult:
    eligibility: EligibilityResult
    status: SelectionStatus
    selected_binding: Binding | None
    selector_receipt: SelectorReceipt | None
    unresolved_binding_ids: tuple[str, ...]
    selection_conflicts: tuple[SelectionConflict, ...]


def _ordered_bindings(bindings: Iterable[Binding]) -> tuple[Binding, ...]:
    candidates = tuple(bindings)
    if any(not isinstance(candidate, Binding) for candidate in candidates):
        raise TypeError("bindings must contain only Binding values")
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.identifier))
    identifiers = [candidate.identifier for candidate in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate binding identifier")
    return ordered


def _ordered_capabilities(values: Iterable[Capability]) -> tuple[Capability, ...]:
    return tuple(sorted(values))


def solve_feasibility(
    requirement: Requirement,
    bindings: Iterable[Binding],
) -> FeasibilityResult:
    """Classify normalized bindings against role requirements only."""

    if not isinstance(requirement, Requirement):
        raise TypeError("requirement must be a Requirement")
    feasible: list[Binding] = []
    rejected: list[Binding] = []
    rejection_reasons: list[BindingFeasibilityRejection] = []
    for candidate in _ordered_bindings(bindings):
        effective = candidate.envelope.effective
        reasons: list[FeasibilityRejection] = []
        missing = requirement.must_have - effective
        if missing:
            reasons.append(
                FeasibilityRejection(
                    FeasibilityRejectionCode.MISSING_MUST_HAVE,
                    _ordered_capabilities(missing),
                )
            )
        forbidden = effective & requirement.must_not_have
        if forbidden:
            reasons.append(
                FeasibilityRejection(
                    FeasibilityRejectionCode.GRANTS_ROLE_FORBIDDEN,
                    _ordered_capabilities(forbidden),
                )
            )
        outside_ceiling = effective - requirement.ceiling
        if outside_ceiling:
            reasons.append(
                FeasibilityRejection(
                    FeasibilityRejectionCode.GRANTS_OUTSIDE_ROLE_CEILING,
                    _ordered_capabilities(outside_ceiling),
                )
            )
        if reasons:
            rejected.append(candidate)
            rejection_reasons.append(
                BindingFeasibilityRejection(candidate.identifier, tuple(reasons))
            )
        else:
            feasible.append(candidate)
    return FeasibilityResult(
        requirement=requirement,
        status=(
            FeasibilityStatus.FEASIBLE
            if feasible
            else FeasibilityStatus.UNSATISFIABLE
        ),
        feasible_bindings=tuple(feasible),
        rejected_bindings=tuple(rejected),
        rejection_reasons=tuple(rejection_reasons),
    )


def evaluate_eligibility(
    feasibility: FeasibilityResult,
    policy: AuthorityPolicy,
) -> EligibilityResult:
    """Apply Human policy without erasing technical feasibility evidence."""

    if not isinstance(feasibility, FeasibilityResult):
        raise TypeError("feasibility must be a FeasibilityResult")
    if not isinstance(policy, AuthorityPolicy):
        raise TypeError("policy must be an AuthorityPolicy")
    if feasibility.status is FeasibilityStatus.UNSATISFIABLE:
        raise ValueError("cannot evaluate eligibility without a feasible binding")
    eligible: list[Binding] = []
    policy_conflicts: list[BindingPolicyConflict] = []
    for candidate in feasibility.feasible_bindings:
        effective = candidate.envelope.effective
        conflicts: list[EligibilityConflict] = []
        outside_permission = effective - policy.permitted
        if outside_permission:
            conflicts.append(
                EligibilityConflict(
                    EligibilityRejectionCode.GRANTS_OUTSIDE_HUMAN_PERMISSION,
                    _ordered_capabilities(outside_permission),
                )
            )
        forbidden = effective & policy.must_not_have
        if forbidden:
            conflicts.append(
                EligibilityConflict(
                    EligibilityRejectionCode.GRANTS_POLICY_FORBIDDEN,
                    _ordered_capabilities(forbidden),
                )
            )
        if conflicts:
            policy_conflicts.append(
                BindingPolicyConflict(candidate.identifier, tuple(conflicts))
            )
        else:
            eligible.append(candidate)
    return EligibilityResult(
        feasibility=feasibility,
        policy=policy,
        status=(
            EligibilityStatus.ELIGIBLE
            if eligible
            else EligibilityStatus.POLICY_CONFLICT
        ),
        eligible_bindings=tuple(eligible),
        policy_conflicts=tuple(policy_conflicts),
    )


def _selection_result(
    eligibility: EligibilityResult,
    *,
    status: SelectionStatus,
    selected: Binding | None = None,
    selector: str | None = None,
    unresolved: tuple[str, ...] = (),
    conflicts: tuple[SelectionConflict, ...] = (),
) -> SelectionResult:
    considered = tuple(
        candidate.identifier for candidate in eligibility.eligible_bindings
    )
    receipt = (
        SelectorReceipt(selector, selected.identifier, considered)
        if selected is not None and selector is not None
        else None
    )
    return SelectionResult(
        eligibility=eligibility,
        status=status,
        selected_binding=selected,
        selector_receipt=receipt,
        unresolved_binding_ids=unresolved,
        selection_conflicts=conflicts,
    )


def select_binding(
    eligibility: EligibilityResult,
    *,
    explicit_binding_id: str | None = None,
) -> SelectionResult:
    """Select explicitly or by a unique least-authority minimum."""

    if not isinstance(eligibility, EligibilityResult):
        raise TypeError("eligibility must be an EligibilityResult")
    eligible = eligibility.eligible_bindings
    if not eligible:
        return _selection_result(
            eligibility,
            status=SelectionStatus.POLICY_CONFLICT,
            conflicts=(
                SelectionConflict(SelectionConflictCode.NO_ELIGIBLE_BINDINGS),
            ),
        )
    if explicit_binding_id is not None:
        if (
            not isinstance(explicit_binding_id, str)
            or IDENTIFIER_RE.fullmatch(explicit_binding_id) is None
        ):
            raise ValueError("explicit binding identifier must be canonical")
        selected = next(
            (
                candidate
                for candidate in eligible
                if candidate.identifier == explicit_binding_id
            ),
            None,
        )
        if selected is None:
            return _selection_result(
                eligibility,
                status=SelectionStatus.POLICY_CONFLICT,
                conflicts=(
                    SelectionConflict(
                        SelectionConflictCode.EXPLICIT_BINDING_NOT_ELIGIBLE,
                        explicit_binding_id,
                    ),
                ),
            )
        return _selection_result(
            eligibility,
            status=SelectionStatus.SELECTED,
            selected=selected,
            selector="explicit_binding",
        )
    if len(eligible) == 1:
        return _selection_result(
            eligibility,
            status=SelectionStatus.SELECTED,
            selected=eligible[0],
            selector="sole_eligible",
        )
    minimal = tuple(
        candidate
        for candidate in eligible
        if not any(
            other.envelope.effective < candidate.envelope.effective
            for other in eligible
            if other.identifier != candidate.identifier
        )
    )
    if len(minimal) == 1:
        return _selection_result(
            eligibility,
            status=SelectionStatus.SELECTED,
            selected=minimal[0],
            selector="least_privilege",
        )
    return _selection_result(
        eligibility,
        status=SelectionStatus.NEEDS_HUMAN_INPUT,
        unresolved=tuple(candidate.identifier for candidate in minimal),
    )
