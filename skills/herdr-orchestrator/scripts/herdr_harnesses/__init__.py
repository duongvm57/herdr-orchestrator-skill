"""Harness adapter registry for the standalone Herdr orchestration helper."""

from importlib import import_module

from .base import HarnessAdapter, HarnessError, IntegrationSpec, RuntimeBinding


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
    if (
        not callable(adapter.runtime_binding_renderer)
        or not callable(adapter.pane_environment_projector)
        or not callable(adapter.global_skill_roots_resolver)
    ):  # pragma: no cover
        raise RuntimeError(
            f"verified harness adapter lacks an end-to-end capability: {module_name}"
        )
    if (
        adapter.integration.role not in {"session", "state_and_session"}
        or adapter.integration.state_authority not in {
            "screen_manifest",
            "lifecycle_with_screen_fallback",
            "lifecycle_without_documented_fallback",
        }
    ):  # pragma: no cover
        raise RuntimeError(f"invalid integration capability: {module_name}")
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
