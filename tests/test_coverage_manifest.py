from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/orchestration-scenarios.json"
OUTPUT = ROOT / "maintenance/orchestration-invariant-coverage.md"
RENDERER = ROOT / "scripts/render_coverage.py"
SPEC = importlib.util.spec_from_file_location("render_coverage", RENDERER)
assert SPEC and SPEC.loader
render_coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_coverage
SPEC.loader.exec_module(render_coverage)


class CoverageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_target_manifest_is_strict_and_separates_live_evidence(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual({group["verification"] for group in manifest["groups"]}, {"automated/static", "live/dogfood", "live/eval"})
        for group in manifest["groups"]:
            self.assertEqual(bool(group["test_selectors"]), group["verification"] == "automated/static")
        invalid = copy.deepcopy(self.raw)
        invalid["groups"][0]["unexpected"] = True
        with self.assertRaisesRegex(render_coverage.ManifestError, "invalid fields"):
            render_coverage.validate_manifest(invalid, ROOT)

    def test_sources_selectors_and_invariant_ids_are_valid(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        ids = [item["id"] for group in manifest["groups"] for item in group["invariants"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("native-launch", ids)
        self.assertIn("candidate-and-handback", ids)
        invalid = copy.deepcopy(self.raw)
        invalid["groups"][1]["invariants"][0]["id"] = invalid["groups"][0]["invariants"][0]["id"]
        with self.assertRaisesRegex(render_coverage.ManifestError, "unique"):
            render_coverage.validate_manifest(invalid, ROOT)

    def test_generated_document_is_current(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        rendered = render_coverage.render_document(manifest)
        self.assertEqual(OUTPUT.read_text(encoding="utf-8"), rendered)
        completed = subprocess.run([sys.executable, str(RENDERER), "--check"], cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            stale = Path(temporary) / "coverage.md"
            stale.write_text("stale\n", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(RENDERER), "--output", str(stale), "--check"], cwd=ROOT, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
