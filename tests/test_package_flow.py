from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
RUNTIME = SKILL_ROOT / "scripts/herdr_runtime.py"


class RealPackageFlowTests(unittest.TestCase):
    def test_installable_bundle_exposes_one_runtime_interface(self) -> None:
        scripts = {path.name for path in (SKILL_ROOT / "scripts").iterdir()}
        self.assertIn("herdr_runtime.py", scripts)
        for obsolete in (
            "herdr_runtime_ops.py",
            "herdr_lead_ops.py",
            "herdr_peer_ops.py",
            "herdr_supervisor_ops.py",
        ):
            self.assertNotIn(obsolete, scripts)

        completed = subprocess.run(
            [sys.executable, str(RUNTIME), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for operation in ("start", "result", "prompt"):
            self.assertIn(operation, completed.stdout)

    def test_role_profiles_delegate_only_runtime_mechanics(self) -> None:
        lead = (SKILL_ROOT / "references/roles/lead.md").read_text(encoding="utf-8")
        peer = (SKILL_ROOT / "references/roles/peer.md").read_text(encoding="utf-8")
        self.assertIn("start the Peer", lead)
        self.assertIn("use `result`", lead)
        self.assertIn("normal agent response", peer)
        for manual in ("herdr agent start", "herdr pane split", "reports/inbox"):
            self.assertNotIn(manual, lead + peer)


if __name__ == "__main__":
    unittest.main()
