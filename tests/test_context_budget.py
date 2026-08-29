from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("context_budget", ROOT / "scripts/context_budget.py")
assert SPEC and SPEC.loader
context_budget = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_budget
SPEC.loader.exec_module(context_budget)


class FakeEncoder:
    def encode(self, text: str) -> list[str]:
        return text.split()


class ContextBudgetTests(unittest.TestCase):
    def test_measures_canonical_static_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.md").write_text("one two", encoding="utf-8")
            manifest = {"routes": {"sample": {"files": ["one.md"], "hard_limit": 4, "baseline": 3}}}
            [result] = context_budget.measure_routes(root, manifest, FakeEncoder())
            self.assertEqual(result.tokens, 2)
            self.assertEqual(result.files, ("one.md",))

    def test_manifest_rejects_retired_pack_transport_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budgets.json"
            path.write_text(json.dumps({"encoding": "fake", "routes": {"bad": {"render": "pack", "files": ["x"], "hard_limit": 1, "baseline": 1}}}), encoding="utf-8")
            with self.assertRaisesRegex(context_budget.BudgetError, "unsupported or missing"):
                context_budget.load_manifest(path)

    def test_missing_source_fails_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(context_budget.BudgetError, "source is missing"):
                context_budget.render_route(Path(temporary), "sample", {"files": ["missing.md"]})

    def test_update_baselines_writes_current_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budgets.json"
            manifest = {"routes": {"sample": {"files": ["one.md"], "hard_limit": 10, "baseline": 2}}}
            context_budget.update_baselines(path, manifest, [context_budget.RouteResult("sample", ("one.md",), 1, 1, 4, 10, 2)])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["routes"]["sample"]["baseline"], 4)


if __name__ == "__main__":
    unittest.main()
