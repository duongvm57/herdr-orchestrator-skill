from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/herdr-orchestrator/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from herdr_setup.authority import (  # noqa: E402
    AuthorityEnvelope,
    AuthorityPolicy,
    Binding,
    Capability,
    EligibilityRejectionCode,
    EligibilityStatus,
    FeasibilityRejectionCode,
    FeasibilityStatus,
    Requirement,
    SelectionConflictCode,
    SelectionStatus,
    evaluate_eligibility,
    select_binding,
    solve_feasibility,
)


READ_PROJECT = Capability("fs.read", "project:repo")
WRITE_PROJECT = Capability("fs.write", "project:repo")
WRITE_EVIDENCE = Capability("fs.write", "evidence:assignment")
READ_GIT = Capability("fs.read", "git-common:repo")
NETWORK = Capability("network.egress")
NATIVE_SPAWN = Capability("native_spawn")


def binding(identifier: str, *effective: Capability) -> Binding:
    return Binding(
        identifier=identifier,
        adapter_kind="fake",
        envelope=AuthorityEnvelope(frozenset(effective)),
    )


class FakeBindingSource:
    def __init__(self, *bindings: Binding) -> None:
        self._bindings = bindings

    def bindings(self, requirement: Requirement) -> tuple[Binding, ...]:
        del requirement
        return self._bindings


class SetupAuthorityTests(unittest.TestCase):
    def reviewer_requirement(self, *may_have: Capability) -> Requirement:
        return Requirement(
            role="reviewer",
            must_have=frozenset({READ_PROJECT, WRITE_EVIDENCE}),
            must_not_have=frozenset({WRITE_PROJECT, NETWORK, NATIVE_SPAWN}),
            may_have=frozenset(may_have),
        )

    def permissive_policy(self, *extra: Capability) -> AuthorityPolicy:
        return AuthorityPolicy(
            permitted=frozenset({READ_PROJECT, WRITE_EVIDENCE, *extra}),
            must_not_have=frozenset(),
        )

    def test_requirement_sets_must_be_disjoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "must_have and must_not_have"):
            Requirement(
                role="reviewer",
                must_have=frozenset({READ_PROJECT}),
                must_not_have=frozenset({READ_PROJECT}),
                may_have=frozenset(),
            )

        with self.assertRaisesRegex(ValueError, "must_have and may_have"):
            Requirement(
                role="reviewer",
                must_have=frozenset({READ_PROJECT}),
                must_not_have=frozenset(),
                may_have=frozenset({READ_PROJECT}),
            )

    def test_feasibility_is_adapter_neutral_and_preserves_rejections(self) -> None:
        requirement = self.reviewer_requirement()
        source = FakeBindingSource(
            binding("missing-evidence", READ_PROJECT),
            binding("valid", READ_PROJECT, WRITE_EVIDENCE),
            binding("project-writer", READ_PROJECT, WRITE_EVIDENCE, WRITE_PROJECT),
        )

        result = solve_feasibility(requirement, source.bindings(requirement))

        self.assertEqual(result.status, FeasibilityStatus.FEASIBLE)
        self.assertEqual(
            [candidate.identifier for candidate in result.feasible_bindings],
            ["valid"],
        )
        self.assertEqual(
            [candidate.identifier for candidate in result.rejected_bindings],
            ["missing-evidence", "project-writer"],
        )
        reasons = {
            rejection.binding_id: {reason.code for reason in rejection.reasons}
            for rejection in result.rejection_reasons
        }
        self.assertEqual(
            reasons["missing-evidence"],
            {FeasibilityRejectionCode.MISSING_MUST_HAVE},
        )
        self.assertEqual(
            reasons["project-writer"],
            {
                FeasibilityRejectionCode.GRANTS_ROLE_FORBIDDEN,
                FeasibilityRejectionCode.GRANTS_OUTSIDE_ROLE_CEILING,
            },
        )

    def test_closed_world_rejects_unlisted_capability_even_when_not_forbidden(self) -> None:
        requirement = self.reviewer_requirement()
        result = solve_feasibility(
            requirement,
            [binding("extra-git-read", READ_PROJECT, WRITE_EVIDENCE, READ_GIT)],
        )

        self.assertEqual(result.status, FeasibilityStatus.UNSATISFIABLE)
        self.assertEqual(
            result.rejection_reasons[0].reasons[0].code,
            FeasibilityRejectionCode.GRANTS_OUTSIDE_ROLE_CEILING,
        )
        self.assertEqual(
            result.rejection_reasons[0].reasons[0].capabilities,
            (READ_GIT,),
        )

    def test_may_have_is_a_ceiling_not_a_requirement(self) -> None:
        requirement = self.reviewer_requirement(READ_GIT)
        result = solve_feasibility(
            requirement,
            [
                binding("minimal", READ_PROJECT, WRITE_EVIDENCE),
                binding("with-tolerated-read", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
            ],
        )

        self.assertEqual(result.status, FeasibilityStatus.FEASIBLE)
        self.assertEqual(len(result.feasible_bindings), 2)

    def test_eligibility_distinguishes_human_ceiling_and_policy_prohibition(self) -> None:
        requirement = self.reviewer_requirement(READ_GIT)
        feasibility = solve_feasibility(
            requirement,
            [
                binding("minimal", READ_PROJECT, WRITE_EVIDENCE),
                binding("git-reader", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
            ],
        )
        policy = AuthorityPolicy(
            permitted=frozenset({READ_PROJECT, WRITE_EVIDENCE}),
            must_not_have=frozenset({READ_GIT}),
        )

        result = evaluate_eligibility(feasibility, policy)

        self.assertEqual(result.status, EligibilityStatus.ELIGIBLE)
        self.assertEqual(
            [candidate.identifier for candidate in result.eligible_bindings],
            ["minimal"],
        )
        conflicts = {
            conflict.code for conflict in result.policy_conflicts[0].conflicts
        }
        self.assertEqual(
            conflicts,
            {
                EligibilityRejectionCode.GRANTS_OUTSIDE_HUMAN_PERMISSION,
                EligibilityRejectionCode.GRANTS_POLICY_FORBIDDEN,
            },
        )

    def test_zero_feasible_and_zero_eligible_have_different_statuses(self) -> None:
        requirement = self.reviewer_requirement()
        infeasible = solve_feasibility(
            requirement,
            [binding("writer", READ_PROJECT, WRITE_EVIDENCE, WRITE_PROJECT)],
        )
        self.assertEqual(infeasible.status, FeasibilityStatus.UNSATISFIABLE)

        feasible = solve_feasibility(
            requirement,
            [binding("valid", READ_PROJECT, WRITE_EVIDENCE)],
        )
        ineligible = evaluate_eligibility(
            feasible,
            AuthorityPolicy(
                permitted=frozenset({READ_PROJECT}),
                must_not_have=frozenset(),
            ),
        )
        self.assertEqual(ineligible.status, EligibilityStatus.POLICY_CONFLICT)

    def test_unique_strict_subset_is_selected_as_least_privilege(self) -> None:
        requirement = self.reviewer_requirement(READ_GIT)
        feasibility = solve_feasibility(
            requirement,
            [
                binding("broader", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
                binding("minimal", READ_PROJECT, WRITE_EVIDENCE),
            ],
        )
        eligibility = evaluate_eligibility(
            feasibility,
            self.permissive_policy(READ_GIT),
        )

        result = select_binding(eligibility)

        self.assertEqual(result.status, SelectionStatus.SELECTED)
        self.assertEqual(result.selected_binding.identifier, "minimal")
        self.assertEqual(result.selector_receipt.selector, "least_privilege")
        self.assertEqual(
            result.selector_receipt.considered_binding_ids,
            ("broader", "minimal"),
        )

    def test_incomparable_or_equal_minima_require_human_input(self) -> None:
        read_logs = Capability("fs.read", "logs:assignment")
        requirement = self.reviewer_requirement(READ_GIT, read_logs)
        policy = self.permissive_policy(READ_GIT, read_logs)

        for candidates in (
            [
                binding("git", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
                binding("logs", READ_PROJECT, WRITE_EVIDENCE, read_logs),
            ],
            [
                binding("codex", READ_PROJECT, WRITE_EVIDENCE),
                binding("pi", READ_PROJECT, WRITE_EVIDENCE),
            ],
        ):
            with self.subTest(candidates=[item.identifier for item in candidates]):
                eligibility = evaluate_eligibility(
                    solve_feasibility(requirement, candidates),
                    policy,
                )
                result = select_binding(eligibility)
                self.assertEqual(result.status, SelectionStatus.NEEDS_HUMAN_INPUT)
                self.assertIsNone(result.selected_binding)
                self.assertIsNone(result.selector_receipt)
                self.assertEqual(len(result.unresolved_binding_ids), 2)

    def test_explicit_selector_may_choose_any_eligible_binding(self) -> None:
        requirement = self.reviewer_requirement(READ_GIT)
        eligibility = evaluate_eligibility(
            solve_feasibility(
                requirement,
                [
                    binding("minimal", READ_PROJECT, WRITE_EVIDENCE),
                    binding("human-choice", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
                ],
            ),
            self.permissive_policy(READ_GIT),
        )

        result = select_binding(eligibility, explicit_binding_id="human-choice")

        self.assertEqual(result.status, SelectionStatus.SELECTED)
        self.assertEqual(result.selected_binding.identifier, "human-choice")
        self.assertEqual(result.selector_receipt.selector, "explicit_binding")

    def test_explicit_selector_cannot_select_an_ineligible_binding(self) -> None:
        requirement = self.reviewer_requirement(READ_GIT)
        eligibility = evaluate_eligibility(
            solve_feasibility(
                requirement,
                [
                    binding("eligible", READ_PROJECT, WRITE_EVIDENCE),
                    binding("forbidden", READ_PROJECT, WRITE_EVIDENCE, READ_GIT),
                ],
            ),
            AuthorityPolicy(
                permitted=frozenset({READ_PROJECT, WRITE_EVIDENCE}),
                must_not_have=frozenset({READ_GIT}),
            ),
        )

        result = select_binding(eligibility, explicit_binding_id="forbidden")

        self.assertEqual(result.status, SelectionStatus.POLICY_CONFLICT)
        self.assertIsNone(result.selected_binding)
        self.assertEqual(
            result.selection_conflicts[0].code,
            SelectionConflictCode.EXPLICIT_BINDING_NOT_ELIGIBLE,
        )

    def test_binding_identifiers_are_unique_and_results_are_stably_ordered(self) -> None:
        requirement = self.reviewer_requirement()
        duplicate = binding("same", READ_PROJECT, WRITE_EVIDENCE)
        with self.assertRaisesRegex(ValueError, "duplicate binding identifier"):
            solve_feasibility(requirement, [duplicate, duplicate])

        result = solve_feasibility(
            requirement,
            [
                binding("zeta", READ_PROJECT, WRITE_EVIDENCE),
                binding("a-binding", READ_PROJECT, WRITE_EVIDENCE),
            ],
        )
        self.assertEqual(
            [candidate.identifier for candidate in result.feasible_bindings],
            ["a-binding", "zeta"],
        )


if __name__ == "__main__":
    unittest.main()
