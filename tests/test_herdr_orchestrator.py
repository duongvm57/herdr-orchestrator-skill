from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from fnmatch import fnmatchcase
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"
CODEX_ROLE_ENVIRONMENT_ARGS = (
    "--config", 'shell_environment_policy.inherit="all"',
    "--config", "shell_environment_policy.ignore_default_excludes=false",
    "--config", "allow_login_shell=false",
    "--config", 'shell_environment_policy.filters.HOME="include"',
    "--config", 'shell_environment_policy.filters.CODEX_HOME="include"',
    "--config", 'shell_environment_policy.filters.PATH="include"',
    "--config", 'shell_environment_policy.filters.SHELL="include"',
    "--config", 'shell_environment_policy.filters.USER="include"',
    "--config", 'shell_environment_policy.filters.LOGNAME="include"',
    "--config", 'shell_environment_policy.filters.PWD="include"',
    "--config", 'shell_environment_policy.filters.TERM="include"',
    "--config", 'shell_environment_policy.filters.TMPDIR="include"',
    "--config", 'shell_environment_policy.filters.LANG="include"',
    "--config", 'shell_environment_policy.filters."LC_*"="include"',
    "--config", 'shell_environment_policy.filters.XDG_RUNTIME_DIR="include"',
    "--config", 'shell_environment_policy.filters."HERDR_*"="include"',
    "--config", 'shell_environment_policy.filters."HERDR_ORCHESTRATOR_*"="include"',
)
CODEX_ROLE_ENVIRONMENT_FILTERS = (
    "HOME", "CODEX_HOME", "PATH", "SHELL", "USER", "LOGNAME", "PWD",
    "TERM", "TMPDIR", "LANG", "LC_*", "XDG_RUNTIME_DIR", "HERDR_*",
    "HERDR_ORCHESTRATOR_*",
)


class ProjectValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *arguments], check=False, capture_output=True, text=True
        )

    def codex_args(self, model: str, *extra: str) -> list[str]:
        return [
            "--model", model, "--sandbox", "workspace-write",
            "--config", "sandbox_workspace_write.network_access=true",
            *CODEX_ROLE_ENVIRONMENT_ARGS, *extra,
        ]

    def project(self, name: str = "project") -> Path:
        project = self.root / name
        orchestration = project / ".orchestration"
        orchestration.mkdir(parents=True)
        (orchestration / "herdr-orchestrator.toml").write_text(
            "\n".join([
                "version = 3",
                'fallback_peer_recipe = "engineer"',
                "", "[roles.lead]", 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-sol'))}",
                "", "[roles.supervisor]", 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-terra'))}",
                "", "[peer_recipes.engineer]",
                'description = "Writable implementation recipe"', 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-luna', '--config', 'model_reasoning_effort=low', '--ask-for-approval', 'never', '--no-alt-screen'))}",
                "",
            ]),
            encoding="utf-8",
        )
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

    def runtime_binding(self, role: str = "lead", pane: str = "wX:pE0") -> Path:
        project = self.project("runtime-project")
        document: dict[str, object] = {
            "schema_version": 2,
            "role": role,
            "herdr_executable": str(Path("/bin/echo").resolve()),
            "herdr_socket_endpoint": str(self.root / "herdr.sock"),
            "herdr_pane_id": pane,
            "helper": str(HELPER.resolve()),
            "project_root": str(project.resolve()),
        }
        binding = self.root / f"{role}-binding.json"
        binding.write_text(json.dumps(document), encoding="utf-8")
        return binding

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
                text = text.replace(
                    f'"--model", "{model}", "--sandbox", "workspace-write"',
                    f'"--model", "{model}", "--sandbox", "read-only"',
                    1,
                )
                config.write_text(text, encoding="utf-8")

                completed = self.run_cli("validate-project", "--project-root", str(project))

                self.assertEqual(completed.returncode, 2)
                self.assertIn(f"roles.{role} Codex requires --sandbox workspace-write", completed.stderr)

    def test_validate_project_does_not_require_peer_control_plane_access(self) -> None:
        project = self.project()

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_validate_project_rejects_codex_recipe_without_role_subprocess_policy(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                '"--config", "shell_environment_policy.filters.\\"HERDR_*\\"=\\"include\\"", ',
                "",
                1,
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("roles.lead Codex requires the explicit role subprocess environment policy", completed.stderr)
        self.assertIn('shell_environment_policy.filters."HERDR_*"="include"', completed.stderr)

    def test_validate_project_rejects_codex_secret_wildcard_inheritance(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                '"--config", "allow_login_shell=false",',
                '"--config", "allow_login_shell=false", "--config", "shell_environment_policy.filters.\\"AWS_*\\"=\\"include\\"",',
                1,
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("roles.lead.args value", completed.stderr)
        self.assertIn("unsupported Codex configuration override", completed.stderr)

    def test_codex_role_environment_policy_preserves_required_parent_values_only(self) -> None:
        """Model Codex's documented all -> default excludes -> include-only order."""
        parent = {
            "HOME": "/isolated/home",
            "CODEX_HOME": "/isolated/codex",
            "HERDR_ENV": "1",
            "HERDR_SOCKET_PATH": "/tmp/herdr.sock",
            "HERDR_ORCHESTRATOR_HELPER": "/project/helper.py",
            "HERDR_ORCHESTRATOR_PROJECT_ROOT": "/project",
            "AWS_REGION": "ap-southeast-1",
            "UNRELATED_VALUE": "discard",
        }
        after_default_excludes = {
            key: value
            for key, value in parent.items()
            if not any(token in key.upper() for token in ("KEY", "SECRET", "TOKEN"))
        }
        effective = {
            key: value
            for key, value in after_default_excludes.items()
            if any(fnmatchcase(key.upper(), pattern.upper()) for pattern in CODEX_ROLE_ENVIRONMENT_FILTERS)
        }

        self.assertIn('shell_environment_policy.inherit="all"', CODEX_ROLE_ENVIRONMENT_ARGS)
        self.assertEqual(
            effective,
            {
                "HOME": "/isolated/home",
                "CODEX_HOME": "/isolated/codex",
                "HERDR_ENV": "1",
                "HERDR_SOCKET_PATH": "/tmp/herdr.sock",
                "HERDR_ORCHESTRATOR_HELPER": "/project/helper.py",
                "HERDR_ORCHESTRATOR_PROJECT_ROOT": "/project",
            },
        )

    def test_validate_project_rejects_read_only_codex_supervisor_even_with_network_config(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                '"--model", "gpt-5.6-terra", "--sandbox", "workspace-write"',
                '"--model", "gpt-5.6-terra", "--sandbox", "read-only"',
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("roles.supervisor Codex requires --sandbox workspace-write", completed.stderr)

    def test_helper_exposes_policy_commands_only(self) -> None:
        completed = self.run_cli("--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command in ("init-run", "stage-assets", "pack", "deliver", "receipt"):
            self.assertNotIn(command, completed.stdout)
        for command in ("validate-project", "render-runtime-binding", "render-runtime-binding-pane", "start-peer", "submit-prompt", "freeze-candidate", "inspect-candidate", "validate-acceptance", "render-assignment", "validate-handback", "harness-models"):
            self.assertIn(command, completed.stdout)

    def test_codex_adapter_renders_literal_runtime_binding_commands(self) -> None:
        binding = self.runtime_binding()
        output = self.root / "codex-runtime.md"

        completed = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(output),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["role"], "lead")
        self.assertEqual(result["harness"], "codex")
        projection = output.read_text(encoding="utf-8")
        self.assertIn("Codex tool subprocesses cannot rely on inherited role environment", projection)
        self.assertIn(f"HERDR_SOCKET_PATH={self.root / 'herdr.sock'}", projection)
        self.assertIn(f"HERDR_ORCHESTRATOR_HELPER={HELPER.resolve()}", projection)
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=wX:pE0", projection)
        self.assertIn(str(Path("/bin/echo").resolve()), projection)
        self.assertNotIn("HOME=", projection)
        self.assertNotIn("CODEX_HOME=", projection)
        self.assertNotIn("shell_environment_policy", projection)

    def test_codex_runtime_binding_needs_no_harness_profile_home(self) -> None:
        binding = self.runtime_binding()

        completed = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(self.root / "codex-runtime.md"),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_runtime_binding_requires_bound_pane_and_rejects_profile_fields(self) -> None:
        binding = self.runtime_binding()
        document = json.loads(binding.read_text(encoding="utf-8"))
        document.pop("herdr_pane_id")
        binding.write_text(json.dumps(document), encoding="utf-8")

        missing = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(self.root / "runtime.md"),
        )

        self.assertEqual(missing.returncode, 2)
        self.assertIn("runtime binding has unsupported or missing fields", missing.stderr)
        document["herdr_pane_id"] = "wX:pE0"
        document["isolation_home"] = str(self.root)
        binding.write_text(json.dumps(document), encoding="utf-8")

        legacy = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(self.root / "runtime.md"),
        )

        self.assertEqual(legacy.returncode, 2)
        self.assertIn("runtime binding has unsupported or missing fields", legacy.stderr)

    def test_returned_peer_pane_identity_is_bound_after_creation(self) -> None:
        binding = self.runtime_binding(role="peer", pane="wX:pPeer")
        output = self.root / "peer-runtime.md"

        completed = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(output),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=wX:pPeer", output.read_text(encoding="utf-8"))

    def test_codex_runtime_commands_override_scrubbed_ambient_binding(self) -> None:
        binding = self.runtime_binding()
        fake_herdr = self.root / "bound-herdr"
        fake_helper = self.root / "bound-helper.py"
        fake_program = (
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CAPTURE']).write_text(json.dumps({\n"
            "  'argv': sys.argv,\n"
            "  'socket': os.environ.get('HERDR_SOCKET_PATH'),\n"
            "  'helper': os.environ.get('HERDR_ORCHESTRATOR_HELPER'),\n"
            "  'home': os.environ.get('HOME'),\n"
            "  'codex_home': os.environ.get('CODEX_HOME'),\n"
            "}), encoding='utf-8')\n"
        )
        fake_herdr.write_text(fake_program, encoding="utf-8")
        fake_herdr.chmod(0o755)
        fake_helper.write_text(fake_program, encoding="utf-8")
        document = json.loads(binding.read_text(encoding="utf-8"))
        document["herdr_executable"] = str(fake_herdr.resolve())
        document["helper"] = str(fake_helper.resolve())
        binding.write_text(json.dumps(document), encoding="utf-8")
        projection_path = self.root / "codex-runtime.md"
        rendered = self.run_cli(
            "render-runtime-binding", "--binding", str(binding), "--kind", "codex",
            "--output", str(projection_path),
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        projection = projection_path.read_text(encoding="utf-8")
        native = re.search(r"Native Herdr: `([^`]+)`", projection)
        helper = re.search(r"Canonical helper: `([^`]+)`", projection)
        self.assertIsNotNone(native)
        self.assertIsNotNone(helper)
        assert native is not None and helper is not None
        native_command = shlex.split(native.group(1))
        helper_command = shlex.split(helper.group(1))
        self.assertEqual(native_command.pop(), "<native-herdr-args...>")
        self.assertEqual(helper_command.pop(), "<helper-command-and-args...>")
        wrong_environment = {
            "PATH": os.environ["PATH"],
            "HERDR_SOCKET_PATH": "/ambient/wrong.sock",
            "HERDR_ORCHESTRATOR_HELPER": "/ambient/wrong-helper.py",
            "HOME": "/ambient/wrong-home",
            "CODEX_HOME": "/ambient/wrong-codex-home",
        }
        native_capture = self.root / "native-capture.json"
        helper_capture = self.root / "helper-capture.json"

        subprocess.run(
            [*native_command, "agent", "list"], check=True,
            env={**wrong_environment, "CAPTURE": str(native_capture)},
        )
        subprocess.run(
            [*helper_command, "probe"], check=True,
            env={**wrong_environment, "CAPTURE": str(helper_capture)},
        )

        native_result = json.loads(native_capture.read_text(encoding="utf-8"))
        helper_result = json.loads(helper_capture.read_text(encoding="utf-8"))
        expected_socket = str(self.root / "herdr.sock")
        expected_helper = str(fake_helper.resolve())
        self.assertEqual(native_result["argv"][0], str(fake_herdr.resolve()))
        self.assertEqual(native_result["argv"][1:], ["agent", "list"])
        self.assertEqual(native_result["socket"], expected_socket)
        self.assertEqual(helper_result["argv"][0], str(fake_helper.resolve()))
        self.assertEqual(helper_result["argv"][1:], ["probe"])
        self.assertEqual(helper_result["helper"], expected_helper)
        for result in (native_result, helper_result):
            self.assertEqual(result["home"], "/ambient/wrong-home")
            self.assertEqual(result["codex_home"], "/ambient/wrong-codex-home")

    def test_codex_peer_pane_projection_uses_bound_lead_pane_without_profile_homes(self) -> None:
        binding = self.runtime_binding(role="lead", pane="wX:pLead")
        pane_binding = self.root / "peer-pane.json"
        completed = self.run_cli(
            "render-runtime-binding-pane", "--binding", str(binding), "--kind", "codex", "--role", "peer",
            "--output", str(pane_binding),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        projection = json.loads(pane_binding.read_text(encoding="utf-8"))
        environment = {
            item["name"]: item["value"] for item in projection["pane_environment"]
        }
        self.assertEqual(projection["role"], "peer")
        self.assertEqual(projection["source_pane_id"], "wX:pLead")
        self.assertEqual(environment["HERDR_ORCHESTRATOR_ROLE"], "peer")
        self.assertEqual(environment["HERDR_ORCHESTRATOR_PROJECT_ROOT"], str((self.root / "runtime-project").resolve()))
        self.assertEqual(environment["HERDR_ORCHESTRATOR_HELPER"], str(HELPER.resolve()))
        self.assertTrue(set(environment).isdisjoint({
            "HOME", "CODEX_HOME", "HERDR_ENV", "HERDR_SOCKET_PATH",
            "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID",
        }))

        fake_herdr = self.root / "pane-herdr"
        capture = self.root / "pane-capture.json"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv), encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        pane_argv = [str(fake_herdr), "pane", "split", "--pane", projection["source_pane_id"]]
        for item in projection["pane_environment"]:
            pane_argv.extend(("--env", f"{item['name']}={item['value']}"))
        subprocess.run(
            pane_argv, check=True,
            env={"PATH": os.environ["PATH"], "CAPTURE": str(capture), "HOME": "/ambient/wrong-home", "CODEX_HOME": "/ambient/wrong-codex-home"},
        )
        supplied = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(supplied, pane_argv)

    def test_non_codex_recipe_has_no_codex_config_requirement(self) -> None:
        project = self.project("claude-project")
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            "\n".join((
                "version = 3",
                'fallback_peer_recipe = "engineer"',
                "", "[roles.lead]", 'kind = "claude"',
                'args = ["--model", "claude-test"]',
                "", "[roles.supervisor]", 'kind = "claude"',
                'args = ["--model", "claude-test"]',
                "", "[peer_recipes.engineer]",
                'description = "Verified Claude recipe"', 'kind = "claude"',
                'args = ["--model", "claude-test"]', "",
            )),
            encoding="utf-8",
        )

        binding = self.runtime_binding()
        validated = self.run_cli("validate-project", "--project-root", str(project))
        projected = self.run_cli(
            "render-runtime-binding", "--binding", str(binding),
            "--kind", "claude", "--output", str(self.root / "claude-runtime.md"),
        )
        pane_projected = self.run_cli(
            "render-runtime-binding-pane", "--binding", str(binding),
            "--kind", "claude", "--role", "peer", "--output", str(self.root / "claude-pane.json"),
        )

        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertNotIn("shell_environment_policy", validated.stdout)
        self.assertEqual(projected.returncode, 2)
        self.assertIn("claude has no verified runtime-binding projection", projected.stderr)
        self.assertNotIn("shell_environment_policy", projected.stderr)
        self.assertEqual(pane_projected.returncode, 2)
        self.assertIn("claude has no verified runtime-binding pane projection", pane_projected.stderr)
        self.assertNotIn("CODEX_HOME", pane_projected.stderr)

    def test_runtime_binding_rejects_unverified_harness_without_guessing(self) -> None:
        completed = self.run_cli(
            "render-runtime-binding", "--binding", str(self.runtime_binding()),
            "--kind", "unverified", "--output", str(self.root / "runtime.md"),
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("unverified has no verified orchestrator adapter", completed.stderr)

    def test_submit_prompt_preserves_adversarial_file_payload_without_shell_evaluation(self) -> None:
        project = self.project()
        command_directory = self.root / "commands"
        command_directory.mkdir()
        capture = self.root / "argv.json"
        marker = self.root / "shell-evaluated"
        fake_herdr = command_directory / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['HERDR_TEST_CAPTURE']).write_text(json.dumps(sys.argv), encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        prompt = self.root / "prompt.txt"
        payload = "quotes \\\" and ' apostrophe `backtick` $dollar $(touch " + str(marker) + ")\nUnicode: cà phê ☕; metacharacters ; | & < >"
        prompt.write_text(payload, encoding="utf-8")
        environment = {
            **os.environ,
            "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", ""),
            "HERDR_TEST_CAPTURE": str(capture),
        }

        completed = subprocess.run(
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt)],
            check=False, capture_output=True, text=True, env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(json.loads(capture.read_text(encoding="utf-8"))[1:], ["agent", "prompt", "lead-01", payload])
        result = json.loads(completed.stdout)
        self.assertEqual(result["submission"], "accepted-by-native-herdr")
        self.assertNotIn(payload, completed.stdout)

    def test_submit_prompt_reports_native_failure(self) -> None:
        project = self.project()
        command_directory = self.root / "failing-commands"
        command_directory.mkdir()
        fake_herdr = command_directory / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stderr.write('native prompt rejected\\n')\n"
            "raise SystemExit(17)\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        prompt = self.root / "prompt.txt"
        prompt.write_text("one payload", encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("native Herdr prompt submission failed with exit status 17", completed.stderr)
        self.assertIn("native prompt rejected", completed.stderr)

    def test_successful_side_effects_tolerate_malformed_native_diagnostics(self) -> None:
        project = self.project()
        arguments = type("Arguments", (), {
            "project_root": str(project), "config": None, "protocol": None,
            "recipe": "engineer", "name": "csv-engineer", "pane": "wX:pED",
            "dry_run": False,
        })()
        native_diagnostics = b"\xff\x1b[31mwarning\x00\x07\n"
        peer_completed = subprocess.CompletedProcess([], 0, native_diagnostics, native_diagnostics)

        with mock.patch("subprocess.run", return_value=peer_completed):
            from importlib.util import module_from_spec, spec_from_file_location

            specification = spec_from_file_location("herdr_orchestrator_diagnostic_test", HELPER)
            assert specification is not None and specification.loader is not None
            module = module_from_spec(specification)
            sys.modules[specification.name] = module
            try:
                specification.loader.exec_module(module)
                peer_result = module.command_start_peer(arguments)
            finally:
                sys.modules.pop(specification.name, None)

        self.assertEqual(peer_result["launch"], "executed")
        self.assertEqual(peer_result["returncode"], 0)
        self.assertIn("\ufffd\\x1b[31mwarning\\x00\\x07", peer_result["stdout"])

        command_directory = self.root / "malformed-diagnostic-commands"
        command_directory.mkdir()
        fake_herdr = command_directory / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdout.buffer.write(b'\\xff\\x1b[32maccepted\\x00')\n"
            "sys.stderr.buffer.write(b'\\xff\\x1b[31mdiag\\x07')\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        prompt = self.root / "prompt.txt"
        prompt.write_text("one payload", encoding="utf-8")

        submitted = subprocess.run(
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        submission = json.loads(submitted.stdout)
        self.assertEqual(submission["submission"], "accepted-by-native-herdr")
        self.assertIn("\ufffd\\x1b[32maccepted\\x00", submission["stdout"])
        self.assertIn("\ufffd\\x1b[31mdiag\\x07", submission["stderr"])

    def test_approval_required_recipe_rejects_never_policy(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        original = config.read_text(encoding="utf-8")
        invalid = json.dumps(self.codex_args("gpt-5.6-sol", "--ask-for-approval", "never"))
        config.write_text(
            original.replace(
                f"args = {json.dumps(self.codex_args('gpt-5.6-sol'))}",
                f"args = {invalid}\napproval_required = true",
                1,
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires approval but native args disable it", completed.stderr)

    def test_start_peer_preserves_every_configured_recipe_argument_in_order(self) -> None:
        project = self.project()
        configured = self.codex_args(
            "gpt-5.6-luna", "--config", "model_reasoning_effort=low",
            "--ask-for-approval", "never", "--no-alt-screen",
        )

        completed = self.run_cli(
            "start-peer", "--project-root", str(project), "--recipe", "engineer",
            "--name", "csv-engineer", "--pane", "wX:pED", "--dry-run",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["recipe"]["args"], configured)
        self.assertEqual(
            result["herdr_argv"],
            [
                "herdr", "agent", "start", "csv-engineer", "--kind", "codex",
                "--pane", "wX:pED", "--", *configured,
            ],
        )

    def test_start_peer_only_accepts_runtime_name_and_pane_outside_recipe(self) -> None:
        project = self.project()
        first = self.run_cli(
            "start-peer", "--project-root", str(project), "--recipe", "engineer",
            "--name", "csv-engineer", "--pane", "wX:pED", "--dry-run",
        )
        second = self.run_cli(
            "start-peer", "--project-root", str(project), "--recipe", "engineer",
            "--name", "candidate-reviewer", "--pane", "wX:pEE", "--dry-run",
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_result, second_result = json.loads(first.stdout), json.loads(second.stdout)
        self.assertEqual(first_result["recipe"]["args"], second_result["recipe"]["args"])
        self.assertEqual(first_result["herdr_argv"][9:], second_result["herdr_argv"][9:])
        self.assertEqual(first_result["name"], "csv-engineer")
        self.assertEqual(second_result["name"], "candidate-reviewer")
        self.assertEqual(first_result["pane"], "wX:pED")
        self.assertEqual(second_result["pane"], "wX:pEE")

    def test_start_peer_executes_the_exact_rendered_herdr_argv(self) -> None:
        project = self.project()
        configured = self.codex_args(
            "gpt-5.6-luna", "--config", "model_reasoning_effort=low",
            "--ask-for-approval", "never", "--no-alt-screen",
        )
        expected = [
            "herdr", "agent", "start", "csv-engineer", "--kind", "codex",
            "--pane", "wX:pED", "--", *configured,
        ]
        arguments = type("Arguments", (), {
            "project_root": str(project), "config": None, "protocol": None,
            "recipe": "engineer", "name": "csv-engineer", "pane": "wX:pED",
            "dry_run": False,
        })()
        completed = subprocess.CompletedProcess(expected, 0, b'{"started":true}\n', b"")

        with mock.patch("subprocess.run", return_value=completed) as run:
            from importlib.util import module_from_spec, spec_from_file_location

            specification = spec_from_file_location("herdr_orchestrator_for_test", HELPER)
            assert specification is not None and specification.loader is not None
            module = module_from_spec(specification)
            sys.modules[specification.name] = module
            try:
                specification.loader.exec_module(module)
                result = module.command_start_peer(arguments)
            finally:
                sys.modules.pop(specification.name, None)

        run.assert_called_once_with(expected, shell=False, check=False, capture_output=True)
        self.assertEqual(result["herdr_argv"], expected)
        self.assertEqual(result["recipe"]["args"], configured)

    def test_start_peer_rejects_an_invented_unsupported_native_flag(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                '"--no-alt-screen"',
                '"--reasoning-effort", "low"',
            ),
            encoding="utf-8",
        )

        completed = self.run_cli(
            "start-peer", "--project-root", str(project), "--recipe", "engineer",
            "--name", "csv-engineer", "--pane", "wX:pED", "--dry-run",
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("peer_recipes.engineer.args has an unsupported option", completed.stderr)


if __name__ == "__main__":
    unittest.main()
