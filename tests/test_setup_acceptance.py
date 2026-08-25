from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/herdr-orchestrator/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from herdr_setup.acceptance import (  # noqa: E402
    AcceptanceRejectionCode,
    AcceptanceStatus,
    PublicationCompileStatus,
    accept_setup_publication,
    compile_setup_publication,
    render_acceptance_receipt,
)
from herdr_setup.candidate import (  # noqa: E402
    discover_setup,
    normalize_codex_harness,
    observe_codex_adapter,
)
from herdr_setup.runtime_proof import RuntimeProofStatus, prove_candidate  # noqa: E402
from tests import test_setup_runtime_proof as runtime_fixture  # noqa: E402


def run(*arguments: str) -> None:
    subprocess.run(arguments, text=True, capture_output=True, check=True)


class SetupAcceptanceTests(unittest.TestCase):
    observation = runtime_fixture.SetupRuntimeProofTests.observation
    candidate = runtime_fixture.SetupRuntimeProofTests.candidate
    passing_runner = staticmethod(
        runtime_fixture.SetupRuntimeProofTests.passing_runner
    )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="herdr-accept-test-")
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

    def prepared(self):
        observed = self.observation()
        candidate, snapshot = self.candidate(observed)
        proof = prove_candidate(candidate, snapshot, runner=self.passing_runner)
        self.assertEqual(proof.status, RuntimeProofStatus.PROVEN)
        compiled = compile_setup_publication(candidate, proof)
        self.assertEqual(compiled.status, PublicationCompileStatus.PREPARED)
        self.assertIsNotNone(compiled.publication)
        return observed, candidate, snapshot, compiled.publication

    def rediscover(self, observed):
        return discover_setup(
            str(self.project),
            harnesses=(normalize_codex_harness((observed,)),),
            adapters=(observe_codex_adapter(),),
        )

    def test_compiler_projects_exact_candidate_and_proof_into_artifacts(self) -> None:
        _, candidate, _, publication = self.prepared()
        artifacts = {artifact.relative_path: artifact for artifact in publication.artifacts}

        self.assertEqual(
            set(artifacts),
            {
                "herdr-orchestrator.toml",
                "runtime-proof.json",
                "setup-plan.json",
                "workspace-protocol.md",
            },
        )
        config = tomllib.loads(artifacts["herdr-orchestrator.toml"].content.decode())
        self.assertEqual(config["candidate_digest"], candidate.candidate_digest)
        self.assertEqual(
            set(config["roles"]),
            {"lead", "engineer", "reviewer", "supervisor"},
        )
        self.assertFalse(config["roles"]["reviewer"]["native_agents_enabled"])
        plan = json.loads(artifacts["setup-plan.json"].content)
        proof = json.loads(artifacts["runtime-proof.json"].content)
        self.assertEqual(plan["candidate_digest"], candidate.candidate_digest)
        self.assertEqual(proof["candidate_digest"], candidate.candidate_digest)
        self.assertIn(
            candidate.candidate_digest,
            artifacts["workspace-protocol.md"].content.decode(),
        )

    def test_failed_runtime_proof_cannot_prepare_a_publication(self) -> None:
        candidate, snapshot = self.candidate()
        failed = prove_candidate(
            candidate,
            snapshot,
            runner=lambda command, timeout: type(self).passing_runner(
                command[:-1] + ("not-json",), timeout
            ),
        )

        compiled = compile_setup_publication(candidate, failed)

        self.assertEqual(failed.status, RuntimeProofStatus.SMOKE_FAILED)
        self.assertEqual(compiled.status, PublicationCompileStatus.SMOKE_FAILED)
        self.assertIsNone(compiled.publication)

    def test_proof_for_another_candidate_is_a_static_identity_failure(self) -> None:
        observed = self.observation()
        first, snapshot = self.candidate(observed)
        proof = prove_candidate(first, snapshot, runner=self.passing_runner)
        (self.project / "AGENTS.md").write_text("changed facts\n", encoding="utf-8")
        second, _ = self.candidate(observed)

        compiled = compile_setup_publication(second, proof)

        self.assertEqual(compiled.status, PublicationCompileStatus.STATIC_INVALID)
        self.assertIsNone(compiled.publication)

    def test_human_must_name_the_exact_candidate_digest_before_any_write(self) -> None:
        _, _, snapshot, publication = self.prepared()

        result = accept_setup_publication(publication, snapshot, "0" * 64)

        self.assertEqual(result.status, AcceptanceStatus.AWAITING_ACCEPTANCE)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.CANDIDATE_DIGEST_MISMATCH,
        )
        self.assertFalse((self.project / ".orchestration").exists())

    def test_acceptance_atomically_activates_one_complete_immutable_generation(self) -> None:
        _, candidate, snapshot, publication = self.prepared()

        result = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.ACCEPTED)
        self.assertIsNotNone(result.receipt)
        assert result.receipt is not None
        current = self.project / ".orchestration/setup/current.json"
        activation = json.loads(current.read_bytes())
        self.assertEqual(activation["candidate_digest"], candidate.candidate_digest)
        self.assertEqual(
            activation["acceptance_receipt_digest"],
            result.receipt.receipt_digest,
        )
        generation = self.project / ".orchestration/setup" / result.receipt.generation
        self.assertEqual(
            {path.name for path in generation.iterdir()},
            {
                "acceptance-receipt.json",
                "herdr-orchestrator.toml",
                "publication-manifest.json",
                "runtime-proof.json",
                "setup-plan.json",
                "workspace-protocol.md",
            },
        )
        for artifact in publication.artifacts:
            self.assertEqual(
                hashlib.sha256((generation / artifact.relative_path).read_bytes()).hexdigest(),
                artifact.sha256,
            )
        receipt_document = json.loads(render_acceptance_receipt(result.receipt))
        self.assertEqual(receipt_document["status"], "ACCEPTED")
        self.assertEqual(receipt_document["receipt_digest"], result.receipt.receipt_digest)
        self.assertFalse(
            (self.project / ".orchestration/herdr-orchestrator.toml").exists()
        )
        self.assertFalse(
            (self.project / ".orchestration/workspace-protocol.md").exists()
        )

    def test_retry_after_acceptance_is_idempotent_with_a_new_snapshot(self) -> None:
        observed, candidate, snapshot, publication = self.prepared()
        first = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )
        rediscovered = self.rediscover(observed)

        second = accept_setup_publication(
            publication,
            rediscovered,
            candidate.candidate_digest,
        )

        self.assertEqual(first.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(second.status, AcceptanceStatus.ACCEPTED)
        self.assertEqual(first.receipt, second.receipt)
        generations = self.project / ".orchestration/setup/generations"
        self.assertEqual(len(tuple(generations.iterdir())), 1)

    def test_changed_discovery_stops_before_publication(self) -> None:
        observed, candidate, _, publication = self.prepared()
        (self.project / "AGENTS.md").write_text("new policy\n", encoding="utf-8")
        changed = self.rediscover(observed)

        result = accept_setup_publication(
            publication,
            changed,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.STALE)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.DISCOVERY_STALE,
        )
        self.assertFalse((self.project / ".orchestration/setup").exists())

    def test_cas_rejects_activation_created_after_discovery(self) -> None:
        _, candidate, snapshot, publication = self.prepared()
        setup_root = self.project / ".orchestration/setup"
        setup_root.mkdir(parents=True)
        (setup_root / "current.json").write_text("{}\n", encoding="utf-8")

        result = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.STALE)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.CURRENT_STATE_CHANGED,
        )
        self.assertEqual((setup_root / "current.json").read_text(), "{}\n")

    def test_live_rediscovery_detects_a_policy_added_after_snapshot(self) -> None:
        _, candidate, snapshot, publication = self.prepared()
        (self.project / "AGENTS.md").write_text("late policy\n", encoding="utf-8")

        result = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.STALE)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.CURRENT_STATE_CHANGED,
        )
        self.assertFalse((self.project / ".orchestration/setup").exists())

    def test_symlinked_publication_root_is_rejected(self) -> None:
        _, candidate, snapshot, publication = self.prepared()
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / ".orchestration").symlink_to(outside, target_is_directory=True)

        result = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.STATIC_INVALID)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.PUBLISH_TARGET_UNSAFE,
        )
        self.assertEqual(tuple(outside.iterdir()), ())

    def test_interrupted_activation_leaves_only_a_complete_inactive_generation(self) -> None:
        _, candidate, snapshot, publication = self.prepared()

        with patch(
            "herdr_setup.acceptance.os.replace",
            side_effect=OSError(5, "injected activation failure"),
        ):
            failed = accept_setup_publication(
                publication,
                snapshot,
                candidate.candidate_digest,
            )

        self.assertEqual(failed.status, AcceptanceStatus.STATIC_INVALID)
        self.assertEqual(
            failed.rejections[0].code,
            AcceptanceRejectionCode.PUBLICATION_IO_FAILED,
        )
        self.assertFalse(
            (self.project / ".orchestration/setup/current.json").exists()
        )
        generation = (
            self.project
            / ".orchestration/setup/generations"
            / publication.publication_digest
        )
        self.assertTrue(generation.is_dir())
        self.assertFalse(any(
            path.name.startswith(".current-")
            for path in (self.project / ".orchestration/setup").iterdir()
        ))

        retried = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )
        self.assertEqual(retried.status, AcceptanceStatus.ACCEPTED)

    def test_conflicting_preexisting_generation_fails_closed(self) -> None:
        _, candidate, snapshot, publication = self.prepared()
        generation = (
            self.project
            / ".orchestration/setup/generations"
            / publication.publication_digest
        )
        generation.mkdir(parents=True)
        (generation / "junk").write_text("conflict", encoding="utf-8")

        result = accept_setup_publication(
            publication,
            snapshot,
            candidate.candidate_digest,
        )

        self.assertEqual(result.status, AcceptanceStatus.STATIC_INVALID)
        self.assertEqual(
            result.rejections[0].code,
            AcceptanceRejectionCode.GENERATION_CONFLICT,
        )
        self.assertFalse(
            (self.project / ".orchestration/setup/current.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
