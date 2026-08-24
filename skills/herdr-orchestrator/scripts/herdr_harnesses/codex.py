"""Codex recipe and model-catalog adapter."""

from __future__ import annotations

import json
from typing import Any

from .base import (
    ArgumentRule,
    CatalogSpec,
    EvidenceRootRule,
    HarnessAdapter,
    HarnessError,
    catalog_model_id,
    choices,
    decode_catalog,
    validate_absolute_directory,
    validate_model,
)


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
    }
    if key not in allowed_values or configured not in allowed_values[key]:
        raise HarnessError(f"{location} uses an unsupported Codex configuration override")


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
)
