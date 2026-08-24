"""OpenCode recipe and model-catalog adapter."""

from __future__ import annotations

from typing import Any

from .base import (
    ArgumentRule,
    CatalogSpec,
    HarnessAdapter,
    HarnessError,
    catalog_model_id,
    decode_catalog,
    validate_identifier,
    validate_model,
)


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
    catalog=CatalogSpec(
        command=("models",),
        modes={"live": ()},
        projector=project_catalog,
    ),
)
