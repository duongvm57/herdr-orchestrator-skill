from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/herdr-orchestrator/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from herdr_setup.acceptance import (  # noqa: E402
    parse_acceptance_receipt,
    render_acceptance_receipt,
)
from herdr_setup.codex_authority import (  # noqa: E402
    AssuranceLevel,
    CodexModelObservation,
    CodexObservation,
    CodexProbeResult,
    CodexProbeStatus,
    CodexVersion,
)
from herdr_setup.engine import (  # noqa: E402
    SetupAnswerError,
    SetupAnswerKind,
    SetupEngine,
    SetupRevisionConflict,
    SetupStateError,
    SetupStatus,
    SetupTransitionError,
    SetupTypedAnswer,
    render_setup_view,
)
from herdr_setup.runtime_proof import (  # noqa: E402
    NativeCommandResult,
    parse_runtime_proof,
    render_runtime_proof,
)


def run(*arguments: str) -> None:
    subprocess.run(arguments, text=True, capture_output=True, check=True)


class CountingProofRunner:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command: tuple[str, ...], timeout: float) -> NativeCommandResult:
        del timeout
        self.calls += 1
        plan = json.loads(command[-1])
        receipt = [
            {
                "identifier": check["identifier"],
                "observed": check["expected"],
                "error_code": 1 if check["expected"] == "DENY" else None,
            }
            for check in plan
        ]
        return NativeCommandResult(
            0,
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            "",
        )


class SetupEngineTests(unittest.TestCase):
    executable = "/usr/bin/true"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="herdr-engine-test-")
        self.project = Path(self.temporary.name).resolve() / "project"
        self.project.mkdir()
        run("git", "init", "-q", str(self.project))
        self.runner = CountingProofRunner()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def probe(self, executable: str, *, cwd: str) -> CodexProbeResult:
        self.assertEqual(executable, self.executable)
        observation = CodexObservation(
            executable=executable,
            version=CodexVersion(0, 149, 1),
            runtime_root="/usr/bin",
            bound_cwd=cwd,
            models=(
                CodexModelObservation("gpt-5.6-sol", ("high", "xhigh")),
                CodexModelObservation("gpt-5.6-terra", ("medium", "high")),
                CodexModelObservation("gpt-5.6-luna", ("low", "medium")),
            ),
            permission_profiles=True,
            permission_profile_assurance=AssuranceLevel.RUNTIME_PROBED,
            native_spawn_control=True,
            native_spawn_assurance=AssuranceLevel.STATIC_PROVEN,
            network_control=True,
            network_assurance=AssuranceLevel.RUNTIME_PROBED,
            legacy_sandbox_settings=False,
        )
        return CodexProbeResult(CodexProbeStatus.READY, observation, ())

    def engine(self) -> SetupEngine:
        return SetupEngine(
            codex_executable=self.executable,
            codex_probe=self.probe,
            proof_runner=self.runner,
        )

    @staticmethod
    def answer_value(question, *, repository: str | None = None):
        del repository
        fixed = {
            "policy.live_language": "Vietnamese",
            "policy.artifact_language": "English",
        }
        return fixed[question.identifier]

    def answer_policy(self, engine: SetupEngine, view, *, repository=None):
        del repository
        answers = tuple(
            SetupTypedAnswer(
                question.identifier,
                question.kind,
                self.answer_value(question),
            )
            for question in view.questions
            if question.identifier.startswith("policy.")
        )
        return engine.answer(view.session_id, view.revision, answers)

    @staticmethod
    def answer_models(engine: SetupEngine, view):
        targets = {
            "binding.lead": ("gpt-5.6-sol", "xhigh"),
            "binding.peer": ("gpt-5.6-terra", "medium"),
            "binding.supervisor": ("gpt-5.6-luna", "low"),
            "binding.fallback": ("gpt-5.6-terra", "high"),
        }
        answers = []
        for question in view.questions:
            model, effort = targets[question.identifier]
            option = next(
                option
                for option in question.options
                if dict(option.facts).get("model") == model
                and dict(option.facts).get("reasoning_effort") == effort
            )
            answers.append(
                SetupTypedAnswer(
                    question.identifier,
                    SetupAnswerKind.CHOICE,
                    option.value,
                )
            )
        return engine.answer(view.session_id, view.revision, tuple(answers))

    def prepare(self):
        engine = self.engine()
        initial = engine.resume(str(self.project))
        language_questions = tuple(q for q in initial.questions if q.identifier.startswith("policy."))
        policy = engine.answer(
            initial.session_id,
            initial.revision,
            tuple(
                SetupTypedAnswer(q.identifier, q.kind, self.answer_value(q))
                for q in language_questions
            ),
        )
        prepared = self.answer_models(engine, policy)
        return engine, initial, policy, prepared

    def test_resume_projects_only_engine_questions_without_model_ranking(self) -> None:
        view = self.engine().resume(str(self.project))

        self.assertEqual(view.status, SetupStatus.NEEDS_HUMAN_INPUT)
        self.assertEqual(view.revision, 0)
        inventory = {item.kind: item for item in view.harnesses}
        self.assertEqual(inventory["codex"].status, "READY")
        self.assertTrue({"claude", "gemini", "opencode", "pi"} <= set(inventory))
        self.assertEqual(
            {question.identifier for question in view.questions},
            {
                "binding.lead",
                "binding.peer",
                "binding.supervisor",
                "binding.fallback",
                "policy.live_language",
                "policy.artifact_language",
            },
        )
        self.assertNotIn(
            "policy.native_agent_policy",
            {question.identifier for question in view.questions},
        )
        rendered = render_setup_view(view)
        self.assertNotIn(b"recommend", rendered.lower())
        self.assertNotIn(b"cheaper", rendered.lower())
        self.assertNotIn(b"strongest", rendered.lower())
        with self.assertRaises(FrozenInstanceError):
            view.revision = 99

    def test_typed_answers_compile_prove_and_prepare_one_immutable_candidate(self) -> None:
        _, _, policy, prepared = self.prepare()

        self.assertEqual(policy.status, SetupStatus.NEEDS_HUMAN_INPUT)
        self.assertEqual(
            {question.identifier for question in policy.questions},
            {"binding.lead", "binding.peer", "binding.supervisor", "binding.fallback"},
        )
        for question in policy.questions:
            self.assertTrue(question.options)
            self.assertIn("not ranked", question.reason)
            self.assertTrue(
                all(
                    set(dict(option.facts))
                    == {"harness", "model", "reasoning_effort"}
                    for option in question.options
                )
            )
        self.assertEqual(prepared.status, SetupStatus.AWAITING_ACCEPTANCE)
        self.assertEqual(prepared.revision, 2)
        self.assertIsNotNone(prepared.candidate_digest)
        self.assertIsNotNone(prepared.runtime_proof_digest)
        self.assertIsNotNone(prepared.publication_digest)
        self.assertEqual(
            {binding.template for binding in prepared.authority_bindings},
            {"lead", "peer_writable", "peer_readonly", "supervisor"},
        )
        reviewer = next(
            binding for binding in prepared.authority_bindings if binding.template == "peer_readonly"
        )
        self.assertIn("fs.write(evidence:assignment)", reviewer.effective_authority)
        self.assertNotIn("fs.write(project:assigned)", reviewer.effective_authority)
        self.assertEqual(self.runner.calls, 4)

    def test_resume_reuses_canonical_runtime_receipt_without_repeating_smoke(self) -> None:
        _, _, _, prepared = self.prepare()
        calls = self.runner.calls

        resumed = self.engine().resume(str(self.project))

        self.assertEqual(resumed, prepared)
        self.assertEqual(self.runner.calls, calls)
        state_file = next(
            (self.project / ".orchestration/setup/sessions").glob("*.json")
        )
        state = json.loads(state_file.read_bytes())
        proof_payload = json.dumps(
            state["runtime_proof"], sort_keys=True, separators=(",", ":")
        ).encode() + b"\n"
        proof = parse_runtime_proof(proof_payload)
        self.assertEqual(render_runtime_proof(proof), proof_payload)

    def test_revision_cas_and_open_question_validation_write_nothing_on_error(self) -> None:
        engine = self.engine()
        initial = engine.resume(str(self.project))
        policy = self.answer_policy(engine, initial)
        first_question = policy.questions[0]
        answer = SetupTypedAnswer(
            first_question.identifier,
            first_question.kind,
            first_question.options[0].value,
        )

        with self.assertRaises(SetupRevisionConflict) as conflict:
            engine.answer(policy.session_id, initial.revision, (answer,))
        self.assertEqual(conflict.exception.view, policy)
        with self.assertRaises(SetupAnswerError):
            engine.answer(
                policy.session_id,
                policy.revision,
                (
                    SetupTypedAnswer(
                        "invented.question",
                        SetupAnswerKind.CHOICE,
                        "invented",
                    ),
                ),
            )
        self.assertEqual(engine.resume(str(self.project)), policy)

    def test_symlinked_session_root_fails_closed(self) -> None:
        outside = Path(self.temporary.name).resolve() / "outside"
        outside.mkdir()
        (self.project / ".orchestration").symlink_to(
            outside,
            target_is_directory=True,
        )

        with self.assertRaises(SetupStateError):
            self.engine().resume(str(self.project))

        self.assertEqual(tuple(outside.iterdir()), ())

    def test_tampered_session_digest_is_never_loaded(self) -> None:
        self.engine().resume(str(self.project))
        state_file = next(
            (self.project / ".orchestration/setup/sessions").glob("*.json")
        )
        document = json.loads(state_file.read_bytes())
        document["revision"] = 999
        state_file.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(SetupStateError):
            self.engine().resume(str(self.project))

    def test_explicit_restart_archives_an_incompatible_session_without_migration(self) -> None:
        initial = self.engine().resume(str(self.project))
        state_file = next(
            (self.project / ".orchestration/setup/sessions").glob("*.json")
        )
        legacy = b'{"schema":"unsupported-old-session"}\n'
        state_file.write_bytes(legacy)

        restarted = self.engine().resume(str(self.project), restart=True)

        self.assertEqual(restarted.status, SetupStatus.NEEDS_HUMAN_INPUT)
        self.assertEqual(restarted.revision, 0)
        archives = tuple(
            (self.project / ".orchestration/setup/sessions").glob(
                f"{initial.session_id}.superseded-*.json"
            )
        )
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), legacy)

    def test_failed_smoke_requires_typed_retry_before_reproof(self) -> None:
        failing = SetupEngine(
            codex_executable=self.executable,
            codex_probe=self.probe,
            proof_runner=lambda command, timeout: NativeCommandResult(
                0,
                "not-json",
                "",
            ),
        )
        initial = failing.resume(str(self.project))
        policy = self.answer_policy(failing, initial)
        failed = self.answer_models(failing, policy)

        self.assertEqual(failed.status, SetupStatus.SMOKE_FAILED)
        self.assertEqual(
            tuple(question.identifier for question in failed.questions),
            ("setup.retry_smoke",),
        )
        recovered = self.engine().answer(
            failed.session_id,
            failed.revision,
            (
                SetupTypedAnswer(
                    "setup.retry_smoke",
                    SetupAnswerKind.CHOICE,
                    "retry",
                ),
            ),
        )
        self.assertEqual(recovered.status, SetupStatus.AWAITING_ACCEPTANCE)

    def test_changed_snapshot_requires_explicit_restart(self) -> None:
        engine = self.engine()
        initial = engine.resume(str(self.project))
        policy = self.answer_policy(engine, initial)
        (self.project / "AGENTS.md").write_text("new policy\n", encoding="utf-8")

        stale = engine.resume(str(self.project))

        self.assertEqual(stale.status, SetupStatus.STALE)
        self.assertEqual(
            tuple(question.identifier for question in stale.questions),
            ("setup.restart",),
        )
        restarted = engine.answer(
            stale.session_id,
            stale.revision,
            (
                SetupTypedAnswer(
                    "setup.restart",
                    SetupAnswerKind.CHOICE,
                    "restart",
                ),
            ),
        )
        self.assertEqual(restarted.status, SetupStatus.NEEDS_HUMAN_INPUT)
        self.assertGreater(restarted.revision, policy.revision)
        self.assertNotEqual(restarted.discovery_digest, policy.discovery_digest)
        self.assertIn("binding.lead", {q.identifier for q in restarted.questions})

    def test_accept_requires_exact_digest_then_resumes_as_verified_accepted(self) -> None:
        engine, _, _, prepared = self.prepare()
        self.assertIsNotNone(prepared.candidate_digest)

        with self.assertRaises(SetupTransitionError) as rejected:
            engine.accept(prepared.session_id, "0" * 64)
        self.assertEqual(
            rejected.exception.view.status,
            SetupStatus.AWAITING_ACCEPTANCE,
        )
        self.assertFalse(
            (self.project / ".orchestration/setup/current.json").exists()
        )

        receipt = engine.accept(prepared.session_id, prepared.candidate_digest)

        self.assertEqual(receipt.candidate_digest, prepared.candidate_digest)
        self.assertEqual(
            parse_acceptance_receipt(render_acceptance_receipt(receipt)),
            receipt,
        )
        accepted = self.engine().resume(str(self.project))
        self.assertEqual(accepted.status, SetupStatus.ACCEPTED)
        self.assertEqual(
            accepted.acceptance_receipt_digest,
            receipt.receipt_digest,
        )
        retried = self.engine().accept(
            prepared.session_id,
            prepared.candidate_digest,
        )
        self.assertEqual(retried, receipt)

    def test_nested_repositories_are_inventory_not_setup_questions(self) -> None:
        backend = self.project / "backend"
        backend.mkdir()
        run("git", "init", "-q", str(backend))
        engine = self.engine()
        initial = engine.resume(str(self.project))
        self.assertNotIn(
            "repository.binding",
            {question.identifier for question in initial.questions},
        )
        policy = self.answer_policy(engine, initial)
        prepared = self.answer_models(engine, policy)

        self.assertEqual(prepared.status, SetupStatus.AWAITING_ACCEPTANCE)
        self.assertTrue(prepared.authority_bindings)
        self.assertTrue(
            all(binding.cwd == str(self.project) for binding in prepared.authority_bindings)
        )


if __name__ == "__main__":
    unittest.main()
