from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
RUNTIME = SKILL_ROOT / "scripts/herdr_runtime.py"


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.log = self.root / "herdr.jsonl"
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "HERDR_ENV": "1",
                "HERDR_PANE_ID": "w1:p1",
                "FAKE_HERDR_LOG": str(self.log),
            }
        )
        self.herdr = self._fake_herdr()
        self.project = self._project()

    def _fake_herdr(self) -> Path:
        path = self.root / "herdr"
        path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json, os, sys
                from pathlib import Path

                args = sys.argv[1:]
                with Path(os.environ["FAKE_HERDR_LOG"]).open("a") as stream:
                    stream.write(json.dumps(args) + "\\n")
                mode = os.environ.get("FAKE_START_MODE", "ready")
                if args[:2] == ["pane", "layout"]:
                    result = {"layout": {"panes": [{"pane_id": "w1:p1", "rect": {"width": 160, "height": 40}}]}}
                elif args[:2] == ["pane", "split"]:
                    result = {"pane": {"pane_id": "w1:p2"}}
                elif args[:2] == ["agent", "start"]:
                    if mode == "not-ready":
                        print(json.dumps({"error": {"code": "agent_not_ready"}}), file=sys.stderr)
                        raise SystemExit(1)
                    result = {"agent": {"name": args[2], "pane_id": "w1:p2"}}
                elif args[:2] == ["agent", "get"]:
                    state = "blocked" if mode == "not-ready" else "idle"
                    result = {"agent": {"name": args[2], "pane_id": "w1:p2", "agent_status": state}}
                elif args[:2] == ["agent", "read"]:
                    print("peer result from Herdr")
                    raise SystemExit(0)
                elif args[:2] == ["agent", "wait"]:
                    result = {"agent": {"name": args[2], "agent_status": "idle"}}
                elif args[:2] == ["agent", "prompt"]:
                    result = {"accepted": True, "agent": args[2]}
                elif args[:2] == ["agent", "focus"]:
                    result = {"focused": args[2]}
                else:
                    print(json.dumps({"error": {"code": "unsupported", "args": args}}), file=sys.stderr)
                    raise SystemExit(2)
                print(json.dumps({"id": "fake", "result": result}))
                """
            ),
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def _project(self) -> Path:
        project = self.root / "project"
        orchestration = project / ".orchestration"
        orchestration.mkdir(parents=True)
        (orchestration / "herdr-orchestrator.toml").write_text(
            textwrap.dedent(
                """\
                version = 3
                fallback_peer_recipe = "balanced"

                [roles.lead]
                kind = "codex"
                args = ["--model", "lead-model", "--sandbox", "workspace-write", "--config", "sandbox_workspace_write.network_access=true"]

                [roles.supervisor]
                kind = "codex"
                args = ["--model", "supervisor-model", "--sandbox", "workspace-write", "--config", "sandbox_workspace_write.network_access=true"]

                [peer_recipes.balanced]
                description = "bounded coding profile"
                kind = "pi"
                args = ["--model", "peer-model"]

                [peer_recipes.review]
                description = "read-only review profile"
                kind = "codex"
                args = ["--model", "review-model", "--sandbox", "read-only"]
                """
            ),
            encoding="utf-8",
        )
        lines: list[str] = []
        template = (SKILL_ROOT / "assets/workspace-protocol-template.md").read_text(encoding="utf-8")
        for line in template.splitlines():
            if line.endswith("YYYY-MM-DD"):
                line = line.replace("YYYY-MM-DD", "2026-08-26")
            elif line.endswith("Live orchestration language:"):
                line += " Vietnamese"
            elif line.endswith("Durable Markdown artifact language:"):
                line += " English"
            elif line.endswith("Repository root:"):
                line += f" {project.resolve()}"
            elif line.lstrip().startswith("- ") and line.endswith(":"):
                line += " configured"
            lines.append(line)
        (orchestration / "workspace-protocol.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return project

    def _run(self, *args: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNTIME), "--herdr", str(self.herdr), *args],
            check=False,
            capture_output=True,
            text=True,
            env=environment or self.environment,
        )

    def _commands(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_lead_start_uses_native_herdr_flow_without_focus_or_files(self) -> None:
        before = {path.relative_to(self.project) for path in self.project.rglob("*")}
        task = "Implement the small task; preserve the literal $herdr-orchestrator."
        completed = self._run(
            "start",
            "--role",
            "lead",
            "--project-root",
            str(self.project),
            "--task",
            task,
            "--name",
            "test-lead",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "prompted")
        commands = self._commands()
        self.assertEqual([command[:2] for command in commands], [
            ["pane", "layout"], ["pane", "split"], ["agent", "start"], ["agent", "prompt"]
        ])
        self.assertIn("--no-focus", commands[1])
        self.assertIn("HERDR_ORCHESTRATOR_ROLE=lead", commands[1])
        self.assertNotIn(["agent", "focus"], [command[:2] for command in commands])
        self.assertIn("lead-model", commands[2])
        prompt = commands[3][3]
        self.assertIn("# Workspace Protocol", prompt)
        self.assertIn("Available Peer profiles", prompt)
        self.assertIn(
            "bounded task must contain\nboth the accepted Git base and the exact candidate",
            prompt,
        )
        self.assertIn(task, prompt)
        self.assertLess(
            prompt.index("Never invoke `$herdr-orchestrator`"),
            prompt.index("## Human task"),
        )
        after = {path.relative_to(self.project) for path in self.project.rglob("*")}
        self.assertEqual(after, before)

    def test_peer_requires_exact_profile_and_receives_bounded_constraints_only(self) -> None:
        lead_environment = {**self.environment, "HERDR_ORCHESTRATOR_ROLE": "lead"}
        missing = self._run(
            "start", "--role", "peer", "--project-root", str(self.project), "--task", "Review it.",
            environment=lead_environment,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("exact configured --profile", missing.stderr)

        completed = self._run(
            "start", "--role", "peer", "--profile", "review", "--project-root", str(self.project),
            "--task", "Review candidate abc.", "--constraints", "Project write is denied.", "--name", "test-peer",
            environment=lead_environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        commands = self._commands()
        start = next(command for command in commands if command[:2] == ["agent", "start"])
        self.assertEqual(start[start.index("--kind") + 1], "codex")
        self.assertIn("review-model", start)
        split = next(command for command in commands if command[:2] == ["pane", "split"])
        self.assertIn("HERDR_ORCHESTRATOR_ROLE=peer", split)
        prompt = next(command for command in commands if command[:2] == ["agent", "prompt"])[3]
        self.assertIn("Project write is denied.", prompt)
        self.assertNotIn("Available Peer profiles", prompt)
        self.assertNotIn("## 12.", prompt)
        self.assertLess(
            prompt.index("Never invoke `$herdr-orchestrator`"),
            prompt.index("## Bounded Assignment"),
        )

    def test_agent_not_ready_preserves_identity_and_does_not_prompt_or_replace(self) -> None:
        environment = {**self.environment, "FAKE_START_MODE": "not-ready"}
        completed = self._run(
            "start", "--role", "lead", "--project-root", str(self.project),
            "--task", "Do the task.", "--name", "blocked-lead", environment=environment
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "blocked_startup")
        self.assertEqual(result["agent"], "blocked-lead")
        commands = self._commands()
        self.assertEqual(sum(command[:2] == ["agent", "start"] for command in commands), 1)
        self.assertFalse(any(command[:2] == ["agent", "prompt"] for command in commands))

    def test_result_waits_then_reads_terminal_output(self) -> None:
        completed = self._run("result", "--agent", "test-peer", "--timeout", "500")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["state"], "idle")
        self.assertEqual(result["output"], "peer result from Herdr\n")
        commands = self._commands()
        self.assertEqual([command[:2] for command in commands], [
            ["agent", "wait"], ["agent", "get"], ["agent", "read"]
        ])

    def test_supervisor_gets_full_protocol_only_for_explicit_protocol_mandate(self) -> None:
        completed = self._run(
            "start", "--role", "supervisor", "--project-root", str(self.project),
            "--task", "Observe coordination friction.", "--name", "test-supervisor"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        prompt = next(command for command in self._commands() if command[:2] == ["agent", "prompt"])[3]
        self.assertNotIn("## 12.", prompt)
        self.assertNotIn("Available Peer profiles", prompt)
        self.assertLess(
            prompt.index("Never invoke `$herdr-orchestrator`"),
            prompt.index("## Observation scope"),
        )
        split = next(command for command in self._commands() if command[:2] == ["pane", "split"])
        self.assertIn("HERDR_ORCHESTRATOR_ROLE=supervisor", split)

    def test_unknown_parent_role_metadata_is_rejected_before_pane_split(self) -> None:
        environment = {**self.environment, "HERDR_ORCHESTRATOR_ROLE": "unknown"}
        completed = self._run(
            "start",
            "--role",
            "lead",
            "--project-root",
            str(self.project),
            "--task",
            "Attempt to use unknown role metadata.",
            environment=environment,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("has unsupported role", completed.stderr)
        self.assertEqual(self._commands(), [])

    def test_forbidden_role_transitions_are_rejected_before_pane_split(self) -> None:
        forbidden = {
            "launcher": ("peer",),
            "lead": ("lead", "supervisor"),
            "peer": ("lead", "peer", "supervisor"),
            "supervisor": ("lead", "peer", "supervisor"),
        }
        for parent, children in forbidden.items():
            for child in children:
                with self.subTest(parent=parent, child=child):
                    environment = self.environment.copy()
                    if parent != "launcher":
                        environment["HERDR_ORCHESTRATOR_ROLE"] = parent
                    completed = self._run(
                        "start",
                        "--role",
                        child,
                        "--project-root",
                        str(self.project),
                        "--task",
                        "Attempt forbidden orchestration after seeing $herdr-orchestrator.",
                        environment=environment,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn("not allowed", completed.stderr)
                    self.assertEqual(self._commands(), [])


if __name__ == "__main__":
    unittest.main()
