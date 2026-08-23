#!/usr/bin/env python3
"""Render the maintainer coverage index from its scenario manifest."""

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
DEFAULT_OUTPUT = "references/orchestration-invariant-coverage.md"
VERIFICATION_MODES = {"automated/static", "live/manual"}
SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SELECTOR_RE = re.compile(
    r"(?P<module>tests(?:\.[a-zA-Z_]\w*)+)\."
    r"(?P<class>[A-Z]\w*)\.(?P<method>test_\w+)\Z"
)


class ManifestError(ValueError):
    """Raised when the coverage manifest cannot be trusted."""


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ManifestError(f"{label} has invalid fields ({'; '.join(details)})")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a nonempty string")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ManifestError(f"{label} must be an array")
    if not allow_empty and not value:
        raise ManifestError(f"{label} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ManifestError(f"{label} must contain only nonempty strings")
    if len(set(value)) != len(value):
        raise ManifestError(f"{label} contains duplicates")
    return value


def expected_legacy_ids(manifest: dict[str, Any]) -> tuple[str, ...]:
    legacy = manifest["legacy_ids"]
    prefix = legacy["prefix"]
    return tuple(
        f"{prefix}{number:02d}"
        for number in range(legacy["first"], legacy["last"] + 1)
    )


def _validate_source_path(root: Path, relative: str, label: str) -> None:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts):
        raise ManifestError(f"{label} must be a normalized repository-relative path")
    candidate = root.joinpath(*path.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ManifestError(f"{label} does not resolve inside the repository: {relative}") from exc
    if not resolved.is_file():
        raise ManifestError(f"{label} is not a file: {relative}")


def validate_test_selector(root: Path, selector: str) -> None:
    match = SELECTOR_RE.fullmatch(selector)
    if match is None:
        raise ManifestError(
            "test selector must be module.Class.test_method: " + selector
        )
    module_path = root.joinpath(*match.group("module").split(".")).with_suffix(".py")
    _validate_source_path(root, module_path.relative_to(root).as_posix(), "test selector module")
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ManifestError(f"cannot inspect test selector {selector}: {exc}") from exc

    class_name = match.group("class")
    method_name = match.group("method")
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == method_name
                for child in node.body
            ):
                return
            break
    raise ManifestError(f"test selector does not exist: {selector}")


def validate_manifest(manifest: Any, root: Path) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    _require_exact_keys(
        manifest,
        {"schema_version", "legacy_ids", "groups"},
        "manifest",
    )
    if manifest["schema_version"] != 1:
        raise ManifestError("schema_version must equal 1")

    legacy = manifest["legacy_ids"]
    if not isinstance(legacy, dict):
        raise ManifestError("legacy_ids must be an object")
    _require_exact_keys(legacy, {"prefix", "first", "last"}, "legacy_ids")
    if legacy["prefix"] != "FT-":
        raise ManifestError("legacy_ids.prefix must equal 'FT-'")
    first = legacy["first"]
    last = legacy["last"]
    if (
        isinstance(first, bool)
        or isinstance(last, bool)
        or not isinstance(first, int)
        or not isinstance(last, int)
        or first < 1
        or last < first
    ):
        raise ManifestError("legacy_ids requires positive ordered integer bounds")

    groups = manifest["groups"]
    if not isinstance(groups, list) or not groups:
        raise ManifestError("groups must be a nonempty array")

    seen_slugs: set[str] = set()
    seen_ids: list[str] = []
    for index, group in enumerate(groups):
        label = f"groups[{index}]"
        if not isinstance(group, dict):
            raise ManifestError(f"{label} must be an object")
        _require_exact_keys(
            group,
            {
                "slug",
                "title",
                "verification",
                "invariants",
                "sources",
                "scenario",
                "test_selectors",
            },
            label,
        )
        slug = _nonempty_string(group["slug"], f"{label}.slug")
        if SLUG_RE.fullmatch(slug) is None:
            raise ManifestError(f"{label}.slug must be lowercase kebab-case")
        if slug in seen_slugs:
            raise ManifestError(f"duplicate group slug: {slug}")
        seen_slugs.add(slug)
        _nonempty_string(group["title"], f"{label}.title")
        _nonempty_string(group["scenario"], f"{label}.scenario")

        mode = group["verification"]
        if mode not in VERIFICATION_MODES:
            raise ManifestError(
                f"{label}.verification must be one of {sorted(VERIFICATION_MODES)}"
            )
        invariants = group["invariants"]
        if not isinstance(invariants, list) or not invariants:
            raise ManifestError(f"{label}.invariants must be a nonempty array")
        ids: list[str] = []
        for invariant_index, invariant in enumerate(invariants):
            invariant_label = f"{label}.invariants[{invariant_index}]"
            if not isinstance(invariant, dict):
                raise ManifestError(f"{invariant_label} must be an object")
            _require_exact_keys(invariant, {"id", "spec"}, invariant_label)
            ids.append(_nonempty_string(invariant["id"], f"{invariant_label}.id"))
            _nonempty_string(invariant["spec"], f"{invariant_label}.spec")
        if len(set(ids)) != len(ids):
            raise ManifestError(f"{label}.invariants contains duplicate IDs")
        sources = _string_list(group["sources"], f"{label}.sources")
        selectors = _string_list(
            group["test_selectors"],
            f"{label}.test_selectors",
            allow_empty=True,
        )
        if mode == "automated/static" and not selectors:
            raise ManifestError(f"{label} automated/static coverage needs a test selector")
        if mode == "live/manual" and selectors:
            raise ManifestError(
                f"{label} live/manual coverage cannot imply automation with test selectors"
            )

        id_numbers: list[int] = []
        for legacy_id in ids:
            if legacy_id not in expected_legacy_ids(manifest):
                raise ManifestError(f"{label} has out-of-range legacy ID: {legacy_id}")
            id_numbers.append(int(legacy_id.removeprefix(legacy["prefix"])))
        if id_numbers != sorted(id_numbers):
            raise ManifestError(f"{label}.invariants must be numerically ordered")
        seen_ids.extend(ids)

        for source in sources:
            _validate_source_path(root, source, f"{label}.sources")
        for selector in selectors:
            validate_test_selector(root, selector)

    expected = set(expected_legacy_ids(manifest))
    actual = set(seen_ids)
    duplicate_ids = sorted({item for item in seen_ids if seen_ids.count(item) > 1})
    if duplicate_ids:
        raise ManifestError("legacy IDs appear more than once: " + ", ".join(duplicate_ids))
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        raise ManifestError("legacy coverage is incomplete (" + "; ".join(details) + ")")
    return manifest


def load_manifest(path: Path, root: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read coverage manifest {path}: {exc}") from exc
    return validate_manifest(raw, root)


def render_document(manifest: dict[str, Any]) -> str:
    lines = [
        "# Orchestration invariant coverage",
        "",
        "<!-- Generated by scripts/render_coverage.py from tests/orchestration-scenarios.json. -->",
        "",
        "This maintainer index groups the legacy scenarios without duplicating their",
        "runtime contracts. The JSON manifest is the source of truth for each group's",
        "per-ID scenario text, contract paths, and automated selectors. Read only the",
        "relevant group's manifest entries when auditing an individual invariant.",
        "The maintenance ownership map is `references/assignments-and-evidence.md`.",
        "",
        "## Verification meaning",
        "",
        "- **Automated/static** names deterministic repository tests. A selector is a",
        "  runnable check, not a stored passing result.",
        "- **Live/manual** names a planned harness scenario. This package stores no live",
        "  execution result and this document implies none.",
        "",
        "## Scenario groups",
    ]
    for group in manifest["groups"]:
        legacy = ", ".join(f"`{item['id']}`" for item in group["invariants"])
        lines.extend(
            [
                "",
                f"### {group['title']}",
                "",
                textwrap.fill(f"- Legacy: {legacy}", width=88, subsequent_indent="  "),
                f"- Verification: **{group['verification']}**",
                "",
                textwrap.fill(
                    group["scenario"],
                    width=88,
                    break_long_words=False,
                    break_on_hyphens=False,
                ),
            ]
        )
        if group["test_selectors"]:
            lines.extend(
                [
                    "",
                    textwrap.fill(
                        f"Automation: {len(group['test_selectors'])} validated "
                        "selector(s) in the manifest.",
                        width=88,
                    ),
                ]
            )

    lines.extend(
        [
            "",
            "## Maintenance gate",
            "",
            "Run `python3 scripts/render_coverage.py --check` to validate the manifest,",
            "source paths, selectors, complete unique legacy mapping, and generated-file",
            "freshness. Live confidence still requires separately recorded runs against",
            "each supported harness, model, and version.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path(DEFAULT_MANIFEST))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate inputs and fail if the generated document is stale",
    )
    return parser.parse_args(argv)


def _under_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    manifest_path = _under_root(root, args.manifest)
    output_path = _under_root(root, args.output)
    try:
        manifest = load_manifest(manifest_path, root)
        rendered = render_document(manifest)
    except ManifestError as exc:
        print(f"coverage error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        try:
            current = output_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"coverage error: cannot read generated document {output_path}: {exc}", file=sys.stderr)
            return 2
        if current != rendered:
            print(
                "coverage error: generated document is stale; "
                "run python3 scripts/render_coverage.py",
                file=sys.stderr,
            )
            return 1
        print("coverage manifest and generated document are current")
        return 0

    try:
        output_path.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"coverage error: cannot write generated document {output_path}: {exc}", file=sys.stderr)
        return 2
    try:
        displayed_output = output_path.relative_to(root)
    except ValueError:
        displayed_output = output_path
    print(f"rendered {displayed_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
