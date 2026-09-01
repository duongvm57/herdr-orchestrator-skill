from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
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

    def run_cli(
        self,
        *arguments: str,
        environment_overrides: dict[str, str | None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve())}
        if "--project-root" in arguments:
            environment["HERDR_ORCHESTRATOR_PROJECT_ROOT"] = str(Path(arguments[arguments.index("--project-root") + 1]).resolve())
        if "--assignment" in arguments:
            assignment = json.loads(Path(arguments[arguments.index("--assignment") + 1]).read_text(encoding="utf-8"))
            environment["HERDR_ORCHESTRATOR_PROJECT_ROOT"] = assignment["project_root"]
        for key, value in (environment_overrides or {}).items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        return subprocess.run(
            [sys.executable, str(HELPER), *arguments], check=False, capture_output=True, text=True, env=environment
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
                "version = 4",
                "assessment_after_cycles = 2",
                "", "[roles.lead]", 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-sol'))}",
                'cost_class = "standard"',
                "", "[roles.supervisor]", 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-terra'))}",
                'cost_class = "standard"',
                "", "[peer_recipes.engineer]",
                'description = "Writable implementation recipe"', 'kind = "codex"',
                f"args = {json.dumps(self.codex_args('gpt-5.6-luna', '--config', 'model_reasoning_effort=low', '--ask-for-approval', 'never', '--no-alt-screen'))}",
                'cost_class = "standard"',
                "", "[routing.engineer]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.reviewer]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.architect]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.default]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
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

    def peer_assignment(self, project: Path, *, owner: str = "csv-engineer", recipe: str = "engineer", disposition: str = "Engineer") -> Path:
        reviewer = disposition.lower() == "reviewer"
        assignment = project / ".orchestration" / f"{owner}.json"
        assignment.write_text(json.dumps({
            "schema_version": 2, "assignment_id": f"lead-01:{owner}", "role": "peer",
            "parent": {"role": "lead", "id": "lead-01"}, "owner": owner,
            "project_root": str(project.resolve()), "worktree": None,
            "objective": "Complete the bounded assigned work.", "owned_scope": [] if reviewer else ["path:app"],
            "exclusions": ["Do not change unrelated files."], "authority": "read-only" if reviewer else "write",
            "disposition": disposition, "recipe": recipe, "verification": ["Run focused checks."],
            "dependencies": [], "languages": {"live": "Vietnamese", "artifact": "English"},
            "topology_rationale": None, "candidate": None, "review_cycle": 1,
            "prior_review": None, "convergence_assessment": None, "cost_approval": None,
        }), encoding="utf-8")
        return assignment

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
        self.assertEqual(result["config"]["version"], 4)
        self.assertEqual(result["languages"], {"artifact": "English", "live": "Vietnamese"})
        self.assertEqual(result["recipes"]["lead"]["kind"], "codex")
        self.assertEqual(result["recipes"]["routing"]["engineer"]["default_recipe"], "engineer")

    def test_validate_project_rejects_unknown_version_and_wrong_root(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("version = 4", "version = 2"), encoding="utf-8")
        version = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(version.returncode, 2)
        self.assertIn("version must be 4", version.stderr)
        config.write_text(config.read_text(encoding="utf-8").replace("version = 2", "version = 4"), encoding="utf-8")
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(protocol.read_text(encoding="utf-8").replace(str(project.resolve()), str(self.root.resolve())), encoding="utf-8")
        wrong_root = self.run_cli("validate-project", "--project-root", str(project))
        self.assertEqual(wrong_root.returncode, 2)
        self.assertIn("canonical project root", wrong_root.stderr)

    def test_validate_project_accepts_repository_root_wrapped_as_inline_code(self) -> None:
        project = self.project()
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                str(project.resolve()), f"`{project.resolve()}`",
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["protocol_repository_root"], str(project.resolve()))

    def test_validate_project_rejects_malformed_inline_code_repository_root(self) -> None:
        project = self.project()
        protocol = project / ".orchestration/workspace-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                str(project.resolve()), f"`{project.resolve()}``",
            ),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("canonical absolute path", completed.stderr)

    def test_validate_project_accepts_a_linked_worktree_of_protocol_repository_root(self) -> None:
        project = self.project()
        for command in (
            ("git", "init", "-q", str(project)),
            ("git", "-C", str(project), "config", "user.email", "test@example.invalid"),
            ("git", "-C", str(project), "config", "user.name", "Project Validation"),
            ("git", "-C", str(project), "add", "."),
            ("git", "-C", str(project), "commit", "-qm", "base"),
        ):
            subprocess.run(command, check=True, capture_output=True, text=True)
        worktree = self.root / "writer-worktree"
        subprocess.run(
            ("git", "-C", str(project), "worktree", "add", "-q", "-b", "writer", str(worktree), "HEAD"),
            check=True, capture_output=True, text=True,
        )
        self.addCleanup(
            lambda: subprocess.run(
                ("git", "-C", str(project), "worktree", "remove", "--force", str(worktree)),
                check=False, capture_output=True, text=True,
            )
        )

        completed = self.run_cli("validate-project", "--project-root", str(worktree))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["project_root"], str(worktree.resolve()))
        self.assertEqual(result["protocol_repository_root"], str(project.resolve()))

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
        candidate_config.write_text(canonical.joinpath("herdr-orchestrator.toml").read_text(encoding="utf-8").replace("version = 4", "version = 2"), encoding="utf-8")
        candidate_protocol.write_bytes(canonical.joinpath("workspace-protocol.md").read_bytes())

        completed = self.run_cli("validate-project", "--project-root", str(project), "--config", str(candidate_config), "--protocol", str(candidate_protocol))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("version must be 4", completed.stderr)

    def test_validate_project_default_uses_canonical_paths(self) -> None:
        project = self.project()
        candidate_config, candidate_protocol = self.root / "candidate.toml", self.root / "candidate.md"
        candidate_config.write_text("not valid", encoding="utf-8")
        candidate_protocol.write_text("not valid", encoding="utf-8")

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_validate_project_requires_default_supervisor_recipe(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        text = config.read_text(encoding="utf-8")
        start = text.index("[roles.supervisor]")
        end = text.index("[peer_recipes.", start)
        config.write_text(text[:start] + text[end:], encoding="utf-8")

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("roles must contain exactly lead and supervisor", completed.stderr)

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
        for command in ("validate-project", "doctor", "install-official-skill", "validate-control-role-launch", "compile-runtime", "prepare-control-role-launch", "render-control-prompt", "submit-control-prompt", "render-runtime-binding", "render-runtime-binding-pane", "start-peer", "submit-prompt", "submit-assignment", "freeze-candidate", "materialize-candidate", "validate-acceptance", "render-assignment", "validate-handback", "harness-models"):
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
        self.assertIn("HERDR_PANE_ID=wX:pE0", projection)
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

    def test_compile_runtime_replaces_hand_authored_binding_and_pane_json(self) -> None:
        project = self.project("compiled-runtime")
        assignment = self.peer_assignment(project)
        output = self.root / "runtime-context.json"

        completed = self.run_cli(
            "compile-runtime",
            "--project-root", str(project),
            "--kind", "codex",
            "--role", "lead",
            "--pane-id", "w9:pLead",
            "--target-role", "peer",
            "--assignment", str(assignment),
            "--herdr-program", "/bin/echo",
            "--socket-endpoint", str(self.root / "herdr.sock"),
            "--output", str(output),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        context = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(context["binding"]["role"], "lead")
        self.assertEqual(context["binding"]["herdr_pane_id"], "w9:pLead")
        self.assertEqual(context["binding"]["helper"], str(HELPER.resolve()))
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=w9:pLead", context["runtime_projection"])
        pane = context["pane_launch"]
        self.assertEqual(pane["source_pane_id"], "w9:pLead")
        self.assertEqual(pane["role"], "peer")
        environment = {item["name"]: item["value"] for item in pane["pane_environment"]}
        self.assertEqual(environment["HERDR_ORCHESTRATOR_ASSIGNMENT_ID"], "lead-01:csv-engineer")
        self.assertEqual(environment["HERDR_ORCHESTRATOR_OWNER"], "csv-engineer")
        self.assertNotIn("HERDR_SOCKET_PATH", environment)

        peer_output = self.root / "pi-peer-runtime.json"
        peer = self.run_cli(
            "compile-runtime",
            "--project-root", str(project),
            "--kind", "pi",
            "--role", "peer",
            "--pane-id", "w9:pPeer",
            "--source-context", str(output),
            "--output", str(peer_output),
        )
        self.assertEqual(peer.returncode, 0, peer.stderr)
        peer_context = json.loads(peer_output.read_text(encoding="utf-8"))
        self.assertEqual(peer_context["harness"], "pi")
        self.assertEqual(
            peer_context["binding"]["herdr_socket_endpoint"],
            context["binding"]["herdr_socket_endpoint"],
        )
        self.assertIn("Pi native runtime binding", peer_context["runtime_projection"])

        conflict = self.run_cli(
            "compile-runtime",
            "--project-root", str(project),
            "--kind", "pi",
            "--role", "peer",
            "--pane-id", "w9:pPeer2",
            "--source-context", str(output),
            "--herdr-program", "/bin/echo",
            "--output", str(self.root / "conflict.json"),
        )
        self.assertEqual(conflict.returncode, 2)
        self.assertIn("cannot be combined with native path overrides", conflict.stderr)

    def test_prepare_control_launch_compiles_exact_recipe_without_starting_agent(self) -> None:
        project = self.project("prepared-launch")
        output = self.root / "lead-launch.json"
        marker = self.root / "unexpected-start"
        fake_herdr = self.root / "manifest-herdr"
        fake_herdr.write_text(
            "#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)

        completed = self.run_cli(
            "prepare-control-role-launch",
            "--project-root", str(project),
            "--role", "lead",
            "--name", "dexport-lead",
            "--pane", "w7:p1",
            "--herdr-program", str(fake_herdr),
            "--output", str(output),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(manifest["agent"], {"name": "dexport-lead", "pane": "w7:p1"})
        self.assertEqual(manifest["recipe"]["kind"], "codex")
        self.assertEqual(manifest["herdr_argv"][:8], [
            str(fake_herdr.resolve()), "agent", "start", "dexport-lead",
            "--kind", "codex", "--pane", "w7:p1",
        ])
        self.assertEqual(manifest["herdr_argv"][8], "--")
        self.assertFalse(marker.exists())

    def test_render_control_prompt_preserves_verbatim_task_and_compiled_runtime(self) -> None:
        project = self.project("control-prompt")
        runtime = self.root / "lead-runtime.json"
        compiled = self.run_cli(
            "compile-runtime",
            "--project-root", str(project),
            "--kind", "codex",
            "--role", "lead",
            "--pane-id", "w8:pLead",
            "--herdr-program", "/bin/echo",
            "--socket-endpoint", str(self.root / "herdr.sock"),
            "--output", str(runtime),
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        task = self.root / "task.txt"
        payload = b"Implement `$herdr-orchestrator`; preserve $(touch nope).\nNo trailing rewrite."
        task.write_bytes(payload)
        output = self.root / "lead-prompt.md"

        completed = self.run_cli(
            "render-control-prompt",
            "--project-root", str(project),
            "--role", "lead",
            "--payload", str(task),
            "--runtime-context", str(runtime),
            "--output", str(output),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        rendered = output.read_bytes()
        self.assertTrue(rendered.endswith(payload))
        text = rendered.decode("utf-8")
        self.assertIn("# Workspace Protocol", text)
        self.assertIn("# Configured Peer Recipes", text)
        self.assertIn("# Adapter Runtime Context", text)
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=w8:pLead", text)
        result = json.loads(completed.stdout)
        self.assertEqual(result["payload_sha256"], hashlib.sha256(payload).hexdigest())

    def test_submit_control_prompt_composes_in_memory_with_exact_pane_binding(self) -> None:
        project = self.project("submitted-control-prompt")
        command_directory = self.root / "control-submit-commands"
        command_directory.mkdir()
        capture = self.root / "control-submit-argv.json"
        fake_herdr = command_directory / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['HERDR_TEST_CAPTURE']).write_text(json.dumps(sys.argv), encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        runtime = self.root / "submitted-lead-runtime.json"
        compiled = self.run_cli(
            "compile-runtime", "--project-root", str(project), "--kind", "codex",
            "--role", "lead", "--pane-id", "w8:pLead", "--herdr-program", str(fake_herdr),
            "--socket-endpoint", str(self.root / "herdr.sock"), "--output", str(runtime),
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        payload = b"literal $(touch never) with Unicode: ca phe \xe2\x98\x95\n"
        task = self.root / "submitted-task.txt"
        task.write_bytes(payload)

        completed = self.run_cli(
            "submit-control-prompt", "--agent", "lead-01", "--project-root", str(project),
            "--role", "lead", "--payload", str(task), "--runtime-context", str(runtime),
            environment_overrides={
                "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", ""),
                "HERDR_TEST_CAPTURE": str(capture),
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        argv = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(argv[1:4], ["agent", "prompt", "lead-01"])
        self.assertTrue(argv[4].encode().endswith(payload))
        self.assertIn("HERDR_PANE_ID=w8:pLead", argv[4])
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=w8:pLead", argv[4])
        result = json.loads(completed.stdout)
        self.assertEqual(result["command"], "submit-control-prompt")
        self.assertEqual(result["payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertNotIn("prompt_file", result)

    def test_submit_assignment_composes_and_submits_without_prompt_artifact(self) -> None:
        project = self.project("submitted-assignment")
        assignment = self.peer_assignment(project)
        command_directory = self.root / "assignment-submit-commands"
        command_directory.mkdir()
        capture = self.root / "assignment-submit-argv.json"
        fake_herdr = command_directory / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['HERDR_TEST_CAPTURE']).write_text(json.dumps(sys.argv), encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        runtime = self.root / "submitted-peer-runtime.json"
        compiled = self.run_cli(
            "compile-runtime", "--project-root", str(project), "--kind", "codex",
            "--role", "peer", "--pane-id", "w8:pPeer", "--herdr-program", str(fake_herdr),
            "--socket-endpoint", str(self.root / "herdr.sock"), "--output", str(runtime),
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        constraints = self.root / "peer-constraints.md"
        constraints.write_text("Only the bounded owned scope applies.\n", encoding="utf-8")

        completed = self.run_cli(
            "submit-assignment", "--agent", "csv-engineer", "--assignment", str(assignment),
            "--role-profile", str(SKILL_ROOT / "references/roles/peer.md"),
            "--applicable-protocol", str(constraints), "--runtime-context", str(runtime),
            environment_overrides={
                "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", ""),
                "HERDR_TEST_CAPTURE": str(capture),
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        argv = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(argv[1:4], ["agent", "prompt", "csv-engineer"])
        self.assertIn('"assignment_id": "lead-01:csv-engineer"', argv[4])
        self.assertIn("HERDR_PANE_ID=w8:pPeer", argv[4])
        self.assertIn("HERDR_ORCHESTRATOR_ASSIGNMENT_ID=lead-01:csv-engineer", argv[4])
        self.assertIn("HERDR_ORCHESTRATOR_OWNER=csv-engineer", argv[4])
        result = json.loads(completed.stdout)
        self.assertEqual(result["command"], "submit-assignment")
        self.assertEqual(result["assignment_id"], "lead-01:csv-engineer")
        self.assertFalse((project / ".orchestration/prompts").exists())

    def test_render_supervisor_prompt_machine_binds_attachment_and_protocol_scope(self) -> None:
        project = self.project("supervisor-prompt")
        runtime = self.root / "supervisor-runtime.json"
        compiled = self.run_cli(
            "compile-runtime",
            "--project-root", str(project),
            "--kind", "codex",
            "--role", "supervisor",
            "--pane-id", "w8:pSupervisor",
            "--herdr-program", "/bin/echo",
            "--socket-endpoint", str(self.root / "herdr.sock"),
            "--output", str(runtime),
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        mandate = self.root / "mandate.txt"
        payload = b"Observe bounded evidence only."
        mandate.write_bytes(payload)
        output = self.root / "supervisor-prompt.md"

        missing = self.run_cli(
            "render-control-prompt",
            "--project-root", str(project),
            "--role", "supervisor",
            "--payload", str(mandate),
            "--runtime-context", str(runtime),
            "--output", str(output),
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("attached Lead name", missing.stderr)

        completed = self.run_cli(
            "render-control-prompt",
            "--project-root", str(project),
            "--role", "supervisor",
            "--payload", str(mandate),
            "--runtime-context", str(runtime),
            "--attached-lead-name", "dexport-lead",
            "--attached-lead-pane", "w8:pLead",
            "--output", str(output),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rendered = output.read_bytes()
        self.assertTrue(rendered.endswith(payload))
        text = rendered.decode("utf-8")
        self.assertIn('"lead_name": "dexport-lead"', text)
        self.assertIn('"lead_pane": "w8:pLead"', text)
        self.assertNotIn("# Workspace Protocol", text)

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
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
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
                "version = 4", "assessment_after_cycles = 2",
                "", "[roles.lead]", 'kind = "claude"',
                'args = ["--model", "claude-test"]',
                'cost_class = "standard"',
                "", "[roles.supervisor]", 'kind = "claude"',
                'args = ["--model", "claude-test"]',
                'cost_class = "standard"',
                "", "[peer_recipes.engineer]",
                'description = "Verified Claude recipe"', 'kind = "claude"',
                'args = ["--model", "claude-test"]', 'cost_class = "standard"',
                "", "[routing.engineer]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.reviewer]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.architect]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]',
                "", "[routing.default]", 'default_recipe = "engineer"', 'allowed_recipes = ["engineer"]', "",
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
        self.assertEqual(projected.returncode, 0, projected.stderr)
        runtime = (self.root / "claude-runtime.md").read_text(encoding="utf-8")
        self.assertIn("Claude Code native runtime binding", runtime)
        self.assertNotIn("shell_environment_policy", runtime)
        self.assertEqual(pane_projected.returncode, 0, pane_projected.stderr)
        pane = json.loads((self.root / "claude-pane.json").read_text(encoding="utf-8"))
        self.assertEqual(pane["harness"], "claude")
        self.assertNotIn("CODEX_HOME", json.dumps(pane))

    def test_every_verified_harness_has_end_to_end_runtime_projection(self) -> None:
        binding = self.runtime_binding()
        expected = ("pi", "claude", "codex", "opencode", "grok", "omp")

        for kind in expected:
            with self.subTest(kind=kind):
                runtime_path = self.root / f"{kind}-runtime.md"
                pane_path = self.root / f"{kind}-pane.json"
                rendered = self.run_cli(
                    "render-runtime-binding",
                    "--binding", str(binding),
                    "--kind", kind,
                    "--output", str(runtime_path),
                )
                pane_rendered = self.run_cli(
                    "render-runtime-binding-pane",
                    "--binding", str(binding),
                    "--kind", kind,
                    "--role", "peer",
                    "--output", str(pane_path),
                )

                self.assertEqual(rendered.returncode, 0, rendered.stderr)
                self.assertEqual(pane_rendered.returncode, 0, pane_rendered.stderr)
                runtime = runtime_path.read_text(encoding="utf-8")
                pane = json.loads(pane_path.read_text(encoding="utf-8"))
                self.assertIn("HERDR_ORCHESTRATOR_PANE_ID=wX:pE0", runtime)
                self.assertNotIn("HOME=", runtime)
                self.assertNotIn("CODEX_HOME=", runtime)
                self.assertEqual(pane["harness"], kind)
                names = {item["name"] for item in pane["pane_environment"]}
                self.assertTrue(names.isdisjoint({
                    "HOME", "CODEX_HOME", "HERDR_ENV", "HERDR_SOCKET_PATH",
                    "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID",
                }))

    def test_doctor_distinguishes_agent_support_from_integration_role(self) -> None:
        kinds = ("pi", "claude", "codex", "opencode", "grok", "omp")
        commands = self.root / "doctor-commands"
        commands.mkdir()
        fake_herdr = commands / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "if args == ['--version']:\n"
            " print('herdr 0.8.2')\n"
            "elif args == ['status']:\n"
            " print('server:\\n  status: running\\n  compatible: yes\\n  socket: /tmp/herdr.sock')\n"
            "elif args == ['--skill']:\n"
            " print('---\\nname: herdr\\ndescription: test\\n---\\n\\n# OFFICIAL SKILL BODY THAT MUST NOT LEAK')\n"
            "elif args == ['agent', 'start', '--help']:\n"
            " print('[possible values: pi, claude, codex, opencode, grok, omp]')\n"
            "elif args == ['integration', 'status']:\n"
            " print('pi: current (v8) (/private/pi)')\n"
            " print('claude: current (v8) (/private/claude)')\n"
            " print('codex: current (v8) (/private/codex)')\n"
            " print('opencode: current (v10) (/private/opencode)')\n"
            " print('grok: not installed (/private/grok)')\n"
            " print('omp: not installed (/private/omp)')\n"
            "else:\n"
            " raise SystemExit(2)\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        arguments = [
            "doctor", "--project-root", str(self.root),
            "--herdr-program", str(fake_herdr),
        ]
        for kind in kinds:
            program = commands / kind
            program.write_text(
                "#!/usr/bin/env python3\nimport pathlib, sys\nprint(pathlib.Path(sys.argv[0]).name + ' 1.0.0')\n",
                encoding="utf-8",
            )
            program.chmod(0o755)
            arguments.extend(("--harness-program", f"{kind}={program}"))

        completed = self.run_cli(*arguments)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ready"])
        self.assertEqual(result["project"]["status"], "not_checked")
        harnesses = {item["kind"]: item for item in result["harnesses"]}
        self.assertEqual(set(harnesses), set(kinds))
        for kind in kinds:
            self.assertTrue(harnesses[kind]["supported_by_herdr"])
            self.assertEqual(harnesses[kind]["runtime"], "static_projection_ready")
        self.assertTrue(harnesses["grok"]["ready"])
        self.assertFalse(harnesses["omp"]["ready"])
        self.assertEqual(harnesses["grok"]["integration"], {
            "required_for_lifecycle": False,
            "role": "session",
            "state": "not_installed",
            "state_authority": "screen_manifest",
        })
        self.assertEqual(harnesses["omp"]["integration"], {
            "required_for_lifecycle": True,
            "role": "state_and_session",
            "state": "not_installed",
            "state_authority": "lifecycle_without_documented_fallback",
        })
        self.assertIn(
            {
                "scope": "harness.omp.integration",
                "reason": "current_lifecycle_integration_required",
                "remediation": ["herdr", "integration", "install", "omp"],
            },
            result["failures"],
        )
        self.assertEqual(result["probe_strategy"], "bounded_parallel")
        self.assertNotIn("OFFICIAL SKILL BODY", completed.stdout)
        self.assertNotIn("/private/", completed.stdout)

        fake_herdr.write_text(
            fake_herdr.read_text(encoding="utf-8").replace(
                "omp: not installed",
                "omp: current",
            ),
            encoding="utf-8",
        )
        accepted = self.run_cli(*arguments)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertTrue(json.loads(accepted.stdout)["ready"])

        fake_herdr.write_text(
            fake_herdr.read_text(encoding="utf-8").replace(
                "pi, claude, codex, opencode, grok, omp",
                "pi, claude, codex, opencode, grok",
            ),
            encoding="utf-8",
        )
        rejected = self.run_cli(
            "doctor", "--project-root", str(self.root),
            "--kind", "omp",
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"omp={commands / 'omp'}",
        )
        self.assertEqual(rejected.returncode, 2)
        rejection = json.loads(rejected.stdout)
        self.assertFalse(rejection["ready"])
        self.assertIn(
            {"scope": "harness.omp.support", "reason": "not_advertised_by_herdr"},
            rejection["failures"],
        )

    def test_doctor_runs_independent_herdr_probes_concurrently(self) -> None:
        commands = self.root / "parallel-doctor"
        commands.mkdir()
        fake_herdr = commands / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys, time\n"
            "time.sleep(0.5)\n"
            "args = sys.argv[1:]\n"
            "if args == ['--version']: print('herdr 1.0')\n"
            "elif args == ['status']: print('server:\\n  status: running\\n  compatible: yes\\n  socket: /tmp/herdr.sock')\n"
            "elif args == ['--skill']: print('---\\nname: herdr\\ndescription: test\\n---\\n\\n# Herdr')\n"
            "elif args == ['agent', 'start', '--help']: print('[possible values: pi]')\n"
            "elif args == ['integration', 'status']: print('pi: current')\n"
            "else: raise SystemExit(2)\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        fake_pi = commands / "pi"
        fake_pi.write_text("#!/bin/sh\necho 'pi 1.0'\n", encoding="utf-8")
        fake_pi.chmod(0o755)

        started = time.monotonic()
        completed = self.run_cli(
            "doctor", "--project-root", str(self.root), "--kind", "pi",
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"pi={fake_pi}",
        )
        elapsed = time.monotonic() - started

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLess(elapsed, 2.0, f"doctor probes ran sequentially in {elapsed:.2f}s")

    def test_install_official_skill_materializes_target_project_roots(self) -> None:
        fake_herdr = self.root / "materialize-herdr"
        skill_text = "---\nname: herdr\ndescription: first\n---\n\n# Herdr\n"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"sys.stdout.write({skill_text!r}) if sys.argv[1:] == ['--skill'] else sys.exit(2)\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        kinds = ("pi", "claude", "codex", "opencode", "grok", "omp")
        arguments = [
            "install-official-skill",
            "--project-root", str(self.root),
            "--herdr-program", str(fake_herdr),
        ]
        for kind in kinds:
            arguments.extend(("--kind", kind))

        installed = self.run_cli(*arguments)

        self.assertEqual(installed.returncode, 0, installed.stderr)
        result = json.loads(installed.stdout)
        self.assertEqual(
            {item["target"]: item["status"] for item in result["installations"]},
            {"agents": "installed", "claude": "installed"},
        )
        targets = {
            "agents": self.root / ".agents/skills/herdr/SKILL.md",
            "claude": self.root / ".claude/skills/herdr/SKILL.md",
        }
        for target_kind, target in targets.items():
            with self.subTest(target=target_kind):
                self.assertEqual(target.read_text(encoding="utf-8"), skill_text)
                self.assertEqual(
                    next(item["path"] for item in result["installations"] if item["target"] == target_kind),
                    str(target.relative_to(self.root)),
                )

        current = self.run_cli(*arguments)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertTrue(all(
            item["status"] == "current"
            for item in json.loads(current.stdout)["installations"]
        ))

        updated_text = skill_text.replace("description: first", "description: updated")
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"sys.stdout.write({updated_text!r}) if sys.argv[1:] == ['--skill'] else sys.exit(2)\n",
            encoding="utf-8",
        )
        stale = self.run_cli(*arguments)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("stale; rerun with --replace", stale.stderr)
        self.assertEqual(
            targets["agents"].read_text(encoding="utf-8"),
            skill_text,
        )

        updated = self.run_cli(
            *arguments, "--replace"
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertTrue(all(
            item["status"] == "updated"
            for item in json.loads(updated.stdout)["installations"]
        ))
        for target in targets.values():
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                updated_text,
            )

    def test_doctor_validates_project_and_configured_catalog_at_setup(self) -> None:
        project = self.project("doctor-project")
        config = project / ".orchestration/herdr-orchestrator.toml"
        config_text = config.read_text(encoding="utf-8")
        updated_config, replacements = re.subn(
            r'(\[peer_recipes\.engineer\]\ndescription = "Writable implementation recipe"\n)'
            r'kind = "codex"\nargs = \[.*?\]',
            r'\1kind = "claude"\nargs = ["--model", "claude-test"]',
            config_text,
            count=1,
        )
        self.assertEqual(replacements, 1)
        config.write_text(updated_config, encoding="utf-8")
        commands = self.root / "doctor-project-commands"
        commands.mkdir()
        fake_herdr = commands / "herdr"
        fake_herdr.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "if args == ['--version']: print('herdr 0.8.2')\n"
            "elif args == ['status']: print('server:\\n  status: running\\n  compatible: yes\\n  socket: /tmp/herdr.sock')\n"
            "elif args == ['--skill']: print('---\\nname: herdr\\ndescription: test\\n---\\n\\n# Herdr')\n"
            "elif args == ['agent', 'start', '--help']: print('[possible values: claude, codex]')\n"
            "elif args == ['integration', 'status']:\n"
            " print('claude: current (v8) (/private/claude)')\n"
            " print('codex: current (v8) (/private/codex)')\n"
            "else: raise SystemExit(2)\n",
            encoding="utf-8",
        )
        fake_herdr.chmod(0o755)
        fake_codex = commands / "codex"
        fake_codex.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "if sys.argv[1:] == ['--version']:\n"
            " print('codex-cli 1.0.0')\n"
            "elif sys.argv[1:] == ['debug', 'models']:\n"
            " print(json.dumps({'models': [{'slug': 'gpt-5.6-sol', 'supported_reasoning_levels': [], 'default_reasoning_level': None}]}))\n"
            "else:\n"
            " raise SystemExit(2)\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        fake_claude = commands / "claude"
        fake_claude.write_text(
            "#!/bin/sh\necho 'claude-cli 1.0.0'\n", encoding="utf-8"
        )
        fake_claude.chmod(0o755)
        install = self.run_cli(
            "install-official-skill", "--project-root", str(project),
            "--herdr-program", str(fake_herdr),
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        for command in (
            ("git", "init", "-q", str(project)),
            ("git", "-C", str(project), "config", "user.email", "test@example.invalid"),
            ("git", "-C", str(project), "config", "user.name", "Doctor Test"),
            ("git", "-C", str(project), "add", "."),
            ("git", "-C", str(project), "commit", "-qm", "setup"),
        ):
            subprocess.run(command, check=True, capture_output=True, text=True)
        worktree = self.root / "doctor-worktree"
        subprocess.run(
            ("git", "-C", str(project), "worktree", "add", "-q", "-b", "doctor-worktree", str(worktree), "HEAD"),
            check=True, capture_output=True, text=True,
        )
        self.addCleanup(
            lambda: subprocess.run(
                ("git", "-C", str(project), "worktree", "remove", "--force", str(worktree)),
                check=False, capture_output=True, text=True,
            )
        )
        self.assertEqual(
            (worktree / ".agents/skills/herdr/SKILL.md").read_text(encoding="utf-8"),
            "---\nname: herdr\ndescription: test\n---\n\n# Herdr\n",
        )
        self.assertEqual(
            (worktree / ".claude/skills/herdr/SKILL.md").read_text(encoding="utf-8"),
            "---\nname: herdr\ndescription: test\n---\n\n# Herdr\n",
        )
        home = self.root / "doctor-home"
        home.mkdir()
        environment = {"HOME": str(home), "CODEX_HOME": None}
        official = project / ".agents/skills/herdr/SKILL.md"

        completed = self.run_cli(
            "doctor", "--project-root", str(project),
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"codex={fake_codex}",
            "--harness-program", f"claude={fake_claude}",
            environment_overrides=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ready"])
        self.assertEqual(result["project"]["status"], "ready")
        harnesses = {item["kind"]: item for item in result["harnesses"]}
        self.assertEqual(set(harnesses), {"claude", "codex"})
        self.assertEqual(harnesses["codex"]["catalog"]["status"], "ready")
        self.assertEqual(harnesses["codex"]["catalog"]["model_count"], 1)
        self.assertEqual(
            {item["target"] for item in result["official_skill"]["targets"]},
            {"agents", "claude"},
        )
        self.assertTrue(all(
            item["status"] == "current"
            and item["repository"]["status"] == "committed"
            for item in result["official_skill"]["targets"]
        ))

        global_skill = home / ".agents/skills/herdr/SKILL.md"
        global_skill.parent.mkdir(parents=True)
        global_skill.write_text("stale\n", encoding="utf-8")
        claude_global_skill = home / ".claude/skills/herdr/SKILL.md"
        claude_global_skill.parent.mkdir(parents=True)
        claude_global_skill.write_text("stale\n", encoding="utf-8")
        shadowed = self.run_cli(
            "doctor", "--project-root", str(project),
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"codex={fake_codex}",
            "--harness-program", f"claude={fake_claude}",
            environment_overrides=environment,
        )
        self.assertEqual(shadowed.returncode, 2)
        shadowed_result = json.loads(shadowed.stdout)
        self.assertEqual(
            {item["kind"]: item for item in shadowed_result["harnesses"]}["codex"]
            ["global_official_skill"]["status"],
            "shadowed",
        )
        self.assertIn(
            {
                "scope": "harness.codex.global_official_skill",
                "reason": "global_skill_shadows_repository_skill",
            },
            shadowed_result["failures"],
        )
        self.assertIn(
            {
                "scope": "harness.claude.global_official_skill",
                "reason": "global_skill_shadows_repository_skill",
            },
            shadowed_result["failures"],
        )
        global_skill.unlink()
        claude_global_skill.unlink()

        official.write_text("stale\n", encoding="utf-8")
        stale = self.run_cli(
            "doctor", "--project-root", str(project),
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"codex={fake_codex}",
            "--harness-program", f"claude={fake_claude}",
            environment_overrides=environment,
        )
        self.assertEqual(stale.returncode, 2)
        stale_result = json.loads(stale.stdout)
        self.assertEqual(
            stale_result["official_skill"]["targets"][0]["status"],
            "stale",
        )
        skill_failure = next(
            failure for failure in stale_result["failures"]
            if failure["scope"] == "official_skill.agents"
        )
        self.assertIn("--replace", skill_failure["remediation"])

        official.unlink()
        missing = self.run_cli(
            "doctor", "--project-root", str(project),
            "--herdr-program", str(fake_herdr),
            "--harness-program", f"codex={fake_codex}",
            "--harness-program", f"claude={fake_claude}",
            environment_overrides=environment,
        )
        self.assertEqual(missing.returncode, 2)
        missing_result = json.loads(missing.stdout)
        self.assertEqual(
            missing_result["official_skill"]["targets"][0]["status"],
            "missing",
        )
        missing_failure = next(
            failure for failure in missing_result["failures"]
            if failure["scope"] == "official_skill.agents"
        )
        self.assertNotIn("--replace", missing_failure["remediation"])

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
            "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead",
            "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve()), "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead",
        }

        completed = subprocess.run(
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt), "--project-root", str(project)],
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
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt), "--project-root", str(project)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", ""), "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("native Herdr prompt submission failed with exit status 17", completed.stderr)
        self.assertIn("native prompt rejected", completed.stderr)

    def test_submit_prompt_rejects_foreign_project_root_binding(self) -> None:
        project = self.project()
        foreign_project = self.project("foreign-project")
        prompt = self.root / "prompt.txt"
        prompt.write_text("one payload", encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt), "--project-root", str(project)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(foreign_project.resolve())},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires a bound canonical project root", completed.stderr)

    def test_successful_side_effects_tolerate_malformed_native_diagnostics(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        arguments = type("Arguments", (), {
            "assignment": str(assignment), "pane": "wX:pED",
            "dry_run": False,
        })()
        native_diagnostics = b"\xff\x1b[31mwarning\x00\x07\n"
        peer_completed = subprocess.CompletedProcess([], 0, native_diagnostics, native_diagnostics)

        environment = {"HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())}
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch("subprocess.run", return_value=peer_completed):
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
            [sys.executable, str(HELPER), "submit-prompt", "--agent", "lead-01", "--prompt-file", str(prompt), "--project-root", str(project)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PATH": str(command_directory) + os.pathsep + os.environ.get("PATH", ""), "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())},
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
        assignment = self.peer_assignment(project)
        configured = self.codex_args(
            "gpt-5.6-luna", "--config", "model_reasoning_effort=low",
            "--ask-for-approval", "never", "--no-alt-screen",
        )

        completed = self.run_cli(
            "start-peer", "--assignment", str(assignment), "--pane", "wX:pED", "--dry-run",
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

    def test_elevated_peer_recipe_requires_assignment_cost_approval(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        config = project / ".orchestration/herdr-orchestrator.toml"
        peer_args = json.dumps(self.codex_args(
            "gpt-5.6-luna", "--config", "model_reasoning_effort=low",
            "--ask-for-approval", "never", "--no-alt-screen",
        ))
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                f"args = {peer_args}\ncost_class = \"standard\"",
                f"args = {peer_args}\ncost_class = \"elevated\"",
            ),
            encoding="utf-8",
        )

        rejected = self.run_cli(
            "start-peer", "--assignment", str(assignment), "--pane", "wX:pED", "--dry-run",
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("requires verbatim Human cost approval", rejected.stderr)

        value = json.loads(assignment.read_text(encoding="utf-8"))
        value["cost_approval"] = "Human approved elevated reviewer spend for this task."
        assignment.write_text(json.dumps(value), encoding="utf-8")
        accepted = self.run_cli(
            "start-peer", "--assignment", str(assignment), "--pane", "wX:pED", "--dry-run",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        result = json.loads(accepted.stdout)
        self.assertEqual(result["recipe"]["cost_class"], "elevated")
        self.assertEqual(result["cost_approval"], value["cost_approval"])

    def test_elevated_control_role_requires_human_cost_approval(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('cost_class = "standard"', 'cost_class = "elevated"', 1), encoding="utf-8")
        rejected = self.run_cli("validate-control-role-launch", "--project-root", str(project), "--role", "lead")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("verbatim Human cost approval", rejected.stderr)
        accepted = self.run_cli("validate-control-role-launch", "--project-root", str(project), "--role", "lead", "--cost-approval", "Human approved elevated Lead cost.")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_project_recipes_require_an_explicit_cost_class(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace('cost_class = "standard"\n', "", 1),
            encoding="utf-8",
        )

        completed = self.run_cli("validate-project", "--project-root", str(project))

        self.assertEqual(completed.returncode, 2)
        self.assertIn("cost_class", completed.stderr)

    def test_start_peer_derives_owner_and_recipe_from_assignment(self) -> None:
        project = self.project()
        first_assignment = self.peer_assignment(project, owner="csv-engineer")
        second_assignment = self.peer_assignment(project, owner="candidate-reviewer", disposition="Reviewer")
        first = self.run_cli(
            "start-peer", "--assignment", str(first_assignment), "--pane", "wX:pED", "--dry-run",
        )
        second = self.run_cli(
            "start-peer", "--assignment", str(second_assignment), "--pane", "wX:pEE", "--dry-run",
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

    def test_start_peer_uses_route_default_when_assignment_omits_recipe(self) -> None:
        project = self.project()
        config = project / ".orchestration/herdr-orchestrator.toml"
        alternate_args = json.dumps(self.codex_args("gpt-5.6-terra"))
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                'default_recipe = "engineer"\nallowed_recipes = ["engineer"]',
                'default_recipe = "alternate"\nallowed_recipes = ["engineer", "alternate"]',
                1,
            ) + "\n[peer_recipes.alternate]\ndescription = \"Default Engineer route\"\nkind = \"codex\"\nargs = " + alternate_args + '\ncost_class = "standard"\n',
            encoding="utf-8",
        )
        assignment = self.peer_assignment(project)
        value = json.loads(assignment.read_text(encoding="utf-8"))
        value["recipe"] = None
        assignment.write_text(json.dumps(value), encoding="utf-8")

        completed = self.run_cli(
            "start-peer", "--assignment", str(assignment), "--pane", "wX:pED", "--dry-run",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["recipe"]["name"], "alternate")

    def test_start_peer_executes_the_exact_rendered_herdr_argv(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        configured = self.codex_args(
            "gpt-5.6-luna", "--config", "model_reasoning_effort=low",
            "--ask-for-approval", "never", "--no-alt-screen",
        )
        expected = [
            "herdr", "agent", "start", "csv-engineer", "--kind", "codex",
            "--pane", "wX:pED", "--", *configured,
        ]
        arguments = type("Arguments", (), {
            "assignment": str(assignment), "pane": "wX:pED",
            "dry_run": False,
        })()
        completed = subprocess.CompletedProcess(expected, 0, b'{"started":true}\n', b"")

        environment = {"HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())}
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch("subprocess.run", return_value=completed) as run:
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
        assignment = self.peer_assignment(project)
        config = project / ".orchestration/herdr-orchestrator.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                '"--no-alt-screen"',
                '"--reasoning-effort", "low"',
            ),
            encoding="utf-8",
        )

        completed = self.run_cli(
            "start-peer", "--assignment", str(assignment), "--pane", "wX:pED", "--dry-run",
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("peer_recipes.engineer.args has an unsupported option", completed.stderr)

    def test_peer_binding_cannot_start_another_peer(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        environment = {**os.environ, "HERDR_ORCHESTRATOR_ROLE": "peer", "HERDR_PANE_ID": "wX:pPeer", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pPeer", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())}
        completed = subprocess.run(
            [sys.executable, str(HELPER), "start-peer", "--assignment", str(assignment), "--pane", "wX:pChild", "--dry-run"],
            check=False, capture_output=True, text=True, env=environment,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires a bound role", completed.stderr)

    def test_start_peer_rejects_mismatched_bound_pane(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        environment = {**os.environ, "HERDR_ORCHESTRATOR_ROLE": "lead", "HERDR_PANE_ID": "wX:pLead", "HERDR_ORCHESTRATOR_PANE_ID": "wX:pForeign", "HERDR_ORCHESTRATOR_HELPER": str(HELPER.resolve()), "HERDR_ORCHESTRATOR_PROJECT_ROOT": str(project.resolve())}
        completed = subprocess.run(
            [sys.executable, str(HELPER), "start-peer", "--assignment", str(assignment), "--pane", "wX:pChild", "--dry-run"],
            check=False, capture_output=True, text=True, env=environment,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("PANE_ID to match", completed.stderr)

    def test_cycle_three_requires_convergence_assessment(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project, disposition="Reviewer")
        value = json.loads(assignment.read_text(encoding="utf-8"))
        value.update({"review_cycle": 3, "prior_review": {"reviewer_assignment_id": "lead-01:review-02", "reviewer_assignment_sha256": "a" * 64, "reviewer_handback_sha256": "b" * 64}})
        assignment.write_text(json.dumps(value), encoding="utf-8")
        rejected = self.run_cli("validate-assignment", "--assignment", str(assignment), "--project-root", str(project))
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("requires convergence_assessment", rejected.stderr)
        value["convergence_assessment"] = {"mechanisms": [{"mechanism": "parser boundary", "findings": ["review-02 finding 1"]}], "decision": "retry", "rationale": "Findings repeat the parser-boundary mechanism."}
        assignment.write_text(json.dumps(value), encoding="utf-8")
        invalid = self.run_cli("validate-assignment", "--assignment", str(assignment), "--project-root", str(project))
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("decision must be continue", invalid.stderr)
        value["convergence_assessment"]["decision"] = "re-architect"
        assignment.write_text(json.dumps(value), encoding="utf-8")
        accepted = self.run_cli("validate-assignment", "--assignment", str(assignment), "--project-root", str(project))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_validate_assignment_uses_its_project_route_without_an_optional_override(self) -> None:
        project = self.project()
        assignment = self.peer_assignment(project)
        value = json.loads(assignment.read_text(encoding="utf-8"))
        value["recipe"] = "unconfigured-recipe"
        assignment.write_text(json.dumps(value), encoding="utf-8")

        rejected = self.run_cli("validate-assignment", "--assignment", str(assignment))

        self.assertEqual(rejected.returncode, 2)
        self.assertIn("not allowed for routing.engineer", rejected.stderr)

    def test_validate_assignment_fails_closed_without_project_policy_unless_explicitly_structural(self) -> None:
        project = self.root / "no-policy-project"
        project.mkdir()
        assignment = self.peer_assignment(self.project("policy-source"))
        value = json.loads(assignment.read_text(encoding="utf-8"))
        value["project_root"] = str(project.resolve())
        assignment.write_text(json.dumps(value), encoding="utf-8")

        rejected = self.run_cli("validate-assignment", "--assignment", str(assignment))
        structural = self.run_cli("validate-assignment", "--assignment", str(assignment), "--structural-only")

        self.assertEqual(rejected.returncode, 2)
        self.assertIn("project config is not a readable file", rejected.stderr)
        self.assertEqual(structural.returncode, 0, structural.stderr)


if __name__ == "__main__":
    unittest.main()
