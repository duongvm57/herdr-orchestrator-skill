"""Harness adapter registry for the standalone Herdr orchestration helper."""

from importlib import import_module

from .base import HarnessAdapter, HarnessError


VERIFIED_HARNESS_KINDS = (
    "pi",
    "claude",
    "codex",
    "opencode",
    "grok",
    "omp",
)
ADAPTERS: dict[str, HarnessAdapter] = {}
for module_name in VERIFIED_HARNESS_KINDS:
    adapter = import_module(f".{module_name}", __name__).ADAPTER
    if adapter.kind != module_name or module_name in ADAPTERS:  # pragma: no cover
        raise RuntimeError(f"invalid harness adapter module: {module_name}")
    ADAPTERS[module_name] = adapter

PACKAGED_FILES = (
    "__init__.py",
    "base.py",
    *(f"{kind}.py" for kind in VERIFIED_HARNESS_KINDS),
)


def get_adapter(kind: str) -> HarnessAdapter:
    try:
        return ADAPTERS[kind]
    except KeyError as exc:
        raise HarnessError(f"{kind} has no verified orchestrator adapter") from exc
