"""Claude Code recipe adapter."""

from __future__ import annotations

import re

from .base import (
    ArgumentRule,
    EvidenceRootRule,
    HarnessAdapter,
    HarnessError,
    choices,
    validate_absolute_directory,
    validate_model,
)


def validate_spawn_tools(value: str, location: str) -> None:
    tools = [item for item in re.split(r"[\s,]+", value) if item]
    if not tools or not set(tools) <= {"Agent", "Task"}:
        raise HarnessError(f"{location} has an unsupported value")


ADAPTER = HarnessAdapter(
    kind="claude",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--effort": ArgumentRule(choices("low", "medium", "high", "xhigh", "max")),
        "--permission-mode": ArgumentRule(
            choices(
                "acceptEdits",
                "auto",
                "bypassPermissions",
                "manual",
                "dontAsk",
                "plan",
            )
        ),
        "--add-dir": ArgumentRule(validate_absolute_directory, repeatable=True),
        "--disallowedTools": ArgumentRule(validate_spawn_tools, repeatable=True),
        "--disallowed-tools": ArgumentRule(validate_spawn_tools, repeatable=True),
        "--disable-slash-commands": ArgumentRule(),
        "--no-chrome": ArgumentRule(),
        "--ax-screen-reader": ArgumentRule(),
    },
    evidence_root=EvidenceRootRule(option="--add-dir"),
)
