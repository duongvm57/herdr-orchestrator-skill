from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "context_budget", ROOT / "scripts" / "context_budget.py"
)
assert SPEC and SPEC.loader
context_budget = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_budget
SPEC.loader.exec_module(context_budget)


class FakeEncoder:
    def encode(self, text: str) -> list[str]:
        return text.split()


class ContextBudgetTests(unittest.TestCase):
    def test_measures_declared_concat_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.md").write_text("one two", encoding="utf-8")
            (root / "two.md").write_text("three", encoding="utf-8")
            manifest = {
                "encoding": "fake",
                "routes": {
                    "sample": {
                        "render": "concat",
                        "files": ["one.md", "two.md"],
                        "hard_limit": 4,
                        "baseline": 3,
                    }
                },
            }

            [result] = context_budget.measure_routes(root, manifest, FakeEncoder())

            self.assertEqual(result.tokens, 3)
            self.assertEqual(result.words, 3)
            self.assertEqual(result.files, ("one.md", "two.md"))
            self.assertEqual(result.failures(), [])

    def test_pack_route_counts_exact_framing_and_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "role.md").write_text("ROLE BODY", encoding="utf-8")
            (root / "fixture.json").write_text('{"fixture":"CARD DIGEST"}\n', encoding="utf-8")
            route = {
                "render": "pack",
                "role": "lead",
                "layers": {
                    "role_profile": [
                        {"label": "role.md", "file": "role.md"},
                        {"label": "manifest.json", "file": "fixture.json"},
                    ],
                    "workspace_protocol": [],
                    "assignment": [],
                },
                "hard_limit": 100,
                "baseline": 49,
            }
            expected = (
                "# Herdr Context Pack\n\nRole: lead\n\n"
                "<!-- BEGIN HERDR LAYER: ROLE PROFILE -->\n\n## Role Profile\n\n"
                "### Source 1: role.md\n\nROLE BODY\n\n"
                "### Source 2: manifest.json\n\n{\"fixture\":\"CARD DIGEST\"}\n\n"
                "<!-- END HERDR LAYER: ROLE PROFILE -->\n\n\n"
                "<!-- BEGIN HERDR LAYER: WORKSPACE PROTOCOL -->\n\n## Workspace Protocol\n\n"
                "<!-- END HERDR LAYER: WORKSPACE PROTOCOL -->\n\n\n"
                "<!-- BEGIN HERDR LAYER: ASSIGNMENT -->\n\n## Assignment\n\n"
                "<!-- END HERDR LAYER: ASSIGNMENT -->\n"
            )

            rendered, files = context_budget.render_route(root, "packed", route)
            [result] = context_budget.measure_routes(
                root,
                {"routes": {"packed": route}},
                FakeEncoder(),
            )

            self.assertEqual(rendered, expected)
            self.assertEqual(files, ("role.md", "fixture.json"))
            self.assertEqual(result.tokens, len(expected.split()))
            self.assertGreater(result.tokens, len("ROLE BODY CARD DIGEST".split()))
            self.assertIn("CARD DIGEST", rendered)

    def test_pack_fixture_growth_triggers_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "role.md").write_text("role\n", encoding="utf-8")
            fixture = root / "manifest.json"
            fixture.write_text('{"assets":[]}\n', encoding="utf-8")
            route = {
                "render": "pack",
                "role": "supervisor",
                "layers": {
                    "role_profile": [
                        {"label": "role.md", "file": "role.md"},
                        {"label": "manifest.json", "file": "manifest.json"},
                    ],
                    "workspace_protocol": [],
                    "assignment": [],
                },
                "hard_limit": 1000,
                "baseline": 1,
            }
            manifest = {"routes": {"packed": route}}
            [initial] = context_budget.measure_routes(root, manifest, FakeEncoder())
            route["baseline"] = initial.tokens
            fixture.write_text(
                '{"assets":["one two three four five six seven eight nine ten"]}\n',
                encoding="utf-8",
            )

            [grown] = context_budget.measure_routes(root, manifest, FakeEncoder())

            self.assertGreater(grown.tokens, grown.drift_limit)
            self.assertTrue(any("drift limit" in failure for failure in grown.failures()))

    def test_pack_renderer_matches_runtime_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = {
                "role_profile": ("role.md", "role body"),
                "workspace_protocol": ("protocol.md", "protocol body\n"),
                "assignment": ("assignment.md", "assignment body"),
            }
            layers: dict[str, list[dict[str, str]]] = {}
            for layer, (filename, body) in sources.items():
                (root / filename).write_text(body, encoding="utf-8")
                layers[layer] = [{"label": filename, "file": filename}]
            route = {
                "render": "pack",
                "role": "supervisor",
                "layers": layers,
                "hard_limit": 1000,
                "baseline": 100,
            }
            rendered, _ = context_budget.render_route(root, "packed", route)
            output = root / "actual.md"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "herdr_orchestrator.py"),
                    "pack",
                    "--role",
                    "supervisor",
                    "--output",
                    str(output),
                    "--role-source",
                    f"role.md={root / 'role.md'}",
                    "--protocol-source",
                    f"protocol.md={root / 'protocol.md'}",
                    "--assignment-source",
                    f"assignment.md={root / 'assignment.md'}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(rendered, output.read_text(encoding="utf-8"))

    def test_repository_supervisor_fixture_has_only_signal_card(self) -> None:
        manifest = context_budget.load_manifest(ROOT / "assets" / "context-budgets.json")
        route = manifest["routes"]["supervisor_initial_fixed"]
        fixture_path = next(
            source["file"]
            for source in route["layers"]["role_profile"]
            if source["label"] == "manifest.json"
        )
        fixture = json.loads((ROOT / fixture_path).read_text(encoding="utf-8"))

        self.assertEqual(
            [asset["name"] for asset in fixture["assets"]],
            ["anti-pattern-details"],
        )

    def test_repository_card_fixtures_match_packaged_assets(self) -> None:
        packaged = {
            "topology": ROOT / "references/topology.md",
            "peer-lifecycle": ROOT / "references/lead/peer-lifecycle.md",
            "candidate-and-verdict": ROOT / "references/lead/candidate-and-verdict.md",
            "anti-pattern-details": ROOT / "references/anti-patterns.md",
            "peer-profile": ROOT / "references/roles/peer.md",
        }
        for fixture_name in (
            "lead-card-manifest.json",
            "supervisor-card-manifest.json",
        ):
            fixture = json.loads(
                (ROOT / "tests/fixtures" / fixture_name).read_text(encoding="utf-8")
            )
            for entry in fixture["assets"]:
                data = packaged[entry["name"]].read_bytes()
                self.assertEqual(entry["bytes"], len(data), entry["name"])
                self.assertEqual(
                    entry["sha256"],
                    hashlib.sha256(data).hexdigest(),
                    entry["name"],
                )

    def test_reports_hard_and_drift_failures(self) -> None:
        result = context_budget.RouteResult(
            name="sample",
            files=("one.md",),
            bytes=20,
            words=5,
            tokens=12,
            hard_limit=10,
            baseline=10,
        )

        failures = result.failures()

        self.assertEqual(len(failures), 2)
        self.assertIn("hard limit", failures[0])
        self.assertIn("drift limit", failures[1])

    def test_manifest_rejects_missing_source_at_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "budgets.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "encoding": "fake",
                        "routes": {
                            "sample": {
                                "render": "concat",
                                "files": ["missing.md"],
                                "hard_limit": 1,
                                "baseline": 1,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            manifest = context_budget.load_manifest(manifest_path)

            with self.assertRaisesRegex(context_budget.BudgetError, "source is missing"):
                context_budget.measure_routes(root, manifest, FakeEncoder())

    def test_update_baselines_writes_current_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "budgets.json"
            manifest = {
                "encoding": "fake",
                "routes": {
                    "sample": {
                        "render": "concat",
                        "files": ["one.md"],
                        "hard_limit": 10,
                        "baseline": 2,
                    }
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = context_budget.RouteResult(
                name="sample",
                files=("one.md",),
                bytes=20,
                words=4,
                tokens=4,
                hard_limit=10,
                baseline=2,
            )

            context_budget.update_baselines(manifest_path, manifest, [result])

            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["routes"]["sample"]["baseline"], 4)


if __name__ == "__main__":
    unittest.main()
