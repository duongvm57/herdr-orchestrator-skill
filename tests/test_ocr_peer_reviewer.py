from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OCR_SKILL_ROOT = ROOT / "skills/ocr-peer-reviewer"
ORCHESTRATOR_SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
ORCHESTRATOR_HELPER = ORCHESTRATOR_SKILL_ROOT / "scripts/herdr_orchestrator.py"
OCR_BINARY = shutil.which("ocr")


def read_ocr_skill() -> str:
    return (OCR_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def read_orchestrator(relative: str) -> str:
    return (ORCHESTRATOR_SKILL_ROOT / relative).read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.split())


def frontmatter(text: str) -> dict[str, str]:
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0] != "":
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    fields: dict[str, str] = {}
    for line in parts[1].splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


class OCRPeerReviewerContractTests(unittest.TestCase):
    def test_reviewer_discovers_ocr_addon(self) -> None:
        peer = read_orchestrator("references/roles/peer.md")
        normalized_peer = normalized(peer)

        self.assertIn("use `ocr-peer-reviewer` when available", normalized_peer)
        self.assertIn("Review procedure: ocr-delegate", read_ocr_skill())
        self.assertIn("OCR status:", read_ocr_skill())

    def test_ocr_skill_requires_exact_candidate(self) -> None:
        skill = read_ocr_skill()

        self.assertIn("git rev-parse <accepted-base>^{commit}", skill)
        self.assertIn("git rev-parse <exact-candidate>^{commit}", skill)
        self.assertIn("Observed `HEAD` must equal the full candidate SHA", skill)
        self.assertIn("--from <accepted-base-sha> --to <exact-candidate-sha>", skill)
        self.assertIn("mode `range`", skill)
        self.assertIn("matching `from` and `to`", skill)

    def test_ocr_skill_forbids_candidate_mutation(self) -> None:
        skill = read_ocr_skill()

        self.assertIn("the only writable OCR evidence directory", skill)
        self.assertIn("the candidate remains read-only", skill)
        for forbidden in (
            "edit",
            "apply fixes",
            "checkout",
            "reset",
            "rebase",
            "commit",
            "push",
            "merge",
            "deploy",
        ):
            self.assertIn(forbidden, skill)

    def test_ocr_failure_falls_back_to_direct_review(self) -> None:
        skill = read_ocr_skill()
        peer = read_orchestrator("references/roles/peer.md")
        combined = skill + peer
        normalized_skill = normalized(skill)
        normalized_peer = normalized(peer)

        for status in (
            "OCR_UNAVAILABLE",
            "NON_GIT_CANDIDATE",
            "OCR_OUTPUT_UNSUPPORTED",
            "NO_REVIEWABLE_FILES",
        ):
            self.assertIn(status, combined)
        self.assertIn("OCR_SKILL_SKIPPED", skill)
        self.assertIn("continue with direct exact-candidate review", normalized_skill)
        self.assertIn("otherwise review directly", normalized_peer)

    def test_ocr_never_owns_project_acceptance(self) -> None:
        skill = read_ocr_skill()
        normalized_skill = normalized(skill)

        self.assertIn("Project acceptance remains with the surrounding Lead", normalized_skill)
        self.assertIn(
            "Return the normal semantic handback: `COMPLETE`, `REOPEN_REQUEST`",
            normalized_skill,
        )
        self.assertIn("never output project-level `ACCEPTED`, `MERGE`", normalized_skill)

    def test_raw_evidence_has_deterministic_destination_and_digest(self) -> None:
        skill = read_ocr_skill()

        for artifact in ("<evidence-root>/ocr/preview.json", "<evidence-root>/ocr/rules.json"):
            self.assertIn(artifact, skill)
        self.assertIn("sibling partial files", skill)
        self.assertIn("atomically rename", skill)
        self.assertIn("compute SHA-256 over the exact final bytes", skill)
        self.assertIn("<evidence-root>/ocr/", skill)

    def test_rule_resolution_is_not_bound_to_candidate_range(self) -> None:
        skill = read_ocr_skill()
        preview = next(
            line.strip()
            for line in skill.splitlines()
            if line.strip().startswith("ocr delegate preview")
        )
        rule = next(
            line.strip()
            for line in skill.splitlines()
            if line.strip().startswith("ocr delegate rule")
        )

        self.assertIn("--from <accepted-base-sha>", preview)
        self.assertIn("--to <exact-candidate-sha>", preview)
        self.assertIn("--format json --repo <repo> -- <selected-paths>", rule)
        self.assertNotIn("--from", rule)
        self.assertNotIn("--to", rule)

    def test_zero_reviewable_files_cannot_yield_ocr_approval(self) -> None:
        skill = read_ocr_skill()
        normalized_skill = normalized(skill)
        peer = normalized(read_orchestrator("references/roles/peer.md"))

        self.assertIn("If `reviewable_files` is empty", skill)
        self.assertIn("do not invoke `rule`", normalized_skill)
        self.assertIn("NO_REVIEWABLE_FILES", skill)
        self.assertIn("never from zero-of-zero OCR coverage", normalized_skill)
        self.assertIn("directly inspects the exact candidate", normalized_skill)
        self.assertIn("same semantic handback outcomes as every other Peer", peer)

    def test_ocr_skill_is_valid_packaged_skill(self) -> None:
        skill_path = OCR_SKILL_ROOT / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        fields = frontmatter(skill)
        openai = (OCR_SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        license_text = (OCR_SKILL_ROOT / "LICENSE").read_text(encoding="utf-8")
        notice = (OCR_SKILL_ROOT / "NOTICE").read_text(encoding="utf-8")

        self.assertEqual(fields["name"], OCR_SKILL_ROOT.name)
        self.assertTrue(fields["description"])
        self.assertEqual(fields["license"], "Apache-2.0")
        self.assertIn('display_name: "OCR Peer Reviewer"', openai)
        self.assertIn("$ocr-peer-reviewer", openai)
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0", license_text)
        self.assertIn("alibaba/open-code-review", notice)
        self.assertIn("adaptation adds", notice)

    @unittest.skipUnless(OCR_BINARY, "ocr CLI is not installed")
    def test_ocr_integration_canary_when_cli_is_installed(self) -> None:
        assert OCR_BINARY is not None
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            rule_path = repo / ".ocr-canary-rules.json"
            source = repo / "app.py"

            def run(*args: str) -> subprocess.CompletedProcess[str]:
                completed = subprocess.run(
                    list(args),
                    cwd=repo,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return completed

            run("git", "init", "--quiet")
            run("git", "config", "user.name", "OCR Canary")
            run("git", "config", "user.email", "ocr-canary@example.invalid")
            rule_path.write_text(
                json.dumps(
                    {
                        "include": ["**/*.py"],
                        "rules": [
                            {
                                "path": "**/*.py",
                                "rule": "Check observable return-value behavior.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            source.write_text("def value():\n    return 1\n", encoding="utf-8")
            run("git", "add", ".ocr-canary-rules.json", "app.py")
            run("git", "commit", "--quiet", "-m", "base")
            source.write_text("def value():\n    return 2\n", encoding="utf-8")
            run("git", "add", "app.py")
            run("git", "commit", "--quiet", "-m", "candidate")
            base = run("git", "rev-parse", "HEAD^").stdout.strip()
            candidate = run("git", "rev-parse", "HEAD").stdout.strip()

            preview = json.loads(
                run(
                    OCR_BINARY,
                    "delegate",
                    "preview",
                    "--format",
                    "json",
                    "--repo",
                    str(repo),
                    "--rule",
                    str(rule_path),
                    "--from",
                    base,
                    "--to",
                    candidate,
                ).stdout
            )
            self.assertEqual(preview["schema_version"], "1")
            self.assertEqual(preview["mode"], "range")
            self.assertEqual(preview["from"], base)
            self.assertEqual(preview["to"], candidate)
            self.assertEqual(preview["merge_base"], base)
            self.assertEqual(
                [(item["path"], item["status"]) for item in preview["reviewable_files"]],
                [("app.py", "modified")],
            )

            selected = [item["path"] for item in preview["reviewable_files"]]
            rules = json.loads(
                run(
                    OCR_BINARY,
                    "delegate",
                    "rule",
                    "--format",
                    "json",
                    "--repo",
                    str(repo),
                    "--rule",
                    str(rule_path),
                    "--",
                    *selected,
                ).stdout
            )
            mapped = [path for group in rules["groups"] for path in group["files"]]
            self.assertEqual(rules["schema_version"], "1")
            self.assertCountEqual(mapped, selected)
            self.assertEqual(run("git", "rev-parse", "HEAD").stdout.strip(), candidate)
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")

    @unittest.skipUnless(OCR_BINARY, "ocr CLI is not installed")
    def test_reviewer_bound_materialization_runs_ocr_and_validates_handback(self) -> None:
        assert OCR_BINARY is not None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            (project / ".orchestration").mkdir()

            def run(*args: str, cwd: Path = project, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
                completed = subprocess.run(
                    list(args), cwd=cwd, env=env, check=False, capture_output=True, text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return completed

            run("git", "init", "--quiet")
            run("git", "config", "user.name", "OCR Materialization")
            run("git", "config", "user.email", "ocr-materialization@example.invalid")
            source = project / "app.py"
            source.write_text("def value():\n    return 1\n", encoding="utf-8")
            run("git", "add", "app.py")
            run("git", "commit", "--quiet", "-m", "base")
            source.write_text("def value():\n    return 2\n", encoding="utf-8")

            lead_binding = {
                **os.environ,
                "HERDR_ORCHESTRATOR_ROLE": "lead",
                "HERDR_PANE_ID": "wocr:pLead",
                "HERDR_ORCHESTRATOR_PANE_ID": "wocr:pLead",
                "HERDR_ORCHESTRATOR_HELPER": str(ORCHESTRATOR_HELPER.resolve()),
                "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve()),
            }
            reviewer_binding = {
                **lead_binding,
                "HERDR_ORCHESTRATOR_ROLE": "peer",
                "HERDR_PANE_ID": "wocr:pReviewer",
                "HERDR_ORCHESTRATOR_PANE_ID": "wocr:pReviewer",
            }
            run(
                "python3", str(ORCHESTRATOR_HELPER), "freeze-candidate", "--project-root", str(project),
                env=lead_binding,
            )
            document = json.loads((project / ".orchestration/current-candidate.json").read_text(encoding="utf-8"))
            candidate = document["candidate"]
            assignment = {
                "schema_version": 2, "assignment_id": "lead-ocr:review-01", "role": "peer",
                "parent": {"role": "lead", "id": "lead-ocr"}, "owner": "ocr-reviewer",
                "project_root": str(project.resolve()), "worktree": None,
                "objective": "Review the exact materialized candidate.", "owned_scope": [],
                "exclusions": ["Do not modify project files."], "authority": "read-only",
                "disposition": "Reviewer", "recipe": "ocr-review", "verification": ["Run OCR."],
                "dependencies": [], "languages": {"live": "English", "artifact": "English"},
                "topology_rationale": None, "candidate": candidate, "review_cycle": 1,
                "prior_review": None, "convergence_assessment": None, "cost_approval": None,
            }
            assignment_path = project / ".orchestration/ocr-reviewer.json"
            assignment_path.write_text(json.dumps(assignment), encoding="utf-8")
            reviewer_binding.update({
                "HERDR_ORCHESTRATOR_ASSIGNMENT_ID": assignment["assignment_id"],
                "HERDR_ORCHESTRATOR_OWNER": assignment["owner"],
            })
            materialized = root / "materialized-candidate"
            receipt = json.loads(run(
                "python3", str(ORCHESTRATOR_HELPER), "materialize-candidate", "--assignment", str(assignment_path),
                "--output", str(materialized), env=reviewer_binding,
            ).stdout)
            rules = root / "ocr-rules.json"
            rules.write_text(json.dumps({"include": ["**/*.py"], "rules": [{"path": "**/*.py", "rule": "Check observable behavior."}]}), encoding="utf-8")
            preview = json.loads(run(
                OCR_BINARY, "delegate", "preview", "--format", "json", "--repo", str(materialized),
                "--rule", str(rules), "--from", receipt["base_commit"], "--to", receipt["synthetic_commit"], cwd=materialized,
            ).stdout)
            selected = [entry["path"] for entry in preview["reviewable_files"]]
            rule_result = json.loads(run(
                OCR_BINARY, "delegate", "rule", "--format", "json", "--repo", str(materialized),
                "--rule", str(rules), "--", *selected, cwd=materialized,
            ).stdout)

            self.assertEqual(preview["mode"], "range")
            self.assertEqual(preview["from"], receipt["base_commit"])
            self.assertEqual(preview["to"], receipt["synthetic_commit"])
            self.assertEqual(selected, ["app.py"])
            self.assertEqual(rule_result["schema_version"], "1")
            self.assertCountEqual(
                [path for group in rule_result["groups"] for path in group["files"]], selected,
            )
            self.assertEqual(run("git", "status", "--porcelain", cwd=materialized).stdout, "")

            # The test has invoked the installed OCR binary against the exact
            # Reviewer materialization. Record the observed successful use in
            # the same semantic handback shape a Reviewer returns; acceptance
            # still requires a real Reviewer/Lead workflow and is not inferred
            # from this integration test.
            handback_path = project / ".orchestration/ocr-reviewer-handback.json"
            handback_path.write_text(json.dumps({
                "assignment_id": assignment["assignment_id"],
                "outcome": "COMPLETE",
                "evidence": (
                    "Review procedure: ocr-delegate\\n"
                    "OCR status: USED\\n"
                    f"Candidate range: {receipt['base_commit']}..{receipt['synthetic_commit']}\\n"
                    f"Reviewable files: {', '.join(selected)}\\n"
                    f"Rule-mapped files: {', '.join(sorted(path for group in rule_result['groups'] for path in group['files']))}"
                ),
                "impact": "OCR delegated selection and rule mapping over the exact candidate.",
                "need": "none",
            }), encoding="utf-8")
            validated = json.loads(run(
                "python3", str(ORCHESTRATOR_HELPER), "validate-handback", "--assignment", str(assignment_path),
                "--handback", str(handback_path),
            ).stdout)
            self.assertEqual(validated["completion"], "semantic_handback")
            self.assertEqual(validated["handback"]["outcome"], "COMPLETE")
            self.assertIn("OCR status: USED", validated["handback"]["evidence"])


if __name__ == "__main__":
    unittest.main()
