from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"


def read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


class InstructionArchitectureTests(unittest.TestCase):
    def test_invocation_is_mechanically_user_only(self) -> None:
        skill = read("SKILL.md")
        openai = read("agents/openai.yaml")

        self.assertNotIn("disable-model-invocation", skill)
        self.assertRegex(openai, r"(?m)^\s*allow_implicit_invocation: false$")

    def test_root_routes_each_invocation_without_runtime_role_sources(self) -> None:
        skill = read("SKILL.md")

        for path in (
            "references/launcher/setup.md",
            "references/launcher/task-launch.md",
            "references/launcher/supervisor-attachment.md",
        ):
            self.assertIn(f"`{path}`", skill)
        self.assertNotIn("references/roles/lead.md", skill)
        self.assertNotIn("references/roles/peer.md", skill)
        self.assertNotIn("references/roles/supervisor.md", skill)

    def test_references_are_grouped_by_consumer(self) -> None:
        reference_root = SKILL_ROOT / "references"

        self.assertEqual(list(reference_root.glob("*.md")), [])
        self.assertEqual(
            {path.name for path in reference_root.iterdir() if path.is_dir()},
            {"anti-patterns", "launcher", "lead", "roles"},
        )

    def test_installable_bundle_excludes_repository_maintenance(self) -> None:
        self.assertFalse((ROOT / "SKILL.md").exists())
        for excluded in (
            "README.md",
            "tests",
            "maintenance",
            ".github",
            "requirements-dev.txt",
        ):
            self.assertFalse((SKILL_ROOT / excluded).exists(), excluded)

    def test_runtime_docs_never_execute_the_generic_herdr_skill_dump(self) -> None:
        runtime_docs = (
            "references/launcher/setup.md",
            "references/launcher/preflight.md",
            "references/launcher/task-launch.md",
            "references/launcher/supervisor-attachment.md",
            "references/roles/lead.md",
            "references/roles/peer.md",
            "references/roles/supervisor.md",
            "references/lead/peer-lifecycle.md",
            "references/lead/candidate-and-verdict.md",
        )
        command_line = re.compile(r"(?m)^\s*herdr --skill\s*$")

        for path in runtime_docs:
            self.assertIsNone(command_line.search(read(path)), path)

    def test_launcher_and_supervisor_branches_are_separate(self) -> None:
        launch = read("references/launcher/task-launch.md")
        supervisor = read("references/launcher/supervisor-attachment.md")

        self.assertNotIn("references/roles/supervisor.md", launch)
        self.assertNotIn("init-run", supervisor)
        self.assertIn("stage-assets", supervisor)

    def test_run_context_uses_launch_time_project_snapshots(self) -> None:
        launch = read("references/launcher/task-launch.md")
        supervisor = read("references/launcher/supervisor-attachment.md")

        self.assertIn("--project-config-file", launch)
        self.assertIn("--workspace-protocol-file", launch)
        self.assertIn("--expected-project-config-sha256", launch)
        self.assertIn("--expected-workspace-protocol-sha256", launch)
        self.assertIn("canonical project paths", launch)
        self.assertIn("context/project-config.toml", launch)
        self.assertIn("context/workspace-protocol.md", launch)
        self.assertIn("run-local `human-task.md`", launch)
        self.assertIn("filtered selection manifest", supervisor)
        self.assertIn("context/workspace-protocol.md", supervisor)
        self.assertNotIn("then the full project Workspace Protocol", launch)

    def test_supervisor_attachment_is_collision_and_language_bound(self) -> None:
        supervisor = read("references/launcher/supervisor-attachment.md")

        self.assertIn("<attachment-id>", supervisor)
        self.assertIn("[a-z][a-z0-9_-]{0,31}", supervisor)
        self.assertIn("--selection-output", supervisor)
        self.assertIn("attachment-assignment.md", supervisor)
        self.assertIn("delivery-receipt.json", supervisor)
        self.assertIn("local-receipt.md", supervisor)
        self.assertIn("lead-notification-receipt.json", supervisor)
        self.assertIn("every bound run's `supervisor/`", supervisor)
        self.assertIn("host project's live language", supervisor)
        self.assertRegex(supervisor, r"that project's\s+artifact language")
        self.assertRegex(supervisor, r"that\s+project's live language")

    def test_readme_stays_user_facing(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for internal in (
            "context-budgets.json",
            "context_budget.py",
            "herdr_orchestrator.py",
            "render_coverage.py",
            "requirements-dev.txt",
            ".github/workflows",
        ):
            self.assertNotIn(internal, readme)

    def test_ci_pip_cache_tracks_dev_requirements(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("cache: pip", workflow)
        self.assertRegex(
            workflow,
            r"(?m)^\s+cache-dependency-path: requirements-dev\.txt$",
        )

    def test_setup_prefers_harness_choice_cards(self) -> None:
        setup = read("references/launcher/setup.md")
        normalized = " ".join(setup.split())

        for contract in (
            r"structured user-input",
            r"one question per card",
            r"2–3\s+exclusive choices",
            r"explicit labels",
            r"recommendation first",
            r"free-form answer",
        ):
            self.assertRegex(normalized, contract)
        self.assertIn("every valid answer as a numbered choice", normalized)
        self.assertIn("request its number", normalized)
        self.assertIn("one question and wait", normalized)

    def test_setup_offers_guided_or_human_configured_toml(self) -> None:
        setup = read("references/launcher/setup.md")
        normalized = " ".join(setup.split())

        self.assertIn("Choose configuration mode", setup)
        self.assertIn("Guided setup", setup)
        self.assertIn("Configure TOML yourself", setup)
        self.assertIn("version-2 TOML", normalized)
        self.assertIn("so the Human can create or edit it", normalized)
        self.assertIn("assets/config.toml", setup)
        self.assertIn("from chat or", normalized)
        self.assertIn("role/recipe fields", normalized)
        self.assertIn("only missing protocol decisions", normalized)
        self.assertLess(
            setup.index("Choose configuration mode"),
            setup.index("profile matrix"),
        )

    def test_setup_selects_harness_before_recipe_details(self) -> None:
        setup = read("references/launcher/setup.md")
        template = read("assets/config.toml")
        normalized = " ".join(setup.split())

        self.assertIn("herdr agent start --help", setup)
        self.assertIn("herdr integration status", setup)
        self.assertIn("intersect kinds", setup)
        self.assertIn("omit the rest", setup)
        self.assertIn("profile matrix", setup)
        self.assertIn("Each row independently selects its harness", setup)
        self.assertIn("fast/general/reasoning/coding/architecture/reviewer", setup)
        self.assertRegex(setup, r"assignment\s+binds the Peer disposition")
        self.assertIn("kinds may differ", template)
        self.assertLess(
            normalized.index("Each row independently selects its harness"),
            normalized.index("then discover and choose its model"),
        )

    def test_lead_asset_names_match_launch_staging_contract(self) -> None:
        launch = read("references/launcher/task-launch.md")
        lead = read("references/roles/lead.md")
        expected = {
            "topology",
            "peer-lifecycle",
            "candidate-and-verdict",
            "anti-pattern-details",
            "peer-profile",
        }

        staged = set(re.findall(r"(?m)^([a-z][a-z-]+)=references/", launch))
        mapped = set(re.findall(r"(?m)^- `([a-z][a-z-]+)` —", lead))

        self.assertEqual(staged, expected)
        self.assertEqual(mapped, expected)

    def test_initial_lead_context_excludes_disclosed_bodies(self) -> None:
        lead = read("references/roles/lead.md")
        index = read("references/anti-patterns/index.md")
        combined = lead + index

        self.assertNotIn("# PEER REPORT", combined)
        self.assertNotIn("## Difficult council", combined)
        self.assertNotIn("## 17. Supervisor overreach", combined)
        self.assertIn("read that card completely before", lead)

    def test_disclosed_cards_have_explicit_trigger_and_completion_bound(self) -> None:
        cards = {
            "references/lead/topology.md": ("before choosing a topology", "Selection is complete"),
            "references/lead/peer-lifecycle.md": ("before drafting", "Collection is complete"),
            "references/lead/candidate-and-verdict.md": ("before recording", "The run is complete"),
            "references/anti-patterns/responses.md": (
                "After a signal triggers",
                "Response is complete only when the observed signal is recorded as evidence",
            ),
        }
        for path, (trigger, completion) in cards.items():
            body = read(path)
            self.assertIn(trigger, body, path)
            self.assertIn(completion, body, path)

    def test_repository_instruction_pointers_resolve(self) -> None:
        documents = [
            SKILL_ROOT / "SKILL.md",
            *sorted((SKILL_ROOT / "references").rglob("*.md")),
        ]
        pointer = re.compile(r"`((?:references|assets|scripts)/[^`\s]+)`")
        missing: list[str] = []
        for document in documents:
            for match in pointer.finditer(document.read_text(encoding="utf-8")):
                relative = match.group(1).rstrip(".,;:")
                if "<" in relative or ">" in relative:
                    continue
                if not (SKILL_ROOT / relative).exists():
                    missing.append(f"{document.relative_to(SKILL_ROOT)} -> {relative}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
