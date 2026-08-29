from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"


class ProjectValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *arguments], check=False, capture_output=True, text=True
        )

    def project(self, name: str = "project") -> Path:
        project = self.root / name
        orchestration = project / ".orchestration"
        orchestration.mkdir(parents=True)
        (orchestration / "herdr-orchestrator.toml").write_text(textwrap.dedent("""\
            version = 3
            fallback_peer_recipe = "engineer"
            [roles.lead]
            kind = "codex"
            args = ["--model", "gpt-5.6-sol", "--config", "sandbox_workspace_write.network_access=true"]
            [roles.supervisor]
            kind = "codex"
            args = ["--model", "gpt-5.6-terra", "--config", "sandbox_workspace_write.network_access=true"]
            [peer_recipes.engineer]
            description = "Writable implementation recipe"
            kind = "codex"
            args = ["--model", "gpt-5.6-terra"]
        """), encoding="utf-8")
        rendered: list[str] = []
        for line in (SKILL_ROOT / "assets/workspace-protocol-template.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and ":" in line:
                label, value = line.split(":", 1)
                if not value.strip() or value.strip() == "YYYY-MM-DD":
                    value = {
                        "- Repository root": f" {project.resolve()}",
                        "- Live orchestration language": " Vietnamese",
                        "- Durable Markdown artifact language": " English",
                        "- Last reviewed": " 2026-08-28",
                    }.get(label, " configured")
                    line = label + ":" + value
            rendered.append(line)
        (orchestration / "workspace-protocol.md").write_text("\n".join(rendered) + "\n", encoding="utf-8")
        return project

    def test_validate_project_returns_config_and_language_policy(self) -> None:
        project = self.project()
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["config"]["version"], 3)
        self.assertEqual(result["languages"], {"artifact": "English", "live": "Vietnamese"})
        self.assertEqual(result["recipes"]["lead"]["kind"], "codex")
        self.assertEqual(result["recipes"]["fallback_peer"]["name"], "engineer")

    def test_validate_project_rejects_unknown_version_and_wrong_root(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("version = 3", "version = 2"), encoding="utf-8")
        version = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(version.returncode, 2)
        self.assertIn("version must be 3", version.stderr)
        config.write_text(config.read_text(encoding="utf-8").replace("version = 2", "version = 3"), encoding="utf-8")
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(protocol.read_text(encoding="utf-8").replace(str(project.resolve()), str(self.root.resolve())), encoding="utf-8")
        wrong_root = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(wrong_root.returncode, 2)
        self.assertIn("canonical project root", wrong_root.stderr)

    def test_validate_project_accepts_first_setup_candidate_paths(self) -> None:
        project = self.project()
        canonical = project / ".orchestration"
        config, protocol = canonical / "herdr-orchestrator.toml", canonical / "workspace-protocol.md"
        candidate_config, candidate_protocol = self.root / "candidate.toml", self.root / "candidate.md"
        candidate_config.write_bytes(config.read_bytes())
        candidate_protocol.write_bytes(protocol.read_bytes())
        config.unlink()
        protocol.unlink()

        completed = self.run_cli("validate-project", "--project-root", str(project), "--config", str(candidate_config), "--protocol", str(candidate_protocol))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["config"]["path"], str(candidate_config.resolve()))
        self.assertEqual(result["protocol"]["path"], str(candidate_protocol.resolve()))

    def test_validate_project_uses_candidate_bytes_instead_of_stale_canonical_files(self) -> None:
        project = self.project()
        canonical = project / ".orchestration"
        candidate_config, candidate_protocol = self.root / "candidate.toml", self.root / "candidate.md"
        candidate_config.write_text(canonical.joinpath("herdr-orchestrator.toml").read_text(encoding="utf-8").replace("version = 3", "version = 2"), encoding="utf-8")
        candidate_protocol.write_bytes(canonical.joinpath("workspace-protocol.md").read_bytes())

        completed = self.run_cli("validate-project", "--project-root", str(project), "--config", str(candidate_config), "--protocol", str(candidate_protocol))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("version must be 3", completed.stderr)

    def test_validate_project_default_uses_canonical_paths(self) -> None:
        project = self.project()
        candidate_config, candidate_protocol = self.root / "candidate.toml", self.root / "candidate.md"
        candidate_config.write_text("not valid", encoding="utf-8")
        candidate_protocol.write_text("not valid", encoding="utf-8")

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_validate_project_rejects_control_roles_without_control_plane_access(self) -> None:
        for role in ("lead", "supervisor"):
            with self.subTest(role=role):
                project = self.project(role)
                config = project / ".orchestration/herdr-orchestrator.toml"
                text = config.read_text(encoding="utf-8")
                model = "gpt-5.6-sol" if role == "lead" else "gpt-5.6-terra"
                text = text.replace(f'args = ["--model", "{model}", "--config", "sandbox_workspace_write.network_access=true"]', f'args = ["--model", "{model}"]', 1)
                config.write_text(text, encoding="utf-8")

                completed = self.run_cli("validate-project", "--project-root", str(project))

                self.assertEqual(completed.returncode, 2)
                self.assertIn(f"roles.{role} Codex cannot reach the Herdr control socket", completed.stderr)

    def test_validate_project_does_not_require_peer_control_plane_access(self) -> None:
        project = self.project()

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_helper_exposes_policy_commands_only(self) -> None:
        completed = self.run_cli("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command in ("init-run", "stage-assets", "pack", "deliver", "receipt"):
            self.assertNotIn(command, completed.stdout)
        for command in ("validate-project", "render-assignment", "validate-handback", "harness-models"):
            self.assertIn(command, completed.stdout)

    def test_approval_required_recipe_rejects_never_policy(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        original = config.read_text(encoding="utf-8")
        config.write_text(
            original.replace(
                'args = ["--model", "gpt-5.6-sol", "--config", "sandbox_workspace_write.network_access=true"]',
                'args = ["--model", "gpt-5.6-sol", "--ask-for-approval", "never"]\napproval_required = true',
                1,
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires approval but native args disable it", completed.stderr)


if __name__ == "__main__":
    unittest.main()
