"""Pi recipe and model-catalog adapter."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .base import (
    IDENTIFIER_RE,
    ArgumentRule,
    CatalogSpec,
    HarnessAdapter,
    HarnessError,
    IntegrationSpec,
    RuntimeBinding,
    catalog_model_id,
    choices,
    decode_catalog,
    no_extra_pane_environment,
    render_literal_runtime_binding,
    validate_identifier,
    validate_model,
    validate_tool_list,
)


LIMIT_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?[KMG]?\Z")
SCOPE_PATTERN_RE = re.compile(r"(?=.{1,256}\Z)[A-Za-z0-9~*?\[\]._/:+-]+\Z")
DATED_MODEL_RE = re.compile(r"-\d{8}\Z")
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
MAX_SETTINGS_BYTES = 1024 * 1024
MAX_SCOPE_PATTERNS = 512


def render_runtime_binding(binding: RuntimeBinding) -> str:
    return render_literal_runtime_binding(
        binding,
        "Pi",
        "Pi shell tools inherit the role process environment; the literal binding "
        "also pins the exact native endpoint and guarded-helper identity.",
    )


def resolve_global_skill_roots(
    environment: Mapping[str, str], home: Path,
) -> tuple[Path, ...]:
    configured = environment.get("PI_CODING_AGENT_DIR")
    root = Path(configured).expanduser() if configured else home / ".pi" / "agent"
    if not root.is_absolute():
        root = Path.cwd() / root
    return (home / ".agents" / "skills", root / "skills")


def _validate_scope_pattern(value: str, location: str) -> None:
    if SCOPE_PATTERN_RE.fullmatch(value) is None:
        raise HarnessError(f"{location} has an unsupported value")


def validate_model_scope(value: str, location: str) -> None:
    patterns = [item.strip() for item in value.split(",")]
    if not patterns or any(not item for item in patterns):
        raise HarnessError(f"{location} has an unsupported value")
    for index, pattern in enumerate(patterns):
        _validate_scope_pattern(pattern, f"{location} scope entry {index}")


def _read_settings(path: Path, label: str) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        if not path.is_file():
            raise HarnessError(f"{label} is not a regular file")
        raw = path.read_bytes()
    except OSError as exc:
        raise HarnessError(f"could not read {label}") from exc
    if len(raw) > MAX_SETTINGS_BYTES:
        raise HarnessError(f"{label} exceeds the bounded size limit")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise HarnessError(f"{label} must contain a JSON object")
    return parsed


def _agent_directory() -> Path:
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    path = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".pi" / "agent"
    )
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HarnessError("pi agent directory is invalid") from exc


def _effective_scope_patterns(project_root: Path) -> tuple[str, ...]:
    global_settings = _read_settings(
        _agent_directory() / "settings.json",
        "pi global settings",
    )
    project_settings = _read_settings(
        project_root / ".pi" / "settings.json",
        "pi project settings",
    )
    configured = (
        project_settings["enabledModels"]
        if "enabledModels" in project_settings
        else global_settings.get("enabledModels")
    )
    if not isinstance(configured, list) or not configured:
        raise HarnessError(
            "pi model scope is not configured; set a non-empty enabledModels list"
        )
    if len(configured) > MAX_SCOPE_PATTERNS:
        raise HarnessError("pi model scope exceeds the bounded entry limit")
    patterns: list[str] = []
    for index, pattern in enumerate(configured):
        if not isinstance(pattern, str):
            raise HarnessError(f"pi model scope entry {index} must be a string")
        _validate_scope_pattern(pattern, f"pi model scope entry {index}")
        patterns.append(pattern)
    return tuple(patterns)


def _model_parts(model: dict[str, Any]) -> tuple[str, str]:
    provider, separator, model_id = model["id"].partition("/")
    if not separator:  # project_catalog has already validated every Pi identifier
        raise HarnessError("pi model catalog contains an unscoped identifier")
    return provider, model_id


def _find_exact_model(
    reference: str,
    models: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized = reference.strip().lower()
    if not normalized:
        return None
    canonical = [model for model in models if model["id"].lower() == normalized]
    if len(canonical) == 1:
        return canonical[0]
    if canonical:
        return None
    bare = [
        model
        for model in models
        if _model_parts(model)[1].lower() == normalized
    ]
    return bare[0] if len(bare) == 1 else None


def _try_model_pattern(
    pattern: str,
    models: list[dict[str, Any]],
) -> dict[str, Any] | None:
    exact = _find_exact_model(pattern, models)
    if exact is not None:
        return exact
    normalized = pattern.lower()
    matches = [
        model
        for model in models
        if normalized in _model_parts(model)[1].lower()
    ]
    if not matches:
        return None
    aliases = [
        model
        for model in matches
        if DATED_MODEL_RE.search(_model_parts(model)[1]) is None
    ]
    candidates = aliases or matches
    return sorted(
        candidates,
        key=lambda model: _model_parts(model)[1].lower(),
        reverse=True,
    )[0]


def _glob_matches(value: str, pattern: str) -> bool:
    value_parts = value.lower().split("/")
    pattern_parts = pattern.lower().split("/")
    memo: dict[tuple[int, int], bool] = {}

    def match(value_index: int, pattern_index: int) -> bool:
        key = (value_index, pattern_index)
        if key in memo:
            return memo[key]
        if pattern_index == len(pattern_parts):
            result = value_index == len(value_parts)
        elif pattern_parts[pattern_index] == "**":
            result = match(value_index, pattern_index + 1) or (
                value_index < len(value_parts)
                and match(value_index + 1, pattern_index)
            )
        else:
            result = (
                value_index < len(value_parts)
                and fnmatch.fnmatchcase(
                    value_parts[value_index],
                    pattern_parts[pattern_index],
                )
                and match(value_index + 1, pattern_index + 1)
            )
        memo[key] = result
        return result

    return match(0, 0)


def _resolve_scope_entry(
    pattern: str,
    models: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    has_glob = any(marker in pattern for marker in "*?[")
    if not has_glob:
        direct = _try_model_pattern(pattern, models)
        if direct is not None:
            return [direct], None
    base, separator, suffix = pattern.rpartition(":")
    thinking = suffix if separator and suffix in THINKING_LEVELS else None
    candidate = base if thinking is not None else pattern
    if has_glob:
        exact = _find_exact_model(candidate, models)
        if exact is not None:
            return [exact], thinking
        return (
            [
                model
                for model in models
                if _glob_matches(model["id"], candidate)
                or _glob_matches(_model_parts(model)[1], candidate)
            ],
            thinking,
        )
    if thinking is not None:
        resolved = _try_model_pattern(candidate, models)
        return ([resolved] if resolved is not None else []), thinking
    return [], None


def select_model_scope(
    models: list[dict[str, Any]],
    project_root: Path,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, pattern in enumerate(_effective_scope_patterns(project_root)):
        matches, thinking = _resolve_scope_entry(pattern, models)
        if not matches:
            raise HarnessError(
                f"pi model scope entry {index} matches no available model"
            )
        for model in matches:
            identifier = model["id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            scoped = dict(model)
            if thinking is not None:
                scoped["scope"] = {"thinking": thinking}
            selected.append(scoped)
    if not selected:
        raise HarnessError("pi model scope resolves to no available models")
    return selected


def project_catalog(raw: bytes, label: str) -> list[dict[str, Any]]:
    text = decode_catalog(raw, label)
    in_table = False
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        columns = line.split()
        if columns[:2] == ["provider", "model"]:
            in_table = True
            continue
        if not in_table or len(columns) != 6:
            continue
        provider, model, context, output, thinking, images = columns
        if (
            IDENTIFIER_RE.fullmatch(provider) is None
            or LIMIT_RE.fullmatch(context) is None
            or LIMIT_RE.fullmatch(output) is None
            or {thinking, images} - {"yes", "no"}
        ):
            raise HarnessError(f"{label} contains an invalid model row")
        identifier = catalog_model_id(f"{provider}/{model}", f"{label} model")
        if identifier in seen:
            raise HarnessError(f"{label} repeats model {identifier}")
        seen.add(identifier)
        projected.append(
            {
                "id": identifier,
                "capabilities": {
                    "thinking": thinking == "yes",
                    "images": images == "yes",
                },
                "limits": {"context": context, "output": output},
            }
        )
    if not projected:
        raise HarnessError(f"{label} contains no model rows")
    return projected


ADAPTER = HarnessAdapter(
    kind="pi",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--models": ArgumentRule(validate_model_scope),
        "--provider": ArgumentRule(validate_identifier),
        "--thinking": ArgumentRule(
            choices("off", "minimal", "low", "medium", "high", "xhigh", "max")
        ),
        "--tools": ArgumentRule(validate_tool_list),
        "--exclude-tools": ArgumentRule(validate_tool_list),
        "--no-tools": ArgumentRule(),
        "--no-builtin-tools": ArgumentRule(),
        "--no-session": ArgumentRule(),
        "--no-skills": ArgumentRule(),
        "--no-prompt-templates": ArgumentRule(),
        "--no-themes": ArgumentRule(),
        "--no-context-files": ArgumentRule(),
        "--offline": ArgumentRule(),
        "--approve": ArgumentRule(),
        "--no-approve": ArgumentRule(),
        "--fast": ArgumentRule(),
        "--tui-mode": ArgumentRule(choices("regular", "fullscreen")),
    },
    runtime_binding_renderer=render_runtime_binding,
    pane_environment_projector=no_extra_pane_environment,
    global_skill_roots_resolver=resolve_global_skill_roots,
    integration=IntegrationSpec(
        role="state_and_session",
        state_authority="lifecycle_with_screen_fallback",
    ),
    catalog=CatalogSpec(
        command=("--list-models",),
        modes={"live": ()},
        projector=project_catalog,
        selector=select_model_scope,
    ),
)
