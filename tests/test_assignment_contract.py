from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py"


def assignment_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "assignment_id": "lead-01:peer-01",
        "role": "peer",
        "parent": {"role": "lead", "id": "lead-01"},
        "owner": "peer-01",
        "objective": "Review the exact candidate without modifying it.",
        "owned_scope": [],
        "exclusions": ["Do not change project files."],
        "authority": "read-only",
        "disposition": "Reviewer",
        "recipe": "review",
        "verification": ["Inspect the exact Git candidate."],
        "dependencies": [],
        "languages": {"live": "Vietnamese", "artifact": "English"},
        "topology_rationale": "Independent falsification changes the verdict.",
        "candidate": {"kind": "git_commit", "value": "a" * 40},
    }
    document.update(changes)
    return document


class AssignmentContractTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            check=False,
            text=True,
            capture_output=True,
        )

    def git_repository(self, root: Path) -> tuple[Path, str]:
        repository = root / "repository"
        repository.mkdir()
        for command in (
            ("git", "init", "-q", str(repository)),
            ("git", "-C", str(repository), "config", "user.email", "test@example.invalid"),
            ("git", "-C", str(repository), "config", "user.name", "Contract Test"),
        ):
            subprocess.run(command, check=True, capture_output=True, text=True)
        (repository / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(("git", "-C", str(repository), "add", "base.txt"), check=True, capture_output=True, text=True)
        subprocess.run(("git", "-C", str(repository), "commit", "-qm", "base"), check=True, capture_output=True, text=True)
        commit = subprocess.run(("git", "-C", str(repository), "rev-parse", "HEAD"), check=True, capture_output=True, text=True).stdout.strip()
        return repository, commit

    def test_assignment_is_inspectable_and_parentage_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assignment = Path(temporary) / "assignment.json"
            assignment.write_text(json.dumps(assignment_document()), encoding="utf-8")

            completed = self.run_cli("validate-assignment", "--assignment", str(assignment))

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["assignment_id"], "lead-01:peer-01")
            self.assertEqual(result["parent"], {"role": "lead", "id": "lead-01"})
            self.assertEqual(result["owner"], "peer-01")
            self.assertEqual(result["disposition"], "Reviewer")
            self.assertEqual(result["recipe"], "review")
            self.assertEqual(result["languages"], {"artifact": "English", "live": "Vietnamese"})

            assignment.write_text(completed.stdout, encoding="utf-8")
            round_trip = self.run_cli("validate-assignment", "--assignment", str(assignment))
            self.assertEqual(round_trip.returncode, 0, round_trip.stderr)
            self.assertEqual(json.loads(round_trip.stdout), result)

    def test_role_disposition_and_recipe_are_separate_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            path.write_text(json.dumps(assignment_document(disposition="Peer")), encoding="utf-8")

            completed = self.run_cli("validate-assignment", "--assignment", str(path))

            self.assertEqual(completed.returncode, 2)
            self.assertIn("must describe work, not repeat role=peer", completed.stderr)

    def test_owner_is_the_assigned_peer_not_the_delegating_lead(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            path.write_text(json.dumps(assignment_document(owner="lead-01")), encoding="utf-8")

            completed = self.run_cli("validate-assignment", "--assignment", str(path))

            self.assertEqual(completed.returncode, 2)
            self.assertIn("assigned Peer", completed.stderr)

    def test_renderer_rejects_self_owned_assignment_before_dispatch_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment, profile, protocol, output = root / "assignment.json", root / "peer.md", root / "protocol.md", root / "prompt.md"
            assignment.write_text(json.dumps(assignment_document(owner="lead-01")), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("Applicable protocol\n", encoding="utf-8")

            completed = self.run_cli(
                "render-assignment", "--assignment", str(assignment), "--role-profile", str(profile),
                "--applicable-protocol", str(protocol), "--output", str(output),
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("assigned Peer", completed.stderr)
            self.assertFalse(output.exists())

    def test_prompt_renderer_preserves_assignment_text_without_runtime_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment = root / "assignment.json"
            profile = root / "peer.md"
            protocol = root / "protocol.md"
            output = root / "prompt.md"
            objective = "  literal $herdr-orchestrator ' \" `x` $() \\nnext line  "
            document = assignment_document(objective=objective)
            assignment.write_text(json.dumps(document), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("Applicable protocol\n", encoding="utf-8")

            completed = self.run_cli(
                "render-assignment", "--assignment", str(assignment), "--role-profile", str(profile),
                "--applicable-protocol", str(protocol), "--output", str(output),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            rendered = output.read_text(encoding="utf-8")
            encoded = rendered.split("```json\n", 1)[1].split("\n```", 1)[0]
            self.assertEqual(json.loads(encoded), document)
            self.assertIn('"assignment_id": "lead-01:peer-01"', rendered)
            self.assertIn("every value is a non-empty string", rendered)
            self.assertIn("prompt delivery and Herdr lifecycle are not assignment completion", rendered)

    def test_renderer_rejects_a_full_workspace_protocol_for_peer_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment, profile, protocol, output = root / "assignment.json", root / "peer.md", root / "protocol.md", root / "prompt.md"
            assignment.write_text(json.dumps(assignment_document()), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("\n".join(f"## {number}. Full protocol" for number in range(1, 13)), encoding="utf-8")
            completed = self.run_cli("render-assignment", "--assignment", str(assignment), "--role-profile", str(profile), "--applicable-protocol", str(protocol), "--output", str(output))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("Peer applicable protocol projection", completed.stderr)

    def test_assignment_is_intentionally_narrowed_to_peer_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            document = assignment_document(
                role="supervisor",
                parent={"role": "human", "id": "human-01"},
                authority="read-only",
                disposition="Governance observer",
                recipe="supervisor",
                candidate=None,
            )
            path.write_text(json.dumps(document), encoding="utf-8")

            completed = self.run_cli("validate-assignment", "--assignment", str(path))

            self.assertEqual(completed.returncode, 2)
            self.assertIn("canonical Assignment is a Peer contract", completed.stderr)

    def test_peer_assignment_requires_lead_parentage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            invalid_peer = assignment_document(parent={"role": "human", "id": "human-01"})
            path.write_text(json.dumps(invalid_peer), encoding="utf-8")
            completed = self.run_cli("validate-assignment", "--assignment", str(path))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("canonical Assignment is a Peer contract", completed.stderr)

    def test_trivial_peer_assignment_does_not_require_topology_rationale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            path.write_text(json.dumps(assignment_document(topology_rationale=None)), encoding="utf-8")
            completed = self.run_cli("validate-assignment", "--assignment", str(path))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIsNone(json.loads(completed.stdout)["topology_rationale"])

    def test_active_lead_delegation_rejects_overlapping_write_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(assignment_document(
                authority="write", owned_scope=["path:src"], disposition="Engineer", recipe="engineer"
            )), encoding="utf-8")
            second.write_text(json.dumps(assignment_document(
                assignment_id="lead-01:peer-02", authority="write", owned_scope=["path:src/api"],
                disposition="Engineer", recipe="engineer"
            )), encoding="utf-8")

            completed = self.run_cli(
                "validate-delegation", "--assignment", str(first), "--assignment", str(second)
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("require Lead reconciliation", completed.stderr)

    def test_active_lead_delegation_rejects_noncanonical_path_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            path.write_text(json.dumps(assignment_document(authority="write", owned_scope=["path:a/../src"], disposition="Engineer", recipe="engineer")), encoding="utf-8")
            completed = self.run_cli("validate-delegation", "--assignment", str(path))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("canonical project-relative path scope", completed.stderr)

    def test_active_lead_delegation_allows_disjoint_scope_and_read_only_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            writer = root / "writer.json"
            reviewer = root / "reviewer.json"
            writer.write_text(json.dumps(assignment_document(
                authority="write", owned_scope=["path:src/api"], disposition="Engineer", recipe="engineer"
            )), encoding="utf-8")
            reviewer.write_text(json.dumps(assignment_document(
                assignment_id="lead-01:peer-02", owned_scope=[], disposition="Reviewer", recipe="review"
            )), encoding="utf-8")

            completed = self.run_cli(
                "validate-delegation", "--assignment", str(writer), "--assignment", str(reviewer)
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["writer_assignment_ids"], ["lead-01:peer-01"])

    def test_review_requires_exact_immutable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, commit = self.git_repository(root)
            path = root / "review.json"
            path.write_text(json.dumps(assignment_document(candidate={"kind": "git_commit", "value": commit})), encoding="utf-8")

            current = root / "current.json"
            current.write_text(json.dumps({"kind": "git_commit", "value": commit}), encoding="utf-8")
            applicable = self.run_cli("validate-review", "--assignment", str(path), "--current-candidate", str(current), "--project-root", str(repository))
            current.write_text(json.dumps({"kind": "git_commit", "value": "b" * 40}), encoding="utf-8")
            stale = self.run_cli("validate-review", "--assignment", str(path), "--current-candidate", str(current), "--project-root", str(repository))

            self.assertEqual(applicable.returncode, 0, applicable.stderr)
            self.assertTrue(json.loads(applicable.stdout)["review_applicable"])
            self.assertEqual(stale.returncode, 2)
            self.assertIn("Git commit must exist", stale.stderr)

    def test_review_accepts_an_existing_frozen_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, commit = self.git_repository(root)
            snapshot = repository / "candidate.snapshot"
            snapshot.write_bytes(b"frozen base, diff, untracked, and generated artifacts\n")
            path = root / "review.json"
            path.write_text(json.dumps(assignment_document(candidate={
                "kind": "frozen_snapshot", "base_commit": commit, "artifact_path": "candidate.snapshot",
                "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            })), encoding="utf-8")

            current = root / "current.json"
            current.write_text(json.dumps({
                "kind": "frozen_snapshot", "base_commit": commit, "artifact_path": "candidate.snapshot",
                "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            completed = self.run_cli("validate-review", "--assignment", str(path), "--current-candidate", str(current), "--project-root", str(repository))

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["review_applicable"])
            snapshot.write_text("mutated\n", encoding="utf-8")
            corrupted = self.run_cli("validate-review", "--assignment", str(path), "--current-candidate", str(current), "--project-root", str(repository))
            self.assertEqual(corrupted.returncode, 2)
            self.assertIn("digest does not match", corrupted.stderr)

    def test_review_rejects_a_different_snapshot_from_the_same_base_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, commit = self.git_repository(root)
            first, second = repository / "first.snapshot", repository / "second.snapshot"
            first.write_bytes(b"first frozen candidate\n")
            second.write_bytes(b"second frozen candidate\n")
            assignment = root / "review.json"
            assignment.write_text(json.dumps(assignment_document(candidate={
                "kind": "frozen_snapshot", "base_commit": commit, "artifact_path": "first.snapshot",
                "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
            })), encoding="utf-8")
            current = root / "current.json"
            current.write_text(json.dumps({
                "kind": "frozen_snapshot", "base_commit": commit, "artifact_path": "second.snapshot",
                "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            completed = self.run_cli("validate-review", "--assignment", str(assignment), "--current-candidate", str(current), "--project-root", str(repository))
            self.assertEqual(completed.returncode, 2)
            self.assertIn("review candidate is stale", completed.stderr)

    def test_matching_handback_is_semantic_completion_and_reads_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment = root / "assignment.json"
            handback = root / "handback.json"
            evidence = root / "evidence.md"
            assignment.write_text(json.dumps(assignment_document()), encoding="utf-8")
            evidence.write_text("Full review evidence\n", encoding="utf-8")
            handback.write_text(json.dumps({
                "assignment_id": "lead-01:peer-01", "outcome": "REOPEN_REQUEST",
                "evidence": "A premise is false.", "impact": "Review cannot approve.",
                "need": "Engineer correction.", "evidence_path": str(evidence),
            }), encoding="utf-8")

            completed = self.run_cli(
                "validate-handback", "--assignment", str(assignment), "--handback", str(handback)
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["completion"], "semantic_handback")
            self.assertEqual(result["handback"]["outcome"], "REOPEN_REQUEST")
            self.assertEqual(result["handback"]["evidence_path"], str(evidence.resolve()))

    def test_handback_cannot_complete_a_different_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment = root / "assignment.json"
            handback = root / "handback.json"
            assignment.write_text(json.dumps(assignment_document()), encoding="utf-8")
            handback.write_text(json.dumps({
                "assignment_id": "wrong", "outcome": "COMPLETE", "evidence": "test",
                "impact": "none", "need": "none",
            }), encoding="utf-8")

            completed = self.run_cli(
                "validate-handback", "--assignment", str(assignment), "--handback", str(handback)
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("does not match the Assignment", completed.stderr)


if __name__ == "__main__":
    unittest.main()
