"""Oh My Pi recipe and authenticated model-catalog adapter."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .base import (
    ArgumentRule,
    CatalogSpec,
    EvidenceRootRule,
    HarnessAdapter,
    HarnessError,
    IntegrationSpec,
    RuntimeBinding,
    catalog_model_id,
    choices,
    decode_catalog,
    no_extra_pane_environment,
    render_literal_runtime_binding,
    validate_absolute_directory,
    validate_model,
    validate_tool_list,
)


THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max", "auto")
COST_FIELDS = ("input", "output", "cacheRead", "cacheWrite")


def resolve_global_skill_roots(
    environment: Mapping[str, str], home: Path,
) -> tuple[Path, ...]:
    config_name = environment.get("PI_CONFIG_DIR") or ".omp"
    profile = environment.get("OMP_PROFILE") or environment.get("PI_PROFILE")
    if profile:
        root = home / config_name / "profiles" / profile / "agent"
    else:
        configured = environment.get("PI_CODING_AGENT_DIR")
        root = Path(configured).expanduser() if configured else home / config_name / "agent"
        if not root.is_absolute():
            root = Path.cwd() / root
    return (home / ".agents" / "skills", root / "skills")


def render_runtime_binding(binding: RuntimeBinding) -> str:
    return render_literal_runtime_binding(
        binding,
        "OMP",
        "OMP uses its normal role profile; the literal binding pins only Herdr "
        "and guarded-helper runtime facts.",
    )


def _option_values(args: list[str], option: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(args):
        current = args[index]
        index += 1
        if current in {"--no-tools", "--no-lsp", "--no-pty", "--no-session", "--no-prewalk", "--no-extensions", "--no-skills", "--no-rules"}:
            continue
        if index >= len(args):  # generic validation reports the missing value first
            break
        if current == option:
            values.append(args[index])
        index += 1
    return values


def validate_argument_set(args: list[str], location: str) -> None:
    if len(_option_values(args, "--model")) != 1:
        raise HarnessError(f"{location}.args must select exactly one OMP model")
    if "--no-prewalk" not in args:
        raise HarnessError(f"{location}.args must include --no-prewalk to prevent model switching")

    tool_values = _option_values(args, "--tools")
    no_tools = "--no-tools" in args
    if len(tool_values) + int(no_tools) != 1:
        raise HarnessError(
            f"{location}.args must use exactly one of --tools or --no-tools"
        )
    if tool_values:
        tools = {item for value in tool_values for item in value.replace(",", " ").split()}
        if "task" in tools:
            raise HarnessError(f"{location}.args must exclude OMP's native task subagent")


def _optional_limit(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HarnessError(f"{label} must be a positive integer or null")
    return value


def _project_cost(value: Any, label: str) -> dict[str, float | int]:
    if not isinstance(value, dict) or set(value) != set(COST_FIELDS):
        raise HarnessError(f"{label} must contain the exact OMP cost fields")
    projected: dict[str, float | int] = {}
    for field in COST_FIELDS:
        amount = value[field]
        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise HarnessError(f"{label}.{field} must be a finite nonnegative number")
        projected[field] = amount
    return projected


def project_catalog(raw: bytes, label: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(decode_catalog(raw, label))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"models"}:
        raise HarnessError(f"{label} must contain only a models array")
    if not isinstance(document["models"], list):
        raise HarnessError(f"{label}.models must be an array")

    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, model in enumerate(document["models"]):
        entry_label = f"{label} entry {index}"
        if not isinstance(model, dict):
            raise HarnessError(f"{entry_label} must be an object")
        provider = model.get("provider")
        model_id = model.get("id")
        if not isinstance(provider, str) or not isinstance(model_id, str):
            raise HarnessError(f"{entry_label} has no provider/model identifier")
        identifier = catalog_model_id(model.get("selector"), entry_label)
        if identifier != f"{provider}/{model_id}":
            raise HarnessError(f"{entry_label} selector does not match provider and model")
        if identifier in seen:
            raise HarnessError(f"{label} repeats model {identifier}")
        seen.add(identifier)

        reasoning = model.get("reasoning")
        inputs = model.get("input")
        thinking = model.get("thinking")
        if not isinstance(reasoning, bool):
            raise HarnessError(f"{entry_label}.reasoning must be boolean")
        if (
            not isinstance(inputs, list)
            or not inputs
            or any(item not in {"text", "image"} for item in inputs)
            or len(inputs) != len(set(inputs))
        ):
            raise HarnessError(f"{entry_label}.input has unsupported capabilities")
        if thinking is None:
            thinking_levels: list[str] = []
        elif (
            not isinstance(thinking, list)
            or any(level not in THINKING_LEVELS for level in thinking)
            or len(thinking) != len(set(thinking))
        ):
            raise HarnessError(f"{entry_label}.thinking has unsupported levels")
        else:
            thinking_levels = thinking

        context = _optional_limit(model.get("contextWindow"), f"{entry_label}.contextWindow")
        output = _optional_limit(model.get("maxTokens"), f"{entry_label}.maxTokens")
        result: dict[str, Any] = {
            "id": identifier,
            "capabilities": {
                "reasoning": reasoning,
                "images": "image" in inputs,
            },
            "cost": _project_cost(model.get("cost"), f"{entry_label}.cost"),
        }
        if thinking_levels:
            result["options"] = {"thinking": {"values": thinking_levels}}
        limits = {
            key: value
            for key, value in (("context", context), ("output", output))
            if value is not None
        }
        if limits:
            result["limits"] = limits
        projected.append(result)
    if not projected:
        raise HarnessError(f"{label} is empty")
    return projected


ADAPTER = HarnessAdapter(
    kind="omp",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--thinking": ArgumentRule(choices(*THINKING_LEVELS)),
        "--tools": ArgumentRule(validate_tool_list),
        "--no-tools": ArgumentRule(),
        "--no-lsp": ArgumentRule(),
        "--no-pty": ArgumentRule(),
        "--no-session": ArgumentRule(),
        "--no-prewalk": ArgumentRule(),
        "--no-extensions": ArgumentRule(),
        "--no-skills": ArgumentRule(),
        "--no-rules": ArgumentRule(),
        "--approval-mode": ArgumentRule(choices("always-ask", "write")),
        "--add-dir": ArgumentRule(validate_absolute_directory, repeatable=True),
    },
    runtime_binding_renderer=render_runtime_binding,
    pane_environment_projector=no_extra_pane_environment,
    global_skill_roots_resolver=resolve_global_skill_roots,
    integration=IntegrationSpec(
        role="state_and_session",
        state_authority="lifecycle_without_documented_fallback",
        required_for_lifecycle=True,
    ),
    argument_set_validator=validate_argument_set,
    catalog=CatalogSpec(
        command=("models", "--json", "--no-extensions"),
        modes={"live": ()},
        projector=project_catalog,
    ),
    evidence_root=EvidenceRootRule(option="--add-dir"),
)
