"""Claude Code recipe adapter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from .base import (
    ArgumentRule,
    EvidenceRootRule,
    HarnessAdapter,
    HarnessError,
    IntegrationSpec,
    RuntimeBinding,
    choices,
    no_extra_pane_environment,
    render_literal_runtime_binding,
    validate_absolute_directory,
    validate_model,
)


def render_runtime_binding(binding: RuntimeBinding) -> str:
    return render_literal_runtime_binding(
        binding,
        "Claude Code",
        "Claude Code uses its normal role profile; the literal binding pins only "
        "Herdr and guarded-helper runtime facts.",
    )


def resolve_global_skill_roots(
    environment: Mapping[str, str], home: Path,
) -> tuple[Path, ...]:
    del environment
    return (home / ".claude" / "skills",)


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
    runtime_binding_renderer=render_runtime_binding,
    pane_environment_projector=no_extra_pane_environment,
    global_skill_roots_resolver=resolve_global_skill_roots,
    integration=IntegrationSpec(
        role="session",
        state_authority="screen_manifest",
    ),
    evidence_root=EvidenceRootRule(option="--add-dir"),
)
