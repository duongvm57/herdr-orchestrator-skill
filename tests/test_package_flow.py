from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.accepted_fixture import publish_accepted_setup


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
HELPER = SKILL_ROOT / "scripts/herdr_orchestrator.py"
LAYOUT = SKILL_ROOT / "scripts/herdr_balanced_split.py"


class RealPackageFlowTests(unittest.TestCase):
    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_real_sources_keep_conditional_bodies_out_of_initial_lead(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            common = root / "common"
            project = root / "project"
            project.mkdir()
            accepted = publish_accepted_setup(project)
            common = accepted["common"]
            task = root / "task.md"
            before = root / "before.txt"
            config = accepted["config"]
            protocol = accepted["protocol"]
            binding = root / "binding.md"
            constraints = root / "constraints.md"
            peer_assignment = root / "peer-assignment.md"
            for path, body in (
                (task, "Implement a tiny bounded task.\n"),
                (before, "## main\n"),
                (binding, "# Run binding\n\nRun: integration-test\n"),
                (constraints, "# Relevant constraints\n\nRead-only review.\n"),
                (peer_assignment, "# Assignment\n\nReturn the required report.\n"),
            ):
                path.write_text(body, encoding="utf-8")
            validated = self.run_helper(
                "validate-project",
                "--project-root",
                str(project),
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            preflight = json.loads(validated.stdout)

            init_args = [
                "init-run",
                "--git-common-dir",
                str(common),
                "--repository-root",
                str(project),
                "--run-id",
                "integration-test",
                "--project-root",
                str(project),
                "--human-task-file",
                str(task),
                "--before-state-file",
                str(before),
                "--expected-activation-sha256",
                preflight["activation"]["sha256"],
                "--layout-helper",
                str(LAYOUT),
            ]
            assets = {
                "topology": SKILL_ROOT / "references/lead/topology.md",
                "peer-lifecycle": SKILL_ROOT / "references/lead/peer-lifecycle.md",
                "candidate-and-verdict": SKILL_ROOT / "references/lead/candidate-and-verdict.md",
                "anti-pattern-details": SKILL_ROOT / "references/anti-patterns/responses.md",
                "peer-profile": SKILL_ROOT / "references/roles/peer.md",
            }
            for name, path in assets.items():
                init_args.extend(("--asset", f"{name}={path}"))

            initialized = self.run_helper(*init_args)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertNotIn("Project Lead core role", initialized.stdout)
            run_dir = Path(json.loads(initialized.stdout)["run_directory"])
            manifest = run_dir / "context/cards/manifest.json"
            self.assertEqual(
                (run_dir / "context/project-config.toml").read_bytes(),
                config.read_bytes(),
            )
            self.assertEqual(
                (run_dir / "context/workspace-protocol.md").read_bytes(),
                protocol.read_bytes(),
            )

            lead_pack = run_dir / "context/lead.md"
            packed = self.run_helper(
                "pack",
                "--role",
                "lead",
                "--output",
                str(lead_pack),
                "--role-source",
                str(SKILL_ROOT / "references/roles/lead.md"),
                "--role-source",
                str(SKILL_ROOT / "references/anti-patterns/index.md"),
                "--role-source",
                str(manifest),
                "--protocol-source",
                str(run_dir / "context/project-config.toml"),
                "--protocol-source",
                str(run_dir / "context/workspace-protocol.md"),
                "--assignment-source",
                str(run_dir / "human-task.md"),
                "--assignment-source",
                str(binding),
            )
            self.assertEqual(packed.returncode, 0, packed.stderr)
            lead_text = lead_pack.read_text(encoding="utf-8")
            self.assertIn("# Project Lead core role", lead_text)
            self.assertIn("# Workspace Protocol", lead_text)
            self.assertIn('"name":"peer-profile"', lead_text)
            self.assertNotIn("# Peer role profile", lead_text)
            self.assertNotIn("# Peer dispatch and report lifecycle", lead_text)
            self.assertNotIn("# Anti-pattern response card", lead_text)
            self.assertNotIn("## Difficult council", lead_text)
            self.assertNotIn("Project Lead core role", packed.stdout)

            peer_pack = run_dir / "context/peer.md"
            peer = self.run_helper(
                "pack",
                "--role",
                "peer",
                "--output",
                str(peer_pack),
                "--role-source",
                str(run_dir / "context/cards/assets/peer-profile"),
                "--protocol-source",
                str(constraints),
                "--assignment-source",
                str(peer_assignment),
            )
            self.assertEqual(peer.returncode, 0, peer.stderr)
            peer_text = peer_pack.read_text(encoding="utf-8")
            self.assertIn("# Peer role profile", peer_text)
            self.assertNotIn("Project Lead core role", peer_text)
            self.assertNotIn("## 1. Status and scope", peer_text)
            self.assertNotIn("Configured recipe capabilities", peer_text)
            self.assertNotIn("context/cards/manifest.json", peer_text)


if __name__ == "__main__":
    unittest.main()
