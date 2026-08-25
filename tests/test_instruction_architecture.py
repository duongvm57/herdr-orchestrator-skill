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

        self.assertIn("--expected-activation-sha256", launch)
        self.assertIn("setup-activation.json", launch)
        self.assertIn("bind-role --role lead", launch)
        self.assertIn("context/lead-launch.json", launch)
        self.assertIn("context/project-config.toml", launch)
        self.assertIn("context/workspace-protocol.md", launch)
        self.assertIn("├── human-task.md", launch)
        self.assertIn("filtered selection manifest", supervisor)
        self.assertIn("context/workspace-protocol.md", supervisor)
        self.assertNotIn(".orchestration/herdr-orchestrator.toml", launch)

    def test_supervisor_attachment_is_collision_and_language_bound(self) -> None:
        supervisor = read("references/launcher/supervisor-attachment.md")

        self.assertIn("<attachment-id>", supervisor)
        self.assertIn("[a-z][a-z0-9_-]{0,31}", supervisor)
        self.assertIn("--selection-output", supervisor)
        self.assertIn("attachment-assignment.md", supervisor)
        self.assertIn("delivery-receipt.json", supervisor)
        self.assertIn("local-receipt.md", supervisor)
        self.assertIn("lead-notification-receipt.json", supervisor)
        self.assertIn("bind-role --role supervisor", supervisor)
        self.assertIn("configured artifact", supervisor)
        self.assertIn("configured live language", supervisor)
        self.assertIn("Cross-project observation requires a later authority slice", supervisor)

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

    def test_setup_presents_only_engine_owned_typed_questions(self) -> None:
        setup = read("references/launcher/setup.md")
        normalized = " ".join(setup.split())

        self.assertIn("present only `questions`", normalized)
        self.assertIn("Preserve each question `id`, `kind`, option value, and fact", normalized)
        self.assertIn("show the complete numbered engine list", normalized)
        self.assertIn("submit only answers to questions open in the same revision", normalized)
        self.assertIn("Use JSON booleans for `BOOLEAN` answers", normalized)
        self.assertIn("For `TEXT`, return the Human's nonempty canonical string exactly", normalized)
        self.assertNotIn("recommendation first", normalized)
        self.assertNotIn("free-form answer", normalized)

    def test_setup_is_a_thin_resume_answer_accept_presenter(self) -> None:
        setup = read("references/launcher/setup.md")
        normalized = " ".join(setup.split())

        self.assertIn("calls only `resume`, `answer`, and `accept`", normalized)
        self.assertIn("herdr_setup_cli.py resume", setup)
        self.assertIn("herdr_setup_cli.py answer", setup)
        self.assertIn("herdr_setup_cli.py accept", setup)
        self.assertIn("A generic “yes” is not a digest confirmation", normalized)
        self.assertIn("only runtime authority", normalized)
        self.assertNotIn("Configure TOML yourself", setup)

    def test_setup_defers_harness_model_and_authority_to_engine_view(self) -> None:
        setup = read("references/launcher/setup.md")
        normalized = " ".join(setup.split())

        self.assertIn("every `role_binding`", setup)
        self.assertIn("complete effective authority", normalized)
        self.assertIn("add no option, recommendation, model ranking", normalized)
        self.assertIn("Never retry, reset Human decisions, weaken authority", normalized)
        self.assertNotIn("herdr agent start --help", setup)
        self.assertNotIn("profile matrix", setup)

    def test_peer_role_selection_is_authority_bound_and_fail_closed(self) -> None:
        setup = read("references/launcher/setup.md")
        lifecycle = read("references/lead/peer-lifecycle.md")
        normalized_setup = " ".join(setup.split())

        self.assertIn("no mutable compatibility config", normalized_setup)
        self.assertIn("project mutation required → `engineer`", lifecycle)
        self.assertIn("project read plus evidence write → `reviewer`", lifecycle)
        self.assertIn("unknown Assignment never routes to a writable role", lifecycle)

    def test_codex_authority_and_runtime_binding_have_separate_modules(self) -> None:
        helper = read("scripts/herdr_orchestrator.py")
        engine = read("scripts/herdr_setup/engine.py")
        codex_authority = read("scripts/herdr_setup/codex_authority.py")
        runtime = read("scripts/herdr_runtime.py")
        self.assertIn("probe_codex", engine)
        self.assertIn("compile_codex", engine)
        self.assertIn("def probe_codex", codex_authority)
        self.assertIn("def compile_codex", codex_authority)
        self.assertIn("def load_accepted_project", runtime)
        self.assertIn("def bind_role_launch", runtime)
        self.assertIn("bind_role_launch", helper)
        self.assertNotIn("--permission-profile", engine)

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

        staged = set(
            re.findall(r"(?m)^\s*--asset ([a-z][a-z-]+)=references/", launch)
        )
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
