from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"


class PackageFlowTests(unittest.TestCase):
    def test_installable_bundle_has_no_generic_runtime_wrapper(self) -> None:
        scripts = {path.name for path in (SKILL_ROOT / "scripts").iterdir()}
        self.assertIn("herdr_orchestrator.py", scripts)
        self.assertNotIn("herdr_runtime.py", scripts)
        self.assertNotIn("herdr_runtime_ops.py", scripts)
        self.assertNotIn("herdr_balanced_split.py", scripts)

    def test_helper_owns_only_bounded_direct_herdr_calls(self) -> None:
        helper = (SKILL_ROOT / "scripts/herdr_orchestrator.py").read_text(encoding="utf-8")
        self.assertNotIn('"pane", "split"', helper)
        self.assertIn('"agent", "prompt"', helper)
        self.assertIn("only Herdr\ncalls are recipe-bound Peer start and one-shot prompt submission", helper)
        self.assertIn("no pane, session, wait, or lifecycle control", helper)

if __name__ == "__main__":
    unittest.main()
