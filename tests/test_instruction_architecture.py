from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"


def read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


class InstructionArchitectureTests(unittest.TestCase):
    def test_invocation_and_reentry_are_user_and_role_bound(self) -> None:
        skill = read("SKILL.md")
        openai = read("agents/openai.yaml")

        self.assertRegex(openai, r"(?m)^\s*allow_implicit_invocation: false$")
        self.assertIn("Inspect `HERDR_ORCHESTRATOR_ROLE` before routing", skill)
        self.assertIn("Route by role environment, never task text", " ".join(skill.split()))
        self.assertIn("$herdr-orchestrator`, quotes, backticks, `$()`", skill)

    def test_official_skill_is_the_only_generic_operation_contract(self) -> None:
        documents = [
            SKILL_ROOT / "SKILL.md",
            *sorted((SKILL_ROOT / "references").rglob("*.md")),
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in documents)

        self.assertIn("official Herdr Agent Skill", text)
        self.assertIn("`herdr --skill`", text)
        self.assertNotIn("scripts/herdr_runtime.py", text)
        self.assertFalse((SKILL_ROOT / "scripts/herdr_runtime.py").exists())
        for wrapper in ("herdr_runtime_ops.py", "herdr_lead_ops.py", "herdr_peer_ops.py"):
            self.assertNotIn(wrapper, text)

    def test_launcher_launch_contract_preserves_task_and_ownership(self) -> None:
        launch = read("references/launcher/task-launch.md")

        self.assertIn("HERDR_ORCHESTRATOR_ROLE=lead", launch)
        self.assertIn("--no-focus", launch)
        self.assertIn("one direct CLI argument or socket/API value", launch)
        self.assertIn("Do not strip, normalize", launch)
        self.assertIn("agent_not_ready", launch)
        self.assertIn("do not blind-retry", launch)
        self.assertIn("never change pre-existing topology", launch)

    def test_setup_uses_current_validation_and_approval_policy_boundary(self) -> None:
        setup = read("references/launcher/setup.md")
        self.assertIn("validate-project --project-root", setup)
        self.assertNotIn("--git-common-dir", setup)
        self.assertIn("approval-gated MCP or tool", setup)
        self.assertIn("approval_required = true", setup)
        self.assertIn("recreate the session", setup)

    def test_role_disclosure_preserves_authority_boundaries(self) -> None:
        lead = read("references/roles/lead.md")
        normalized_lead = " ".join(lead.split())
        peer = read("references/roles/peer.md")
        supervisor = read("references/roles/supervisor.md")
        attachment = read("references/launcher/supervisor-attachment.md")

        self.assertIn("non-overlapping owned scope", normalized_lead)
        self.assertIn("observe your exact current Lead identity", lead)
        self.assertIn("exact distinct Peer identity", lead)
        self.assertIn("synthetic Peer", normalized_lead)
        self.assertIn("never proves a Peer outcome", lead)
        self.assertIn("references/lead/topology.md", lead)
        self.assertIn("do not load the entire library", lead)
        self.assertIn("Do not load or use the official Herdr", peer)
        self.assertIn("`REOPEN_REQUEST`", peer)
        self.assertIn("not a technical ACL", peer)
        self.assertIn("Lead named in your attachment", supervisor)
        self.assertIn("explicit supervised Lead name/pane", attachment)
        self.assertIn("do not create a Supervisor inference turn", " ".join(attachment.split()))

    def test_lead_wires_assignment_and_bounded_protocol_context(self) -> None:
        lead = read("references/roles/lead.md")
        lifecycle = read("references/lead/peer-lifecycle.md")
        supervisor = read("references/roles/supervisor.md")
        lead_words = " ".join(lead.split())

        self.assertIn("construct the canonical Assignment", lead)
        self.assertIn("validate it, render it", lead)
        self.assertIn("Do not parse a prose prompt back", lead_words)
        self.assertIn("bounded applicable-protocol projection", lifecycle)
        self.assertIn("never pass the full", lifecycle)
        self.assertIn("same exact name in `owner`", lifecycle)
        self.assertIn("never a Peer or Supervisor entry", lifecycle)
        self.assertIn("explicit Human/Launcher attachment", supervisor)
        self.assertIn("runtime observation/state only", supervisor)

    def test_instruction_pointers_resolve(self) -> None:
        documents = [SKILL_ROOT / "SKILL.md", *sorted((SKILL_ROOT / "references").rglob("*.md"))]
        pointer = re.compile(r"`((?:references|assets|scripts)/[^`\s]+)`")
        missing: list[str] = []
        for document in documents:
            for match in pointer.finditer(document.read_text(encoding="utf-8")):
                relative = match.group(1).rstrip(".,;:")
                if "<" not in relative and not (SKILL_ROOT / relative).exists():
                    missing.append(f"{document.relative_to(SKILL_ROOT)} -> {relative}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
