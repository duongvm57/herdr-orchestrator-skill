from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/herdr-orchestrator/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from herdr_runtime import (  # noqa: E402
    LaunchRepositoryBinding,
    ModelSelection,
    RuntimeConfigError,
    bind_launch,
    load_accepted_project,
)
from herdr_setup.acceptance import (  # noqa: E402
    AcceptanceStatus,
    accept_setup_publication,
    compile_setup_publication,
)
from herdr_setup.runtime_proof import prove_candidate  # noqa: E402
from tests import test_setup_runtime_proof as runtime_fixture  # noqa: E402
from tests.accepted_fixture import publish_accepted_setup  # noqa: E402


class RuntimeConfigTests(unittest.TestCase):
    setUp = runtime_fixture.SetupRuntimeProofTests.setUp
    tearDown = runtime_fixture.SetupRuntimeProofTests.tearDown
    observation = runtime_fixture.SetupRuntimeProofTests.observation
    candidate = runtime_fixture.SetupRuntimeProofTests.candidate
    passing_runner = staticmethod(runtime_fixture.SetupRuntimeProofTests.passing_runner)

    def accept_project(self):
        candidate, snapshot = self.candidate()
        proof = prove_candidate(candidate, snapshot, runner=self.passing_runner)
        compiled = compile_setup_publication(candidate, proof)
        self.assertIsNotNone(compiled.publication)
        result = accept_setup_publication(
            compiled.publication,
            snapshot,
            candidate.candidate_digest,
        )
        self.assertEqual(result.status, AcceptanceStatus.ACCEPTED)
        return candidate, result

    def test_load_verifies_the_active_generation_and_projects_runtime_templates(self) -> None:
        candidate, result = self.accept_project()

        accepted = load_accepted_project(str(self.project))

        self.assertEqual(accepted.config.candidate_digest, candidate.candidate_digest)
        self.assertEqual(accepted.publication_digest, result.receipt.publication_digest)
        self.assertEqual(accepted.config.live_language, "Vietnamese")
        self.assertEqual(accepted.config.artifact_language, "English")
        self.assertEqual(
            set(accepted.config.route_map),
            {"lead", "peer", "supervisor", "fallback"},
        )
        self.assertFalse(
            (self.project / ".orchestration/herdr-orchestrator.toml").exists()
        )

    def test_bind_launch_replaces_proof_paths_with_exact_assignment_paths(self) -> None:
        self.accept_project()
        accepted = load_accepted_project(str(self.project))
        inbox = self.root / "run/reports/inbox/reviewer"
        inbox.mkdir(parents=True)

        launch = bind_launch(
            accepted.config,
            profile="peer",
            disposition="reviewer",
            authority="project_readonly",
            cwd=str(inbox),
            repositories=(LaunchRepositoryBinding(str(self.project), str(self.project / ".git")),),
            evidence_root=str(inbox),
        )

        authority = {resource: (path, access) for resource, path, access in launch.filesystem}
        self.assertEqual(
            authority["evidence:assignment"],
            (str(inbox), "write"),
        )
        self.assertEqual(
            authority["project:assigned.0"],
            (str(self.project), "read"),
        )
        self.assertNotIn(str(self.evidence), launch.arguments)
        self.assertIn(str(inbox), "\n".join(launch.arguments))
        self.assertFalse(any("agents.enabled=true" in item for item in launch.arguments))

    def test_unknown_or_extra_binding_fails_closed(self) -> None:
        self.accept_project()
        config = load_accepted_project(str(self.project)).config

        with self.assertRaises(RuntimeConfigError):
            bind_launch(
                config,
                profile="peer",
                disposition="reviewer",
                authority="project_writable",
                cwd=str(self.project),
                repositories=(),
            )

    def test_model_routing_precedence_never_changes_peer_authority(self) -> None:
        self.accept_project()
        config = load_accepted_project(str(self.project)).config
        inbox = self.root / "route-inbox"
        inbox.mkdir()
        repository = LaunchRepositoryBinding(str(self.project), str(self.project / ".git"))
        accepted_model = ModelSelection("codex", "human-selected-model", "medium")

        fallback = bind_launch(
            config,
            profile="peer",
            disposition="custom_audit",
            authority="project_readonly",
            cwd=str(inbox),
            repositories=(repository,),
            evidence_root=str(inbox),
        )
        routed = bind_launch(
            config,
            profile="peer",
            disposition="reviewer",
            authority="project_readonly",
            cwd=str(inbox),
            repositories=(repository,),
            evidence_root=str(inbox),
            runtime_route=accepted_model,
        )
        overridden = bind_launch(
            config,
            profile="peer",
            disposition="reviewer",
            authority="project_readonly",
            cwd=str(inbox),
            repositories=(repository,),
            evidence_root=str(inbox),
            model_override=accepted_model,
            runtime_route=accepted_model,
        )

        self.assertEqual(fallback.route_source, "global_fallback")
        self.assertEqual(routed.route_source, "lead_runtime_route")
        self.assertEqual(overridden.route_source, "human_override")
        for launch in (fallback, routed, overridden):
            access = {resource: value for resource, _path, value in launch.filesystem}
            self.assertEqual(access["project:assigned.0"], "read")
            self.assertEqual(launch.authority_template, "peer_readonly")

    def test_one_launch_can_bind_multiple_discovered_repositories(self) -> None:
        backend = self.project / "backend"
        backend.mkdir()
        import subprocess
        subprocess.run(("git", "init", "-q", str(backend)), check=True)
        self.accept_project()
        config = load_accepted_project(str(self.project)).config
        inbox = self.root / "multi-inbox"
        inbox.mkdir()

        launch = bind_launch(
            config,
            profile="peer",
            disposition="engineer",
            authority="project_writable",
            cwd=str(self.project),
            repositories=(
                LaunchRepositoryBinding(str(self.project), str(self.project / ".git")),
                LaunchRepositoryBinding(str(backend), str(backend / ".git")),
            ),
            evidence_root=str(inbox),
        )

        access = {resource: (path, mode) for resource, path, mode in launch.filesystem}
        self.assertEqual(access["project:assigned.0"], (str(self.project), "write"))
        self.assertEqual(access["project:assigned.1"], (str(backend), "write"))

    def test_tampered_generation_is_never_loaded(self) -> None:
        self.accept_project()
        current = json.loads(
            (self.project / ".orchestration/setup/current.json").read_bytes()
        )
        config = (
            self.project
            / ".orchestration/setup"
            / current["generation"]
            / "herdr-orchestrator.toml"
        )
        config.write_bytes(config.read_bytes() + b"\n")

        with self.assertRaises(RuntimeConfigError):
            load_accepted_project(str(self.project))

    def test_self_consistent_but_failed_runtime_proof_is_not_accepted(self) -> None:
        project = self.root / "failed-proof-project"
        project.mkdir()
        publish_accepted_setup(project, proof_status="SMOKE_FAILED")

        with self.assertRaisesRegex(RuntimeConfigError, "does not prove"):
            load_accepted_project(str(project))

    def test_self_consistent_but_incomplete_setup_plan_is_not_accepted(self) -> None:
        project = self.root / "incomplete-plan-project"
        project.mkdir()
        publish_accepted_setup(project, omit_plan_role="peer_readonly")

        with self.assertRaisesRegex(RuntimeConfigError, "role set"):
            load_accepted_project(str(project))


if __name__ == "__main__":
    unittest.main()
