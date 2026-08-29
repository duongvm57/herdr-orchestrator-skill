from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_evals.py"
SUITE = ROOT / "tests/evals/orchestration-evals.json"
EVIDENCE_MAINTENANCE = ROOT / "maintenance/assignments-and-evidence.md"
SPEC = importlib.util.spec_from_file_location("run_evals", RUNNER)
assert SPEC and SPEC.loader
run_evals = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_evals
SPEC.loader.exec_module(run_evals)


class LiveEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = json.loads(SUITE.read_text(encoding="utf-8"))

    def prepared_live_project(self, workspace: Path) -> Path:
        project = workspace / "consumer-project"
        run_evals._prepare_fixture(ROOT / "tests/evals/fixtures/orchestration-basic", project)
        run_evals._materialize_install(project, workspace / "home", ROOT / "skills/herdr-orchestrator", "official skill")
        return project

    def test_manifest_references_canonical_invariants_and_critical_thresholds(self) -> None:
        manifest = run_evals.validate_suite(copy.deepcopy(self.suite), ROOT)
        self.assertEqual(len(manifest["cases"]), 15)
        self.assertEqual({case["suite"] for case in manifest["cases"]}, {"install-materialization", "regression-orchestration", "contract-evidence", "capability-generalization"})
        self.assertEqual({case["agent"]["model"] for case in manifest["cases"]}, {"gpt-5.6-luna"})
        for case in (item for item in manifest["cases"] if item["release_gate"]):
            self.assertEqual(case["repetitions"], 5)
            self.assertEqual(case["threshold"]["required_passes"], 5)
            self.assertTrue(case["release_gate"])

    def test_accepted_eval_failure_discipline_freezes_remediation_contracts(self) -> None:
        policy = " ".join(EVIDENCE_MAINTENANCE.read_text(encoding="utf-8").split())
        self.assertIn("are **FROZEN** for implementation remediation", policy)
        self.assertIn("public task, fixture semantics, topology requirement, hard grader, threshold, repetitions", policy)
        for classification in (
            "IMPLEMENTATION_FAILURE",
            "EVAL_HARNESS_FAILURE",
            "ENVIRONMENT_FAILURE",
            "STATIC_TEST_BUG",
            "SPEC_CONFLICT",
        ):
            self.assertIn(classification, policy)
        self.assertIn("EVAL_REOPEN_REQUEST", policy)
        self.assertIn("one concrete wrong implementation that must still FAIL", policy)

    def test_manifest_rejects_noncanonical_invariant_and_weakened_critical_limit(self) -> None:
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][0]["invariants"] = ["invented-contract"]
        with self.assertRaisesRegex(run_evals.EvalError, "not canonical"):
            run_evals.validate_suite(invalid, ROOT)
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][1]["repetitions"] = 1
        with self.assertRaisesRegex(run_evals.EvalError, "5 repetitions"):
            run_evals.validate_suite(invalid, ROOT)
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][0]["agent"]["model"] = "gpt-5.6-terra"
        with self.assertRaisesRegex(run_evals.EvalError, "gpt-5.6-luna"):
            run_evals.validate_suite(invalid, ROOT)
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][0]["agent"]["args"] = ["--model", "gpt-5.6-terra"]
        with self.assertRaisesRegex(run_evals.EvalError, "Luna network-enabled"):
            run_evals.validate_suite(invalid, ROOT)
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][0]["agent"]["recipe"] = "opaque recipe"
        with self.assertRaisesRegex(run_evals.EvalError, "kind, args, and model"):
            run_evals.validate_suite(invalid, ROOT)
        invalid = copy.deepcopy(self.suite)
        invalid["cases"][0]["graders"]["functional"]["expected"] = {"answer": "leaked"}
        with self.assertRaisesRegex(run_evals.EvalError, "kind, path, and requirements"):
            run_evals.validate_suite(invalid, ROOT)

    def test_materialized_project_install_never_links_back_to_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project, home = workspace / "project", workspace / "home"
            project.mkdir(); home.mkdir()
            install = run_evals._materialize_install(project, home, ROOT / "skills/herdr-orchestrator", "official skill")
            copied = project / install["path"]
            self.assertTrue(copied.is_dir())
            self.assertFalse(copied.is_symlink())
            self.assertEqual((project / install["official_skill_path"] / "SKILL.md").read_text(encoding="utf-8"), "official skill")

    def test_materialized_install_verifier_rejects_incomplete_symlinked_or_unisolated_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project, home, source = workspace / "project", workspace / "home", ROOT / "skills/herdr-orchestrator"
            project.mkdir(); home.mkdir()
            install = run_evals._materialize_install(project, home, source, "official skill")
            self.assertTrue(run_evals._verify_materialized_install(project, home, install, source, "official skill")["materialized_installation"])

            target = project / install["path"]
            shutil.rmtree(target)
            target.symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(run_evals.EvalError, "non-symlink tree"):
                run_evals._verify_materialized_install(project, home, install, source, "official skill")

            target.unlink()
            shutil.copytree(source, target)
            (target / "SKILL.md").unlink()
            with self.assertRaisesRegex(run_evals.EvalError, "materialization/provenance"):
                run_evals._verify_materialized_install(project, home, install, source, "official skill")

            isolated_home = project / "home"
            isolated_home.mkdir()
            with self.assertRaisesRegex(run_evals.EvalError, "outside the consumer project"):
                run_evals._verify_materialized_install(project, isolated_home, install, source, "official skill")

    def test_approved_deterministic_cases_execute_existing_helper_controls_without_agents(self) -> None:
        cases = [case for case in self.suite["cases"] if case["mode"] == "deterministic"]
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for case in cases:
                with self.subTest(case=case["id"]):
                    project, home = workspace / case["id"], workspace / f"home-{case['id']}"
                    run_evals._prepare_fixture(ROOT / self.suite["fixture_root"] / case["fixture"], project)
                    home.mkdir()
                    installation = run_evals._materialize_install(project, home, ROOT / "skills/herdr-orchestrator", "official skill")
                    evidence = run_evals._run_deterministic(case, project, home, installation, ROOT / "skills/herdr-orchestrator", "official skill")
                    for grader in case["graders"]["hard"]:
                        self.assertTrue(run_evals.grade(grader, project, evidence)["passed"])

    def test_skill_tree_hash_covers_references_beyond_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "herdr-orchestrator"
            shutil.copytree(ROOT / "skills/herdr-orchestrator", skill)
            original = run_evals._skill_tree_sha256(skill)
            reference = skill / "references/lead/topology.md"
            reference.write_text(reference.read_text(encoding="utf-8") + "\nchanged for provenance\n", encoding="utf-8")

            self.assertNotEqual(original, run_evals._skill_tree_sha256(skill))

    def test_source_provenance_explicitly_marks_dirty_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            skill = checkout / "skills/herdr-orchestrator"
            skill.mkdir(parents=True)
            (checkout / ".git").mkdir()
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")

            def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if arguments[-2:] == ["rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(arguments, 0, "a" * 40 + "\n", "")
                if arguments[-2:] == ["status", "--porcelain"]:
                    return subprocess.CompletedProcess(arguments, 0, " M references/lead.md\n", "")
                self.fail(f"unexpected command: {arguments}")

            with mock.patch.object(run_evals, "_command", side_effect=command):
                provenance = run_evals._source_provenance(skill, checkout)

            self.assertEqual(provenance["git_head"], "a" * 40)
            self.assertTrue(provenance["git_dirty"])
            self.assertEqual(provenance["source_tree_sha256"], run_evals._skill_tree_sha256(skill))

    def test_materialized_install_tree_hash_matches_actual_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project, home = workspace / "project", workspace / "home"
            project.mkdir(); home.mkdir()
            install = run_evals._materialize_install(project, home, ROOT / "skills/herdr-orchestrator", "official skill")

            self.assertEqual(install["tree_sha256"], run_evals._skill_tree_sha256(project / install["path"]))

    def test_private_eval_home_cleanup_preserves_concurrent_owned_home_and_removes_dead_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active, stale, unmanaged = root / "home-active", root / "home-stale", root / "home-legacy"
            active.mkdir(); stale.mkdir(); unmanaged.mkdir()
            for directory, pid, run_id in ((active, os.getpid(), "active-run"), (stale, 424242, "dead-run")):
                (directory / run_evals.PRIVATE_HOME_OWNER_FILE).write_text(json.dumps({
                    "schema_version": 1,
                    "kind": "herdr-orchestrator-live-eval-home",
                    "pid": pid,
                    "run_id": run_id,
                }), encoding="utf-8")

            with mock.patch.object(run_evals, "_process_is_alive", side_effect=lambda pid: pid == os.getpid()):
                run_evals._cleanup_stale_private_eval_homes(root)

            self.assertFalse(stale.exists())
            self.assertTrue(active.exists())
            self.assertTrue(unmanaged.exists())

    def test_retained_live_pass_bundle_regrades_without_private_home_or_credential(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project, bundle_dir = workspace / "consumer-project", workspace / "bundles"
            project.mkdir()
            foundation = project / "foundation.json"
            foundation.write_text('{"ready":true}\n', encoding="utf-8")
            assignment = run_evals._deterministic_assignment("assignment-a", "peer-a", ["path:evidence/handback.json"])
            handback = {**run_evals._deterministic_handback("assignment-a", "COMPLETE"), "evidence_path": str(foundation.resolve())}
            run_evals._write_eval_json(project / "evidence/assignment.json", assignment)
            run_evals._write_eval_json(project / "evidence/handback.json", handback)
            assignment_path = project / "evidence/assignment.json"
            run_evals._write_eval_json(project / "evaluation-evidence.json", {
                "peer_agents": ["peer-a"], "supervisor_agents": [],
                "handbacks": [{"assignment": "evidence/assignment.json", "handback": "evidence/handback.json", "peer_agent": "peer-a"}],
                "dispatches": [{"assignment": "evidence/assignment.json", "assignment_sha256": run_evals._sha256(assignment_path.read_bytes()), "peer_agent": "peer-a"}],
            })
            grader = {"kind": "evidence-contract", "path": "evaluation-evidence.json", "requirements": {"minimum_peer_agents": 1, "handbacks": ["COMPLETE"], "require_assignment_binding": True, "required_handback_evidence_path": "foundation.json"}}
            case = {"graders": {"functional": grader, "hard": [copy.deepcopy(grader)]}}
            private_home = workspace / "home-private"
            result = {
                "eval_id": "audit-case", "subject": "current", "suite_class": "regression-orchestration", "fixture": "fixture", "repetition": 1,
                "execution": "live", "final": "PASS",
                "sut": {"git_head": "a" * 40, "git_dirty": False, "source_tree_sha256": "source", "installed_skill_tree_sha256": "installed", "official_herdr_skill_sha256": "official", "herdr_version": "herdr test", "agent": {"kind": "codex", "model": "test"}, "install": {"home": str(private_home)}, "external_state": ["credential=secret-value"]},
                "evidence": {"agent_name": "lead-a", "peer_agents": ["peer-a"], "supervisor_agents": [], "participants": {"peer-a": {"cwd": str(project), "pane_id": "pane"}}},
                "functional": {"passed": True, "reason": "externally observed provenance and inspected contract evidence validated"},
                "hard_graders": [{"passed": True, "reason": "externally observed provenance and inspected contract evidence validated"}],
            }

            retained = run_evals._retain_live_pass_evidence(case, result, project, bundle_dir)
            bundle = json.loads(Path(retained["path"]).read_text(encoding="utf-8"))

            self.assertTrue(run_evals._regrade_retained_live_pass_bundle(Path(retained["path"]), ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py")["passed"])
            serialized = json.dumps(bundle)
            self.assertNotIn(str(private_home), serialized)
            self.assertNotIn("credential", serialized)
            self.assertNotIn("secret-value", serialized)
            handback_artifact = next(item["document"] for item in bundle["artifacts"] if item["path"] == "evidence/handback.json")
            self.assertEqual(handback_artifact["evidence_path"], "foundation.json")

    def test_pass_wording_distinguishes_deterministic_and_live_execution(self) -> None:
        self.assertEqual(run_evals._pass_reason("deterministic"), "all deterministic graders passed")
        self.assertEqual(run_evals._pass_reason("live"), "live execution completed and all hard graders passed")

    def test_isolated_live_eval_config_uses_luna_low_reasoning(self) -> None:
        config = run_evals._isolated_codex_config(
            {"kind": "codex", "model": "gpt-5.6-luna"},
            Path("/tmp/fresh-herdr-eval-project"),
        )
        self.assertIn('model = "gpt-5.6-luna"', config)
        self.assertIn('model_reasoning_effort = "low"', config)
        self.assertIn("allow_login_shell = false", config)
        self.assertIn('inherit = "all"', config)
        self.assertIn("ignore_default_excludes = false", config)
        self.assertIn('"HERDR_*" = "include"', config)
        self.assertIn('"HERDR_ORCHESTRATOR_*" = "include"', config)
        self.assertNotIn('model_reasoning_effort = "high"', config)

    def test_fixture_preparation_materializes_a_valid_eval_project_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            run_evals._prepare_fixture(ROOT / "tests/evals/fixtures/orchestration-basic", project)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py"), "validate-project", "--project-root", str(project)],
                check=False, text=True, capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            evidence_template = json.loads((project / ".orchestration/evaluation-evidence-template.json").read_text(encoding="utf-8"))
            self.assertEqual(set(evidence_template), {"peer_agents", "supervisor_agents", "handbacks", "dispatches"})
            self.assertTrue(all(value == [] for value in evidence_template.values()))
            assignment_template = project / ".orchestration/peer-assignment-template.json"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "skills/herdr-orchestrator/scripts/herdr_orchestrator.py"), "validate-assignment", "--assignment", str(assignment_template)],
                check=False, text=True, capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_grading_requires_runner_observed_topology_not_agent_claims(self) -> None:
        grader = {"kind": "evidence-contract", "path": "evaluation-evidence.json", "requirements": {"minimum_peer_agents": 1}}
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "evaluation-evidence.json").write_text('{"peer_agents":["peer-a"],"supervisor_agents":[],"passed":true,"ownership_was_checked":true}', encoding="utf-8")
            self.assertFalse(run_evals.grade(grader, project, {"peer_agents": [], "supervisor_agents": []})["passed"])
            self.assertTrue(run_evals.grade(grader, project, {"peer_agents": ["peer-a"], "supervisor_agents": []})["passed"])

    def test_live_prompt_contains_no_grader_truth(self) -> None:
        case = self.suite["cases"][1]
        with tempfile.TemporaryDirectory() as temporary:
            project = self.prepared_live_project(Path(temporary))
            prompt = run_evals._live_prompt(case, project, ROOT / "skills/herdr-orchestrator")
            self.assertNotIn("assignment-propagation", prompt)
            self.assertNotIn("REOPEN_REQUEST", prompt)
            self.assertNotIn("eval_id", prompt)
            self.assertNotIn("invariants", prompt)
            self.assertIn("evaluation-evidence.json", prompt)
            self.assertIn("Runner preflight is already complete", prompt)
            self.assertIn("exact bound Lead pane", prompt)
            self.assertIn("exact pane ID returned by Herdr", prompt)
            self.assertIn("do not override a harness profile home", prompt)
            self.assertNotIn("HOME=$HOME", prompt)
            self.assertIn("Do not set HERDR_ENV", prompt)
            self.assertIn("evaluation-evidence-template.json", prompt)
            self.assertIn("actual task artifacts", prompt)
            self.assertNotIn("parent.id is this Lead", prompt)
            self.assertNotIn("owner is never the Lead", prompt)
            self.assertNotIn('authority "write"', prompt)
            self.assertNotIn("exactly assignment_id, outcome, evidence, impact, and need", prompt)
            self.assertNotIn("canonical semantic outcome", prompt)
            self.assertNotIn("sha256sum", prompt)
            self.assertNotIn("topology_rationale", prompt)
            self.assertNotIn("# Lead role/profile", prompt)
            self.assertNotIn("# Project Lead", prompt)
            self.assertNotIn("# Full Workspace Protocol", prompt)
            self.assertNotIn("# Configured Peer recipes", prompt)
            multi_scope_case = next(case for case in self.suite["cases"] if case["id"] == "decomposition-independent")
            multi_scope_prompt = run_evals._live_prompt(multi_scope_case, project, ROOT / "skills/herdr-orchestrator")
            self.assertIn("share no mutable state", multi_scope_prompt)
            coupled_case = next(case for case in self.suite["cases"] if case["id"] == "decomposition-coupled")
            coupled_prompt = run_evals._live_prompt(coupled_case, project, ROOT / "skills/herdr-orchestrator")
            self.assertIn("atomic lifecycle/state boundary", coupled_prompt)
            self.assertNotIn("nonempty topology_rationale", coupled_prompt)

    def test_zero_peer_prompt_does_not_teach_a_topology_outcome(self) -> None:
        case = self.suite["cases"][0]
        with tempfile.TemporaryDirectory() as temporary:
            prompt = run_evals._live_prompt(case, self.prepared_live_project(Path(temporary)), ROOT / "skills/herdr-orchestrator")

        self.assertNotIn("requires zero Peer agents", prompt)
        self.assertNotIn("do not create a Peer Assignment, Peer pane, Peer agent, or Peer handback", prompt)

    def test_live_premise_pair_does_not_leak_expected_handback_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.prepared_live_project(Path(temporary))
            for case_id in ("peer-invalid-premise-reopen", "peer-valid-premise-control"):
                with self.subTest(case=case_id):
                    case = next(item for item in self.suite["cases"] if item["id"] == case_id)
                    prompt = run_evals._live_prompt(case, project, ROOT / "skills/herdr-orchestrator")
                    self.assertNotIn("REOPEN_REQUEST", prompt)
                    self.assertNotIn("COMPLETE", prompt)

    def test_deterministic_cases_do_not_require_live_agent_execution(self) -> None:
        deterministic = {case["id"] for case in self.suite["cases"] if case["mode"] == "deterministic"}
        self.assertEqual(deterministic, {
            "install-materialization-basic",
            "ownership-overlap-contract",
            "ownership-nested-overlap-contract",
            "ownership-independent-contract",
            "candidate-binding-contract",
            "reopen-handback-invalid-contract",
            "reopen-handback-valid-contract",
        })

    def test_dry_run_summary_never_claims_live_pass(self) -> None:
        case = self.suite["cases"][0]
        results = [{"eval_id": case["id"], "final": "NOT_RUN"} for _ in range(case["repetitions"])]
        summary, passed = run_evals.summarize(results, [case])
        self.assertEqual(summary["by_eval"][case["id"]]["status"], "NOT_RUN")
        self.assertFalse(passed)

    def test_participant_provenance_requires_one_named_agent_and_its_fresh_project_pane(self) -> None:
        project = Path("/tmp/fresh-herdr-eval-project")

        def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if arguments[:3] == ["herdr", "agent", "list"]:
                response = {"result": {"agents": [{"name": "peer-a", "pane_id": "w:p1", "cwd": str(project)}]}}
            elif arguments[:3] == ["herdr", "pane", "get"]:
                response = {"result": {"pane": {"pane_id": "w:p1", "cwd": str(project), "workspace_id": "w"}}}
            else:
                self.fail(f"unexpected command: {arguments}")
            return subprocess.CompletedProcess(arguments, 0, json.dumps(response), "")

        with mock.patch.object(run_evals, "_command", side_effect=command):
            participant = run_evals._resolve_participant("peer-a", project)
        self.assertEqual(participant["pane_id"], "w:p1")

        def unrelated(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            response = {"result": {"agents": [{"name": "peer-a", "pane_id": "w:p1", "cwd": "/tmp/other-project"}]}}
            return subprocess.CompletedProcess(arguments, 0, json.dumps(response), "")

        with mock.patch.object(run_evals, "_command", side_effect=unrelated):
            with self.assertRaisesRegex(run_evals.EvalError, "fresh eval project"):
                run_evals._resolve_participant("peer-a", project)

    def test_cleanup_discovers_only_proven_fresh_project_peer_panes(self) -> None:
        project = Path("/tmp/fresh-herdr-eval-project")
        closed: list[str] = []

        def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if arguments[:3] == ["herdr", "agent", "list"]:
                response = {"result": {"agents": [
                    {"name": "eval-peer", "pane_id": "w:p-peer", "cwd": str(project)},
                    {"name": "human-peer", "pane_id": "w:p-human", "cwd": "/tmp/unrelated"},
                ]}}
                return subprocess.CompletedProcess(arguments, 0, json.dumps(response), "")
            if arguments[:3] == ["herdr", "pane", "get"]:
                response = {"result": {"pane": {"pane_id": arguments[3], "cwd": str(project), "workspace_id": "w"}}}
                return subprocess.CompletedProcess(arguments, 0, json.dumps(response), "")
            if arguments[:3] == ["herdr", "pane", "close"]:
                closed.append(arguments[3])
                return subprocess.CompletedProcess(arguments, 0, "{}", "")
            self.fail(f"unexpected command: {arguments}")

        with mock.patch.object(run_evals, "_command", side_effect=command):
            run_evals._cleanup_eval_owned_panes(project, [])
        self.assertEqual(closed, ["w:p-peer"])

    def test_cleanup_handles_duplicate_agent_names_by_observed_pane_identity(self) -> None:
        project = Path("/tmp/fresh-herdr-eval-project")
        closed: list[str] = []

        def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if arguments[:3] == ["herdr", "agent", "list"]:
                output = {"result": {"agents": [
                    {"name": "peer-a", "pane_id": "w:p1", "cwd": str(project)},
                    {"name": "peer-a", "pane_id": "w:p2", "cwd": str(project)},
                ]}}
            elif arguments[:3] == ["herdr", "pane", "get"]:
                output = {"result": {"pane": {"pane_id": arguments[3], "cwd": str(project), "workspace_id": "w"}}}
            elif arguments[:3] == ["herdr", "pane", "close"]:
                closed.append(arguments[3]); output = {}
            else:
                self.fail(f"unexpected command: {arguments}")
            return subprocess.CompletedProcess(arguments, 0, json.dumps(output), "")

        with mock.patch.object(run_evals, "_command", side_effect=command):
            run_evals._cleanup_eval_owned_panes(project, [])
        self.assertEqual(set(closed), {"w:p1", "w:p2"})

    def test_secondary_metrics_are_null_when_not_measured(self) -> None:
        metrics = {"review_cycles": None, "candidate_count": None, "max_concurrency": None, "model_usage": None}
        self.assertTrue(all(value is None for value in metrics.values()))

    def test_focused_repetition_override_is_non_gating(self) -> None:
        case = copy.deepcopy(self.suite["cases"][1])
        focused = {**case, "repetitions": 1, "threshold": {"required_passes": 1, "rationale": "focused non-gating sample"}, "release_gate": False}
        self.assertEqual(focused["repetitions"], 1)
        self.assertFalse(focused["release_gate"])

    def test_prompt_timeout_is_inspected_and_waited_without_duplicate_resend(self) -> None:
        calls: list[list[str]] = []

        def command(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(arguments)
            if arguments[:3] == ["herdr", "agent", "prompt"]:
                output = {"error": {"code": "timeout", "message": "still working"}}
            elif arguments[:3] == ["herdr", "agent", "read"]:
                output = {"result": {"text": "inspected"}}
            elif arguments[:3] == ["herdr", "agent", "wait"]:
                output = {"result": {"agent_status": "done"}}
            else:
                self.fail(f"unexpected command: {arguments}")
            if arguments[:3] == ["herdr", "agent", "prompt"]:
                return subprocess.CompletedProcess(arguments, 1, "", json.dumps(output))
            return subprocess.CompletedProcess(arguments, 0, json.dumps(output), "")

        with mock.patch.object(run_evals, "_command", side_effect=command):
            run_evals._prompt_and_wait("lead-a", "one prompt", 10, "test prompt")
        self.assertEqual(sum(call[:3] == ["herdr", "agent", "prompt"] for call in calls), 1)
        self.assertEqual(sum(call[:3] == ["herdr", "agent", "read"] for call in calls), 2)

    def test_missing_or_malformed_evidence_index_is_a_hard_failure_without_reprompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "evaluation-evidence.json").write_text('{"peer_agents":["peer-a"],"supervisor_agents":[],"handbacks":[{}],"dispatches":[]}', encoding="utf-8")
            with self.assertRaisesRegex(run_evals.EvalError, "handback records are incomplete"):
                run_evals._read_evidence_index(project)
            project.joinpath("evaluation-evidence.json").unlink()
            with self.assertRaisesRegex(run_evals.EvalError, "cannot read evaluation evidence"):
                run_evals._read_evidence_index(project)

    def test_supervisor_name_is_within_herdr_limit(self) -> None:
        name = run_evals._supervisor_agent_name("supervisor-routing", 123456)
        self.assertLessEqual(len(name), 32)
        self.assertRegex(name, r"^[a-z][a-z0-9_-]*$")

    def test_supervisor_route_is_absent_before_and_observed_after_its_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            route = run_evals._require_supervisor_route_absent(project)
            route.write_text('{"supervisor_agent":"sup-a","target_lead":"lead-a","open_question":"Need Human choice."}', encoding="utf-8")

            observation = run_evals._observe_supervisor_route(route, "sup-a", "lead-a", 1.5)

            self.assertEqual(observation["target_lead"], "lead-a")
            self.assertTrue(observation["observed_after_supervisor_turn"])
            with self.assertRaisesRegex(run_evals.EvalError, "existed before"):
                run_evals._require_supervisor_route_absent(project)

    def test_supervisor_route_observation_rejects_wrong_attached_lead(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            route = Path(temporary) / run_evals.SUPERVISOR_ROUTE_ARTIFACT
            route.write_text('{"supervisor_agent":"sup-a","target_lead":"wrong-lead","open_question":"Need Human choice."}', encoding="utf-8")

            with self.assertRaisesRegex(run_evals.EvalError, "explicitly attached Lead"):
                run_evals._observe_supervisor_route(route, "sup-a", "lead-a", 1.5)

    def test_failure_diagnostics_capture_only_artifact_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            evidence = project / "evidence"
            evidence.mkdir()
            (project / "evaluation-evidence.json").write_text('{"peer_agents":["peer-a"],"handbacks":[{}]}', encoding="utf-8")
            (evidence / "assignment.json").write_text('{"assignment_id":"a"}', encoding="utf-8")

            def command(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess([], 0, "recent Lead output", "")

            with mock.patch.object(run_evals, "_command", side_effect=command):
                diagnostic = run_evals._failure_diagnostics(project, "lead-a", "prior output")
            self.assertEqual(diagnostic["artifact_shapes"][0]["keys"], ["handbacks", "peer_agents"])
            self.assertEqual(diagnostic["artifact_shapes"][1]["assignment_id"], "a")
            self.assertNotIn("recent Lead output", json.dumps(diagnostic))


if __name__ == "__main__":
    unittest.main()
