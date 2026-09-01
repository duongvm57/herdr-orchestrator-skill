"""Codex recipe and model-catalog adapter."""

from __future__ import annotations

import json
import shlex
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
    validate_absolute_directory,
    validate_model,
)


ROLE_ENVIRONMENT_FILTERS = frozenset({
    "HOME",
    "CODEX_HOME",
    "PATH",
    "SHELL",
    "USER",
    "LOGNAME",
    "PWD",
    "TERM",
    "TMPDIR",
    "LANG",
    '"LC_*"',
    "XDG_RUNTIME_DIR",
    '"HERDR_*"',
    '"HERDR_ORCHESTRATOR_*"',
})

ROLE_ENVIRONMENT_CONFIG = {
    "shell_environment_policy.inherit": '"all"',
    "shell_environment_policy.ignore_default_excludes": "false",
    "allow_login_shell": "false",
    **{
        f"shell_environment_policy.filters.{key}": '"include"'
        for key in ROLE_ENVIRONMENT_FILTERS
    },
}


def validate_config(value: str, location: str) -> None:
    if "=" not in value:
        raise HarnessError(f"{location} has an unsupported Codex configuration override")
    key, configured = value.split("=", 1)
    allowed_values = {
        "sandbox_workspace_write.network_access": {"true", "false"},
        "model_reasoning_effort": {
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
            '"low"',
            '"medium"',
            '"high"',
            '"xhigh"',
            '"max"',
            '"ultra"',
        },
        "service_tier": {"priority", '"priority"'},
        "agents.enabled": {"false"},
        "shell_environment_policy.inherit": {'"all"'},
        "shell_environment_policy.ignore_default_excludes": {"false"},
        "allow_login_shell": {"false"},
    }
    allowed_values.update({
        f"shell_environment_policy.filters.{key}": {'"include"'}
        for key in ROLE_ENVIRONMENT_FILTERS
    })
    if key not in allowed_values or configured not in allowed_values[key]:
        raise HarnessError(f"{location} uses an unsupported Codex configuration override")


def validate_role_environment(args: list[str], location: str) -> None:
    """Require Codex's observed native subprocess compatibility policy."""
    configured = {
        args[index + 1].split("=", 1)[0]: args[index + 1].split("=", 1)[1]
        for index in range(len(args) - 1)
        if args[index] == "--config" and "=" in args[index + 1]
    }
    missing = [
        f"{key}={value}"
        for key, value in ROLE_ENVIRONMENT_CONFIG.items()
        if configured.get(key) != value
    ]
    if missing:
        raise HarnessError(
            f"{location} Codex requires the explicit role subprocess environment policy: "
            + ", ".join(missing)
        )


def render_runtime_binding(binding: RuntimeBinding) -> str:
    """Render literal native commands because Codex subprocesses drop ambient role env."""
    if (binding.assignment_id is None) != (binding.owner is None):
        raise HarnessError("Codex runtime binding requires Assignment id and owner together")
    environment = (
        ("HERDR_ENV", "1"),
        ("HERDR_SOCKET_PATH", str(binding.herdr_socket_endpoint)),
        ("HERDR_PANE_ID", binding.herdr_pane_id),
        ("HERDR_ORCHESTRATOR_PANE_ID", binding.herdr_pane_id),
        ("HERDR_ORCHESTRATOR_PROJECT_ROOT", str(binding.project_root)),
        ("HERDR_ORCHESTRATOR_HELPER", str(binding.helper)),
        ("HERDR_ORCHESTRATOR_ROLE", binding.role),
        *(
            (("HERDR_ORCHESTRATOR_ASSIGNMENT_ID", binding.assignment_id),
             ("HERDR_ORCHESTRATOR_OWNER", binding.owner))
            if binding.assignment_id is not None and binding.owner is not None
            else ()
        ),
    )
    prefix = "env " + " ".join(
        f"{key}={shlex.quote(value)}" for key, value in environment
    )
    return "\n".join((
        "## Codex native runtime binding",
        "",
        "Codex tool subprocesses cannot rely on inherited role environment. "
        "For every native Herdr or helper operation, use the applicable literal "
        "command form below; never replace it with bare `herdr` or a bare helper path.",
        "",
        f"- Native Herdr: `{prefix} {shlex.quote(str(binding.herdr_executable))} <native-herdr-args...>`",
        f"- Canonical helper: `{prefix} python3 {shlex.quote(str(binding.helper))} <helper-command-and-args...>`",
        "",
        "These commands carry runtime facts only. They do not change the configured "
        "recipe, Assignment authority, role topology, or lifecycle ownership.",
    )) + "\n"


def resolve_global_skill_roots(
    environment: Mapping[str, str], home: Path,
) -> tuple[Path, ...]:
    configured = environment.get("CODEX_HOME")
    root = Path(configured).expanduser() if configured else home / ".codex"
    if not root.is_absolute():
        root = Path.cwd() / root
    return (home / ".agents" / "skills", root / "skills")


def project_pane_environment(
    binding: RuntimeBinding,
) -> tuple[tuple[str, str], ...]:
    """Preserve the user's normal Codex profile for every role process."""
    return ()


def project_catalog(raw: bytes, label: str) -> list[dict[str, Any]]:
    try:
        document = json.loads(decode_catalog(raw, label))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("models"), list):
        raise HarnessError(f"{label} must contain a models array")
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, model in enumerate(document["models"]):
        if not isinstance(model, dict):
            raise HarnessError(f"{label} entry {index} must be an object")
        identifier = catalog_model_id(model.get("slug"), f"{label} entry {index}")
        if identifier in seen:
            raise HarnessError(f"{label} repeats model {identifier}")
        seen.add(identifier)
        raw_levels = model.get("supported_reasoning_levels")
        if not isinstance(raw_levels, list):
            raise HarnessError(
                f"{label} model {identifier} supported_reasoning_levels is not an array"
            )
        levels: list[str] = []
        for level_index, level in enumerate(raw_levels):
            effort = level.get("effort") if isinstance(level, dict) else level
            if not isinstance(effort, str) or not effort:
                raise HarnessError(
                    f"{label} model {identifier} reasoning level {level_index} has no effort"
                )
            if effort in levels:
                raise HarnessError(
                    f"{label} model {identifier} repeats reasoning effort {effort}"
                )
            levels.append(effort)
        default = model.get("default_reasoning_level")
        if levels and (not isinstance(default, str) or default not in levels):
            raise HarnessError(
                f"{label} model {identifier} default reasoning level is missing or unsupported"
            )
        if not levels and default is not None:
            raise HarnessError(
                f"{label} model {identifier} has a default reasoning level but no supported levels"
            )
        raw_tiers = model.get("service_tiers", [])
        if not isinstance(raw_tiers, list):
            raise HarnessError(f"{label} model {identifier} service_tiers must be an array")
        tiers: list[str] = []
        for tier in raw_tiers:
            tier_id = tier.get("id") if isinstance(tier, dict) else tier
            if not isinstance(tier_id, str) or not tier_id:
                raise HarnessError(f"{label} model {identifier} has an invalid service tier")
            if tier_id not in tiers:
                tiers.append(tier_id)
        entry: dict[str, Any] = {"id": identifier}
        options: dict[str, Any] = {}
        if levels:
            options["reasoning_effort"] = {"default": default, "values": levels}
        if tiers:
            options["service_tier"] = {"values": tiers}
        if options:
            entry["options"] = options
        projected.append(entry)
    if not projected:
        raise HarnessError(f"{label} is empty")
    return projected


def validate_control_plane(args: list[str], location: str) -> None:
    sandbox = None
    configs: set[str] = set()
    index = 0
    while index < len(args):
        option = args[index]
        index += 1
        if option in {"--no-alt-screen", "--strict-config"}:
            continue
        if index >= len(args):
            break
        value = args[index]
        index += 1
        if option == "--sandbox":
            sandbox = value
        elif option == "--config":
            configs.add(value)
    if sandbox == "danger-full-access":
        return
    if (
        sandbox != "workspace-write"
        or "sandbox_workspace_write.network_access=true" not in configs
    ):
        raise HarnessError(
            f"{location} Codex requires --sandbox workspace-write with "
            "sandbox_workspace_write.network_access=true to reach the Herdr "
            "control socket"
        )


ADAPTER = HarnessAdapter(
    kind="codex",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--sandbox": ArgumentRule(
            choices("read-only", "workspace-write", "danger-full-access")
        ),
        "--ask-for-approval": ArgumentRule(choices("on-request", "never")),
        "--add-dir": ArgumentRule(validate_absolute_directory, repeatable=True),
        "--config": ArgumentRule(
            validate_config,
            repeatable=True,
            unique_value_key=True,
        ),
        "--no-alt-screen": ArgumentRule(),
        "--strict-config": ArgumentRule(),
    },
    catalog=CatalogSpec(
        command=("debug", "models"),
        modes={"live": (), "bundled": ("--bundled",)},
        projector=project_catalog,
    ),
    evidence_root=EvidenceRootRule(
        option="--add-dir",
        mode_option="--sandbox",
        restricted_modes=frozenset({"workspace-write"}),
    ),
    argument_set_validator=validate_role_environment,
    control_plane_validator=validate_control_plane,
    runtime_binding_renderer=render_runtime_binding,
    pane_environment_projector=project_pane_environment,
    global_skill_roots_resolver=resolve_global_skill_roots,
    integration=IntegrationSpec(
        role="session",
        state_authority="screen_manifest",
    ),
)
