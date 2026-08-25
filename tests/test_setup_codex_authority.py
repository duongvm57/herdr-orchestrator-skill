from __future__ import annotations

import sys
import tomllib
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
    Requirement,
    SelectionResult,
    evaluate_eligibility,
    select_binding,
    solve_feasibility,
)
from herdr_setup.codex_authority import (  # noqa: E402
    AssuranceLevel,
    CodexCompileRejectionCode,
    CodexCompileStatus,
    CodexModelObservation,
    CodexObservation,
    CodexProbeRejectionCode,
    CodexProbeStatus,
    CodexVersion,
    RuntimeBindingContext,
    RuntimePathBinding,
    compile_codex,
    probe_codex,
)


RUNTIME_READ = Capability("fs.read", "runtime:codex")
READ_PROJECT = Capability("fs.read", "project:root")
WRITE_PROJECT = Capability("fs.write", "project:root")
READ_REPOSITORY = Capability("fs.read", "repository:assigned")
READ_WORKSPACE = Capability("fs.read", "workspace:assigned")
WRITE_WORKSPACE = Capability("fs.write", "workspace:assigned")
READ_GIT_COMMON = Capability("fs.read", "git-common:assigned")
WRITE_GIT_COMMON = Capability("fs.write", "git-common:assigned")
READ_EVIDENCE = Capability("fs.read", "evidence:assignment")
WRITE_EVIDENCE = Capability("fs.write", "evidence:assignment")
READ_NOTEBOOK = Capability("fs.read", "notebook:session")
WRITE_NOTEBOOK = Capability("fs.write", "notebook:session")
READ_CONTROL = Capability("fs.read", "control:project")
WRITE_CONTROL = Capability("fs.write", "control:project")
NETWORK = Capability("network.egress")
NATIVE_SPAWN = Capability("native_spawn")


def selected_binding(
    *effective: Capability,
    adapter_kind: str = "codex",
) -> SelectionResult:
    envelope = frozenset(effective)
    requirement = Requirement(
        role="test-role",
        must_have=envelope,
        must_not_have=frozenset(),
        may_have=frozenset(),
    )
    feasibility = solve_feasibility(
        requirement,
        [
            Binding(
                identifier="codex-test",
                adapter_kind=adapter_kind,
                envelope=AuthorityEnvelope(envelope),
            )
        ],
    )
    eligibility = evaluate_eligibility(
        feasibility,
        AuthorityPolicy(permitted=envelope, must_not_have=frozenset()),
    )
    return select_binding(eligibility)


def unresolved_selection(*effective: Capability) -> SelectionResult:
    envelope = frozenset(effective)
    requirement = Requirement(
        role="test-role",
        must_have=envelope,
        must_not_have=frozenset(),
        may_have=frozenset(),
    )
    feasibility = solve_feasibility(
        requirement,
        [
            Binding("codex-a", "codex", AuthorityEnvelope(envelope)),
            Binding("codex-b", "codex", AuthorityEnvelope(envelope)),
        ],
    )
    eligibility = evaluate_eligibility(
        feasibility,
        AuthorityPolicy(permitted=envelope, must_not_have=frozenset()),
    )
    return select_binding(eligibility)


class SetupCodexAuthorityTests(unittest.TestCase):
    def observation(self, **overrides: object) -> CodexObservation:
        values: dict[str, object] = {
            "executable": "/opt/codex/bin/codex",
            "version": CodexVersion(0, 149, 1),
            "runtime_root": "/opt/codex",
            "bound_cwd": "/srv/herdr/project",
            "models": (
                CodexModelObservation(
                    identifier="gpt-5.6-sol",
                    reasoning_efforts=("medium", "high", "xhigh"),
                ),
            ),
            "permission_profiles": True,
            "permission_profile_assurance": AssuranceLevel.RUNTIME_PROBED,
            "native_spawn_control": True,
            "native_spawn_assurance": AssuranceLevel.STATIC_PROVEN,
            "network_control": True,
            "network_assurance": AssuranceLevel.RUNTIME_PROBED,
            "legacy_sandbox_settings": False,
        }
        values.update(overrides)
        return CodexObservation(**values)

    def context(
        self,
        *resources: tuple[str, str],
        cwd: str = "/srv/herdr/project",
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "high",
    ) -> RuntimeBindingContext:
        return RuntimeBindingContext(
            cwd=cwd,
            resources=tuple(RuntimePathBinding(*resource) for resource in resources),
            model=model,
            reasoning_effort=reasoning_effort,
        )

    def compile(
        self,
        selection: SelectionResult,
        context: RuntimeBindingContext,
        **observation_overrides: object,
    ):
        observation_overrides.setdefault("bound_cwd", context.cwd)
        return compile_codex(
            selection,
            context,
            self.observation(**observation_overrides),
        )

    def profile(self, result) -> dict[str, object]:
        self.assertEqual(result.status, CodexCompileStatus.COMPILED)
        arguments = result.launch_spec.arguments
        overrides = [
            arguments[index + 1]
            for index, argument in enumerate(arguments[:-1])
            if argument == "--config"
        ]
        encoded = next(
            override for override in overrides if override.startswith("permissions=")
        )
        return tomllib.loads(encoded)["permissions"]["herdr_runtime"]

    def rejection_codes(self, result) -> set[CodexCompileRejectionCode]:
        return {rejection.code for rejection in result.rejections}

    def test_version_parser_accepts_native_output_without_inferring_model_quality(self) -> None:
        self.assertEqual(
            CodexVersion.parse("codex-cli 0.149.1"),
            CodexVersion(0, 149, 1),
        )

    def test_missing_codex_executable_is_a_structured_probe_result(self) -> None:
        result = probe_codex(
            "/nonexistent/herdr/codex",
            cwd="/srv/herdr/project",
        )

        self.assertEqual(result.status, CodexProbeStatus.UNUSABLE)
        self.assertIsNone(result.observation)
        self.assertEqual(
            {rejection.code for rejection in result.rejections},
            {CodexProbeRejectionCode.EXECUTABLE_UNAVAILABLE},
        )

    def test_compiles_all_supported_roles_to_exact_permission_profiles(self) -> None:
        cases = {
            "reviewer": (
                selected_binding(
                    RUNTIME_READ,
                    READ_REPOSITORY,
                    READ_EVIDENCE,
                    WRITE_EVIDENCE,
                ),
                self.context(
                    ("repository:assigned", "/srv/herdr/project/backend"),
                    ("evidence:assignment", "/srv/herdr/evidence/review-1"),
                    cwd="/srv/herdr/project/backend",
                ),
                {
                    "/opt/codex": "read",
                    "/srv/herdr/project/backend": "read",
                    "/srv/herdr/evidence/review-1": "write",
                    ":minimal": "read",
                },
            ),
            "supervisor": (
                selected_binding(
                    RUNTIME_READ,
                    READ_PROJECT,
                    READ_NOTEBOOK,
                    WRITE_NOTEBOOK,
                ),
                self.context(
                    ("project:root", "/srv/herdr/project"),
                    ("notebook:session", "/srv/herdr/notebook/run-1"),
                ),
                {
                    "/opt/codex": "read",
                    "/srv/herdr/project": "read",
                    "/srv/herdr/notebook/run-1": "write",
                    ":minimal": "read",
                },
            ),
            "engineer": (
                selected_binding(
                    RUNTIME_READ,
                    READ_WORKSPACE,
                    WRITE_WORKSPACE,
                    READ_GIT_COMMON,
                    WRITE_GIT_COMMON,
                    READ_EVIDENCE,
                    WRITE_EVIDENCE,
                ),
                self.context(
                    ("workspace:assigned", "/srv/herdr/worktrees/backend-task"),
                    ("git-common:assigned", "/srv/herdr/project/backend/.git"),
                    ("evidence:assignment", "/srv/herdr/evidence/engineer-1"),
                    cwd="/srv/herdr/worktrees/backend-task",
                ),
                {
                    "/opt/codex": "read",
                    "/srv/herdr/worktrees/backend-task": "write",
                    "/srv/herdr/project/backend/.git": "write",
                    "/srv/herdr/evidence/engineer-1": "write",
                    ":minimal": "read",
                },
            ),
            "lead": (
                selected_binding(
                    RUNTIME_READ,
                    READ_PROJECT,
                    READ_CONTROL,
                    WRITE_CONTROL,
                    READ_EVIDENCE,
                    WRITE_EVIDENCE,
                ),
                self.context(
                    ("project:root", "/srv/herdr/project"),
                    ("control:project", "/srv/herdr/control"),
                    ("evidence:assignment", "/srv/herdr/evidence/lead-1"),
                ),
                {
                    "/opt/codex": "read",
                    "/srv/herdr/project": "read",
                    "/srv/herdr/control": "write",
                    "/srv/herdr/evidence/lead-1": "write",
                    ":minimal": "read",
                },
            ),
        }

        for role, (selection, context, expected_rules) in cases.items():
            with self.subTest(role=role):
                result = self.compile(selection, context)
                profile = self.profile(result)
                self.assertEqual(profile["filesystem"], expected_rules)
                self.assertEqual(profile["network"], {"enabled": False})
                arguments = result.launch_spec.arguments
                self.assertNotIn("--sandbox", arguments)
                self.assertNotIn("--add-dir", arguments)
                self.assertIn("agents.enabled=false", arguments)
                self.assertIn('default_permissions="herdr_runtime"', arguments)
                self.assertIn('model_reasoning_effort="high"', arguments)
                self.assertEqual(
                    result.launch_spec.effective_envelope,
                    selection.selected_binding.envelope,
                )

    def test_lead_project_write_is_granted_only_when_selected(self) -> None:
        context = self.context(("project:root", "/srv/herdr/project"))

        readonly = self.compile(
            selected_binding(RUNTIME_READ, READ_PROJECT),
            context,
        )
        writable = self.compile(
            selected_binding(RUNTIME_READ, READ_PROJECT, WRITE_PROJECT),
            context,
        )

        self.assertEqual(
            self.profile(readonly)["filesystem"]["/srv/herdr/project"],
            "read",
        )
        self.assertEqual(
            self.profile(writable)["filesystem"]["/srv/herdr/project"],
            "write",
        )

    def test_nested_repository_uses_its_exact_git_common_directory(self) -> None:
        selection = selected_binding(
            RUNTIME_READ,
            READ_WORKSPACE,
            WRITE_WORKSPACE,
            READ_GIT_COMMON,
            WRITE_GIT_COMMON,
        )
        context = self.context(
            ("workspace:assigned", "/srv/project/backend-worktree"),
            ("git-common:assigned", "/srv/project/backend/.git"),
            cwd="/srv/project/backend-worktree",
        )

        rules = self.profile(self.compile(selection, context))["filesystem"]

        self.assertEqual(rules["/srv/project/backend/.git"], "write")
        self.assertNotIn("/srv/project/.git", rules)

    def test_unselected_context_resources_are_not_proactively_granted(self) -> None:
        selection = selected_binding(RUNTIME_READ, READ_PROJECT)
        context = self.context(
            ("project:root", "/srv/herdr/project"),
            ("evidence:assignment", "/srv/herdr/evidence/unused"),
        )

        rules = self.profile(self.compile(selection, context))["filesystem"]

        self.assertNotIn("/srv/herdr/evidence/unused", rules)

    def test_native_write_requires_read_in_the_selected_effective_envelope(self) -> None:
        result = self.compile(
            selected_binding(RUNTIME_READ, WRITE_EVIDENCE),
            self.context(
                ("evidence:assignment", "/srv/herdr/evidence/review-1"),
            ),
        )

        self.assertEqual(result.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(result),
            {CodexCompileRejectionCode.EFFECTIVE_ENVELOPE_MISMATCH},
        )

    def test_selection_must_be_complete_and_codex_bound(self) -> None:
        context = self.context(("project:root", "/srv/herdr/project"))

        incomplete = self.compile(
            unresolved_selection(RUNTIME_READ, READ_PROJECT),
            context,
        )
        wrong_adapter = self.compile(
            selected_binding(
                RUNTIME_READ,
                READ_PROJECT,
                adapter_kind="pi",
            ),
            context,
        )

        self.assertEqual(incomplete.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(incomplete),
            {CodexCompileRejectionCode.SELECTION_NOT_COMPLETE},
        )
        self.assertEqual(wrong_adapter.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(wrong_adapter),
            {CodexCompileRejectionCode.ADAPTER_KIND_MISMATCH},
        )

    def test_unbound_and_unknown_capabilities_are_structured_static_errors(self) -> None:
        unbound = self.compile(
            selected_binding(RUNTIME_READ, READ_PROJECT),
            self.context(),
        )
        unknown = self.compile(
            selected_binding(RUNTIME_READ, Capability("process.signal")),
            self.context(),
        )

        self.assertEqual(unbound.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(unbound),
            {CodexCompileRejectionCode.UNBOUND_RESOURCE},
        )
        self.assertEqual(unknown.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(unknown),
            {CodexCompileRejectionCode.UNSUPPORTED_CAPABILITY},
        )

    def test_codex_runtime_read_is_explicit_not_an_implicit_extra_grant(self) -> None:
        result = self.compile(
            selected_binding(READ_PROJECT),
            self.context(("project:root", "/srv/herdr/project")),
        )

        self.assertEqual(result.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(result),
            {CodexCompileRejectionCode.MISSING_RUNTIME_READ},
        )

    def test_native_spawn_stays_disabled_for_the_herdr_control_plane(self) -> None:
        result = self.compile(
            selected_binding(RUNTIME_READ, READ_PROJECT, NATIVE_SPAWN),
            self.context(("project:root", "/srv/herdr/project")),
        )

        self.assertEqual(result.status, CodexCompileStatus.CAPABILITY_INVALID)
        self.assertEqual(
            self.rejection_codes(result),
            {CodexCompileRejectionCode.NATIVE_SPAWN_UNSUPPORTED},
        )

    def test_unsupported_runtime_controls_fail_closed(self) -> None:
        selection = selected_binding(RUNTIME_READ, READ_PROJECT)
        context = self.context(("project:root", "/srv/herdr/project"))
        cases = (
            (
                {"version": CodexVersion(0, 137, 9)},
                CodexCompileRejectionCode.VERSION_TOO_OLD,
            ),
            (
                {"permission_profiles": False},
                CodexCompileRejectionCode.PERMISSION_PROFILES_UNAVAILABLE,
            ),
            (
                {"permission_profile_assurance": AssuranceLevel.UNVERIFIED},
                CodexCompileRejectionCode.PERMISSION_PROFILE_UNVERIFIED,
            ),
            (
                {"native_spawn_control": False},
                CodexCompileRejectionCode.NATIVE_SPAWN_CONTROL_UNAVAILABLE,
            ),
            (
                {"network_control": False},
                CodexCompileRejectionCode.NETWORK_CONTROL_UNAVAILABLE,
            ),
            (
                {"legacy_sandbox_settings": True},
                CodexCompileRejectionCode.LEGACY_SANDBOX_CONFLICT,
            ),
        )

        for overrides, expected in cases:
            with self.subTest(expected=expected):
                result = self.compile(selection, context, **overrides)
                self.assertEqual(result.status, CodexCompileStatus.CAPABILITY_INVALID)
                self.assertIn(expected, self.rejection_codes(result))

    def test_model_and_reasoning_are_validated_without_quality_ranking(self) -> None:
        selection = selected_binding(RUNTIME_READ, READ_PROJECT)
        resources = (("project:root", "/srv/herdr/project"),)

        missing_model = self.compile(
            selection,
            self.context(*resources, model="provider-model-not-observed"),
        )
        unsupported_effort = self.compile(
            selection,
            self.context(*resources, reasoning_effort="ultra"),
        )

        self.assertEqual(missing_model.status, CodexCompileStatus.CAPABILITY_INVALID)
        self.assertEqual(
            self.rejection_codes(missing_model),
            {CodexCompileRejectionCode.MODEL_NOT_OBSERVED},
        )
        self.assertEqual(
            unsupported_effort.status,
            CodexCompileStatus.CAPABILITY_INVALID,
        )
        self.assertEqual(
            self.rejection_codes(unsupported_effort),
            {CodexCompileRejectionCode.REASONING_EFFORT_UNSUPPORTED},
        )

    def test_observation_is_bound_to_the_exact_runtime_cwd(self) -> None:
        result = self.compile(
            selected_binding(RUNTIME_READ, READ_PROJECT),
            self.context(
                ("project:root", "/srv/herdr/other-project"),
                cwd="/srv/herdr/other-project",
            ),
            bound_cwd="/srv/herdr/project",
        )

        self.assertEqual(result.status, CodexCompileStatus.CAPABILITY_INVALID)
        self.assertEqual(
            self.rejection_codes(result),
            {CodexCompileRejectionCode.OBSERVATION_CONTEXT_MISMATCH},
        )

    def test_cwd_must_be_inside_selected_read_or_write_authority(self) -> None:
        result = self.compile(
            selected_binding(RUNTIME_READ, READ_REPOSITORY),
            self.context(
                ("repository:assigned", "/srv/herdr/project/backend"),
                cwd="/srv/herdr/project",
            ),
        )

        self.assertEqual(result.status, CodexCompileStatus.STATIC_INVALID)
        self.assertEqual(
            self.rejection_codes(result),
            {CodexCompileRejectionCode.CWD_NOT_ACCESSIBLE},
        )


if __name__ == "__main__":
    unittest.main()
