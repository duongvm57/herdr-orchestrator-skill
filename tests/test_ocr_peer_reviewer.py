from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OCR_SKILL_ROOT = ROOT / "skills/ocr-peer-reviewer"
ORCHESTRATOR_SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
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
        lifecycle = read_orchestrator("references/lead/peer-lifecycle.md")
        normalized_peer = normalized(peer)
        normalized_lifecycle = normalized(lifecycle)

        self.assertIn("load `ocr-peer-reviewer`", peer)
        self.assertIn("available skill catalog", normalized_peer)
        self.assertIn("explicitly require the Peer to load it", normalized_lifecycle)
        self.assertIn("Review procedure: <ocr-delegate | direct>", lifecycle)
        self.assertIn("OCR status:", lifecycle)
        self.assertIn("SKILL_NOT_AVAILABLE", lifecycle)

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
        lifecycle = read_orchestrator("references/lead/peer-lifecycle.md")
        combined = skill + peer + lifecycle
        normalized_skill = normalized(skill)
        normalized_peer = normalized(peer)

        for status in (
            "SKILL_NOT_AVAILABLE",
            "OCR_UNAVAILABLE",
            "NON_GIT_CANDIDATE",
            "OCR_OUTPUT_UNSUPPORTED",
            "NO_REVIEWABLE_FILES",
        ):
            self.assertIn(status, combined)
        self.assertIn("OCR_SKILL_SKIPPED", skill)
        self.assertIn("continue with direct exact-candidate review", normalized_skill)
        self.assertIn("review the exact candidate directly", normalized_peer)

    def test_ocr_never_owns_project_acceptance(self) -> None:
        skill = read_ocr_skill()
        normalized_skill = normalized(skill)

        self.assertIn("Project acceptance remains with the surrounding Lead", normalized_skill)
        self.assertIn(
            "Use only the existing Reviewer outcome `APPROVE` or `FINDINGS`",
            normalized_skill,
        )
        self.assertIn("never output project-level `ACCEPTED`, `MERGE`", normalized_skill)

    def test_raw_evidence_has_deterministic_destination_and_digest(self) -> None:
        skill = read_ocr_skill()
        lifecycle = read_orchestrator("references/lead/peer-lifecycle.md")

        for artifact in ("<inbox>/ocr/preview.json", "<inbox>/ocr/rules.json"):
            self.assertIn(artifact, skill)
        self.assertIn("sibling partial files", skill)
        self.assertIn("atomically rename", skill)
        self.assertIn("compute SHA-256 over the exact artifact bytes", skill)
        self.assertIn("reports/inbox/<agent-name>/ocr/preview.json", lifecycle)
        self.assertIn("verify their reported SHA-256 digests", normalized(lifecycle))

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
        peer = read_orchestrator("references/roles/peer.md")
        normalized_skill = normalized(skill)

        self.assertIn("If `reviewable_files` is empty", skill)
        self.assertIn("do not invoke `rule`", normalized_skill)
        self.assertIn("NO_REVIEWABLE_FILES", skill)
        self.assertIn("never from zero-of-zero OCR coverage", normalized_skill)
        self.assertIn("direct path reports the absent/returned status", normalized(peer))
        self.assertIn("establishes its own coverage", normalized(peer))

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


if __name__ == "__main__":
    unittest.main()
