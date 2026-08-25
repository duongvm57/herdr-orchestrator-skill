from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
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
    AdapterObservation,
    BindingChoice,
    CandidateCompileStatus,
    CandidateRejectionCode,
    DecisionValueKind,
    DiscoveryFailure,
    DiscoveryFailureCode,
    FreshnessStatus,
    HarnessObservation,
    HarnessStatus,
    HumanDecisions,
    ModelBinding,
    NativeAgentPolicy,
    PolicyAnswer,
    ProvenanceKind,
    RoleAuthorityDecision,
    RoleCompilation,
    check_candidate_freshness,
    compile_setup_candidate,
    discover_setup,
    normalize_codex_harness,
    observe_codex_adapter,
    render_discovery_snapshot,
    render_setup_candidate,
)
from herdr_setup.codex_authority import (  # noqa: E402
    AssuranceLevel,
    CodexModelObservation,
    CodexObservation,
    CodexVersion,
    RuntimeBindingContext,
    RuntimePathBinding,
    compile_codex,
)


READ_PROJECT = Capability("fs.read", "project:repo")
READ_CONTROL = Capability("fs.read", "control:lead")
WRITE_CONTROL = Capability("fs.write", "control:lead")
READ_RUNTIME = Capability("fs.read", "runtime:codex")
WRITE_PROJECT = Capability("fs.write", "project:repo")
NETWORK = Capability("network.egress")
NATIVE_SPAWN = Capability("native_spawn")


def run(*arguments: str, cwd: Path | None = None) -> None:
    subprocess.run(
        arguments,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


class SetupCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="herdr-candidate-test-")
        self.project = Path(self.temporary.name).resolve() / "project"
        self.project.mkdir()
        run("git", "init", "-q", str(self.project))
        (self.project / "AGENTS.md").write_text("Project policy\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def observation(
        self,
        *,
        cwd: Path | None = None,
        models: tuple[CodexModelObservation, ...] | None = None,
    ) -> CodexObservation:
        return CodexObservation(
            executable="/opt/codex/bin/codex",
            version=CodexVersion(0, 149, 1),
            runtime_root="/opt/codex",
            bound_cwd=str(cwd or self.project),
            models=models
            or (
                CodexModelObservation("gpt-5.6-sol", ("high", "xhigh")),
                CodexModelObservation("gpt-5.6-terra", ("medium", "high")),
                CodexModelObservation("gpt-5.6-luna", ("low", "medium")),
            ),
            permission_profiles=True,
            permission_profile_assurance=AssuranceLevel.RUNTIME_PROBED,
            native_spawn_control=True,
            native_spawn_assurance=AssuranceLevel.STATIC_PROVEN,
            network_control=True,
            network_assurance=AssuranceLevel.RUNTIME_PROBED,
            legacy_sandbox_settings=False,
        )

    def snapshot(
        self,
        observation: CodexObservation | None = None,
        *,
        extra_harnesses: tuple[HarnessObservation, ...] = (),
        extra_adapters: tuple[AdapterObservation, ...] = (),
    ):
        observed = observation or self.observation()
        return discover_setup(
            str(self.project),
            harnesses=(normalize_codex_harness((observed,)), *extra_harnesses),
            adapters=(observe_codex_adapter(), *extra_adapters),
        )

    def lead_compilation(
        self,
        observation: CodexObservation,
        *,
        model: str = "gpt-5.6-luna",
        effort: str = "medium",
        explicit: bool = False,
    ) -> tuple[RoleCompilation, AuthorityPolicy, Binding]:
        effective = frozenset(
            {READ_PROJECT, READ_CONTROL, WRITE_CONTROL, READ_RUNTIME}
        )
        requirement = Requirement(
            role="lead",
            must_have=effective,
            must_not_have=frozenset({WRITE_PROJECT, NETWORK, NATIVE_SPAWN}),
            may_have=frozenset(),
        )
        policy = AuthorityPolicy(permitted=effective, must_not_have=frozenset())
        selected = Binding(
            "codex-lead",
            "codex",
            AuthorityEnvelope(effective),
        )
        eligibility = evaluate_eligibility(
            solve_feasibility(requirement, (selected,)),
            policy,
        )
        selection = select_binding(
            eligibility,
            explicit_binding_id=selected.identifier if explicit else None,
        )
        context = RuntimeBindingContext(
            cwd=str(self.project),
            resources=(
                RuntimePathBinding("project:repo", str(self.project)),
                RuntimePathBinding(
                    "control:lead",
                    str(self.project / ".orchestration"),
                ),
            ),
            model=model,
            reasoning_effort=effort,
        )
        compiled = compile_codex(selection, context, observation)
        return (
            RoleCompilation("lead", selection, context, observation, compiled),
            policy,
            selected,
        )

    def decisions(
        self,
        policy: AuthorityPolicy,
        *,
        model: str = "gpt-5.6-luna",
        effort: str = "medium",
        binding_choices: tuple[BindingChoice, ...] = (),
        commit_authority: str = "human_only",
    ) -> HumanDecisions:
        return HumanDecisions(
            native_agent_policy=NativeAgentPolicy.DISABLED,
            role_authority=(RoleAuthorityDecision("lead", policy),),
            model_bindings=(ModelBinding("lead", "codex", model, effort),),
            binding_choices=binding_choices,
            policy_answers=(
                PolicyAnswer(
                    "commit_authority",
                    DecisionValueKind.CHOICE,
                    commit_authority,
                ),
            ),
        )

    def compile_candidate(
        self,
        *,
        explicit: bool = False,
        commit_authority: str = "human_only",
    ):
        observation = self.observation()
        snapshot = self.snapshot(observation)
        compilation, policy, selected = self.lead_compilation(
            observation,
            explicit=explicit,
        )
        choices = (
            (BindingChoice("lead", selected.identifier),) if explicit else ()
        )
        decisions = self.decisions(
            policy,
            binding_choices=choices,
            commit_authority=commit_authority,
        )
        result = compile_setup_candidate(snapshot, decisions, (compilation,))
        self.assertEqual(result.status, CandidateCompileStatus.COMPILED)
        self.assertIsNotNone(result.candidate)
        return result.candidate

    def test_discovery_records_nested_repositories_and_exact_git_common_dirs(self) -> None:
        backend = self.project / "backend"
        backend.mkdir()
        run("git", "init", "-q", str(backend))

        snapshot = self.snapshot()

        self.assertEqual(
            [(repo.identifier, repo.relative_path) for repo in snapshot.repositories],
            [("root", "."), ("backend", "backend")],
        )
        root, nested = snapshot.repositories
        self.assertEqual(root.git_common_dir, str(self.project / ".git"))
        self.assertEqual(nested.git_common_dir, str(backend / ".git"))
        self.assertNotEqual(root.git_common_dir, nested.git_common_dir)
        rendered = json.loads(render_discovery_snapshot(snapshot))
        self.assertEqual(rendered["discovery_digest"], snapshot.discovery_digest)

    def test_discovery_records_a_linked_worktree_and_its_shared_common_dir(self) -> None:
        run("git", "-C", str(self.project), "config", "user.email", "test@example.com")
        run("git", "-C", str(self.project), "config", "user.name", "Test")
        run(
            "git",
            "-C",
            str(self.project),
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "initial",
        )
        linked = self.project / "linked-worktree"
        run(
            "git",
            "-C",
            str(self.project),
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-test",
            str(linked),
        )

        snapshot = self.snapshot()

        repositories = {repo.relative_path: repo for repo in snapshot.repositories}
        self.assertEqual(set(repositories), {".", "linked-worktree"})
        self.assertEqual(
            repositories["linked-worktree"].git_common_dir,
            repositories["."].git_common_dir,
        )
        self.assertNotEqual(
            repositories["linked-worktree"].git_dir,
            repositories["."].git_dir,
        )

    def test_discovery_digest_is_canonical_across_inventory_order(self) -> None:
        pi = HarnessObservation("pi", HarnessStatus.NOT_INSTALLED)
        pi_adapter = AdapterObservation("pi", "0", "0" * 64)
        observation = self.observation()
        first = self.snapshot(
            observation,
            extra_harnesses=(pi,),
            extra_adapters=(pi_adapter,),
        )
        second = discover_setup(
            str(self.project),
            harnesses=(pi, normalize_codex_harness((observation,))),
            adapters=(pi_adapter, observe_codex_adapter()),
        )

        self.assertEqual(first.discovery_digest, second.discovery_digest)
        self.assertEqual(render_discovery_snapshot(first), render_discovery_snapshot(second))

    def test_activation_and_policy_sources_are_content_observations(self) -> None:
        absent = self.snapshot()
        self.assertFalse(absent.existing_activation.exists)
        self.assertEqual(
            [source.relative_path for source in absent.policy_sources],
            ["AGENTS.md"],
        )

        setup_root = self.project / ".orchestration/setup"
        setup_root.mkdir(parents=True)
        (setup_root / "current.json").write_text("{}\n", encoding="utf-8")
        present = self.snapshot()

        self.assertTrue(present.existing_activation.exists)
        self.assertNotEqual(absent.discovery_digest, present.discovery_digest)

    def test_policy_symlink_fails_closed_instead_of_hashing_outside_project(self) -> None:
        outside = Path(self.temporary.name) / "outside-policy"
        outside.write_text("outside\n", encoding="utf-8")
        (self.project / "CLAUDE.md").symlink_to(outside)

        with self.assertRaises(DiscoveryFailure) as caught:
            self.snapshot()

        self.assertEqual(caught.exception.code, DiscoveryFailureCode.UNSUPPORTED_FILE)

    def test_human_selected_model_is_validated_without_quality_ranking(self) -> None:
        observation = self.observation()
        snapshot = self.snapshot(observation)
        compilation, policy, _ = self.lead_compilation(
            observation,
            model="gpt-5.6-luna",
            effort="medium",
        )

        result = compile_setup_candidate(
            snapshot,
            self.decisions(policy, model="gpt-5.6-luna", effort="medium"),
            (compilation,),
        )

        self.assertEqual(result.status, CandidateCompileStatus.COMPILED)
        self.assertEqual(result.candidate.model_bindings[0].model, "gpt-5.6-luna")

    def test_candidate_binds_digests_structured_outputs_and_provenance(self) -> None:
        candidate = self.compile_candidate(explicit=True)
        document = json.loads(render_setup_candidate(candidate))

        self.assertEqual(document["candidate_digest"], candidate.candidate_digest)
        self.assertEqual(document["discovery_digest"], candidate.discovery_digest)
        self.assertEqual(
            document["human_decisions_digest"],
            candidate.human_decisions_digest,
        )
        launch = document["authority_templates"][0]["native_launch_spec"]
        self.assertEqual(launch["model"], "gpt-5.6-luna")
        self.assertFalse(launch["native_agents_enabled"])
        self.assertFalse(launch["network_enabled"])
        provenance = {
            record.subject: record.kind for record in candidate.provenance
        }
        self.assertEqual(provenance["/discovery"], ProvenanceKind.OBSERVED)
        self.assertEqual(
            provenance["/discovery/policy_sources/0"],
            ProvenanceKind.OBSERVED,
        )
        self.assertEqual(
            provenance["/compiled_policy/native_agent_policy"],
            ProvenanceKind.DEFAULTED,
        )
        self.assertEqual(
            provenance["/model_bindings/lead"],
            ProvenanceKind.HUMAN_APPROVED,
        )
        self.assertEqual(
            provenance["/roles/lead/selected_binding"],
            ProvenanceKind.HUMAN_APPROVED,
        )
        self.assertEqual(
            provenance["/roles/lead/native_launch_spec"],
            ProvenanceKind.INFERRED,
        )

    def test_candidate_and_nested_domain_values_are_immutable(self) -> None:
        candidate = self.compile_candidate()

        with self.assertRaises(FrozenInstanceError):
            candidate.candidate_digest = "0" * 64
        with self.assertRaises(FrozenInstanceError):
            candidate.model_bindings[0].model = "gpt-5.6-sol"

    def test_candidate_digest_changes_with_a_human_policy_answer(self) -> None:
        human_only = self.compile_candidate(commit_authority="human_only")
        engineer = self.compile_candidate(commit_authority="assigned_engineer")

        self.assertNotEqual(
            human_only.human_decisions_digest,
            engineer.human_decisions_digest,
        )
        self.assertNotEqual(human_only.candidate_digest, engineer.candidate_digest)

    def test_whole_snapshot_change_marks_candidate_stale(self) -> None:
        candidate = self.compile_candidate()
        current = self.snapshot()
        self.assertEqual(
            check_candidate_freshness(candidate, current).status,
            FreshnessStatus.CURRENT,
        )

        (self.project / "AGENTS.md").write_text("Changed policy\n", encoding="utf-8")
        changed = self.snapshot()

        receipt = check_candidate_freshness(candidate, changed)
        self.assertEqual(receipt.status, FreshnessStatus.STALE)
        self.assertEqual(receipt.candidate_discovery_digest, candidate.discovery_digest)
        self.assertEqual(receipt.current_discovery_digest, changed.discovery_digest)

    def test_explicit_selector_requires_a_matching_human_binding_choice(self) -> None:
        observation = self.observation()
        snapshot = self.snapshot(observation)
        compilation, policy, _ = self.lead_compilation(observation, explicit=True)

        result = compile_setup_candidate(
            snapshot,
            self.decisions(policy),
            (compilation,),
        )

        self.assertEqual(result.status, CandidateCompileStatus.STATIC_INVALID)
        self.assertEqual(
            {rejection.code for rejection in result.rejections},
            {CandidateRejectionCode.BINDING_CHOICE_MISMATCH},
        )

    def test_model_or_runtime_not_in_snapshot_fails_capability_validation(self) -> None:
        observed = self.observation()
        snapshot = self.snapshot(observed)
        unobserved_models = (
            *observed.models,
            CodexModelObservation("provider-new-model", ("medium",)),
        )
        unobserved = self.observation(models=unobserved_models)
        compilation, policy, _ = self.lead_compilation(
            unobserved,
            model="provider-new-model",
            effort="medium",
        )

        result = compile_setup_candidate(
            snapshot,
            self.decisions(policy, model="provider-new-model", effort="medium"),
            (compilation,),
        )

        self.assertEqual(result.status, CandidateCompileStatus.CAPABILITY_INVALID)
        codes = {rejection.code for rejection in result.rejections}
        self.assertIn(CandidateRejectionCode.MODEL_NOT_DISCOVERED, codes)
        self.assertIn(CandidateRejectionCode.RUNTIME_OBSERVATION_STALE, codes)

    def test_lead_is_required_and_role_sets_must_match(self) -> None:
        snapshot = self.snapshot()
        decisions = HumanDecisions(
            NativeAgentPolicy.DISABLED,
            role_authority=(),
            model_bindings=(),
        )

        result = compile_setup_candidate(snapshot, decisions, ())

        self.assertEqual(result.status, CandidateCompileStatus.STATIC_INVALID)
        self.assertEqual(
            {rejection.code for rejection in result.rejections},
            {CandidateRejectionCode.LEAD_REQUIRED},
        )


if __name__ == "__main__":
    unittest.main()
