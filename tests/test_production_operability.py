from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
TASK_LAUNCH = ROOT / "skills/herdr-orchestrator/references/launcher/task-launch.md"


class ProductionOperabilityTests(unittest.TestCase):
    def run_cli(self, project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *arguments], cwd=project, check=False, capture_output=True, text=True
        )

    def git(self, project: Path, *arguments: str) -> str:
        return subprocess.run(["git", "-C", str(project), *arguments], check=True, capture_output=True, text=True).stdout.strip()

    def project(self, name: str = "project") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        project = Path(temporary.name) / name
        (project / ".orchestration").mkdir(parents=True)
        (project / "app.txt").write_text("base\n", encoding="utf-8")
        (project / ".orchestration/control.txt").write_text("base control\n", encoding="utf-8")
        self.git(project, "init", "--quiet")
        self.git(project, "config", "user.email", "test@example.invalid")
        self.git(project, "config", "user.name", "Test")
        self.git(project, "add", ".")
        self.git(project, "commit", "--quiet", "-m", "base")
        return project

    def freeze(self, project: Path) -> tuple[dict[str, object], dict[str, object]]:
        completed = self.run_cli(project, "freeze-candidate", "--project-root", str(project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        document = json.loads((project / ".orchestration/current-candidate.json").read_text(encoding="utf-8"))
        return result, document

    def candidate_object_paths(self, project: Path) -> list[str]:
        store = project / ".orchestration/candidate-objects"
        return sorted(path.relative_to(store).as_posix() for path in store.rglob("*") if path.is_file())

    def candidate_object_type(self, project: Path, object_id: str) -> str:
        store = project / ".orchestration/candidate-objects"
        git_dir = Path(self.git(project, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = project / git_dir
        completed = subprocess.run(
            ["git", "-C", str(project), "cat-file", "-t", object_id], check=True,
            capture_output=True, text=True,
            env={**os.environ, "GIT_OBJECT_DIRECTORY": str(store), "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(git_dir / "objects")},
        )
        return completed.stdout.strip()

    def acceptance_document(self, project: Path, candidate_document: dict[str, object], *, review: dict[str, object] | None = None) -> dict[str, object]:
        candidate = candidate_document["candidate"]
        return {
            "schema_version": 1,
            "candidate": candidate,
            "candidate_document_sha256": hashlib.sha256(
                (project / ".orchestration/current-candidate.json").read_bytes()
            ).hexdigest(),
            "lead": {"role": "lead", "id": "lead-01"},
            "inspection": {
                "candidate": candidate,
                "command": "python3 \"$HERDR_ORCHESTRATOR_HELPER\" inspect-candidate --project-root .",
                "result": "Inspected the exact base-to-tree diff.",
            },
            "verification": [{
                "candidate": candidate,
                "command": "python3 -m unittest",
                "result": "passed",
            }],
            "unresolved_findings": [],
            "residual_risk": "No unresolved technical risk observed after candidate-bound verification.",
            "review": review or {"decision": "not_required", "rationale": "This bounded local change has no protocol review trigger."},
        }

    def write_acceptance(self, project: Path, value: dict[str, object]) -> None:
        (project / ".orchestration/current-acceptance.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    def reviewer_assignment(self, candidate: dict[str, str]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "assignment_id": "lead-01:review-01",
            "role": "peer",
            "parent": {"role": "lead", "id": "lead-01"},
            "owner": "reviewer-01",
            "objective": "Falsify the exact candidate without modifying it.",
            "owned_scope": [],
            "exclusions": ["Do not change project files."],
            "authority": "read-only",
            "disposition": "Reviewer",
            "recipe": "review",
            "verification": ["Inspect the exact candidate."],
            "dependencies": [],
            "languages": {"live": "English", "artifact": "English"},
            "topology_rationale": "Independent falsification is required by risk.",
            "candidate": candidate,
        }

    def test_freeze_uses_candidate_object_store_when_real_git_is_read_only(self) -> None:
        project = self.project()
        (project / "app.txt").write_text("candidate\n", encoding="utf-8")
        (project / "new.txt").write_text("untracked candidate\n", encoding="utf-8")
        (project / "control-delete.txt").write_text("delete me\n", encoding="utf-8")
        self.git(project, "add", "control-delete.txt")
        self.git(project, "commit", "--quiet", "-m", "add deletable application file")
        (project / "control-delete.txt").unlink()
        (project / "skills-lock.json").write_text("installed skill control\n", encoding="utf-8")
        (project / ".orchestration/control.txt").write_text("mutable control\n", encoding="utf-8")
        head_before = self.git(project, "rev-parse", "HEAD")
        index_before = self.git(project, "ls-files", "-s")
        git_dir = Path(self.git(project, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = project / git_dir
        index_path, objects_path = git_dir / "index", git_dir / "objects"
        index_bytes = index_path.read_bytes()
        objects_before = sorted(
            path.relative_to(objects_path).as_posix()
            for path in objects_path.rglob("*") if path.is_file()
        )
        original_modes = {path: path.stat().st_mode for path in (git_dir, objects_path, index_path)}
        os.chmod(index_path, 0o444)
        os.chmod(objects_path, 0o555)
        os.chmod(git_dir, 0o555)
        try:
            first, document = self.freeze(project)
        finally:
            for path, mode in original_modes.items():
                os.chmod(path, mode)

        inspected = self.run_cli(project, "inspect-candidate", "--project-root", str(project))

        self.assertEqual(self.git(project, "rev-parse", "HEAD"), head_before)
        self.assertEqual(self.git(project, "ls-files", "-s"), index_before)
        self.assertEqual(index_path.read_bytes(), index_bytes)
        self.assertEqual(
            sorted(path.relative_to(objects_path).as_posix() for path in objects_path.rglob("*") if path.is_file()),
            objects_before,
        )
        self.assertEqual(first["real_index"], "not used")
        candidate = document["candidate"]
        assert isinstance(candidate, dict)
        self.assertFalse((objects_path / candidate["tree"][:2] / candidate["tree"][2:]).exists())
        self.assertTrue((project / ".orchestration/candidate-objects" / candidate["tree"][:2] / candidate["tree"][2:]).is_file())
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        changed = json.loads(inspected.stdout)["changed_paths"]
        self.assertEqual(changed, ["app.txt", "control-delete.txt", "new.txt"])
        self.assertNotIn("skills-lock.json", changed)
        (project / "app.txt").write_text("later mutation\n", encoding="utf-8")
        self.assertEqual(self.run_cli(project, "inspect-candidate", "--project-root", str(project)).returncode, 0)

        (project / "app.txt").write_text("candidate\n", encoding="utf-8")
        second, _ = self.freeze(project)
        self.assertEqual(second["candidate"], first["candidate"])

        reviewer = self.reviewer_assignment(candidate)
        review_path = project / ".orchestration/reviewer-assignment.json"
        review_path.write_text(json.dumps(reviewer), encoding="utf-8")
        review = self.run_cli(
            project, "validate-review", "--assignment", str(review_path),
            "--current-candidate", str(project / ".orchestration/current-candidate.json"),
            "--project-root", str(project),
        )
        self.assertEqual(review.returncode, 0, review.stderr)

        shutil.rmtree(project / ".orchestration/candidate-objects")
        missing_store = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(missing_store.returncode, 2)
        self.assertIn("candidate object storage is missing", missing_store.stderr)

        _, restored = self.freeze(project)
        restored_candidate = restored["candidate"]
        assert isinstance(restored_candidate, dict)
        candidate_tree = project / ".orchestration/candidate-objects" / restored_candidate["tree"][:2] / restored_candidate["tree"][2:]
        candidate_tree.unlink()
        missing_tree = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(missing_tree.returncode, 2)
        self.assertIn("Git tree is absent from candidate object storage", missing_tree.stderr)

        _, restored = self.freeze(project)
        restored_candidate = restored["candidate"]
        assert isinstance(restored_candidate, dict)
        candidate_tree = project / ".orchestration/candidate-objects" / restored_candidate["tree"][:2] / restored_candidate["tree"][2:]
        os.chmod(candidate_tree, 0o600)
        candidate_tree.write_bytes(b"corrupt candidate object")
        corrupt_store = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(corrupt_store.returncode, 2)
        self.assertIn("unreadable from candidate object storage", corrupt_store.stderr)

    def test_candidate_control_paths_never_self_ingest_or_grow_object_storage(self) -> None:
        project = self.project()
        (project / "app.txt").write_text("first candidate\n", encoding="utf-8")
        first, first_document = self.freeze(project)
        first_candidate = first_document["candidate"]
        assert isinstance(first_candidate, dict)
        first_objects = self.candidate_object_paths(project)

        second, second_document = self.freeze(project)
        self.assertEqual(second["candidate"], first["candidate"])
        self.assertEqual(second_document["candidate"], first_candidate)
        self.assertEqual(self.candidate_object_paths(project), first_objects)

        self.write_acceptance(project, self.acceptance_document(project, second_document))
        (project / ".orchestration/only-control-evidence.json").write_text("control evidence\n", encoding="utf-8")
        control_only = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(control_only.returncode, 0, control_only.stderr)
        self.assertEqual(self.candidate_object_paths(project), first_objects)

        (project / "app.txt").write_text("second candidate\n", encoding="utf-8")
        third, _ = self.freeze(project)
        self.assertNotEqual(third["candidate"], first_candidate)
        self.assertNotEqual(self.candidate_object_paths(project), first_objects)

    def test_candidate_inspection_reads_immutable_diff_and_rejects_changed_blob_damage(self) -> None:
        project = self.project()
        (project / "app.txt").write_text("candidate bytes\n", encoding="utf-8")
        _, document = self.freeze(project)
        candidate = document["candidate"]
        assert isinstance(candidate, dict)
        inspected = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        first_inspection = json.loads(inspected.stdout)
        diff_path = Path(first_inspection["diff_path"])
        diff_before = diff_path.read_bytes()
        self.assertEqual(first_inspection["diff_sha256"], hashlib.sha256(diff_before).hexdigest())
        self.assertIn(b"+candidate bytes", diff_before)

        (project / "app.txt").write_text("mutable worktree bytes\n", encoding="utf-8")
        after_mutation = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(after_mutation.returncode, 0, after_mutation.stderr)
        self.assertEqual(json.loads(after_mutation.stdout)["diff_sha256"], first_inspection["diff_sha256"])
        self.assertEqual(diff_path.read_bytes(), diff_before)
        self.assertNotIn(b"mutable worktree bytes", diff_before)

        changed_blob = next(
            object_path for object_path in self.candidate_object_paths(project)
            if object_path != f"{candidate['tree'][:2]}/{candidate['tree'][2:]}"
            and self.candidate_object_type(project, object_path.replace("/", "")) == "blob"
        )
        blob_path = project / ".orchestration/candidate-objects" / changed_blob
        os.chmod(blob_path, 0o600)
        blob_path.write_bytes(b"corrupt changed candidate blob")
        corrupt = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(corrupt.returncode, 2)
        self.assertIn("candidate immutable diff failed", corrupt.stderr)

        missing_project = self.project("missing-project")
        (missing_project / "app.txt").write_text("missing candidate blob\n", encoding="utf-8")
        _, missing_document = self.freeze(missing_project)
        missing_candidate = missing_document["candidate"]
        assert isinstance(missing_candidate, dict)
        missing_blob = next(
            object_path for object_path in self.candidate_object_paths(missing_project)
            if object_path != f"{missing_candidate['tree'][:2]}/{missing_candidate['tree'][2:]}"
            and self.candidate_object_type(missing_project, object_path.replace("/", "")) == "blob"
        )
        (missing_project / ".orchestration/candidate-objects" / missing_blob).unlink()
        missing = self.run_cli(missing_project, "inspect-candidate", "--project-root", str(missing_project))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("candidate immutable diff failed", missing.stderr)

    def test_candidate_inspection_rejects_missing_or_malformed_metadata(self) -> None:
        project = self.project()
        _, document = self.freeze(project)
        document["candidate"] = {"kind": "git_tree", "base_commit": self.git(project, "rev-parse", "HEAD"), "tree": "a" * 40}
        (project / ".orchestration/current-candidate.json").write_text(json.dumps(document), encoding="utf-8")
        missing = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("candidate object storage", missing.stderr)
        document["excluded_path_prefixes"] = [".orchestration"]
        (project / ".orchestration/current-candidate.json").write_text(json.dumps(document), encoding="utf-8")
        malformed = self.run_cli(project, "inspect-candidate", "--project-root", str(project))
        self.assertEqual(malformed.returncode, 2)
        self.assertIn("canonical project-control exclusions", malformed.stderr)

    def test_acceptance_requires_candidate_inspection_and_complete_fields(self) -> None:
        project = self.project()
        _, candidate_document = self.freeze(project)
        acceptance = self.acceptance_document(project, candidate_document)
        self.write_acceptance(project, acceptance)
        valid = self.run_cli(project, "validate-acceptance", "--project-root", str(project), "--lead-id", "lead-01")
        self.assertEqual(valid.returncode, 0, valid.stderr)

        tests_only = copy.deepcopy(acceptance)
        tests_only.pop("inspection")
        self.write_acceptance(project, tests_only)
        failed = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(failed.returncode, 2)
        self.assertIn("unsupported or missing fields", failed.stderr)

        mutable = copy.deepcopy(acceptance)
        mutable["candidate"] = {"kind": "working_tree_diff", "sha256": "a" * 64}
        self.write_acceptance(project, mutable)
        failed = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(failed.returncode, 2)
        self.assertIn("git_commit or git_tree", failed.stderr)

        for field in ("unresolved_findings", "residual_risk"):
            incomplete = copy.deepcopy(acceptance)
            incomplete.pop(field)
            self.write_acceptance(project, incomplete)
            failed = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
            self.assertEqual(failed.returncode, 2)
            self.assertIn("unsupported or missing fields", failed.stderr)

    def test_acceptance_rechecks_application_state_but_ignores_control_artifacts(self) -> None:
        project = self.project()
        _, candidate_document = self.freeze(project)
        self.write_acceptance(project, self.acceptance_document(project, candidate_document))
        (project / "skills-lock.json").write_text("updated installed skill control\n", encoding="utf-8")
        (project / ".orchestration/control-only.json").write_text("control-only\n", encoding="utf-8")

        control_only = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(control_only.returncode, 0, control_only.stderr)

        (project / "app.txt").write_text("application mutation after freeze\n", encoding="utf-8")
        stale = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(stale.returncode, 2)
        self.assertIn("application artifact has mutated since freeze", stale.stderr)

    def test_acceptance_validates_conditional_matching_review(self) -> None:
        project = self.project()
        _, candidate_document = self.freeze(project)
        candidate = candidate_document["candidate"]
        assert isinstance(candidate, dict)
        review = {
            "decision": "required",
            "rationale": "The protocol requires independent review for this risk.",
            "assignment_path": ".orchestration/reviewer-assignment.json",
            "handback_path": ".orchestration/reviewer-handback.json",
        }
        acceptance = self.acceptance_document(project, candidate_document, review=review)
        self.write_acceptance(project, acceptance)
        absent = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(absent.returncode, 2)

        (project / ".orchestration/reviewer-assignment.json").write_text(
            json.dumps(self.reviewer_assignment(candidate)), encoding="utf-8"
        )
        (project / ".orchestration/reviewer-handback.json").write_text(json.dumps({
            "assignment_id": "lead-01:review-01", "outcome": "COMPLETE",
            "evidence": "Reviewed the exact candidate.", "impact": "No blocking finding.", "need": "None.",
        }), encoding="utf-8")
        matching = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(matching.returncode, 0, matching.stderr)

        (project / "app.txt").write_text("new candidate\n", encoding="utf-8")
        _, newer_candidate = self.freeze(project)
        stale_acceptance = self.acceptance_document(project, newer_candidate, review=review)
        self.write_acceptance(project, stale_acceptance)
        stale = self.run_cli(project, "validate-acceptance", "--project-root", str(project))
        self.assertEqual(stale.returncode, 2)
        self.assertIn("review candidate is stale", stale.stderr)

    def test_production_gate_has_one_recovery_and_never_exposes_first_invalid_completion(self) -> None:
        project = self.project()
        _, candidate_document = self.freeze(project)
        first = self.run_cli(project, "validate-acceptance", "--project-root", str(project), "--lead-id", "lead-01")
        self.assertEqual(first.returncode, 2)
        self.assertIn("current-acceptance.json", first.stderr)

        self.write_acceptance(project, self.acceptance_document(project, candidate_document))
        recovered = self.run_cli(project, "validate-acceptance", "--project-root", str(project), "--lead-id", "lead-01")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)

        (project / ".orchestration/current-acceptance.json").unlink()
        second = self.run_cli(project, "validate-acceptance", "--project-root", str(project), "--lead-id", "lead-01")
        self.assertEqual(second.returncode, 2)
        launch = TASK_LAUNCH.read_text(encoding="utf-8")
        self.assertIn("Only a passing check permits the Launcher to surface successful project\ncompletion", launch)
        self.assertIn("one structured follow-up to that same Lead", launch)
        self.assertIn("On a second failure, surface `BLOCKED`", launch)
        self.assertIn("There is no third validation or correction loop", launch)
        self.assertIn("Do not edit implementation, manufacture evidence, create a\nReviewer, change topology, restart the task", launch)


if __name__ == "__main__":
    unittest.main()
