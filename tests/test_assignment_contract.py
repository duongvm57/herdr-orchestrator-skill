from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py"


def assignment_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 2,
        "assignment_id": "lead-01:peer-01",
        "role": "peer",
        "parent": {"role": "lead", "id": "lead-01"},
        "owner": "peer-01",
        "project_root": "/tmp",
        "worktree": None,
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
        "review_cycle": 1,
        "prior_review": None,
        "convergence_assessment": None,
        "cost_approval": None,
    }
    document.update(changes)
    return document


class AssignmentContractTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "validate-assignment" and "--project-root" not in args:
            args = (*args, "--structural-only")
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

    def runtime_context(self, root: Path) -> Path:
        orchestration = root / ".orchestration"
        orchestration.mkdir(exist_ok=True)
        config = orchestration / "herdr-orchestrator.toml"
        if not config.exists():
            config.write_text(
                "\n".join((
                    "version = 4",
                    "assessment_after_cycles = 2",
                    "", "[roles.lead]", 'kind = "pi"',
                    'args = ["--model", "test/model"]', 'cost_class = "standard"',
                    "", "[roles.supervisor]", 'kind = "pi"',
                    'args = ["--model", "test/model"]', 'cost_class = "standard"',
                    "", "[peer_recipes.review]", 'description = "Review recipe"',
                    'kind = "pi"', 'args = ["--model", "test/model"]',
                    'cost_class = "standard"',
                    "", "[routing.engineer]", 'default_recipe = "review"', 'allowed_recipes = ["review"]',
                    "", "[routing.reviewer]", 'default_recipe = "review"', 'allowed_recipes = ["review"]',
                    "", "[routing.architect]", 'default_recipe = "review"', 'allowed_recipes = ["review"]',
                    "", "[routing.default]", 'default_recipe = "review"', 'allowed_recipes = ["review"]',
                    "",
                )),
                encoding="utf-8",
            )
        output = root / "peer-runtime.json"
        completed = self.run_cli(
            "compile-runtime",
            "--project-root", str(root.resolve()),
            "--kind", "pi",
            "--role", "peer",
            "--pane-id", "w1:pPeer",
            "--herdr-program", "/bin/echo",
            "--socket-endpoint", str(root / "herdr.sock"),
            "--output", str(output),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output

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
            self.assertEqual(result["project_root"], "/tmp")
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
            assignment.write_text(json.dumps(assignment_document(owner="lead-01", project_root=str(root.resolve()))), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("Applicable protocol\n", encoding="utf-8")
            runtime = self.runtime_context(root)

            completed = self.run_cli(
                "render-assignment", "--assignment", str(assignment), "--role-profile", str(profile),
                "--applicable-protocol", str(protocol), "--runtime-context", str(runtime),
                "--output", str(output),
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("assigned Peer", completed.stderr)
            self.assertFalse(output.exists())

    def test_prompt_renderer_preserves_assignment_and_inserts_compiled_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment = root / "assignment.json"
            profile = root / "peer.md"
            protocol = root / "protocol.md"
            output = root / ".orchestration" / "prompts" / "prompt.md"
            objective = "  literal $herdr-orchestrator ' \" `x` $() \\nnext line  "
            document = assignment_document(objective=objective, project_root=str(root.resolve()))
            assignment.write_text(json.dumps(document), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("Applicable protocol\n", encoding="utf-8")
            runtime = self.runtime_context(root)

            completed = self.run_cli(
                "render-assignment", "--assignment", str(assignment), "--role-profile", str(profile),
                "--applicable-protocol", str(protocol), "--runtime-context", str(runtime),
                "--output", str(output),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            rendered = output.read_text(encoding="utf-8")
            encoded = rendered.split("```json\n", 1)[1].split("\n```", 1)[0]
            self.assertEqual(json.loads(encoded), document)
            self.assertIn('"assignment_id": "lead-01:peer-01"', rendered)
            self.assertIn("every value is a non-empty string", rendered)
            self.assertIn("prompt delivery and Herdr lifecycle are not assignment completion", rendered)
            self.assertIn("# Adapter Runtime Context", rendered)
            self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=w1:pPeer", rendered)

            wrong_runtime = root / "wrong-runtime.json"
            compiled = self.run_cli(
                "compile-runtime", "--project-root", str(root.resolve()),
                "--kind", "codex", "--role", "peer", "--pane-id", "w1:pWrong",
                "--herdr-program", "/bin/echo", "--socket-endpoint", str(root / "herdr.sock"),
                "--output", str(wrong_runtime),
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            mismatch = self.run_cli(
                "render-assignment", "--assignment", str(assignment),
                "--role-profile", str(profile), "--applicable-protocol", str(protocol),
                "--runtime-context", str(wrong_runtime),
                "--output", str(root / ".orchestration" / "prompts" / "wrong.md"),
            )
            self.assertEqual(mismatch.returncode, 2)
            self.assertIn("must match the Assignment recipe", mismatch.stderr)

    def test_renderer_rejects_a_full_workspace_protocol_for_peer_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assignment, profile, protocol, output = root / "assignment.json", root / "peer.md", root / "protocol.md", root / "prompt.md"
            assignment.write_text(json.dumps(assignment_document(project_root=str(root.resolve()))), encoding="utf-8")
            profile.write_text("Peer profile\n", encoding="utf-8")
            protocol.write_text("\n".join(f"## {number}. Full protocol" for number in range(1, 13)), encoding="utf-8")
            runtime = self.runtime_context(root)
            completed = self.run_cli("render-assignment", "--assignment", str(assignment), "--role-profile", str(profile), "--applicable-protocol", str(protocol), "--runtime-context", str(runtime), "--output", str(output))
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

    def test_concurrent_writers_require_distinct_project_root_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            integration_root, _ = self.git_repository(root)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(assignment_document(
                authority="write", owned_scope=["path:src/api"], disposition="Engineer", recipe="engineer",
                project_root=str(integration_root),
            )), encoding="utf-8")
            second.write_text(json.dumps(assignment_document(
                assignment_id="lead-01:peer-02", authority="write", owned_scope=["path:src/ui"],
                disposition="Engineer", recipe="engineer", project_root=str(integration_root),
            )), encoding="utf-8")

            shared = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second))

            self.assertEqual(shared.returncode, 2)
            self.assertIn("require distinct project_root worktrees", shared.stderr)

            first_root, second_root = root / "first-worktree", root / "second-worktree"
            for branch, checkout in (("writer-first", first_root), ("writer-second", second_root)):
                subprocess.run(
                    ("git", "-C", str(integration_root), "worktree", "add", "-q", "-b", branch, str(checkout), "HEAD"),
                    check=True, capture_output=True, text=True,
                )
            worktree_list = root / "herdr-worktree-list.json"
            worktree_list.write_text(json.dumps({
                "result": {
                    "type": "worktree_list",
                    "source": {"repo_root": str(integration_root)},
                    "worktrees": [
                        {"path": str(first_root), "open_workspace_id": "wA"},
                        {"path": str(second_root), "open_workspace_id": "wB"},
                    ],
                },
            }), encoding="utf-8")
            first.write_text(json.dumps(assignment_document(
                authority="write", owned_scope=["path:src/api"], disposition="Engineer", recipe="engineer",
                project_root=str(first_root),
            )), encoding="utf-8")
            second.write_text(json.dumps(assignment_document(
                assignment_id="lead-01:peer-02", authority="write", owned_scope=["path:src/ui"],
                disposition="Engineer", recipe="engineer", project_root=str(second_root),
            )), encoding="utf-8")

            missing_allocation = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second), "--worktree-list", str(worktree_list))

            self.assertEqual(missing_allocation.returncode, 2)
            self.assertIn("requires Herdr worktree allocation metadata; dispatch is blocked", missing_allocation.stderr)

            allocation = {"kind": "herdr_worktree", "source_project_root": str(integration_root)}
            first.write_text(json.dumps(assignment_document(
                authority="write", owned_scope=["path:src/api"], disposition="Engineer", recipe="engineer",
                project_root=str(first_root), worktree={**allocation, "workspace_id": "wA"},
            )), encoding="utf-8")
            isolated = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second), "--worktree-list", str(worktree_list))

            self.assertEqual(isolated.returncode, 2)
            self.assertIn("requires Herdr worktree allocation metadata; dispatch is blocked", isolated.stderr)

            second.write_text(json.dumps(assignment_document(
                assignment_id="lead-01:peer-02", authority="write", owned_scope=["path:src/ui"],
                disposition="Engineer", recipe="engineer", project_root=str(second_root),
                worktree={**allocation, "workspace_id": "wB"},
            )), encoding="utf-8")

            uncaptured = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second))

            self.assertEqual(uncaptured.returncode, 2)
            self.assertIn("requires captured Herdr worktree list evidence; dispatch is blocked", uncaptured.stderr)

            worktree_list.write_text(json.dumps({
                "result": {
                    "type": "worktree_list",
                    "source": {"repo_root": str(integration_root)},
                    "worktrees": [{"path": str(first_root), "open_workspace_id": "wA"}],
                },
            }), encoding="utf-8")
            unbound = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second), "--worktree-list", str(worktree_list))

            self.assertEqual(unbound.returncode, 2)
            self.assertIn("does not bind every concurrent writer", unbound.stderr)

            worktree_list.write_text(json.dumps({
                "result": {
                    "type": "worktree_list",
                    "source": {"repo_root": str(integration_root)},
                    "worktrees": [
                        {"path": str(first_root), "open_workspace_id": "wA"},
                        {"path": str(second_root), "open_workspace_id": "wB"},
                    ],
                },
            }), encoding="utf-8")
            isolated = self.run_cli("validate-delegation", "--assignment", str(first), "--assignment", str(second), "--worktree-list", str(worktree_list))

            self.assertEqual(isolated.returncode, 0, isolated.stderr)
            self.assertEqual(json.loads(isolated.stdout)["writer_project_roots"], {
                "lead-01:peer-01": str(first_root), "lead-01:peer-02": str(second_root),
            })
            self.assertEqual(json.loads(isolated.stdout)["writer_workspaces"], {
                "lead-01:peer-01": "wA", "lead-01:peer-02": "wB",
            })

    def test_assignment_rejects_noncanonical_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "assignment.json"
            path.write_text(json.dumps(assignment_document(project_root="relative-root")), encoding="utf-8")

            completed = self.run_cli("validate-assignment", "--assignment", str(path))

            self.assertEqual(completed.returncode, 2)
            self.assertIn("project_root must be a canonical absolute path", completed.stderr)

    def test_review_rejects_a_raw_candidate_identity_without_v2_envelope(self) -> None:
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

            self.assertEqual(applicable.returncode, 2)
            self.assertIn("canonical candidate document", applicable.stderr)
            self.assertEqual(stale.returncode, 2)
            self.assertIn("canonical candidate document", stale.stderr)

    def test_review_rejects_mutable_diff_digest_as_candidate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, _ = self.git_repository(root)
            assignment = root / "review.json"
            assignment.write_text(json.dumps(assignment_document(candidate={
                "kind": "working_tree_diff", "sha256": "a" * 64,
            })), encoding="utf-8")
            current = root / "current.json"
            current.write_text(json.dumps({"kind": "working_tree_diff", "sha256": "a" * 64}), encoding="utf-8")

            completed = self.run_cli("validate-review", "--assignment", str(assignment), "--current-candidate", str(current), "--project-root", str(repository))

            self.assertEqual(completed.returncode, 2)
            self.assertIn("git_commit or git_tree", completed.stderr)

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
