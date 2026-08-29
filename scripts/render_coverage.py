#!/usr/bin/env python3
"""Render target-architecture invariant coverage from its scenario manifest."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import textwrap
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


DEFAULT_MANIFEST = "tests/orchestration-scenarios.json"
DEFAULT_OUTPUT = "maintenance/orchestration-invariant-coverage.md"
MODES = {"automated/static", "live/dogfood", "live/eval"}
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SELECTOR = re.compile(r"(tests(?:\.[A-Za-z_]\w*)+)\.([A-Z]\w*)\.(test_\w+)\Z")


class ManifestError(ValueError):
    pass


def _keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ManifestError(f"{label} has invalid fields")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a nonempty string")
    return value


def _source(root: Path, relative: str, label: str) -> None:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts):
        raise ManifestError(f"{label} must be a normalized repository-relative path")
    candidate = root.joinpath(*path.parts)
    try:
        candidate.resolve(strict=True).relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        raise ManifestError(f"{label} does not resolve inside the repository: {relative}") from exc
    if not candidate.is_file():
        raise ManifestError(f"{label} is not a file: {relative}")


def validate_test_selector(root: Path, selector: str) -> None:
    match = SELECTOR.fullmatch(selector)
    if match is None:
        raise ManifestError(f"test selector must be module.Class.test_method: {selector}")
    path = root.joinpath(*match.group(1).split(".")).with_suffix(".py")
    _source(root, path.relative_to(root).as_posix(), "test selector module")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == match.group(2):
            if any(isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == match.group(3) for child in node.body):
                return
    raise ManifestError(f"test selector does not exist: {selector}")


def validate_manifest(value: Any, root: Path) -> dict[str, Any]:
    manifest = _keys(value, {"schema_version", "source_root", "groups"}, "manifest")
    if manifest["schema_version"] != 2:
        raise ManifestError("schema_version must equal 2")
    source_root = _text(manifest["source_root"], "source_root")
    root_path = root / source_root
    if not root_path.is_dir():
        raise ManifestError("source_root must resolve to a directory")
    groups = manifest["groups"]
    if not isinstance(groups, list) or not groups:
        raise ManifestError("groups must be a nonempty array")
    names: set[str] = set()
    invariant_ids: set[str] = set()
    for index, group in enumerate(groups):
        group = _keys(group, {"slug", "title", "verification", "invariants", "sources", "scenario", "test_selectors"}, f"groups[{index}]")
        slug = _text(group["slug"], f"groups[{index}].slug")
        if SLUG.fullmatch(slug) is None or slug in names:
            raise ManifestError("group slug must be unique lowercase kebab-case")
        names.add(slug)
        _text(group["title"], f"groups[{index}].title")
        _text(group["scenario"], f"groups[{index}].scenario")
        if group["verification"] not in MODES:
            raise ManifestError("verification mode is invalid")
        if not isinstance(group["invariants"], list) or not group["invariants"]:
            raise ManifestError("group invariants must be nonempty")
        for invariant in group["invariants"]:
            invariant = _keys(invariant, {"id", "spec"}, "invariant")
            identifier = _text(invariant["id"], "invariant.id")
            if SLUG.fullmatch(identifier) is None or identifier in invariant_ids:
                raise ManifestError("invariant IDs must be unique lowercase kebab-case")
            invariant_ids.add(identifier)
            _text(invariant["spec"], "invariant.spec")
        if not isinstance(group["sources"], list) or not group["sources"]:
            raise ManifestError("group sources must be nonempty")
        if not isinstance(group["test_selectors"], list):
            raise ManifestError("group test_selectors must be an array")
        if group["verification"] == "automated/static" and not group["test_selectors"]:
            raise ManifestError("automated/static group needs selectors")
        if group["verification"] in {"live/dogfood", "live/eval"} and group["test_selectors"]:
            raise ManifestError("live evidence cannot imply static verification")
        for source in group["sources"]:
            _source(root_path, _text(source, "source"), "group source")
        for selector in group["test_selectors"]:
            validate_test_selector(root, _text(selector, "test selector"))
    return manifest


def load_manifest(path: Path, root: Path) -> dict[str, Any]:
    try:
        return validate_manifest(json.loads(path.read_text(encoding="utf-8")), root)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read coverage manifest {path}: {exc}") from exc


def render_document(manifest: dict[str, Any]) -> str:
    lines = ["# Orchestration invariant coverage", "", "<!-- Generated by scripts/render_coverage.py from tests/orchestration-scenarios.json. -->", "", "Evidence taxonomy: **automated/static** verifies deterministic contracts; **live/dogfood** is exploratory real-workflow discovery; **live/eval** is a repeatable real-agent evaluation with isolated setup, an explicit grader, repetitions, and machine-readable results. None of these labels implies another.", "", "Actionable live failures belong in the project issue tracker. Once reproducible, they become a scenario or live-eval regression case; checked-in Markdown is not a parallel failure ledger.", "", "## Scenario groups"]
    for group in manifest["groups"]:
        lines.extend(["", f"### {group['title']}", "", f"- Verification: **{group['verification']}**", f"- Invariants: {', '.join(f'`{item["id"]}`' for item in group['invariants'])}", "", textwrap.fill(group["scenario"], width=88, break_long_words=False)])
        if group["test_selectors"]:
            lines.append(f"\nAutomation: {len(group['test_selectors'])} validated selector(s).")
    lines.extend(["", "## Maintenance gate", "", "Run `python3 scripts/render_coverage.py --check` to validate source paths, selectors, target invariant coverage, and generated-file freshness. Run `python3 scripts/run_evals.py --suite tests/evals/orchestration-evals.json` for repeatable real-agent evidence; results are ephemeral under `.eval-results/`.", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(DEFAULT_MANIFEST))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(args.manifest, root)
    rendered = render_document(manifest)
    current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
    if args.check:
        if current != rendered:
            print(f"coverage document is stale: {args.output}", file=sys.stderr)
            return 1
        print("coverage manifest and generated document are current")
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    print(f"rendered {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
