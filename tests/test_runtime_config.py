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
    RuntimeConfigError,
    bind_role_launch,
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
            set(accepted.config.role_map),
            {"lead", "engineer", "reviewer", "supervisor"},
        )
        self.assertFalse(
            (self.project / ".orchestration/herdr-orchestrator.toml").exists()
        )

    def test_bind_role_replaces_proof_paths_with_exact_assignment_paths(self) -> None:
        self.accept_project()
        accepted = load_accepted_project(str(self.project))
        inbox = self.root / "run/reports/inbox/reviewer"
        inbox.mkdir(parents=True)

        launch = bind_role_launch(
            accepted.config,
            "reviewer",
            cwd=str(inbox),
            bindings={
                "workspace": str(self.project),
                "git_common": str(self.project / ".git"),
                "evidence": str(inbox),
            },
        )

        authority = {resource: (path, access) for resource, path, access in launch.filesystem}
        self.assertEqual(
            authority["evidence:assignment"],
            (str(inbox), "write"),
        )
        self.assertEqual(
            authority["project:assigned"],
            (str(self.project), "read"),
        )
        self.assertNotIn(str(self.evidence), launch.arguments)
        self.assertIn(str(inbox), "\n".join(launch.arguments))
        self.assertFalse(any("agents.enabled=true" in item for item in launch.arguments))

    def test_unknown_or_extra_binding_fails_closed(self) -> None:
        self.accept_project()
        config = load_accepted_project(str(self.project)).config

        with self.assertRaises(RuntimeConfigError):
            bind_role_launch(
                config,
                "reviewer",
                cwd=str(self.project),
                bindings={"workspace": str(self.project)},
            )

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
        publish_accepted_setup(project, omit_plan_role="reviewer")

        with self.assertRaisesRegex(RuntimeConfigError, "role set"):
            load_accepted_project(str(project))


if __name__ == "__main__":
    unittest.main()
