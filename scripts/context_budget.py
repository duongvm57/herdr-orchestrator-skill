#!/usr/bin/env python3
"""Measure bounded role and launcher instruction routes.

Prompt content is rendered by `herdr_orchestrator.py render-assignment`; this
development check measures only canonical static instruction sources and never
reintroduces a context-pack transport route.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MANIFEST = "tests/context-budgets.json"


class BudgetError(RuntimeError):
    pass


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
        result: list[str] = []
        if self.tokens > self.hard_limit:
            result.append(f"{self.name}: {self.tokens} tokens exceeds hard limit {self.hard_limit}")
        if self.tokens > self.drift_limit:
            result.append(f"{self.name}: {self.tokens} tokens exceeds 10% drift limit {self.drift_limit} from baseline {self.baseline}")
        return result


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BudgetError(f"cannot read budget manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("encoding"), str) or not value["encoding"]:
        raise BudgetError("budget manifest requires an encoding")
    routes = value.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise BudgetError("budget manifest requires a nonempty routes object")
    for name, route in routes.items():
        if not isinstance(name, str) or not name or not isinstance(route, dict):
            raise BudgetError("route names and values must be nonempty strings and objects")
        if set(route) != {"files", "hard_limit", "baseline"}:
            raise BudgetError(f"route {name!r} has unsupported or missing fields")
        files = route["files"]
        if not isinstance(files, list) or not files or any(not isinstance(item, str) or not item for item in files):
            raise BudgetError(f"route {name!r} requires a nonempty files array")
        for field in ("hard_limit", "baseline"):
            if isinstance(route[field], bool) or not isinstance(route[field], int) or route[field] <= 0:
                raise BudgetError(f"route {name!r} field {field!r} must be a positive integer")
    return value


def load_encoder(name: str) -> Any:
    try:
        import tiktoken  # type: ignore[import-not-found]
        return tiktoken.get_encoding(name)
    except Exception as exc:
        raise BudgetError(f"cannot load tokenizer {name!r}: {exc}") from exc


def render_route(root: Path, name: str, route: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    files = tuple(route["files"])
    content: list[str] = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            raise BudgetError(f"route {name!r} source is missing: {relative}")
        try:
            content.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise BudgetError(f"cannot read route source {relative}: {exc}") from exc
    return "\n".join(content), files


def measure_routes(root: Path, manifest: dict[str, Any], encoder: Any) -> list[RouteResult]:
    result = []
    for name, route in manifest["routes"].items():
        rendered, files = render_route(root, name, route)
        result.append(RouteResult(name, files, len(rendered.encode()), len(rendered.split()), len(encoder.encode(rendered)), route["hard_limit"], route["baseline"]))
    return result


def update_baselines(path: Path, manifest: dict[str, Any], results: Sequence[RouteResult]) -> None:
    for result in results:
        manifest["routes"][result.name]["baseline"] = result.tokens
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path(DEFAULT_MANIFEST))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_manifest(args.manifest)
    results = measure_routes(args.root.resolve(), manifest, load_encoder(manifest["encoding"]))
    print(f"{'route':24} {'tokens':>8} {'limit':>8} {'baseline':>9} {'bytes':>9}")
    for result in results:
        print(f"{result.name:24} {result.tokens:8d} {result.hard_limit:8d} {result.baseline:9d} {result.bytes:9d}")
    failures = [failure for result in results for failure in result.failures()]
    if failures:
        print("\n".join(failures), file=__import__("sys").stderr)
        return 1
    if args.update_baseline:
        update_baselines(args.manifest, manifest, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
