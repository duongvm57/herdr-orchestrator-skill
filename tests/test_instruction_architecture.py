from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"


def read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


class InstructionArchitectureTests(unittest.TestCase):
    def test_invocation_and_reentry_are_user_and_role_bound(self) -> None:
        skill = read("SKILL.md")
        openai = read("agents/openai.yaml")

        self.assertRegex(openai, r"(?m)^\s*allow_implicit_invocation: false$")
        self.assertIn("Inspect `HERDR_ORCHESTRATOR_ROLE` before routing", skill)
        self.assertIn("Route by role environment, never task text", " ".join(skill.split()))
        self.assertIn("$herdr-orchestrator`, quotes, backticks, `$()`", skill)

    def test_official_skill_is_the_only_generic_operation_contract(self) -> None:
        documents = [
            SKILL_ROOT / "SKILL.md",
            *sorted((SKILL_ROOT / "references").rglob("*.md")),
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in documents)

        self.assertIn("official Herdr Agent Skill", text)
        self.assertIn("`herdr --skill`", text)
        self.assertNotIn("scripts/herdr_runtime.py", text)
        self.assertFalse((SKILL_ROOT / "scripts/herdr_runtime.py").exists())
        for wrapper in ("herdr_runtime_ops.py", "herdr_lead_ops.py", "herdr_peer_ops.py"):
            self.assertNotIn(wrapper, text)

    def test_launcher_launch_contract_preserves_task_and_ownership(self) -> None:
        launch = read("references/launcher/task-launch.md")

        self.assertIn("HERDR_ORCHESTRATOR_ROLE=lead", launch)
        self.assertIn("--no-focus", launch)
        self.assertIn("submit-control-prompt --agent <unique-lead-name>", launch)
        self.assertIn("--project-root <root>", launch)
        self.assertIn("prepare-control-role-launch", launch)
        self.assertNotIn("render-control-prompt", launch)
        self.assertIn("verbatim Human decision", launch)
        self.assertIn("payload hash", launch)
        self.assertIn("<adapter-runtime-bound-helper> submit-control-prompt", launch)
        self.assertIn("direct subprocess argv", launch)
        self.assertIn("exact bytes", launch)
        self.assertIn("unique run-scoped scratch directory", launch)
        self.assertIn("no rendered prompt transport file", launch)
        self.assertIn("agent_not_ready", launch)
        self.assertIn("surface the exact native question to the Human", launch)
        self.assertIn("continue with that same Lead and pane", launch)
        self.assertIn("do not blind-retry", launch)
        self.assertIn("never change pre-existing topology", launch)
        self.assertIn("Every task launch requires this attachment", launch)
        self.assertIn("failed Supervisor launch is a `DEPENDENCY_REQUEST`", launch)

    def test_launcher_creates_a_task_workspace_and_supervisor_splits_the_attached_lead(self) -> None:
        launch = read("references/launcher/task-launch.md")
        supervisor = read("references/launcher/supervisor-attachment.md")

        self.assertIn("herdr workspace create --cwd <root>", launch)
        self.assertIn(".result.root_pane.pane_id", launch)
        self.assertIn("never split the Launcher pane", launch)
        self.assertNotIn("herdr pane split --pane <returned-launcher-pane-id>", launch)
        self.assertNotIn("herdr pane current --current", launch)
        self.assertIn("herdr pane split --pane <attached-lead-pane-id>", supervisor)
        self.assertIn("never use the Launcher's current pane", supervisor)
        self.assertNotIn("herdr pane current --current", supervisor)
        self.assertNotIn("herdr pane split --current", supervisor)
        self.assertNotIn("HERDR_PANE_ID", supervisor)
        self.assertIn("default task launch", supervisor)
        self.assertIn("one native wait", supervisor)
        self.assertIn("it does not poll", supervisor)

    def test_setup_uses_current_validation_and_approval_policy_boundary(self) -> None:
        setup = read("references/launcher/setup.md")
        self.assertIn("doctor --project-root", setup)
        self.assertIn("direct integration", setup)
        self.assertIn("does not mean Herdr lacks agent support", setup)
        self.assertNotIn("--git-common-dir", setup)
        self.assertIn("Approval-gated routes", setup)
        self.assertIn("approval_required = true", setup)
        self.assertIn("selected adapter's verified runtime-binding projection", setup)
        self.assertIn("install-official-skill", setup)
        self.assertRegex(setup, r"matching configured-harness\s+digests")
        self.assertIn("committed files", setup)
        self.assertIn("global `herdr` skill", setup)
        self.assertIn("No install/check enters task launch", setup)
        self.assertIn("assets/orchestration.gitignore", setup)
        self.assertIn("active-flow artifacts remain readable", setup)
        ignore = read("assets/orchestration.gitignore")
        for generated in ("/candidates/", "/prompts/", "/current-candidate.json", "/*-assignment.json", "/*-handback.json"):
            self.assertIn(generated, ignore)
        self.assertNotIn("shell_environment_policy", setup)
        self.assertIn("Recreate the session", setup)
        self.assertIn("one `[roles.lead]` and one `[roles.supervisor]`", setup)

    def test_task_preflight_does_not_repeat_setup_doctor_or_native_discovery(self) -> None:
        preflight = read("references/launcher/preflight.md")

        self.assertIn("no `doctor`, `validate-project`", preflight)
        self.assertIn("rerun setup doctor", preflight)
        for command in (
            "herdr --version",
            "herdr --skill",
            "herdr status",
            "herdr agent start --help",
            "herdr integration status",
            "harness-models",
        ):
            self.assertNotIn(command, preflight)

    def test_role_disclosure_preserves_authority_boundaries(self) -> None:
        lead = read("references/roles/lead.md")
        normalized_lead = " ".join(lead.split())
        peer = read("references/roles/peer.md")
        supervisor = read("references/roles/supervisor.md")
        attachment = read("references/launcher/supervisor-attachment.md")

        self.assertIn("non-overlapping project-relative scope", normalized_lead)
        self.assertIn("observe your exact current Lead identity", lead)
        self.assertIn("exact distinct Peer identity", lead)
        self.assertIn("synthetic Peer", normalized_lead)
        self.assertIn("never proves a Peer outcome", lead)
        self.assertIn("references/lead/topology.md", lead)
        self.assertIn("do not load the entire library", lead)
        self.assertIn("Do not load or use the official Herdr", peer)
        self.assertIn("`REOPEN_REQUEST`", peer)
        self.assertIn("not a technical ACL", peer)
        self.assertIn("Lead named in your attachment", supervisor)
        self.assertIn("--attached-lead-name <lead-name> --attached-lead-pane <lead-pane>", attachment)
        self.assertIn("do not create a Supervisor inference turn", " ".join(attachment.split()))

    def test_continuous_supervision_stays_fail_closed_without_native_wake_proof(self) -> None:
        attachment = read("references/launcher/supervisor-attachment.md")
        scenarios = (ROOT / "tests/orchestration-scenarios.json").read_text(encoding="utf-8")

        self.assertIn("return `DEPENDENCY_REQUEST`", attachment)
        self.assertIn("no native-wake proof bundled", attachment)
        self.assertIn("Bounded Supervisor and topology dogfood", scenarios)
        self.assertIn("Every task launches a bounded Human/Launcher-attached Supervisor", scenarios)
        self.assertIn("continuous supervision remains a DEPENDENCY_REQUEST", scenarios)

    def test_lead_wires_assignment_and_bounded_protocol_context(self) -> None:
        lead = read("references/roles/lead.md")
        lifecycle = read("references/lead/peer-lifecycle.md")
        supervisor = read("references/roles/supervisor.md")
        lead_words = " ".join(lead.split())

        self.assertIn("construct, validate, and submit the canonical Assignment", lead)
        self.assertIn("Do not parse prose back into an Assignment", lead_words)
        self.assertIn("bounded protocol constraints", lifecycle)
        self.assertIn("--applicable-protocol <bounded-constraints.md>", lifecycle)
        self.assertIn("same exact name in `owner`", lifecycle)
        self.assertIn("never a Peer or Supervisor entry", lifecycle)
        self.assertIn("herdr pane split --pane <pane_launch.source_pane_id>", lifecycle)
        self.assertIn("returned Peer pane", lifecycle)
        self.assertIn("compile-runtime --project-root", lifecycle)
        self.assertIn("pane_environment", lifecycle)
        self.assertIn("literal `--env NAME=VALUE`", lifecycle)
        self.assertNotIn("CODEX_HOME", lifecycle)
        self.assertIn("fresh Peer context", lifecycle)
        self.assertIn("no provider syntax is assembled in prose", lifecycle)
        for managed in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID"):
            self.assertIn(managed, lifecycle)
        self.assertIn("not a separate runtime role", lifecycle)
        peer_words = " ".join(read("references/roles/peer.md").split())
        self.assertIn("load and use `ocr-peer-reviewer` when available before inspecting candidate files", peer_words)
        self.assertIn("Submit the Assignment once", lifecycle)
        self.assertIn("native `agent wait`\nwithout a short default timeout", lifecycle)
        self.assertIn("Do not repeat that\nwait or send another prompt until new state or evidence appears", lifecycle)
        self.assertIn("one bounded native `agent get` or `agent read` observation", lifecycle)
        self.assertIn("Do not resend the Assignment blindly", lifecycle)
        self.assertIn("prompt-wait subsystem or exact-turn tracker", lifecycle)
        self.assertIn("start-peer", lifecycle)
        self.assertIn("Never freehand", lifecycle)
        self.assertIn("explicit Human/Launcher attachment", supervisor)
        self.assertIn("runtime observation/state only", supervisor)

    def test_concurrent_writer_route_uses_herdr_worktrees_and_preserves_candidate_gate(self) -> None:
        lifecycle = read("references/lead/peer-lifecycle.md")
        topology = read("references/lead/topology.md")

        self.assertIn("herdr worktree create", lifecycle)
        self.assertIn("herdr worktree list", lifecycle)
        self.assertIn("herdr worktree remove", lifecycle)
        self.assertIn("workspace.worktree.checkout_path", lifecycle)
        self.assertIn("project_root", lifecycle)
        self.assertIn("do not launch\nthat concurrent writer in the shared checkout", lifecycle)
        self.assertIn("Only then freeze the\nsingle common candidate", lifecycle)
        self.assertIn("--worktree-list", lifecycle)
        self.assertIn("Two or more concurrent writers require distinct Herdr-created", topology)
        self.assertIn("no read-only Peer receives a\nworktree", topology)
        self.assertIn("--cwd <canonical-integration-root>", lifecycle)
        self.assertIn("never from an ambient workspace or a workspace ID", lifecycle)
        self.assertIn("Do not use\n`--workspace` as a repository selector", lifecycle)

    def test_config_template_documents_native_permission_policy_without_new_schema(self) -> None:
        template = read("assets/config.toml")

        parsed = tomllib.loads(template)
        self.assertEqual(parsed["version"], 4)
        self.assertEqual(parsed["assessment_after_cycles"], 2)
        self.assertEqual(set(parsed["routing"]), {"engineer", "reviewer", "architect", "default"})
        self.assertIn("approval_required", template)
        self.assertIn("provider-native recipe policy", template)
        self.assertIn("`never` removes prompts only", template)
        self.assertIn("do not translate them into a generic SLP", template)

    def test_global_anti_pattern_catalog_adds_only_the_remaining_mechanisms(self) -> None:
        index = read("references/anti-patterns/index.md")
        responses = read("references/anti-patterns/responses.md")

        for title in (
            "Contract-minting red test",
            "Foundation ballooning",
            "Review-loop non-convergence",
            "Scout-as-Judge",
            "Nested orchestration ownership",
        ):
            self.assertIn(title, index)
            self.assertIn(title, responses)
        self.assertIn("Severity labels do not outrank dependency", responses)
        self.assertNotIn("Priority myopia", index)

    def test_lead_acceptance_gate_is_delivered_and_keeps_review_conditional(self) -> None:
        launch = read("references/launcher/task-launch.md")
        lead = read("references/roles/lead.md")
        candidate = read("references/lead/candidate-and-verdict.md")

        self.assertIn("submit-control-prompt", launch)
        self.assertIn("do not issue a project acceptance or Human-facing final\nverdict", lead)
        self.assertIn("exact stable candidate identity", lead)
        self.assertIn("actual diff/artifact", lead)
        self.assertIn("actual verification command/results", lead)
        self.assertIn("Passing tests alone never\npermits a verdict", lead)
        self.assertIn("An acceptance or Human-facing final verdict is prohibited", candidate)
        self.assertIn("Passing tests does\nnot create a candidate or permit a verdict", candidate)
        self.assertIn("only when\nthe applicable protocol or risk requires it", candidate)

    def test_production_completion_gate_is_mechanical_and_bounded(self) -> None:
        launch = read("references/launcher/task-launch.md")
        lead = read("references/roles/lead.md")
        candidate = read("references/lead/candidate-and-verdict.md")

        self.assertIn("<adapter-runtime-bound-helper> freeze-candidate --project-root <root>", lead)
        self.assertIn("candidate-specific diff path/digest", lead)
        self.assertIn("<adapter-runtime-bound-helper> validate-acceptance --project-root <root>", lead)
        self.assertIn("A bare helper command does not\ncarry that binding and is rejected", lead)
        self.assertIn("<adapter-runtime-bound-helper> validate-acceptance --project-root <root>", launch)
        self.assertIn(".orchestration/current-acceptance.json", candidate)
        self.assertIn("candidate-owned private object directory under Git common metadata", candidate)
        self.assertIn("read-only Git alternate", candidate)
        self.assertIn("candidate-specific immutable diff", candidate)
        self.assertIn("not successful project completion", launch)
        self.assertIn("Only a passing check permits the Launcher", launch)
        self.assertIn("one structured follow-up to that same Lead", launch)
        self.assertIn("Do not edit implementation, manufacture evidence, create a", launch)
        self.assertIn("There is no third validation or correction loop", launch)

    def test_guarded_helper_examples_use_the_role_runtime_binding(self) -> None:
        documents = {
            "lead profile": read("references/roles/lead.md"),
            "candidate card": read("references/lead/candidate-and-verdict.md"),
            "peer lifecycle": read("references/lead/peer-lifecycle.md"),
            "task launch": read("references/launcher/task-launch.md"),
            "OCR Reviewer": (ROOT / "skills/ocr-peer-reviewer/SKILL.md").read_text(encoding="utf-8"),
        }
        guarded = {
            "lead profile": ("start-peer", "freeze-candidate", "validate-acceptance"),
            "candidate card": ("freeze-candidate", "validate-acceptance"),
            "peer lifecycle": ("start-peer", "submit-assignment"),
            "task launch": ("submit-control-prompt", "validate-acceptance"),
            "OCR Reviewer": ("materialize-candidate",),
        }
        for name, commands in guarded.items():
            with self.subTest(document=name):
                for command in commands:
                    self.assertIn(f"<adapter-runtime-bound-helper> {command}", documents[name])
                    self.assertNotIn(
                        f'python3 "$HERDR_ORCHESTRATOR_HELPER" {command}', documents[name],
                    )
                    self.assertNotIn(f"python3 <canonical-helper> {command}", documents[name])

    def test_installed_helper_and_observation_contract_are_unambiguous(self) -> None:
        launch = read("references/launcher/task-launch.md")
        lead = read("references/roles/lead.md")
        supervisor = read("references/launcher/supervisor-attachment.md")
        documents = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [SKILL_ROOT / "SKILL.md", *sorted((SKILL_ROOT / "references").rglob("*.md"))]
        )

        self.assertIn("HERDR_ORCHESTRATOR_HELPER=<canonical-helper-absolute-path>", launch)
        self.assertIn("canonical helper path in the workspace environment", launch)
        self.assertIn("Never guess consumer-root `scripts/`", lead)
        self.assertIn("submit-control-prompt", supervisor)
        self.assertIn("<adapter-runtime-bound-helper> submit-control-prompt", supervisor)
        self.assertIn("--project-root <root>", supervisor)
        self.assertIn("no native-wake proof bundled", supervisor)
        self.assertIn("do not depend on a final result from `agent prompt\n--wait`", launch)
        self.assertIn("matching Assignment handback", launch)
        self.assertIn("candidate plus valid acceptance evidence", launch)
        self.assertNotIn("python3 scripts/herdr_orchestrator.py", documents)

    def test_runtime_binding_is_generic_and_codex_projection_is_local(self) -> None:
        binding = read("references/launcher/runtime-binding.md")
        generic_documents = "\n".join(
            read(relative)
            for relative in (
                "SKILL.md",
                "references/launcher/preflight.md",
                "references/launcher/setup.md",
                "references/launcher/task-launch.md",
                "references/launcher/supervisor-attachment.md",
                "references/lead/peer-lifecycle.md",
                "references/roles/lead.md",
                "references/roles/peer.md",
                "references/roles/supervisor.md",
            )
        )
        codex_adapter = read("scripts/herdr_harnesses/codex.py")

        for option in (
            "compile-runtime",
            "--project-root",
            "--kind",
            "--role",
            "--pane-id",
            "--target-role peer",
            "--assignment",
        ):
            self.assertIn(option, binding)
        self.assertNotIn('"herdr_executable"', binding)
        self.assertNotIn("codex", binding.lower())
        self.assertNotIn("shell_environment_policy", generic_documents)
        self.assertNotIn("CODEX_HOME", generic_documents)
        self.assertIn("render_runtime_binding", codex_adapter)
        self.assertIn("runtime_binding_renderer=render_runtime_binding", codex_adapter)
        self.assertIn("project_pane_environment", codex_adapter)
        self.assertIn("pane_environment_projector=project_pane_environment", codex_adapter)
        self.assertIn("shell_environment_policy.inherit", codex_adapter)
        self.assertIn("HERDR_ORCHESTRATOR_PANE_ID", codex_adapter)
        self.assertIn("exact command form", binding)
        self.assertIn("native `HERDR_PANE_ID`", binding)
        self.assertIn("Adapter code and tests own provider runtime rules", read("SKILL.md"))
        for kind in ("pi", "claude", "codex", "opencode", "grok", "omp"):
            adapter = read(f"scripts/herdr_harnesses/{kind}.py")
            self.assertIn("runtime_binding_renderer=", adapter)
            self.assertIn("pane_environment_projector=", adapter)
            self.assertIn("global_skill_roots_resolver=", adapter)
            self.assertIn("integration=IntegrationSpec", adapter)

    def test_instruction_pointers_resolve(self) -> None:
        documents = [SKILL_ROOT / "SKILL.md", *sorted((SKILL_ROOT / "references").rglob("*.md"))]
        pointer = re.compile(r"`((?:references|assets|scripts)/[^`\s]+)`")
        missing: list[str] = []
        for document in documents:
            for match in pointer.finditer(document.read_text(encoding="utf-8")):
                relative = match.group(1).rstrip(".,;:")
                if "<" not in relative and not (SKILL_ROOT / relative).exists():
                    missing.append(f"{document.relative_to(SKILL_ROOT)} -> {relative}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
