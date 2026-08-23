#!/usr/bin/env python3
"""Measure and enforce context budgets declared by route.

The manifest is intentionally separate from the runtime helper: token counting is
a development check and must not add a dependency to installed skill execution.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MANIFEST = "tests/context-budgets.json"
PACK_LAYERS = (
    ("role_profile", "Role Profile"),
    ("workspace_protocol", "Workspace Protocol"),
    ("assignment", "Assignment"),
)


class BudgetError(RuntimeError):
    """Raised for an invalid manifest or a failed context budget."""


@dataclass(frozen=True)
class RouteResult:
    name: str
    files: tuple[str, ...]
    bytes: int
    words: int
    tokens: int
    hard_limit: int
    baseline: int

    @property
    def drift_limit(self) -> int:
        return math.floor(self.baseline * 1.10)

    def failures(self) -> list[str]:
        failures: list[str] = []
        if self.tokens > self.hard_limit:
            failures.append(
                f"{self.name}: {self.tokens} tokens exceeds hard limit "
                f"{self.hard_limit}"
            )
        if self.tokens > self.drift_limit:
            failures.append(
                f"{self.name}: {self.tokens} tokens exceeds 10% drift limit "
                f"{self.drift_limit} from baseline {self.baseline}"
            )
        return failures


def _positive_int(value: Any, field: str, route: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BudgetError(f"route {route!r} field {field!r} must be a positive integer")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BudgetError(f"cannot read budget manifest {path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise BudgetError("budget manifest root must be an object")
    if not isinstance(manifest.get("encoding"), str) or not manifest["encoding"]:
        raise BudgetError("budget manifest requires a nonempty encoding")
    routes = manifest.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise BudgetError("budget manifest requires a nonempty routes object")

    for name, route in routes.items():
        if not isinstance(name, str) or not name:
            raise BudgetError("route names must be nonempty strings")
        if not isinstance(route, dict):
            raise BudgetError(f"route {name!r} must be an object")
        render = route.get("render", "concat")
        if render == "concat":
            files = route.get("files")
            if (
                not isinstance(files, list)
                or not files
                or any(not isinstance(item, str) or not item for item in files)
            ):
                raise BudgetError(f"route {name!r} requires a nonempty files array")
        elif render == "pack":
            _validate_pack_route(name, route)
        else:
            raise BudgetError(
                f"route {name!r} field 'render' must be 'concat' or 'pack'"
            )
        _positive_int(route.get("hard_limit"), "hard_limit", name)
        _positive_int(route.get("baseline"), "baseline", name)
    return manifest


def _validate_pack_route(name: str, route: dict[str, Any]) -> None:
    role = route.get("role")
    if role not in {"lead", "peer", "supervisor"}:
        raise BudgetError(
            f"route {name!r} field 'role' must be 'lead', 'peer', or 'supervisor'"
        )
    layers = route.get("layers")
    expected_layers = {key for key, _ in PACK_LAYERS}
    if not isinstance(layers, dict) or set(layers) != expected_layers:
        raise BudgetError(
            f"route {name!r} field 'layers' must contain exactly "
            f"{', '.join(key for key, _ in PACK_LAYERS)}"
        )

    labels: set[str] = set()
    files: set[str] = set()
    for key, _ in PACK_LAYERS:
        sources = layers[key]
        if not isinstance(sources, list):
            raise BudgetError(f"route {name!r} layer {key!r} must be an array")
        for source in sources:
            if not isinstance(source, dict) or set(source) != {"label", "file"}:
                raise BudgetError(
                    f"route {name!r} layer {key!r} sources require only "
                    "nonempty 'label' and 'file' fields"
                )
            label = source["label"]
            relative = source["file"]
            if (
                not isinstance(label, str)
                or not label
                or len(label) > 200
                or any(ord(character) < 32 or ord(character) == 127 for character in label)
                or not isinstance(relative, str)
                or not relative
            ):
                raise BudgetError(
                    f"route {name!r} layer {key!r} sources require only "
                    "nonempty 'label' and 'file' fields"
                )
            if label in labels:
                raise BudgetError(f"route {name!r} repeats source label {label!r}")
            if relative in files:
                raise BudgetError(f"route {name!r} repeats source file {relative!r}")
            labels.add(label)
            files.add(relative)
    if not layers["role_profile"]:
        raise BudgetError(f"route {name!r} requires at least one Role Profile source")


def load_encoder(name: str) -> Any:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BudgetError(
            "tiktoken is required for context checks; install requirements-dev.txt"
        ) from exc
    try:
        return tiktoken.get_encoding(name)
    except Exception as exc:  # pragma: no cover - library-specific exceptions
        raise BudgetError(f"cannot load tokenizer {name!r}: {exc}") from exc


def _read_source(root: Path, route: str, relative: str) -> str:
    candidate = root / relative
    if not candidate.is_file():
        raise BudgetError(f"route {route!r} source is missing: {relative}")
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BudgetError(f"cannot read route source {relative}: {exc}") from exc


def _render_layer(title: str, sources: list[tuple[str, str]]) -> str:
    pieces = [f"<!-- BEGIN HERDR LAYER: {title.upper()} -->\n\n## {title}\n\n"]
    for index, (label, content) in enumerate(sources, 1):
        pieces.append(f"### Source {index}: {label}\n\n")
        pieces.append(content)
        if not content.endswith("\n"):
            pieces.append("\n")
        pieces.append("\n")
    pieces.append(f"<!-- END HERDR LAYER: {title.upper()} -->\n")
    return "".join(pieces)


def render_route(root: Path, name: str, route: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    if route.get("render", "concat") == "concat":
        files = tuple(route["files"])
        return "\n".join(_read_source(root, name, relative) for relative in files), files

    files: list[str] = []
    rendered_layers: list[str] = []
    for key, title in PACK_LAYERS:
        sources: list[tuple[str, str]] = []
        for source in route["layers"][key]:
            relative = source["file"]
            files.append(relative)
            sources.append((source["label"], _read_source(root, name, relative)))
        rendered_layers.append(_render_layer(title, sources))
    heading = f"# Herdr Context Pack\n\nRole: {route['role']}\n\n"
    return heading + "\n\n".join(rendered_layers), tuple(files)


def measure_routes(root: Path, manifest: dict[str, Any], encoder: Any) -> list[RouteResult]:
    results: list[RouteResult] = []
    for name, route in manifest["routes"].items():
        combined, files = render_route(root, name, route)
        results.append(
            RouteResult(
                name=name,
                files=files,
                bytes=len(combined.encode("utf-8")),
                words=len(combined.split()),
                tokens=len(encoder.encode(combined)),
                hard_limit=route["hard_limit"],
                baseline=route["baseline"],
            )
        )
    return results


def render_table(results: Sequence[RouteResult]) -> str:
    header = f"{'route':24} {'tokens':>8} {'limit':>8} {'baseline':>9} {'bytes':>9}"
    rows = [header]
    for result in results:
        rows.append(
            f"{result.name:24} {result.tokens:8d} {result.hard_limit:8d} "
            f"{result.baseline:9d} {result.bytes:9d}"
        )
    return "\n".join(rows)


def update_baselines(path: Path, manifest: dict[str, Any], results: Sequence[RouteResult]) -> None:
    for result in results:
        manifest["routes"][result.name]["baseline"] = result.tokens
    rendered = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    path.write_text(rendered, encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path(DEFAULT_MANIFEST))
    parser.add_argument("--check", action="store_true", help="fail when a route exceeds its limits")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="write current counts as baselines after all hard limits pass",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    try:
        manifest = load_manifest(manifest_path)
        encoder = load_encoder(manifest["encoding"])
        results = measure_routes(root, manifest, encoder)
        hard_failures = [
            f"{result.name}: {result.tokens} tokens exceeds hard limit {result.hard_limit}"
            for result in results
            if result.tokens > result.hard_limit
        ]
        if args.update_baseline:
            if hard_failures:
                raise BudgetError("; ".join(hard_failures))
            update_baselines(manifest_path, manifest, results)
            results = [replace(result, baseline=result.tokens) for result in results]
        failures = [failure for result in results for failure in result.failures()]
    except BudgetError as exc:
        print(f"context-budget error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "route": result.name,
                        "files": result.files,
                        "bytes": result.bytes,
                        "words": result.words,
                        "tokens": result.tokens,
                        "hard_limit": result.hard_limit,
                        "baseline": result.baseline,
                        "drift_limit": result.drift_limit,
                    }
                    for result in results
                ],
                indent=2,
            )
        )
    else:
        print(render_table(results))

    if args.check and failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
