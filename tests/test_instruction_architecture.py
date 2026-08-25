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
        self.assertIn("runtime-binding.json", supervisor)
        self.assertNotIn("start-lead", supervisor)

    def test_run_context_uses_launch_time_project_snapshots(self) -> None:
        launch = read("references/launcher/task-launch.md")
        supervisor = read("references/launcher/supervisor-attachment.md")
        normalized_launch = " ".join(launch.split())

        self.assertIn("config/protocol paths and digests", launch)
        self.assertIn("accepted config and protocol", launch)
        self.assertIn("runtime-manifest.json", launch)
        self.assertIn("start-lead", launch)
        self.assertIn("concise Lead and Peer profiles", normalized_launch)
        self.assertIn("verbatim Human task", launch)
        self.assertIn("context/workspace-protocol.md", supervisor)
        self.assertNotIn("peer-lifecycle=references/", launch)

    def test_supervisor_attachment_is_collision_and_language_bound(self) -> None:
        supervisor = read("references/launcher/supervisor-attachment.md")
        normalized = " ".join(supervisor.split())

        self.assertIn("<attachment-id>", supervisor)
        self.assertIn("[a-z][a-z0-9_-]{0,31}", supervisor)
        self.assertIn("attachment-assignment.md", supervisor)
        self.assertIn("runtime-binding.json", supervisor)
        self.assertIn("herdr_supervisor_ops.py", supervisor)
        self.assertIn("delivery-receipt.json", supervisor)
        self.assertIn("host live language", normalized)
        self.assertIn("Do not prompt, notify, or modify any Lead", supervisor)
        self.assertIn("artifact_language", supervisor)

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
        self.assertIn("version-3 TOML", normalized)
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

    def test_peer_fallback_is_explicit_and_envelope_bound(self) -> None:
        template = read("assets/config.toml")
        setup = read("references/launcher/setup.md")
        runtime = read("scripts/herdr_runtime_ops.py")

        self.assertIn('fallback_peer_recipe = "<fallback-recipe-name>"', template)
        self.assertIn("naming an exact Peer recipe", setup)
        self.assertIn("Human chooses reuse and one fallback recipe", setup)
        self.assertIn('runtime["fallback_peer_profile"]', runtime)
        self.assertIn('config["peer_recipes"].get(name)', runtime)
        self.assertIn('"fallback": request["profile"] is None', runtime)

    def test_harness_specific_logic_lives_in_separate_adapter_modules(self) -> None:
        helper = read("scripts/herdr_orchestrator.py")
        adapter_root = SKILL_ROOT / "scripts/herdr_harnesses"
        registry = (adapter_root / "__init__.py").read_text(encoding="utf-8")
        registered = set(re.findall(r'(?m)^    "([a-z][a-z0-9]*)",$', registry))
        module_names = {
            path.stem
            for path in adapter_root.glob("*.py")
            if path.name not in {"__init__.py", "base.py"}
        }

        self.assertEqual(module_names, registered)
        self.assertEqual(
            registered,
            {"codex", "claude", "grok", "pi", "opencode", "omp"},
        )
        self.assertNotIn(
            "model_only_adapter",
            (adapter_root / "base.py").read_text(encoding="utf-8"),
        )

        for kind in ("codex", "claude", "grok", "pi", "opencode", "omp"):
            module = (adapter_root / f"{kind}.py").read_text(encoding="utf-8")
            self.assertIn(f'kind="{kind}"', module)
            self.assertIn("HarnessAdapter(", module)
            self.assertNotRegex(helper, rf"[\"']{kind}[\"']")

        for kind in ("codex", "grok", "pi", "opencode", "omp"):
            module = (adapter_root / f"{kind}.py").read_text(encoding="utf-8")
            self.assertIn("def project_catalog", module)

        setup = read("references/launcher/setup.md")
        normalized_setup = " ".join(setup.split())
        self.assertIn("harness-models --kind <kind>", setup)
        self.assertIn("--project-root", setup)
        self.assertIn("exact harness adapter", setup)
        self.assertIn(
            "Pi projects only effective native `enabledModels` scope",
            normalized_setup,
        )

    def test_runtime_ops_replace_lead_lifecycle_cards(self) -> None:
        launch = read("references/launcher/task-launch.md")
        lead = read("references/roles/lead.md")
        helper = read("scripts/herdr_orchestrator.py")
        normalized_lead = " ".join(lead.split())

        for wrapper in ("herdr_lead_ops.py", "herdr_peer_ops.py"):
            self.assertIn(wrapper, launch)
            self.assertIn(wrapper, helper)
        self.assertIn("runtime-manifest.json", launch)
        self.assertIn("copy the exact `request_example`", normalized_lead)
        self.assertIn("invoke that contract's `argv`", normalized_lead)
        self.assertIn("Do not invent request keys or inspect CLI help", normalized_lead)
        self.assertNotIn("peer-lifecycle=references/", launch)
        self.assertNotIn("digest-bound disclosure", lead.casefold())

    def test_initial_lead_profile_excludes_runtime_mechanics(self) -> None:
        lead = read("references/roles/lead.md")
        normalized = " ".join(lead.split())

        for mechanics in (
            "herdr agent start",
            "mailbox path",
            "Git common dir",
            "atomic rename",
            "SHA-256",
            "report schema",
        ):
            self.assertNotIn(mechanics, lead)
        self.assertIn("The helper owns routing", normalized)
        self.assertIn("smallest useful topology", normalized)

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
