#!/usr/bin/env python3
"""Thin JSON command interface for the deterministic setup engine."""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("error: herdr_setup_cli.py requires Python 3.11 or newer\n")
    raise SystemExit(2)

import argparse
import json
from collections.abc import Sequence

from herdr_setup import (
    SetupAnswerKind,
    SetupEngine,
    SetupEngineError,
    SetupRevisionConflict,
    SetupStateError,
    SetupTransitionError,
    SetupTypedAnswer,
    render_acceptance_receipt,
    render_setup_view,
)


def _answers(value: str) -> tuple[SetupTypedAnswer, ...]:
    try:
        document = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("answers must be valid JSON") from exc
    if not isinstance(document, list):
        raise argparse.ArgumentTypeError("answers JSON must be a list")
    answers: list[SetupTypedAnswer] = []
    try:
        for item in document:
            if not isinstance(item, dict) or set(item) != {"id", "kind", "value"}:
                raise ValueError("answer fields")
            answers.append(
                SetupTypedAnswer(
                    identifier=item["id"],
                    kind=SetupAnswerKind(item["kind"]),
                    value=item["value"],
                )
            )
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("answers JSON contains invalid values") from exc
    if not answers:
        raise argparse.ArgumentTypeError("answers JSON must not be empty")
    return tuple(answers)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-executable",
        help="advanced override for the exact Codex executable path",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    resume = commands.add_parser("resume", help="resume or start project setup")
    resume.add_argument("--project-root", required=True)

    answer = commands.add_parser("answer", help="submit engine-issued typed answers")
    answer.add_argument("--session-id", required=True)
    answer.add_argument("--revision", type=int, required=True)
    answer.add_argument("--answers-json", type=_answers, required=True)

    accept = commands.add_parser("accept", help="accept one exact Candidate Digest")
    accept.add_argument("--session-id", required=True)
    accept.add_argument("--candidate-digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    engine = SetupEngine(codex_executable=arguments.codex_executable)
    try:
        if arguments.command == "resume":
            sys.stdout.buffer.write(render_setup_view(engine.resume(arguments.project_root)))
        elif arguments.command == "answer":
            sys.stdout.buffer.write(
                render_setup_view(
                    engine.answer(
                        arguments.session_id,
                        arguments.revision,
                        arguments.answers_json,
                    )
                )
            )
        else:
            sys.stdout.buffer.write(
                render_acceptance_receipt(
                    engine.accept(
                        arguments.session_id,
                        arguments.candidate_digest,
                    )
                )
            )
        return 0
    except (SetupRevisionConflict, SetupTransitionError) as exc:
        sys.stdout.buffer.write(render_setup_view(exc.view))
        sys.stderr.write(f"error: {exc}\n")
        return 3
    except SetupEngineError as exc:
        if hasattr(exc, "view"):
            sys.stdout.buffer.write(render_setup_view(exc.view))
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except (OSError, ValueError) as exc:
        error = SetupStateError(str(exc))
        sys.stderr.write(f"error: {error}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
