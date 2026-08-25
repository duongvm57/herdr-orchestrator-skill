from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"


class RealPackageFlowTests(unittest.TestCase):
    def test_installable_bundle_exposes_runtime_operations(self) -> None:
        expected = {
            "herdr_orchestrator.py",
            "herdr_runtime_ops.py",
            "herdr_lead_ops.py",
            "herdr_peer_ops.py",
            "herdr_supervisor_ops.py",
            "herdr_balanced_split.py",
        }
        scripts = SKILL_ROOT / "scripts"
        self.assertTrue(expected.issubset({path.name for path in scripts.iterdir()}))

        completed = subprocess.run(
            [sys.executable, str(HELPER), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for operation in (
            "start-lead",
            "lead-launch-peer",
            "lead-launch-reviewer",
            "lead-wait",
            "lead-collect",
            "lead-followup",
            "peer-handoff",
            "peer-reopen",
            "peer-dependency",
            "peer-blocked",
            "supervisor-record",
            "supervisor-human-attention",
            "supervisor-recommend-handoff",
        ):
            self.assertIn(operation, completed.stdout)

    def test_role_profiles_delegate_mechanics_to_run_local_operations(self) -> None:
        lead = (SKILL_ROOT / "references/roles/lead.md").read_text(encoding="utf-8")
        peer = (SKILL_ROOT / "references/roles/peer.md").read_text(encoding="utf-8")
        normalized_lead = " ".join(lead.split())
        normalized_peer = " ".join(peer.split())

        self.assertIn("copy the exact `request_example`", normalized_lead)
        self.assertIn("do not prepend or substitute another executable", normalized_lead)
        self.assertIn("The helper owns routing", normalized_lead)
        self.assertIn("exact Peer operations command", peer)
        self.assertIn("creates the durable report atomically", normalized_peer)
        for manual in (
            "herdr agent start",
            "herdr pane split",
            "context/cards/manifest.json",
            "reports/inbox/<agent-name>",
        ):
            self.assertNotIn(manual, lead + peer)


if __name__ == "__main__":
    unittest.main()
