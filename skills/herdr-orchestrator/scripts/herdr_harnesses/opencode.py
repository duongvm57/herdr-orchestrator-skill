"""OpenCode recipe and model-catalog adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .base import (
    ArgumentRule,
    CatalogSpec,
    HarnessAdapter,
    HarnessError,
    IntegrationSpec,
    RuntimeBinding,
    catalog_model_id,
    decode_catalog,
    no_extra_pane_environment,
    render_literal_runtime_binding,
    validate_identifier,
    validate_model,
)


def render_runtime_binding(binding: RuntimeBinding) -> str:
    return render_literal_runtime_binding(
        binding,
        "OpenCode",
        "OpenCode uses its normal provider profile; the literal binding pins only "
        "Herdr and guarded-helper runtime facts.",
    )


def resolve_global_skill_roots(
    environment: Mapping[str, str], home: Path,
) -> tuple[Path, ...]:
    configured = environment.get("XDG_CONFIG_HOME")
    root = Path(configured).expanduser() if configured else home / ".config"
    if not root.is_absolute():
        root = Path.cwd() / root
    return (home / ".agents" / "skills", root / "opencode" / "skills")


def project_catalog(raw: bytes, label: str) -> list[dict[str, Any]]:
    text = decode_catalog(raw, label)
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        identifier = catalog_model_id(line.strip(), f"{label} line {index + 1}")
        if identifier in seen:
            raise HarnessError(f"{label} repeats model {identifier}")
        seen.add(identifier)
        projected.append({"id": identifier})
    if not projected:
        raise HarnessError(f"{label} is empty")
    return projected


ADAPTER = HarnessAdapter(
    kind="opencode",
    arguments={
        "--model": ArgumentRule(validate_model),
        "--agent": ArgumentRule(validate_identifier),
    },
    runtime_binding_renderer=render_runtime_binding,
    pane_environment_projector=no_extra_pane_environment,
    global_skill_roots_resolver=resolve_global_skill_roots,
    integration=IntegrationSpec(
        role="state_and_session",
        state_authority="lifecycle_with_screen_fallback",
    ),
    catalog=CatalogSpec(
        command=("models",),
        modes={"live": ()},
        projector=project_catalog,
    ),
)
