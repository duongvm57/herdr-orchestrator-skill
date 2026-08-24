"""Grok CLI recipe and model-catalog adapter."""

from __future__ import annotations

import re
from typing import Any

from .base import (
    ArgumentRule,
    CatalogSpec,
    HarnessAdapter,
    HarnessError,
    catalog_model_id,
    choices,
    decode_catalog,
    validate_identifier,
    validate_model,
)


def project_catalog(raw: bytes, label: str) -> list[dict[str, Any]]:
    text = decode_catalog(raw, label)
    default_match = re.search(r"(?m)^Default model:\s*(\S+)\s*$", text)
    default = (
        catalog_model_id(default_match.group(1), f"{label} default")
        if default_match is not None
        else None
    )
    available = False
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "Available models:":
            available = True
            continue
        if not available:
            continue
        match = re.fullmatch(r"\*\s+(\S+?)(?:\s+\(default\))?", stripped)
        if match is None:
            continue
        identifier = catalog_model_id(match.group(1), f"{label} model")
        if identifier in seen:
            raise HarnessError(f"{label} repeats model {identifier}")
        seen.add(identifier)
        entry: dict[str, Any] = {"id": identifier}
        if identifier == default or stripped.endswith("(default)"):
            entry["default"] = True
        projected.append(entry)
    if not projected:
        raise HarnessError(f"{label} contains no available models")
    if default is not None and default not in seen:
        raise HarnessError(f"{label} default model is absent from the available models")
    return projected


reasoning_effort = choices("off", "minimal", "low", "medium", "high", "xhigh", "max")

ADAPTER = HarnessAdapter(
    kind="grok",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--reasoning-effort": ArgumentRule(reasoning_effort),
        "--effort": ArgumentRule(reasoning_effort),
        "--permission-mode": ArgumentRule(
            choices(
                "default",
                "acceptEdits",
                "auto",
                "bypassPermissions",
                "dontAsk",
                "plan",
            )
        ),
        "--sandbox": ArgumentRule(validate_identifier),
        "--no-subagents": ArgumentRule(),
        "--disable-web-search": ArgumentRule(),
        "--no-alt-screen": ArgumentRule(),
        "--no-plan": ArgumentRule(),
    },
    catalog=CatalogSpec(
        command=("models",),
        modes={"live": ()},
        projector=project_catalog,
    ),
)
