from __future__ import annotations

import hashlib
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
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"
LAYOUT = SKILL_ROOT / "scripts/herdr_balanced_split.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = os.environ.copy()
        self.environment["HERDR_ENV"] = "1"
        self.state = self.root / "fake-herdr-state.json"
        self.environment["FAKE_HERDR_STATE"] = str(self.state)
        self.herdr = self._fake_herdr()
        self.project = self._project()
        self.run_dir = self._init_run()

    def _run(
        self,
        *arguments: str,
        helper: Path = HELPER,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(helper), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment,
        )

    def _fake_herdr(self) -> Path:
        script = self.root / "fake-herdr.py"
        script.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json, os, sys
                from pathlib import Path

                state_path = Path(os.environ["FAKE_HERDR_STATE"])
                if state_path.exists():
                    state = json.loads(state_path.read_text())
                else:
                    state = {
                        "panes": [{
                            "pane_id": "pane-launcher",
                            "rect": {"x": 0, "y": 0, "width": 160, "height": 48},
                        }],
                        "agents": [],
                        "next_pane": 1,
                    }

                def save():
                    state_path.write_text(json.dumps(state))

                args = sys.argv[1:]
                result = {}
                if args[:2] == ["agent", "list"]:
                    result = {"agents": state["agents"], "type": "agent_list"}
                elif args[:2] == ["pane", "layout"]:
                    result = {"layout": {
                        "workspace_id": "workspace",
                        "tab_id": "tab",
                        "zoomed": False,
                        "panes": state["panes"],
                    }}
                elif args[:2] == ["pane", "split"]:
                    target = args[args.index("--pane") + 1]
                    current = next(item for item in state["panes"] if item["pane_id"] == target)
                    before = dict(current["rect"])
                    pane_id = f"pane-{state['next_pane']}"
                    state["next_pane"] += 1
                    direction = args[args.index("--direction") + 1]
                    if direction == "right":
                        left = before["width"] // 2
                        current["rect"]["width"] = left
                        rect = {**before, "x": before["x"] + left, "width": before["width"] - left}
                    else:
                        top = before["height"] // 2
                        current["rect"]["height"] = top
                        rect = {**before, "y": before["y"] + top, "height": before["height"] - top}
                    state["panes"].append({"pane_id": pane_id, "rect": rect})
                    save()
                    result = {"pane": {"pane_id": pane_id}}
                elif args[:2] == ["agent", "start"]:
                    name = args[2]
                    pane = args[args.index("--pane") + 1]
                    state["agents"].append({
                        "name": name,
                        "pane_id": pane,
                        "agent_status": "idle",
                    })
                    save()
                    result = {"agent": {"name": name, "pane_id": pane}}
                elif args[:2] == ["agent", "prompt"]:
                    result = {"accepted": True, "agent": args[2]}
                elif args[:2] == ["agent", "wait"]:
                    result = {"agent": {"name": args[2], "agent_status": "idle"}}
                elif args[:2] == ["agent", "focus"]:
                    result = {"focused": args[2]}
                else:
                    print(json.dumps({"error": {"message": "unsupported", "args": args}}))
                    raise SystemExit(2)
                print(json.dumps({"id": "fake", "result": result}))
                """
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def _project(self) -> Path:
        project = self.root / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        nested = project / "backend"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        for repository in (project, nested):
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.name", "Runtime Ops Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "config", "user.email", "runtime@example.invalid"],
                check=True,
            )
            marker = repository / "marker.txt"
            marker.write_text(f"{repository.name}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "marker.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "initial"],
                check=True,
            )
        orchestration = project / ".orchestration"
        orchestration.mkdir()
        (orchestration / "herdr-orchestrator.toml").write_text(
            textwrap.dedent(
                f"""\
                version = 3
                fallback_peer_recipe = "balanced"

                [roles.lead]
                kind = "codex"
                args = ["--model", "gpt-test", "--sandbox", "workspace-write", "--add-dir", "{(project / '.git').resolve()}", "--config", "sandbox_workspace_write.network_access=true"]

                [peer_recipes.balanced]
                description = "Human-approved balanced Peer profile"
                kind = "codex"
                args = ["--model", "gpt-test"]

                [peer_recipes.critical]
                description = "Human-approved critical review profile"
                kind = "codex"
                args = ["--model", "gpt-review"]
                """
            ),
            encoding="utf-8",
        )
        lines: list[str] = []
        for line in (SKILL_ROOT / "assets/workspace-protocol-template.md").read_text(
            encoding="utf-8"
        ).splitlines():
            if line.endswith("YYYY-MM-DD"):
                line = line.replace("YYYY-MM-DD", "2026-08-25")
            elif line.endswith("Live orchestration language:"):
                line += " Vietnamese"
            elif line.endswith("Durable Markdown artifact language:"):
                line += " English"
            elif line.endswith("Repository root:"):
                line += f" {project.resolve()}"
            elif line.lstrip().startswith("- ") and line.endswith(":"):
                line += " configured"
            lines.append(line)
        (orchestration / "workspace-protocol.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        return project

    def _init_run(self) -> Path:
        config = self.project / ".orchestration/herdr-orchestrator.toml"
        protocol = self.project / ".orchestration/workspace-protocol.md"
        task = self.root / "task.md"
        before = self.root / "before.txt"
        task.write_text("Implement the bounded task.\n", encoding="utf-8")
        before.write_text("## main\n", encoding="utf-8")
        common = Path(
            subprocess.run(
                ["git", "-C", str(self.project), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        completed = self._run(
            "init-run",
            "--git-common-dir",
            str(common),
            "--run-id",
            "runtime-ops-test",
            "--repository-root",
            str(self.project),
            "--human-task-file",
            str(task),
            "--before-state-file",
            str(before),
            "--project-config-file",
            str(config),
            "--workspace-protocol-file",
            str(protocol),
            "--expected-project-config-sha256",
            sha256(config),
            "--expected-workspace-protocol-sha256",
            sha256(protocol),
            "--layout-helper",
            str(LAYOUT),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return Path(json.loads(completed.stdout)["run_directory"])

    def _start_lead(self) -> dict[str, object]:
        completed = self._run(
            "start-lead",
            "--run-dir",
            str(self.run_dir),
            "--anchor-pane",
            "pane-launcher",
            "--herdr",
            str(self.herdr),
            "--no-focus",
            helper=self.run_dir / "tools/herdr_orchestrator.py",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_start_lead_builds_short_manifest_bound_context(self) -> None:
        result = self._start_lead()
        runtime = json.loads((self.run_dir / "runtime-manifest.json").read_text())
        context = (self.run_dir / "context/lead.md").read_text(encoding="utf-8")

        self.assertEqual(result["command"], "start-lead")
        self.assertEqual([item["id"] for item in runtime["repositories"]], ["root", "backend"])
        self.assertEqual(
            [item["name"] for item in runtime["peer_profiles"]],
            ["balanced", "critical"],
        )
        self.assertEqual(runtime["herdr_executable"], str(self.herdr.resolve()))
        launch_contract = runtime["operation_contracts"]["lead"]["launch_peer"]
        self.assertEqual(
            launch_contract,
            {
                "argv": [
                    *runtime["operations"]["lead"],
                    "launch-peer",
                    "--request",
                    "<absolute-request.json>",
                ],
                "allowed_dispositions": [
                    "Engineer",
                    "Architect",
                    "Scout",
                    "Proof Auditor",
                    "Feature Owner",
                ],
                "request_example": {
                    "schema_version": 1,
                    "task_id": "bounded-task",
                    "disposition": "Engineer",
                    "objective": "Own one bounded outcome",
                    "repository": "root",
                    "profile": "balanced",
                    "project_write": True,
                    "owned_scope": ["relative/path/**"],
                    "excluded_scope": [],
                    "verification": ["exact command or acceptance check"],
                    "dependencies": [],
                    "constraints": [],
                },
            },
        )
        self.assertNotEqual(launch_contract["argv"][0], runtime["herdr_executable"])
        self.assertIn("# Project Lead", context)
        self.assertIn("Implement the bounded task", context)
        self.assertIn('"operations"', context)
        self.assertNotIn("# Peer dispatch and report lifecycle", context)
        self.assertNotIn("[peer_recipes", context)
        self.assertNotIn("herdr agent start", context)

    def test_start_lead_rejects_codex_without_control_socket_access_before_mutation(self) -> None:
        config = self.run_dir / "context/project-config.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                ', "--config", "sandbox_workspace_write.network_access=true"',
                "",
                1,
            ),
            encoding="utf-8",
        )
        manifest_path = self.run_dir / "run-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["project_config"].update(
            bytes=len(config.read_bytes()),
            sha256=sha256(config),
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        completed = self._run(
            "start-lead",
            "--run-dir",
            str(self.run_dir),
            "--anchor-pane",
            "pane-launcher",
            "--herdr",
            str(self.herdr),
            "--no-focus",
            helper=self.run_dir / "tools/herdr_orchestrator.py",
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("cannot reach the Herdr control socket", completed.stderr)
        self.assertFalse((self.run_dir / "runtime-manifest.json").exists())
        self.assertFalse(self.state.exists())

    def test_peer_launch_handoff_and_collect_are_one_call_interfaces(self) -> None:
        self._start_lead()
        request = self.run_dir / "assignments/request.json"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "task_id": "backend-fix",
                    "disposition": "Engineer",
                    "objective": "Implement the bounded backend fix",
                    "repository": "backend",
                    "project_write": True,
                    "owned_scope": ["src/**", "tests/**"],
                    "excluded_scope": ["migrations/**"],
                    "verification": ["pytest"],
                }
            ),
            encoding="utf-8",
        )
        launched = self._run(
            "launch-peer",
            "--request",
            str(request),
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(launched.returncode, 0, launched.stderr)
        launch_result = json.loads(launched.stdout)
        agent = launch_result["peer"]["name"]
        self.assertEqual(launch_result["selection"]["profile"], "balanced")
        self.assertTrue(launch_result["selection"]["fallback"])
        self.assertEqual(launch_result["repository"]["id"], "backend")
        assignment = (self.run_dir / "assignments" / f"{agent}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('"changed": ["src/**", "tests/**"]', assignment)

        peer_context = (self.run_dir / "context" / f"{agent}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("# Peer", peer_context)
        self.assertIn("Implement the bounded backend fix", peer_context)
        self.assertIn("herdr_peer_ops.py handoff", peer_context)
        self.assertNotIn("atomic rename", peer_context)
        self.assertNotIn("mailbox layout", peer_context)

        followup_message = self.run_dir / "assignments/followup.md"
        followup_message.write_text("Return exact verification evidence.\n", encoding="utf-8")
        first_followup = self._run(
            "followup",
            "--agent",
            agent,
            "--message",
            str(followup_message),
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(first_followup.returncode, 0, first_followup.stderr)
        second_followup = self._run(
            "followup",
            "--agent",
            agent,
            "--message",
            str(followup_message),
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(second_followup.returncode, 2)
        self.assertIn("already been used", second_followup.stderr)

        inbox = self.run_dir / "reports/inbox" / agent
        result_path = inbox / "result.json"
        backend_commit = subprocess.run(
            ["git", "-C", str(self.project / "backend"), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result_path.write_text(
            json.dumps(
                {
                    "status": "DONE",
                    "candidate": {"kind": "git", "commit": backend_commit},
                    "changed": ["src/fix.py"],
                    "verification": [
                        {
                            "command": "pytest",
                            "cwd": str(self.project / "backend"),
                            "exit_code": 0,
                            "summary": "passed",
                        }
                    ],
                    "findings": [],
                    "risks": ["none known"],
                    "unfinished_dependencies": [],
                    "decision_needed": "accept or review",
                }
            ),
            encoding="utf-8",
        )
        handed_off = self._run(
            "handoff",
            "--agent",
            agent,
            "--result",
            str(result_path),
            helper=self.run_dir / "tools/herdr_peer_ops.py",
        )
        self.assertEqual(handed_off.returncode, 0, handed_off.stderr)

        collected = self._run(
            "collect",
            "--agent",
            agent,
            "--no-wait",
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(collected.returncode, 0, collected.stderr)
        collection = json.loads(collected.stdout)
        self.assertEqual(collection["outcome"], "DONE")
        self.assertEqual(
            collection["result"]["candidate"],
            {"kind": "git", "commit": backend_commit},
        )
        self.assertTrue(Path(collection["report"]["path"]).is_file())
        events = [json.loads(line) for line in (self.run_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual([event["type"] for event in events], ["launch", "assignment", "report"])

    def test_reviewer_requires_exact_candidate_and_can_select_profile(self) -> None:
        self._start_lead()
        request = self.run_dir / "assignments/reviewer.json"
        request.write_text(
            json.dumps(
                {
                    "disposition": "Reviewer",
                    "objective": "Falsify the candidate",
                    "repository": "root",
                    "profile": "critical",
                    "project_write": False,
                }
            ),
            encoding="utf-8",
        )
        missing = self._run(
            "launch-reviewer",
            "--request",
            str(request),
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("requires exact_candidate", missing.stderr)

        root_commit = subprocess.run(
            ["git", "-C", str(self.project), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        request.write_text(
            request.read_text().replace(
                '"project_write": false',
                f'"project_write": false, "exact_candidate": "commit {root_commit}"',
            ),
            encoding="utf-8",
        )
        launched = self._run(
            "launch-reviewer",
            "--request",
            str(request),
            helper=self.run_dir / "tools/herdr_lead_ops.py",
        )
        self.assertEqual(launched.returncode, 0, launched.stderr)
        result = json.loads(launched.stdout)
        self.assertEqual(result["selection"]["profile"], "critical")
        self.assertFalse(result["selection"]["fallback"])
        agent = result["peer"]["name"]
        assignment = (self.run_dir / "assignments" / f"{agent}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(f'"candidate": {{"kind": "git", "commit": "{root_commit}"}}', assignment)
        self.assertIn('"status": "APPROVE"', assignment)
        self.assertIn('"status": "DIRECT"', assignment)
        self.assertIn("Nested `review.status`", assignment)
        result_path = self.run_dir / "reports/inbox" / agent / "result.json"
        result_path.write_text(
            json.dumps(
                {
                    "status": "APPROVE",
                    "candidate": {"kind": "git", "commit": root_commit},
                    "changed": [],
                    "verification": [],
                    "findings": [],
                    "risks": ["none found"],
                    "unfinished_dependencies": [],
                    "decision_needed": "Lead verdict",
                    "review": {
                        "procedure": "direct",
                        "status": "DIRECT",
                        "coverage_complete": True,
                        "artifacts": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        handoff = self._run(
            "handoff",
            "--agent",
            agent,
            "--result",
            str(result_path),
            helper=self.run_dir / "tools/herdr_peer_ops.py",
        )
        self.assertEqual(handoff.returncode, 0, handoff.stderr)
        report = Path(json.loads(handoff.stdout)["report"]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("Review procedure: direct", report)
        self.assertIn("OCR status: DIRECT", report)

    def test_supervisor_operations_record_without_exposing_it_to_lead(self) -> None:
        attachment = self.run_dir / "supervisor/attachments/observe1"
        attachment.mkdir(parents=True)
        binding = attachment / "runtime-binding.json"
        binding.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "attachment_id": "observe1",
                    "supervisor": "supervisor-test",
                    "projects": [
                        {
                            "project_id": "project",
                            "run_id": self.run_dir.name,
                            "evidence_root": str(self.run_dir),
                        }
                    ],
                    "notebook_root": str(attachment),
                    "artifact_language": "English",
                    "operations": [
                        sys.executable,
                        str(self.run_dir / "tools/herdr_supervisor_ops.py"),
                    ],
                }
            ),
            encoding="utf-8",
        )
        payload = attachment / "observation.json"
        payload.write_text(
            json.dumps(
                {
                    "observation": "Repeated retry without a changed prerequisite",
                    "evidence": "three identical failure receipts",
                    "suspected_mechanism": "unchanged runtime dependency",
                    "impact": "token and time waste",
                    "question": "Which prerequisite can change?",
                    "recommendation": "stop retrying and inspect the dependency",
                    "escalation": "Human attention requested",
                    "protocol_candidate": "require changed prerequisite before retry",
                }
            ),
            encoding="utf-8",
        )

        completed = self._run(
            "request-human-attention",
            "--binding",
            str(binding),
            "--payload",
            str(payload),
            helper=self.run_dir / "tools/herdr_supervisor_ops.py",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["human_attention"])
        self.assertFalse(result["lead_notified"])
        observation = Path(result["observation"]["path"])
        self.assertTrue(observation.is_file())
        self.assertTrue(observation.is_relative_to(attachment))
        self.assertIn("Repeated retry", observation.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
