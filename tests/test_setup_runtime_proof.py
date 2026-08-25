from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
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
    evaluate_eligibility,
    select_binding,
    solve_feasibility,
)
from herdr_setup.candidate import (  # noqa: E402
    CandidateCompileStatus,
    DecisionValueKind,
    DiscoverySnapshot,
    HumanDecisions,
    ModelBinding,
    NativeAgentPolicy,
    PolicyAnswer,
    RoleAuthorityDecision,
    RoleCompilation,
    SetupCandidate,
    compile_setup_candidate,
    discover_setup,
    normalize_codex_harness,
    observe_codex_adapter,
)
from herdr_setup.codex_authority import (  # noqa: E402
    AssuranceLevel,
    CodexModelObservation,
    CodexObservation,
    CodexProbeStatus,
    CodexVersion,
    RuntimeBindingContext,
    RuntimePathBinding,
    compile_codex,
    probe_codex,
)
from herdr_setup.runtime_proof import (  # noqa: E402
    ExpectedEffect,
    NativeCommandResult,
    ObservedEffect,
    ProofCheck,
    ProofOperation,
    RoleProofStatus,
    RuntimeProofStatus,
    prove_candidate,
    render_runtime_proof,
)


RUNTIME_READ = Capability("fs.read", "runtime:codex")
READ_PROJECT = Capability("fs.read", "project:assigned")
WRITE_PROJECT = Capability("fs.write", "project:assigned")
READ_CONTROL = Capability("fs.read", "control:run")
WRITE_CONTROL = Capability("fs.write", "control:run")
READ_GIT = Capability("fs.read", "git-common:assigned")
WRITE_GIT = Capability("fs.write", "git-common:assigned")
READ_EVIDENCE = Capability("fs.read", "evidence:assignment")
WRITE_EVIDENCE = Capability("fs.write", "evidence:assignment")
READ_NOTEBOOK = Capability("fs.read", "notebook:session")
WRITE_NOTEBOOK = Capability("fs.write", "notebook:session")
NETWORK = Capability("network.egress")
NATIVE_SPAWN = Capability("native_spawn")


def run(*arguments: str) -> None:
    subprocess.run(arguments, text=True, capture_output=True, check=True)


class SetupRuntimeProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="herdr-proof-test-")
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        run("git", "init", "-q", str(self.project))
        self.control = self.root / "control"
        self.workspace = self.project / "assigned-workspace"
        self.evidence = self.root / "evidence"
        self.notebook = self.root / "notebook"
        for directory in (
            self.control,
            self.workspace,
            self.evidence,
            self.notebook,
        ):
            directory.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def observation(
        self,
        *,
        executable: str = "/usr/bin/true",
        runtime_root: str = "/usr/bin",
        models: tuple[CodexModelObservation, ...] | None = None,
    ) -> CodexObservation:
        return CodexObservation(
            executable=executable,
            version=CodexVersion(0, 149, 1),
            runtime_root=runtime_root,
            bound_cwd=str(self.project),
            models=models
            or (CodexModelObservation("human-selected-model", ("medium",)),),
            permission_profiles=True,
            permission_profile_assurance=AssuranceLevel.RUNTIME_PROBED,
            native_spawn_control=True,
            native_spawn_assurance=AssuranceLevel.STATIC_PROVEN,
            network_control=True,
            network_assurance=AssuranceLevel.RUNTIME_PROBED,
            legacy_sandbox_settings=False,
        )

    def candidate(
        self,
        observation: CodexObservation | None = None,
    ) -> tuple[SetupCandidate, DiscoverySnapshot]:
        observed = observation or self.observation()
        snapshot = discover_setup(
            str(self.project),
            harnesses=(normalize_codex_harness((observed,)),),
            adapters=(observe_codex_adapter(),),
        )
        definitions = {
            "lead": (
                (RUNTIME_READ, READ_PROJECT, READ_GIT, READ_CONTROL, WRITE_CONTROL),
                (
                    ("project:assigned", self.project),
                    ("git-common:assigned", self.project / ".git"),
                    ("control:run", self.control),
                ),
            ),
            "engineer": (
                (
                    RUNTIME_READ,
                    READ_PROJECT,
                    WRITE_PROJECT,
                    READ_GIT,
                    WRITE_GIT,
                    READ_EVIDENCE,
                    WRITE_EVIDENCE,
                ),
                (
                    ("project:assigned", self.project),
                    ("git-common:assigned", self.project / ".git"),
                    ("evidence:assignment", self.evidence),
                ),
            ),
            "reviewer": (
                (RUNTIME_READ, READ_PROJECT, READ_GIT, READ_EVIDENCE, WRITE_EVIDENCE),
                (
                    ("project:assigned", self.project),
                    ("git-common:assigned", self.project / ".git"),
                    ("evidence:assignment", self.evidence),
                ),
            ),
            "supervisor": (
                (RUNTIME_READ, READ_PROJECT, READ_NOTEBOOK, WRITE_NOTEBOOK),
                (
                    ("project:assigned", self.project),
                    ("notebook:session", self.notebook),
                ),
            ),
        }
        compilations: list[RoleCompilation] = []
        authority_decisions: list[RoleAuthorityDecision] = []
        model_bindings: list[ModelBinding] = []
        model = observed.models[0]
        effort = model.reasoning_efforts[0]
        for role, (effective_values, resources) in definitions.items():
            effective = frozenset(effective_values)
            requirement = Requirement(
                role,
                must_have=effective,
                must_not_have=frozenset(
                    {WRITE_PROJECT, NETWORK, NATIVE_SPAWN} - effective
                ),
                may_have=frozenset(),
            )
            policy = AuthorityPolicy(effective, frozenset())
            binding = Binding(
                f"codex-{role}",
                "codex",
                AuthorityEnvelope(effective),
            )
            selection = select_binding(
                evaluate_eligibility(
                    solve_feasibility(requirement, (binding,)),
                    policy,
                )
            )
            context = RuntimeBindingContext(
                str(self.project),
                tuple(
                    RuntimePathBinding(resource, str(path))
                    for resource, path in resources
                ),
                model.identifier,
                effort,
            )
            compiled = compile_codex(selection, context, observed)
            compilations.append(
                RoleCompilation(role, selection, context, observed, compiled)
            )
            authority_decisions.append(RoleAuthorityDecision(role, policy))
            model_bindings.append(
                ModelBinding(role, "codex", model.identifier, effort)
            )
        decisions = HumanDecisions(
            NativeAgentPolicy.DISABLED,
            tuple(reversed(authority_decisions)),
            tuple(reversed(model_bindings)),
            policy_answers=(
                PolicyAnswer(
                    "policy.artifact_language",
                    DecisionValueKind.TEXT,
                    "English",
                ),
                PolicyAnswer(
                    "policy.live_language",
                    DecisionValueKind.TEXT,
                    "Vietnamese",
                ),
            ),
        )
        result = compile_setup_candidate(
            snapshot,
            decisions,
            tuple(reversed(compilations)),
        )
        self.assertEqual(result.status, CandidateCompileStatus.COMPILED)
        self.assertIsNotNone(result.candidate)
        assert result.candidate is not None
        return result.candidate, snapshot

    @staticmethod
    def passing_runner(command: tuple[str, ...], timeout: float) -> NativeCommandResult:
        del timeout
        plan = json.loads(command[-1])
        receipt = [
            {
                "identifier": check["identifier"],
                "observed": check["expected"],
                "error_code": 1 if check["expected"] == "DENY" else None,
            }
            for check in plan
        ]
        return NativeCommandResult(
            0,
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            "",
        )

    def test_all_supported_roles_receive_complete_allow_and_deny_matrix(self) -> None:
        candidate, snapshot = self.candidate()

        receipt = prove_candidate(
            candidate,
            snapshot,
            runner=self.passing_runner,
        )

        self.assertEqual(receipt.status, RuntimeProofStatus.PROVEN)
        self.assertEqual(
            [role.role for role in receipt.roles],
            ["engineer", "lead", "reviewer", "supervisor"],
        )
        for role in receipt.roles:
            with self.subTest(role=role.role):
                self.assertEqual(role.status, RoleProofStatus.PROVEN)
                checks = {check.identifier: check for check in role.checks}
                self.assertEqual(
                    checks["native_spawn.config"].assurance,
                    AssuranceLevel.STATIC_PROVEN,
                )
                self.assertEqual(
                    checks["network.egress"].assurance,
                    AssuranceLevel.RUNTIME_PROBED,
                )
                self.assertTrue(checks["fs.read:project:assigned"].passed)
                self.assertTrue(checks["fs.write:project:assigned"].passed)
                self.assertEqual(
                    checks["fs.write:project:assigned"].observed,
                    (
                        ObservedEffect.ALLOW
                        if role.role == "engineer"
                        else ObservedEffect.DENY
                    ),
                )
                self.assertTrue(checks["fs.read:outside"].passed)
                self.assertTrue(checks["fs.write:outside"].passed)
        engineer = next(role for role in receipt.roles if role.role == "engineer")
        engineer_checks = {check.identifier: check for check in engineer.checks}
        self.assertEqual(
            engineer_checks["fs.write:project:assigned"].observed,
            ObservedEffect.ALLOW,
        )
        self.assertEqual(
            engineer_checks["fs.write:git-common:assigned"].observed,
            ObservedEffect.ALLOW,
        )
        document = json.loads(render_runtime_proof(receipt))
        self.assertEqual(document["receipt_digest"], receipt.receipt_digest)
        self.assertEqual(document["candidate_digest"], candidate.candidate_digest)

    def test_unexpected_project_write_fails_closed(self) -> None:
        candidate, snapshot = self.candidate()

        def violating_runner(
            command: tuple[str, ...],
            timeout: float,
        ) -> NativeCommandResult:
            result = self.passing_runner(command, timeout)
            document = json.loads(result.stdout)
            for check in document:
                if check["identifier"] == "fs.write:project:assigned":
                    check["observed"] = "ALLOW"
                    check["error_code"] = None
            return NativeCommandResult(0, json.dumps(document), "")

        receipt = prove_candidate(candidate, snapshot, runner=violating_runner)

        self.assertEqual(receipt.status, RuntimeProofStatus.SMOKE_FAILED)
        statuses = {role.role: role.status for role in receipt.roles}
        self.assertEqual(statuses["engineer"], RoleProofStatus.PROVEN)
        self.assertTrue(
            all(
                status is RoleProofStatus.SMOKE_FAILED
                for role, status in statuses.items()
                if role != "engineer"
            )
        )

    def test_malformed_or_failed_native_receipt_does_not_become_proof(self) -> None:
        candidate, snapshot = self.candidate()

        for native_result in (
            NativeCommandResult(0, "not-json", ""),
            NativeCommandResult(70, "", "sandbox startup failed"),
        ):
            with self.subTest(native_result=native_result):
                receipt = prove_candidate(
                    candidate,
                    snapshot,
                    runner=lambda command, timeout, value=native_result: value,
                )
                self.assertEqual(
                    receipt.status,
                    RuntimeProofStatus.SMOKE_FAILED,
                )
                dynamic = [
                    check
                    for role in receipt.roles
                    for check in role.checks
                    if check.operation is not ProofOperation.NATIVE_SPAWN
                    and check.identifier != "network.config"
                ]
                self.assertTrue(
                    all(check.assurance is AssuranceLevel.UNVERIFIED for check in dynamic)
                )

    def test_runner_failure_is_a_failed_receipt_not_an_engine_crash(self) -> None:
        candidate, snapshot = self.candidate()

        def failing_runner(
            command: tuple[str, ...],
            timeout: float,
        ) -> NativeCommandResult:
            del command, timeout
            raise RuntimeError("runner failed")

        receipt = prove_candidate(candidate, snapshot, runner=failing_runner)

        self.assertEqual(receipt.status, RuntimeProofStatus.SMOKE_FAILED)
        self.assertTrue(
            all(role.status is RoleProofStatus.SMOKE_FAILED for role in receipt.roles)
        )

    def test_denial_requires_a_native_sandbox_error_code(self) -> None:
        candidate, snapshot = self.candidate()

        def false_denial_runner(
            command: tuple[str, ...],
            timeout: float,
        ) -> NativeCommandResult:
            result = self.passing_runner(command, timeout)
            document = json.loads(result.stdout)
            denied = next(
                check for check in document if check["observed"] == "DENY"
            )
            denied["error_code"] = 111  # ECONNREFUSED is not sandbox denial.
            return NativeCommandResult(0, json.dumps(document), "")

        receipt = prove_candidate(candidate, snapshot, runner=false_denial_runner)

        self.assertEqual(receipt.status, RuntimeProofStatus.SMOKE_FAILED)
        self.assertTrue(
            any(
                check.observed is ObservedEffect.ERROR
                and check.assurance is AssuranceLevel.UNVERIFIED
                for role in receipt.roles
                for check in role.checks
            )
        )

    def test_model_observation_alone_never_satisfies_authority_proof(self) -> None:
        check = ProofCheck(
            "native_spawn.model_behavior",
            ProofOperation.NATIVE_SPAWN,
            None,
            "model behavior",
            ExpectedEffect.DENY,
            ObservedEffect.DENY,
            AssuranceLevel.MODEL_OBSERVED,
        )

        self.assertFalse(check.passed)

    def test_unavailable_exact_write_root_aborts_role_probe(self) -> None:
        candidate, snapshot = self.candidate()
        self.notebook.rmdir()
        calls = 0

        def counting_runner(
            command: tuple[str, ...],
            timeout: float,
        ) -> NativeCommandResult:
            nonlocal calls
            calls += 1
            return self.passing_runner(command, timeout)

        receipt = prove_candidate(candidate, snapshot, runner=counting_runner)

        self.assertEqual(receipt.status, RuntimeProofStatus.SMOKE_FAILED)
        supervisor = next(role for role in receipt.roles if role.role == "supervisor")
        self.assertEqual(supervisor.status, RoleProofStatus.SMOKE_FAILED)
        notebook_write = next(
            check
            for check in supervisor.checks
            if check.identifier == "fs.write:notebook:session"
        )
        self.assertEqual(notebook_write.observed, ObservedEffect.ERROR)
        self.assertEqual(notebook_write.assurance, AssuranceLevel.NATIVE_INTROSPECTED)
        self.assertEqual(calls, 3)

    def test_stale_candidate_stops_before_any_native_probe(self) -> None:
        candidate, snapshot = self.candidate()
        # Change a real observed field while retaining a valid snapshot shape.
        changed = DiscoverySnapshot(
            snapshot.project_root,
            snapshot.repositories,
            snapshot.harnesses,
            tuple(
                type(adapter)(
                    adapter.kind,
                    adapter.version + "-changed",
                    adapter.implementation_digest,
                )
                for adapter in snapshot.adapters
            ),
            snapshot.policy_sources,
            snapshot.existing_activation,
        )
        calls = 0

        def forbidden_runner(
            command: tuple[str, ...],
            timeout: float,
        ) -> NativeCommandResult:
            nonlocal calls
            calls += 1
            return self.passing_runner(command, timeout)

        receipt = prove_candidate(candidate, changed, runner=forbidden_runner)

        self.assertEqual(receipt.status, RuntimeProofStatus.STALE)
        self.assertEqual(receipt.roles, ())
        self.assertEqual(calls, 0)

    def test_native_runtime_canary_when_codex_is_available(self) -> None:
        executable = shutil.which("codex")
        if executable is None:
            self.skipTest("Codex CLI is not installed")
        executable = str(Path(executable).resolve(strict=True))
        probe = probe_codex(executable, cwd=str(self.project))
        if probe.status is not CodexProbeStatus.READY or probe.observation is None:
            self.skipTest(f"Codex permission profile is not ready: {probe.status.value}")
        candidate, snapshot = self.candidate(probe.observation)

        receipt = prove_candidate(candidate, snapshot)

        failures = {
            role.role: [
                (check.identifier, check.observed.value, check.error_code)
                for check in role.checks
                if not check.passed
            ]
            for role in receipt.roles
            if role.status is not RoleProofStatus.PROVEN
        }
        self.assertEqual(failures, {})
        self.assertEqual(receipt.status, RuntimeProofStatus.PROVEN)
        self.assertEqual(
            list(self.root.rglob(".herdr-runtime-proof-*")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
