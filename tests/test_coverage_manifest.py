from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests/orchestration-scenarios.json"
OUTPUT_PATH = ROOT / "maintenance/orchestration-invariant-coverage.md"
RENDERER_PATH = ROOT / "scripts/render_coverage.py"

SPEC = importlib.util.spec_from_file_location("render_coverage", RENDERER_PATH)
assert SPEC and SPEC.loader
render_coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_coverage
SPEC.loader.exec_module(render_coverage)


class CoverageManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_schema_is_strict_and_modes_are_explicit(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source_root"], "skills/herdr-orchestrator")
        self.assertEqual(
            {group["verification"] for group in manifest["groups"]},
            {"automated/static", "live/manual"},
        )
        for group in manifest["groups"]:
            if group["verification"] == "automated/static":
                self.assertTrue(group["test_selectors"], group["slug"])
            else:
                self.assertEqual(group["test_selectors"], [], group["slug"])

        invalid = copy.deepcopy(self.raw)
        invalid["groups"][0]["unexpected"] = True
        with self.assertRaisesRegex(render_coverage.ManifestError, "invalid fields"):
            render_coverage.validate_manifest(invalid, ROOT)

        escaping = copy.deepcopy(self.raw)
        escaping["source_root"] = "../outside"
        with self.assertRaisesRegex(render_coverage.ManifestError, "normalized"):
            render_coverage.validate_manifest(escaping, ROOT)

    def test_source_paths_and_automated_selectors_resolve(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        source_root = ROOT / manifest["source_root"]

        for group in manifest["groups"]:
            for relative in group["sources"]:
                self.assertTrue(
                    (source_root / relative).is_file(),
                    f"{group['slug']}: {relative}",
                )
            for selector in group["test_selectors"]:
                render_coverage.validate_test_selector(ROOT, selector)

        missing_source = copy.deepcopy(self.raw)
        missing_source["groups"][0]["sources"][0] = "references/missing.md"
        with self.assertRaisesRegex(render_coverage.ManifestError, "does not resolve"):
            render_coverage.validate_manifest(missing_source, ROOT)

        missing_selector = copy.deepcopy(self.raw)
        missing_selector["groups"][0]["test_selectors"][0] += "_missing"
        with self.assertRaisesRegex(render_coverage.ManifestError, "does not exist"):
            render_coverage.validate_manifest(missing_selector, ROOT)

    def test_every_legacy_id_is_covered_exactly_once(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        expected = set(render_coverage.expected_legacy_ids(manifest))
        ids = [
            invariant["id"]
            for group in manifest["groups"]
            for invariant in group["invariants"]
        ]

        self.assertEqual(set(ids), expected)
        self.assertTrue(all(count == 1 for count in Counter(ids).values()))

        rendered = render_coverage.render_document(manifest)
        rendered_ids = re.findall(r"FT-\d{2}", rendered)
        self.assertEqual(set(rendered_ids), expected)
        self.assertTrue(all(count == 1 for count in Counter(rendered_ids).values()))

        duplicate = copy.deepcopy(self.raw)
        duplicate["groups"][0]["invariants"].append(
            copy.deepcopy(duplicate["groups"][2]["invariants"][0])
        )
        duplicate["groups"][0]["invariants"].sort(key=lambda item: item["id"])
        with self.assertRaisesRegex(render_coverage.ManifestError, "more than once"):
            render_coverage.validate_manifest(duplicate, ROOT)

        incomplete = copy.deepcopy(self.raw)
        incomplete["groups"][3]["invariants"].pop()
        with self.assertRaisesRegex(render_coverage.ManifestError, "incomplete"):
            render_coverage.validate_manifest(incomplete, ROOT)

    def test_invariant_specs_are_bound_and_ordered(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        specs = {
            invariant["id"]: invariant["spec"]
            for group in manifest["groups"]
            for invariant in group["invariants"]
        }

        self.assertEqual(len(specs), 69)
        self.assertIn("Role Profile", specs["FT-08"])
        self.assertIn("live and artifact languages", specs["FT-69"])

        permuted = copy.deepcopy(self.raw)
        first = permuted["groups"][0]["invariants"]
        first[0], first[1] = first[1], first[0]
        with self.assertRaisesRegex(render_coverage.ManifestError, "numerically ordered"):
            render_coverage.validate_manifest(permuted, ROOT)

        blank = copy.deepcopy(self.raw)
        blank["groups"][0]["invariants"][0]["spec"] = "  "
        with self.assertRaisesRegex(render_coverage.ManifestError, "nonempty string"):
            render_coverage.validate_manifest(blank, ROOT)

    def test_ft40_attention_claim_is_live_and_static_flow_is_executable(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        by_slug = {group["slug"]: group for group in manifest["groups"]}

        opaque = by_slug["live-launcher-opaque-attention"]
        self.assertEqual(opaque["verification"], "live/manual")
        self.assertEqual([item["id"] for item in opaque["invariants"]], ["FT-40"])
        self.assertEqual(opaque["test_selectors"], [])

        static = by_slug["static-context-architecture"]
        self.assertIn(
            "tests.test_runtime.RuntimeTests."
            "test_lead_start_uses_native_herdr_flow_without_focus_or_files",
            static["test_selectors"],
        )

    def test_generated_document_is_deterministic_and_current(self) -> None:
        manifest = render_coverage.validate_manifest(copy.deepcopy(self.raw), ROOT)
        first = render_coverage.render_document(manifest)
        second = render_coverage.render_document(copy.deepcopy(manifest))

        self.assertEqual(first, second)
        self.assertEqual(OUTPUT_PATH.read_text(encoding="utf-8"), first)

        completed = subprocess.run(
            [sys.executable, str(RENDERER_PATH), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("current", completed.stdout)

        with tempfile.TemporaryDirectory() as temporary:
            stale = Path(temporary) / "coverage.md"
            stale.write_text("stale\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RENDERER_PATH),
                    "--output",
                    str(stale),
                    "--check",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("stale", completed.stderr)
            self.assertEqual(stale.read_text(encoding="utf-8"), "stale\n")


if __name__ == "__main__":
    unittest.main()
