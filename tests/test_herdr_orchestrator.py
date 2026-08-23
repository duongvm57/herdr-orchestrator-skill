from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"
LAYOUT_HELPER = SKILL_ROOT / "scripts/herdr_balanced_split.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class HerdrOrchestratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative: str, text: str, *, executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def run_cli(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(HELPER), *map(str, arguments)]
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def preflight_digest_args(self, config: Path, protocol: Path) -> tuple[str, ...]:
        return (
            "--expected-project-config-sha256",
            sha256(config.read_bytes()),
            "--expected-workspace-protocol-sha256",
            sha256(protocol.read_bytes()),
        )

    def valid_project(self) -> Path:
        project = self.root / "project"
        orchestration = project / ".orchestration"
        orchestration.mkdir(parents=True)
        (orchestration / "herdr-orchestrator.toml").write_text(
            textwrap.dedent(
                """\
                version = 2

                [roles.lead]
                kind = "codex"
                args = ["--model", "gpt-5.6-sol"]

                [roles.supervisor]
                kind = "codex"
                args = ["--model", "gpt-5.6-terra"]

                [peer_recipes.engineer]
                description = "Writable implementation recipe"
                kind = "codex"
                args = ["--model", "gpt-5.6-terra"]
                """
            ),
            encoding="utf-8",
        )
        protocol_lines = []
        for line in (SKILL_ROOT / "assets/workspace-protocol-template.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and ":" in line:
                label, value = line.split(":", 1)
                if not value.strip() or value.strip() == "YYYY-MM-DD":
                    configured = {
                        "- Repository root": str(project.resolve()),
                        "- Live orchestration language": "Vietnamese",
                        "- Durable Markdown artifact language": "English",
                        "- Last reviewed": "2026-08-23",
                    }.get(label, f"configured {label[2:].lower()}")
                    line = f"{label}: {configured}"
            protocol_lines.append(line)
        (orchestration / "workspace-protocol.md").write_text(
            "\n".join(protocol_lines) + "\n",
            encoding="utf-8",
        )
        return project

    def init_run(self, *assets: tuple[str, Path]) -> tuple[Path, dict[str, object]]:
        common = self.root / "common"
        common.mkdir(exist_ok=True)
        task = self.write("inputs/task.md", "Implement the exact Human task.\n")
        before = self.write("inputs/before.txt", "## main\n M preserved.txt\n")
        project = self.valid_project()
        repository = project
        config = project / ".orchestration/herdr-orchestrator.toml"
        protocol = project / ".orchestration/workspace-protocol.md"
        arguments = [
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "20260823T010203Z-ab12",
            "--repository-root",
            str(repository),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            *self.preflight_digest_args(config, protocol),
            "--layout-helper",
            str(LAYOUT_HELPER),
        ]
        for name, source in assets:
            arguments.extend(("--asset", f"{name}={source}"))
        completed = self.run_cli(*arguments)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        metadata = json.loads(completed.stdout)
        return Path(metadata["run_directory"]), metadata

    def test_help_exposes_the_bounded_commands(self) -> None:
        completed = self.run_cli("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command in (
            "validate-project",
            "init-run",
            "stage-assets",
            "pack",
            "deliver",
            "codex-models",
        ):
            self.assertIn(command, completed.stdout)

        pack_help = self.run_cli("pack", "--help")
        self.assertEqual(pack_help.returncode, 0, pack_help.stderr)
        self.assertIn("--role {lead,peer,supervisor}", pack_help.stdout)

    def test_validate_project_returns_compact_metadata(self) -> None:
        project = self.valid_project()
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["config"]["version"], 2)
        self.assertEqual(result["languages"], {"artifact": "English", "live": "Vietnamese"})
        self.assertEqual(
            result["recipes"]["lead"],
            {"args": ["--model", "gpt-5.6-sol"], "kind": "codex"},
        )
        self.assertEqual(result["recipes"]["peers"][0]["name"], "engineer")

    def test_validate_project_binds_canonical_paths_and_protocol_root(self) -> None:
        project = self.valid_project()
        protocol = project / ".orchestration/workspace-protocol.md"
        other = self.root / "other-project"
        other.mkdir()
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                str(project.resolve()),
                str(other.resolve()),
            ),
            encoding="utf-8",
        )
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("does not match the repository root", completed.stderr)

        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                str(other.resolve()),
                str(project.resolve()),
            ),
            encoding="utf-8",
        )
        copied = self.write(
            "copied-config.toml",
            (project / ".orchestration/herdr-orchestrator.toml").read_text(
                encoding="utf-8"
            ),
        )
        completed = self.run_cli(
            "validate-project",
            "--project-root",
            str(project),
            "--config",
            str(copied),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("canonical project paths", completed.stderr)

    def test_validate_project_rejects_unknown_schema_and_blank_language(self) -> None:
        project = self.valid_project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(config.read_text(encoding="utf-8") + "\nlegacy = true\n", encoding="utf-8")
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("unsupported keys", completed.stderr)

        config.write_text(config.read_text(encoding="utf-8").replace("\nlegacy = true\n", "\n"), encoding="utf-8")
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                "Live orchestration language: Vietnamese",
                "Live orchestration language:",
            ),
            encoding="utf-8",
        )
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("populated value for Live orchestration language", completed.stderr)

    def test_protocol_requires_every_template_label_populated_in_its_section(self) -> None:
        project = self.valid_project()
        protocol = project / ".orchestration/workspace-protocol.md"
        populated = protocol.read_text(encoding="utf-8")

        protocol.write_bytes((SKILL_ROOT / "assets/workspace-protocol-template.md").read_bytes())
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires a populated value", completed.stderr)

        owner_line = "- Owner: configured owner\n"
        misplaced = populated.replace(owner_line, "").replace(
            "## 2. Project characteristics and risk classes\n",
            "## 2. Project characteristics and risk classes\n\n" + owner_line,
        )
        protocol.write_text(misplaced, encoding="utf-8")
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Owner belongs in section 1, not section 2", completed.stderr)

        missing = populated.replace(
            "- Dominant risks: configured dominant risks\n",
            "",
        )
        protocol.write_text(missing, encoding="utf-8")
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("section 2 is missing required label Dominant risks", completed.stderr)

    def test_protocol_label_contract_matches_packaged_template(self) -> None:
        spec = importlib.util.spec_from_file_location("herdr_protocol_contract", HELPER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)

        sections: list[tuple[str, ...]] = []
        labels: list[str] = []
        for line in (SKILL_ROOT / "assets/workspace-protocol-template.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if labels:
                    sections.append(tuple(labels))
                    labels = []
            elif line.startswith("- ") and ":" in line:
                labels.append(line[2:].split(":", 1)[0])
        sections.append(tuple(labels))
        self.assertEqual(tuple(sections), module.PROTOCOL_LABELS)

    def test_validate_project_rejects_placeholder_and_credential_arguments(self) -> None:
        project = self.valid_project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        original = config.read_text(encoding="utf-8")
        config.write_text(original.replace("gpt-5.6-sol", "<lead-model>"), encoding="utf-8")
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("non-placeholder", completed.stderr)

        unsafe_vectors = (
            '["--api-key", "stored-secret"]',
            '["--token", "stored-secret"]',
            '["-H", "Authorization: Bearer stored-secret"]',
            '["-H", "X-Api-Key: highly-sensitive"]',
            '["@secret.args"]',
            '["--model", "${MODEL_ID}"]',
            '["--model", "$MODEL_ID"]',
            '["--model", "sk-live-HERDRCANARY74af"]',
            '["--env-file", "/tmp/credentials.env"]',
            '["--config", "/tmp/profile.toml"]',
            '["--config", "model_providers.x.http_headers=highly-sensitive"]',
            '["--add-dir", "/definitely-missing/HERDRCANARY"]',
        )
        for vector in unsafe_vectors:
            with self.subTest(vector=vector):
                config.write_text(
                    original.replace(
                        'args = ["--model", "gpt-5.6-sol"]',
                        f"args = {vector}",
                        1,
                    ),
                    encoding="utf-8",
                )
                completed = self.run_cli("validate-project", "--project-root", str(project))
                self.assertEqual(completed.returncode, 2)
                self.assertIn("unsupported", completed.stderr)
                self.assertNotIn("stored-secret", completed.stderr)
                self.assertNotIn("highly-sensitive", completed.stderr)
                self.assertNotIn("credentials.env", completed.stderr)
                self.assertNotIn("profile.toml", completed.stderr)
                self.assertNotIn("HERDRCANARY", completed.stderr)

        config.write_text(
            original.replace(
                'args = ["--model", "gpt-5.6-sol"]',
                'args = ["--model", "gpt-5.6-sol", "--sandbox", "workspace-write", '
                '"--config", "sandbox_workspace_write.network_access=true"]',
                1,
            ),
            encoding="utf-8",
        )
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 0, completed.stderr)

        config.write_text(
            original.replace(
                'args = ["--model", "gpt-5.6-sol"]',
                'args = ["--model", "gpt-5.6-sol", '
                '"--config", "agents.enabled=false", '
                '"--config", "agents.enabled=false"]',
                1,
            ),
            encoding="utf-8",
        )
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("repeats", completed.stderr)

        config.write_text(
            original.replace('kind = "codex"', 'kind = "unregistered"', 1),
            encoding="utf-8",
        )
        completed = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("not supported by the safe recipe schema", completed.stderr)

    def test_init_run_publishes_complete_tree_and_digest_only_manifests(self) -> None:
        card = self.write("cards/topology.md", "TOPOLOGY CARD\n")
        run_dir, metadata = self.init_run(("topology.md", card))

        self.assertTrue((run_dir / "context/cards/assets/topology.md").is_file())
        self.assertTrue((run_dir / "reports/inbox").is_dir())
        self.assertTrue((run_dir / "assignments").is_dir())
        self.assertTrue((run_dir / "supervisor").is_dir())
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), b"")
        self.assertFalse((run_dir / "tools/layout-state.json").exists())
        self.assertEqual((run_dir / "tools/herdr_balanced_split.py").read_bytes(), LAYOUT_HELPER.read_bytes())
        self.assertEqual((run_dir / "tools/herdr_orchestrator.py").read_bytes(), HELPER.read_bytes())

        cards = json.loads((run_dir / "context/cards/manifest.json").read_text(encoding="utf-8"))
        entry = cards["assets"][0]
        self.assertEqual(set(entry), {"name", "path", "bytes", "sha256"})
        self.assertEqual(entry["name"], "topology.md")
        self.assertEqual(entry["sha256"], sha256(card.read_bytes()))
        self.assertNotIn("TOPOLOGY CARD", json.dumps(cards))
        project_config = self.root / "project/.orchestration/herdr-orchestrator.toml"
        project_protocol = self.root / "project/.orchestration/workspace-protocol.md"
        self.assertEqual(
            (run_dir / "context/project-config.toml").read_bytes(), project_config.read_bytes()
        )
        self.assertEqual(
            (run_dir / "context/workspace-protocol.md").read_bytes(), project_protocol.read_bytes()
        )
        run_manifest_text = (run_dir / "run-manifest.json").read_text(encoding="utf-8")
        run_manifest = json.loads(run_manifest_text)
        self.assertNotIn("Implement the exact Human task", run_manifest_text)
        self.assertIn("orchestration_helper", run_manifest["artifacts"])
        self.assertEqual(
            run_manifest["artifacts"]["project_config"]["sha256"],
            sha256(project_config.read_bytes()),
        )
        self.assertEqual(
            run_manifest["artifacts"]["workspace_protocol"]["sha256"],
            sha256(project_protocol.read_bytes()),
        )
        self.assertEqual(
            run_manifest["project_sources"],
            {
                "project_config": str(project_config.resolve()),
                "workspace_protocol": str(project_protocol.resolve()),
            },
        )
        self.assertEqual(metadata["asset_count"], 1)

    def test_init_run_rejects_post_preflight_change_before_mutation(self) -> None:
        common = self.root / "common"
        common.mkdir()
        project = self.valid_project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        protocol = project / ".orchestration/workspace-protocol.md"
        validated = self.run_cli(
            "validate-project",
            "--project-root",
            str(project),
        )
        self.assertEqual(validated.returncode, 0, validated.stderr)
        preflight = json.loads(validated.stdout)
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "gpt-5.6-sol",
                "gpt-5.6-terra",
                1,
            ),
            encoding="utf-8",
        )
        task = self.write("authority/task.md", "task\n")
        before = self.write("authority/before.txt", "state\n")
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "authority-bind",
            "--repository-root",
            str(project),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            "--expected-project-config-sha256",
            preflight["config"]["sha256"],
            "--expected-workspace-protocol-sha256",
            preflight["protocol"]["sha256"],
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("changed after preflight validation", completed.stderr)
        self.assertEqual(list(common.iterdir()), [])

        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "gpt-5.6-terra",
                "gpt-5.6-sol",
                1,
            ),
            encoding="utf-8",
        )
        validated = self.run_cli(
            "validate-project",
            "--project-root",
            str(project),
        )
        self.assertEqual(validated.returncode, 0, validated.stderr)
        preflight = json.loads(validated.stdout)
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                "Live orchestration language: Vietnamese",
                "Live orchestration language: Thai",
            ),
            encoding="utf-8",
        )
        common_protocol = self.root / "common-protocol-change"
        common_protocol.mkdir()
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common_protocol),
            "--run-id",
            "protocol-authority-bind",
            "--repository-root",
            str(project),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            "--expected-project-config-sha256",
            preflight["config"]["sha256"],
            "--expected-workspace-protocol-sha256",
            preflight["protocol"]["sha256"],
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("workspace protocol changed", completed.stderr)
        self.assertEqual(list(common_protocol.iterdir()), [])

    def test_init_run_failure_leaves_no_partial_run_tree(self) -> None:
        common = self.root / "common"
        common.mkdir()
        task = self.write("task.md", "task\n")
        before = self.write("before.txt", "state\n")
        project = self.valid_project()
        repository = project
        config = project / ".orchestration/herdr-orchestrator.toml"
        protocol = project / ".orchestration/workspace-protocol.md"
        first = self.write("one.md", "one\n")
        second = self.write("two.md", "two\n")
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "run-1",
            "--repository-root",
            str(repository),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            *self.preflight_digest_args(config, protocol),
            "--asset",
            f"same.md={first}",
            "--asset",
            f"same.md={second}",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertFalse((common / "herdr-orchestrator").exists())
        self.assertEqual(list(common.iterdir()), [])

    def test_init_run_strictly_validates_snapshots_before_mutation(self) -> None:
        common = self.root / "common"
        common.mkdir()
        project = self.valid_project()
        repository = project
        config = project / ".orchestration/herdr-orchestrator.toml"
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                "- Owner: configured owner",
                "- Owner:",
            ),
            encoding="utf-8",
        )
        task = self.write("task.md", "task\n")
        before = self.write("before.txt", "state\n")
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "run-1",
            "--repository-root",
            str(repository),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            *self.preflight_digest_args(config, protocol),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("populated value for Owner", completed.stderr)
        self.assertEqual(list(common.iterdir()), [])

    def test_init_run_rejects_symlinked_run_container(self) -> None:
        common = self.root / "common"
        outside = self.root / "outside"
        common.mkdir()
        outside.mkdir()
        (common / "herdr-orchestrator").symlink_to(outside, target_is_directory=True)
        task = self.write("task.md", "task\n")
        before = self.write("before.txt", "state\n")
        project = self.valid_project()
        repository = project
        config = project / ".orchestration/herdr-orchestrator.toml"
        protocol = project / ".orchestration/workspace-protocol.md"
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "run-1",
            "--repository-root",
            str(repository),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            *self.preflight_digest_args(config, protocol),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("must not be a symlink", completed.stderr)
        self.assertEqual(list(outside.iterdir()), [])

        (common / "herdr-orchestrator").unlink()
        (common / "herdr-orchestrator").mkdir()
        (common / "herdr-orchestrator/runs").symlink_to(outside, target_is_directory=True)
        completed = self.run_cli(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "run-1",
            "--repository-root",
            str(repository),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            *self.preflight_digest_args(config, protocol),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("runs path must not be a symlink", completed.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_stage_assets_is_additive_idempotent_and_mismatch_safe(self) -> None:
        topology = self.write("cards/topology.md", "topology-v1\n")
        run_dir, _ = self.init_run(("topology.md", topology))
        same_bytes = self.write("copies/topology.md", "topology-v1\n")

        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"topology.md={same_bytes}",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["idempotent"], 1)

        evidence = self.write("cards/evidence.md", "evidence card\n")
        selection = run_dir / "supervisor/anti-pattern-selection.json"
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"anti-pattern-details={evidence}",
            "--selection-output",
            str(selection),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["selection"]["asset_count"], 1)
        selected = json.loads(selection.read_text(encoding="utf-8"))
        self.assertEqual(
            [entry["name"] for entry in selected["assets"]],
            ["anti-pattern-details"],
        )
        self.assertNotIn("topology.md", selection.read_text(encoding="utf-8"))

        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"anti-pattern-details={evidence}",
            "--selection-output",
            str(selection),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["selection"]["idempotent"])

        conflicting_source = self.write("cards/conflicting.md", "conflicting\n")
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"conflicting={conflicting_source}",
            "--selection-output",
            str(selection),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("differs from the requested selection", completed.stderr)
        self.assertFalse((run_dir / "context/cards/assets/conflicting").exists())
        manifest_before = (run_dir / "context/cards/manifest.json").read_bytes()
        staged_before = (run_dir / "context/cards/assets/topology.md").read_bytes()

        changed = self.write("changed.md", "topology-v2\n")
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"topology.md={changed}",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("overwrite or digest mismatch", completed.stderr)
        self.assertEqual((run_dir / "context/cards/manifest.json").read_bytes(), manifest_before)
        self.assertEqual((run_dir / "context/cards/assets/topology.md").read_bytes(), staged_before)

        outside_source = self.write("cards/outside.md", "outside\n")
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"outside={outside_source}",
            "--selection-output",
            str(self.root / "outside-selection.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("must stay inside the run directory", completed.stderr)
        self.assertFalse((run_dir / "context/cards/assets/outside").exists())

    def test_stage_assets_recovers_matching_orphan_and_rejects_mismatched_evidence(self) -> None:
        run_dir, _ = self.init_run()
        source = self.write("cards/recovered.md", "recoverable bytes\n")
        orphan = run_dir / "context/cards/assets/recovered"
        orphan.write_bytes(source.read_bytes())
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"recovered={source}",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(result["added"], 1)
        manifest = json.loads((run_dir / "context/cards/manifest.json").read_text(encoding="utf-8"))
        self.assertIn("recovered", [entry["name"] for entry in manifest["assets"]])

        bad_source = self.write("cards/bad.md", "requested bytes\n")
        (run_dir / "context/cards/assets/bad").write_text("different orphan\n", encoding="utf-8")
        manifest_before = (run_dir / "context/cards/manifest.json").read_bytes()
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"bad={bad_source}",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("digest mismatch", completed.stderr)
        self.assertEqual((run_dir / "context/cards/manifest.json").read_bytes(), manifest_before)

        run_manifest_path = run_dir / "run-manifest.json"
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        run_manifest["run_id"] = "copied-run"
        run_manifest_path.write_text(json.dumps(run_manifest), encoding="utf-8")
        another = self.write("cards/another.md", "another\n")
        completed = self.run_cli(
            "stage-assets",
            "--run-dir",
            str(run_dir),
            "--asset",
            f"another={another}",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("IDs disagree", completed.stderr)
        self.assertFalse((run_dir / "context/cards/assets/another").exists())

    def test_stage_assets_flock_prevents_lost_concurrent_updates(self) -> None:
        run_dir, _ = self.init_run()
        first = self.write("cards/concurrent-a.md", "a" * (1024 * 1024))
        second = self.write("cards/concurrent-b.md", "b" * (1024 * 1024))
        commands = [
            [
                sys.executable,
                str(HELPER),
                "stage-assets",
                "--run-dir",
                str(run_dir),
                "--asset",
                f"{name}={source}",
            ]
            for name, source in (("concurrent-a", first), ("concurrent-b", second))
        ]
        processes = [
            subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for command in commands
        ]
        results = [process.communicate(timeout=30) for process in processes]
        for process, (_stdout, stderr) in zip(processes, results):
            self.assertEqual(process.returncode, 0, stderr)
        manifest = json.loads(
            (run_dir / "context/cards/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {entry["name"] for entry in manifest["assets"]},
            {"concurrent-a", "concurrent-b"},
        )

    def test_pack_preserves_source_order_and_enforces_ceiling(self) -> None:
        role_one = self.write("sources/role-one.md", "ROLE_ONE_SENTINEL\n")
        role_two = self.write("sources/role-two.md", "ROLE_TWO_SENTINEL\n")
        protocol = self.write("sources/protocol.md", "PROTOCOL_SENTINEL\n")
        assignment = self.write("sources/assignment.md", "ASSIGNMENT_SENTINEL\n")
        output = self.root / "lead.md"
        completed = self.run_cli(
            "pack",
            "--role",
            "lead",
            "--output",
            str(output),
            "--role-source",
            f"core={role_one}",
            "--role-source",
            f"contract={role_two}",
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
            "--max-bytes",
            "4096",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        metadata = json.loads(completed.stdout)
        pack = output.read_text(encoding="utf-8")
        ordered = [
            pack.index("## Role Profile"),
            pack.index("ROLE_ONE_SENTINEL"),
            pack.index("ROLE_TWO_SENTINEL"),
            pack.index("## Workspace Protocol"),
            pack.index("PROTOCOL_SENTINEL"),
            pack.index("## Assignment"),
            pack.index("ASSIGNMENT_SENTINEL"),
        ]
        self.assertEqual(ordered, sorted(ordered))
        for sentinel in (
            "ROLE_ONE_SENTINEL",
            "ROLE_TWO_SENTINEL",
            "PROTOCOL_SENTINEL",
            "ASSIGNMENT_SENTINEL",
        ):
            self.assertEqual(pack.count(sentinel), 1)
            self.assertNotIn(sentinel, completed.stdout)
        self.assertEqual(metadata["sha256"], sha256(output.read_bytes()))
        self.assertLessEqual(
            metadata["bytes"] + metadata["reserved_delivery_bytes"],
            metadata["max_bytes"],
        )

        oversized = self.root / "oversized.md"
        failed = self.run_cli(
            "pack",
            "--role",
            "lead",
            "--output",
            str(oversized),
            "--role-source",
            str(role_one),
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
            "--max-bytes",
            "10",
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(oversized.exists())
        self.assertIn("delivery-envelope framing", failed.stderr)

        too_large = self.write("sources/too-large.md", "x" * (97 * 1024))
        default_ceiling_output = self.root / "default-ceiling.md"
        failed = self.run_cli(
            "pack",
            "--role",
            "lead",
            "--output",
            str(default_ceiling_output),
            "--role-source",
            str(too_large),
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(default_ceiling_output.exists())
        self.assertIn("after reserving delivery-envelope framing", failed.stderr)

        framing_large = self.write("sources/framing-large.md", "y" * (95 * 1024))
        framing_output = self.root / "framing-large-pack.md"
        failed = self.run_cli(
            "pack",
            "--role",
            "lead",
            "--output",
            str(framing_output),
            "--role-source",
            str(framing_large),
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(framing_output.exists())
        self.assertIn("delivery-envelope framing", failed.stderr)

        control_source = self.root / "sources/control.md"
        control_source.write_bytes(b"safe\x00hidden\n")
        control_output = self.root / "control-pack.md"
        failed = self.run_cli(
            "pack",
            "--role",
            "lead",
            "--output",
            str(control_output),
            "--role-source",
            str(control_source),
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(control_output.exists())
        self.assertIn("forbidden control character", failed.stderr)

    def test_pack_rejects_duplicate_sources_and_never_replaces_canonical_output(self) -> None:
        source = self.write("source.md", "same source\n")
        other = self.write("other.md", "other\n")
        duplicate_output = self.root / "duplicate.md"
        completed = self.run_cli(
            "pack",
            "--role",
            "peer",
            "--output",
            str(duplicate_output),
            "--role-source",
            str(source),
            "--protocol-source",
            str(source),
            "--assignment-source",
            str(other),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("exactly once", completed.stderr)
        self.assertFalse(duplicate_output.exists())

        output = self.root / "canonical.md"
        assignment = self.write("assignment.md", "assignment\n")
        arguments = (
            "pack",
            "--role",
            "peer",
            "--output",
            str(output),
            "--role-source",
            str(source),
            "--protocol-source",
            str(other),
            "--assignment-source",
            f"assignment={assignment}",
        )
        completed = self.run_cli(*arguments)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        canonical = output.read_bytes()
        assignment.write_text("changed assignment\n", encoding="utf-8")
        completed = self.run_cli(*arguments)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("output already exists", completed.stderr)
        self.assertEqual(output.read_bytes(), canonical)

    def test_pack_ceiling_always_fits_largest_valid_delivery_envelope(self) -> None:
        role = self.write("boundary/role.md", "")
        protocol = self.write("boundary/protocol.md", "")
        assignment = self.write("boundary/assignment.md", "")
        probe = self.root / "boundary/probe.md"
        common_args = (
            "--role",
            "lead",
            "--role-source",
            str(role),
            "--protocol-source",
            str(protocol),
            "--assignment-source",
            str(assignment),
        )
        completed = self.run_cli("pack", "--output", str(probe), *common_args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        probe_metadata = json.loads(completed.stdout)
        padding_bytes = probe_metadata["pack_ceiling_bytes"] - probe_metadata["bytes"]
        self.assertGreater(padding_bytes, 0)
        role.write_text("x" * padding_bytes, encoding="utf-8")

        boundary_pack = self.root / "boundary/exact-pack.md"
        completed = self.run_cli("pack", "--output", str(boundary_pack), *common_args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        pack_metadata = json.loads(completed.stdout)
        self.assertEqual(pack_metadata["bytes"], pack_metadata["pack_ceiling_bytes"])

        opening = "Vietnamese" + "x" * (512 - len("Vietnamese"))
        closing = "Vietnamese" + "y" * (512 - len("Vietnamese"))
        receipt = self.root / "boundary/delivery.json"
        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(boundary_pack),
            "--live-language",
            "Vietnamese",
            "--opening",
            opening,
            "--closing",
            closing,
            "--herdr",
            "/bin/true",
            "--receipt",
            str(receipt),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["payload"]["bytes"], 96 * 1024)

    def test_deliver_uses_one_argument_without_leaking_payload_or_child_output(self) -> None:
        shell_marker = self.root / "payload-shell-marker"
        context = self.write(
            "context.md",
            f"CONTEXT_SECRET_SENTINEL $(touch {shell_marker})\n",
        )
        capture = self.root / "captured.json"
        fake = self.write(
            "fake-herdr",
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import pathlib
                import sys

                pathlib.Path(os.environ["CAPTURE_ARGS"]).write_text(
                    json.dumps(sys.argv[1:]), encoding="utf-8"
                )
                sys.stdout.write("RAW_CHILD_SENTINEL " + sys.argv[-1])
                sys.stderr.write("RAW_CHILD_STDERR_SENTINEL")
                """
            ),
            executable=True,
        )
        receipt = self.root / "receipt.json"
        env = os.environ.copy()
        env["CAPTURE_ARGS"] = str(capture)
        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead_test",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Hãy dùng Vietnamese cho hội thoại.",
            "--closing",
            "Tiếp tục dùng Vietnamese cho hội thoại.",
            "--herdr",
            str(fake),
            "--receipt",
            str(receipt),
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for secret in (
            "CONTEXT_SECRET_SENTINEL",
            "RAW_CHILD_SENTINEL",
            "RAW_CHILD_STDERR_SENTINEL",
            "Hãy dùng Vietnamese",
        ):
            self.assertNotIn(secret, completed.stdout)
            self.assertNotIn(secret, receipt.read_text(encoding="utf-8"))
        child_arguments = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(child_arguments[:3], ["agent", "prompt", "lead_test"])
        self.assertEqual(len(child_arguments), 4)
        payload = child_arguments[3]
        self.assertTrue(payload.startswith("Hãy dùng Vietnamese cho hội thoại.\n"))
        self.assertTrue(payload.endswith("Tiếp tục dùng Vietnamese cho hội thoại."))
        self.assertIn(context.read_text(encoding="utf-8"), payload)
        self.assertFalse(shell_marker.exists())
        result = json.loads(completed.stdout)
        self.assertEqual(result["payload"]["sha256"], sha256(payload.encode("utf-8")))
        self.assertEqual(result["state"], "accepted")
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["state"], "accepted")

    def test_deliver_validates_envelope_and_size_before_external_effect(self) -> None:
        context = self.write("context.md", "context\n")
        marker = self.root / "called"
        fake = self.write(
            "fake-herdr",
            f"#!/bin/sh\ntouch {marker}\n",
            executable=True,
        )
        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "This omits the configured value.",
            "--closing",
            "Continue in Vietnamese.",
            "--herdr",
            str(fake),
            "--receipt",
            str(self.root / "invalid-envelope-receipt.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(marker.exists())
        self.assertIn("exact live-language value", completed.stderr)

        completed = self.run_cli(
            "deliver",
            "--agent",
            "Lead;touch-marker",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--herdr",
            str(fake),
            "--receipt",
            str(self.root / "invalid-agent-receipt.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(marker.exists())
        self.assertIn("agent name must match", completed.stderr)

        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--max-bytes",
            "5",
            "--herdr",
            str(fake),
            "--receipt",
            str(self.root / "small-receipt.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(marker.exists())
        self.assertIn("ceiling", completed.stderr)

        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--max-bytes",
            str(96 * 1024 + 1),
            "--herdr",
            str(fake),
            "--receipt",
            str(self.root / "large-receipt.json"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(marker.exists())
        self.assertIn("safe single-argument ceiling", completed.stderr)

        nan_receipt = self.root / "nan-receipt.json"
        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--timeout-seconds",
            "nan",
            "--herdr",
            str(fake),
            "--receipt",
            str(nan_receipt),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("finite", completed.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(nan_receipt.exists())

        unsafe_context = self.root / "unsafe-context.md"
        unsafe_context.write_bytes(b"context\x00payload")
        unsafe_receipt = self.root / "unsafe-receipt.json"
        completed = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(unsafe_context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--herdr",
            str(fake),
            "--receipt",
            str(unsafe_receipt),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("forbidden control character", completed.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(unsafe_receipt.exists())

    def test_deliver_prepared_receipt_blocks_unrecorded_or_duplicate_attempts(self) -> None:
        context = self.write("context.md", "context\n")
        calls = self.root / "delivery-calls"
        fake = self.write(
            "failing-herdr",
            f"#!/bin/sh\nprintf x >> {calls}\nexit 1\n",
            executable=True,
        )
        receipt = self.root / "prepared-receipt.json"
        arguments = (
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--herdr",
            str(fake),
            "--receipt",
            str(receipt),
        )
        first = self.run_cli(*arguments)
        self.assertEqual(first.returncode, 2)
        prepared = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(prepared["state"], "prepared")
        self.assertNotIn("context\n", receipt.read_text(encoding="utf-8"))

        second = self.run_cli(*arguments)
        self.assertEqual(second.returncode, 2)
        self.assertIn("must be reconciled before any redelivery", second.stderr)
        self.assertEqual(calls.read_text(encoding="utf-8"), "x")

        marker = self.root / "should-not-run"
        successful_fake = self.write(
            "successful-herdr",
            f"#!/bin/sh\ntouch {marker}\n",
            executable=True,
        )
        unwritable_receipt = self.root / "missing-parent/receipt.json"
        blocked = self.run_cli(
            "deliver",
            "--agent",
            "lead",
            "--context",
            str(context),
            "--live-language",
            "Vietnamese",
            "--opening",
            "Use Vietnamese.",
            "--closing",
            "Continue in Vietnamese.",
            "--herdr",
            str(successful_fake),
            "--receipt",
            str(unwritable_receipt),
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("receipt parent", blocked.stderr)
        self.assertFalse(marker.exists())

    def test_deliver_finalize_failure_preserves_prepared_receipt(self) -> None:
        spec = importlib.util.spec_from_file_location("herdr_orchestrator_test_module", HELPER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)

        context = self.write("context.md", "context\n")
        receipt = self.root / "finalize-failure.json"
        args = module.build_parser().parse_args(
            [
                "deliver",
                "--agent",
                "lead",
                "--context",
                str(context),
                "--live-language",
                "Vietnamese",
                "--opening",
                "Use Vietnamese.",
                "--closing",
                "Continue in Vietnamese.",
                "--herdr",
                "herdr",
                "--receipt",
                str(receipt),
            ]
        )
        real_atomic_write = module._atomic_write
        writes = 0

        def fail_finalize(path, data, *, replace=False, mode=0o600):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise module.HelperError("injected finalize failure")
            return real_atomic_write(path, data, replace=replace, mode=mode)

        completed = subprocess.CompletedProcess([], 0, stdout=b"accepted", stderr=b"")
        with mock.patch.object(module, "_atomic_write", side_effect=fail_finalize), mock.patch.object(
            module.subprocess, "run", return_value=completed
        ) as prompt:
            with self.assertRaisesRegex(module.HelperError, "receipt remains prepared"):
                module.command_deliver(args)
        prompt.assert_called_once()
        prepared = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(prepared["state"], "prepared")
        self.assertEqual(writes, 2)

    def test_codex_models_writes_only_compact_projection(self) -> None:
        raw = {
            "models": [
                {
                    "slug": "gpt-one",
                    "default_reasoning_level": "medium",
                    "supported_reasoning_levels": [
                        {"effort": "low", "description": "RAW_LEVEL_DESCRIPTION"},
                        {"effort": "medium", "description": "RAW_LEVEL_DESCRIPTION"},
                    ],
                    "service_tiers": [{"id": "priority", "description": "RAW_TIER"}],
                    "base_instructions": "RAW_CATALOG_SECRET_SENTINEL",
                },
                {
                    "slug": "gpt-two",
                    "default_reasoning_level": "high",
                    "supported_reasoning_levels": ["medium", "high"],
                    "service_tiers": [],
                    "description": "RAW_MODEL_DESCRIPTION",
                },
            ]
        }
        catalog = self.write("catalog.json", json.dumps(raw))
        output = self.root / "models.json"
        completed = self.run_cli(
            "codex-models",
            "--catalog-file",
            str(catalog),
            "--output",
            str(output),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        projection = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            projection["models"],
            [
                {
                    "id": "gpt-one",
                    "default_reasoning_level": "medium",
                    "reasoning_levels": ["low", "medium"],
                    "service_tiers": ["priority"],
                },
                {
                    "id": "gpt-two",
                    "default_reasoning_level": "high",
                    "reasoning_levels": ["medium", "high"],
                    "service_tiers": [],
                },
            ],
        )
        for secret in (
            "RAW_CATALOG_SECRET_SENTINEL",
            "RAW_LEVEL_DESCRIPTION",
            "RAW_MODEL_DESCRIPTION",
        ):
            self.assertNotIn(secret, output.read_text(encoding="utf-8"))
            self.assertNotIn(secret, completed.stdout)
        metadata = json.loads(completed.stdout)
        self.assertEqual(metadata["model_count"], 2)
        self.assertEqual(metadata["sha256"], sha256(output.read_bytes()))


if __name__ == "__main__":
    unittest.main()
