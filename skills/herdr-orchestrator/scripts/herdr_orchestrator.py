#!/usr/bin/env python3
"""Deterministic runtime operations for the Herdr Orchestrator skill.

The helper keeps large context payloads and raw harness output out of its own
stdout.  Successful commands emit one compact JSON metadata object; errors go
to stderr and leave no partially written destination file or run directory.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("error: herdr_orchestrator.py requires Python 3.11 or newer\n")
    raise SystemExit(2)

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import tomllib
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence


SCHEMA_VERSION = 1
PROJECT_CONFIG_VERSION = 2
SAFE_PROMPT_MAX_BYTES = 96 * 1024
DEFAULT_PROMPT_MAX_BYTES = SAFE_PROMPT_MAX_BYTES
DEFAULT_DELIVERY_TIMEOUT_SECONDS = 30.0
MAX_ENVELOPE_LINE_BYTES = 512
MAX_RECIPE_ARGUMENTS = 64
MAX_RECIPE_ARGUMENT_BYTES = 1024
DELIVERY_ENVELOPE_RESERVE_BYTES = (
    2 * MAX_ENVELOPE_LINE_BYTES
    + len("\n--- BEGIN SAVED CONTEXT sha256=".encode("utf-8"))
    + 64
    + len(" ---\n".encode("utf-8"))
    + len("\n--- END SAVED CONTEXT sha256=".encode("utf-8"))
    + 64
    + len(" ---\n".encode("utf-8"))
)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
ASSET_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
AGENT_NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
PLACEHOLDER_RE = re.compile(r"^\s*(?:todo|tbd|unknown|n/?a|yyyy-mm-dd)\s*$", re.I)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MODEL_ID_RE = re.compile(
    r"(?=.{1,128}\Z)[A-Za-z0-9][A-Za-z0-9._:+-]*"
    r"(?:/[A-Za-z0-9][A-Za-z0-9._:+-]*)*\Z"
)
SENSITIVE_LITERAL_RE = re.compile(
    r"(?i)(?:"
    r"\bsk-[a-z0-9][a-z0-9_-]{8,}\b"
    r"|\b(?:api[-_]?key|access[-_]?token|auth[-_]?token|password|secret|credential)\b"
    r"|\bbearer\s+"
    r"|(?:\$|%)[{A-Za-z_][^}\r\n]*"
    r"|@[A-Za-z0-9_./~-]+"
    r")"
)
HERDR_AGENT_KINDS = (
    "pi",
    "claude",
    "codex",
    "gemini",
    "cursor",
    "devin",
    "agy",
    "cline",
    "omp",
    "mastracode",
    "opencode",
    "copilot",
    "kimi",
    "kiro",
    "droid",
    "amp",
    "grok",
    "hermes",
    "kilo",
    "qodercli",
    "qwen",
    "maki",
)
COMMON_RECIPE_ARGUMENTS = {
    "--model": "model",
}
RECIPE_ARGUMENT_SCHEMAS: dict[str, dict[str, str]] = {
    kind: dict(COMMON_RECIPE_ARGUMENTS) for kind in HERDR_AGENT_KINDS
}
RECIPE_ARGUMENT_SCHEMAS["codex"].update(
    {
        "--sandbox": "codex-sandbox",
        "--ask-for-approval": "codex-approval",
        "--add-dir": "absolute-directory",
        "--config": "codex-config",
        "--no-alt-screen": "flag",
        "--strict-config": "flag",
    }
)
RECIPE_ARGUMENT_SCHEMAS["claude"].update(
    {
        "--effort": "effort",
        "--permission-mode": "claude-permission",
        "--add-dir": "absolute-directory",
        "--disallowedTools": "claude-spawn-tools",
        "--disallowed-tools": "claude-spawn-tools",
        "--disable-slash-commands": "flag",
        "--no-chrome": "flag",
        "--no-session-persistence": "flag",
        "--bare": "flag",
        "--ax-screen-reader": "flag",
    }
)
RECIPE_ARGUMENT_SCHEMAS["gemini"].update(
    {
        "--approval-mode": "gemini-approval",
        "--sandbox": "flag",
    }
)
REPEATABLE_RECIPE_ARGUMENTS = {
    ("codex", "--add-dir"),
    ("codex", "--config"),
    ("claude", "--add-dir"),
    ("claude", "--disallowedTools"),
    ("claude", "--disallowed-tools"),
}
LANGUAGE_FIELDS = (
    "Live orchestration language",
    "Durable Markdown artifact language",
)
PROTOCOL_LABELS: tuple[tuple[str, ...], ...] = (
    (
        "Owner",
        "Version",
        "Last reviewed",
        "Repository root",
        "Readers",
        "Live orchestration language",
        "Durable Markdown artifact language",
    ),
    (
        "Criticality",
        "Dominant risks",
        "Expensive-to-reverse decisions",
        "External side effects",
        "Model/cost budget",
    ),
    (
        "Lead may decide",
        "Human must decide",
        "Edit/commit/push/deploy/publish authority",
        "Scope-expansion boundary",
        "Architecture contracts reserved for Human review",
        "Prohibited without explicit Human authority",
    ),
    (
        "Tiny",
        "Bounded implementation",
        "Cross-module or lifecycle-sensitive",
        "Architecture lock-in",
        "Subjective/product evidence",
    ),
    (
        "Configured recipe capabilities and access constraints",
        "Selection by Assignment risk, independence, cost, and required access",
        "Recipe reuse or mixing across dynamically created Peers",
        "Missing capability, availability check, and no-fallback rule",
    ),
    (
        "Fresh Architect required when",
        "Fresh Reviewer required when",
        "Sealed council allowed when",
        "Same-Engineer correction rule",
    ),
    (
        "One writer per moving scope",
        "Worktree rules for concurrent writers",
        "Exclusive resources",
        "Handback and integration owner",
    ),
    (
        "Allowed identity forms (commit or deterministic base/diff/artifact digest)",
        "Candidate freeze and replacement rules",
    ),
    (
        "Checks by task class",
        "Independent falsification expectations",
        "Subjective/Human evidence",
        "Minimum evidence required for Lead verdict",
        "Residual risk reporting",
    ),
    (
        "`REOPEN_REQUEST` for failed foundations or premises",
        "`DEPENDENCY_REQUEST` for another owner, API, scope, or prerequisite",
        "`BLOCKED` for missing authority, external state, or Human decision",
    ),
    (
        "Signal, evidence, suspected mechanism, open question, allowed response",
        "Supervisor observation retention/export policy",
        "Supervisor project-read/notebook-write boundary",
        "Repeated-failure prerequisite check",
    ),
    (
        "Review trigger and date",
        "Human approval required for material authority changes",
        "Version-history practice",
        "Repeated evidence required before promoting a protocol candidate",
    ),
)


class HelperError(Exception):
    """A bounded, user-actionable command failure."""


@dataclass(frozen=True)
class Source:
    label: str
    path: Path
    data: bytes


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.buffer.write(_json_bytes(value))
    sys.stdout.buffer.flush()


def _require_file(path: Path, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"{label} is not a readable file: {path}: {exc}") from exc
    if not resolved.is_file():
        raise HelperError(f"{label} is not a regular file: {resolved}")
    return resolved


def _require_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"{label} is not a directory: {path}: {exc}") from exc
    if not resolved.is_dir():
        raise HelperError(f"{label} is not a directory: {resolved}")
    return resolved


def _read(path: Path, label: str) -> bytes:
    source = _require_file(path, label)
    try:
        return source.read_bytes()
    except OSError as exc:
        raise HelperError(f"could not read {label} {source}: {exc}") from exc


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HelperError(f"{label} must be UTF-8: byte {exc.start}") from exc


def _decode_safe_text(data: bytes, label: str) -> str:
    text = _decode_utf8(data, label)
    for index, character in enumerate(text):
        if unicodedata.category(character) == "Cc" and character not in "\t\r\n":
            raise HelperError(f"{label} contains a forbidden control character at index {index}")
    return text


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise HelperError(f"could not open output directory for fsync {path}: {exc}") from exc
    try:
        os.fsync(fd)
    except OSError as exc:
        raise HelperError(f"could not fsync output directory {path}: {exc}") from exc
    finally:
        os.close(fd)


def _check_output_path(path: Path, *, replace: bool = False) -> Path:
    expanded = path.expanduser()
    try:
        parent = expanded.parent.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"output parent is not a directory: {expanded.parent}: {exc}") from exc
    if not parent.is_dir():
        raise HelperError(f"output parent is not a directory: {parent}")
    target = parent / expanded.name
    if target.exists() and not replace:
        raise HelperError(f"output already exists: {target}")
    return target


def _atomic_write(path: Path, data: bytes, *, replace: bool = False, mode: int = 0o600) -> None:
    target = _check_output_path(path, replace=replace)
    temporary: Optional[Path] = None
    try:
        fd, raw_temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(raw_temporary)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise HelperError(f"output already exists: {target}") from exc
            temporary.unlink()
        temporary = None
        _fsync_directory(target.parent)
    except HelperError:
        raise
    except OSError as exc:
        raise HelperError(f"could not atomically write {target}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _write_staged(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    """Write inside a hidden staging directory before its atomic publication."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_tree_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(path)
    _fsync_directory(root)


def _is_populated(value: str) -> bool:
    return (
        bool(value.strip())
        and PLACEHOLDER_RE.fullmatch(value) is None
        and re.search(r"<[^>\r\n]+>", value) is None
    )


def _validate_absolute_directory_argument(value: str, location: str) -> None:
    path = Path(value)
    if not path.is_absolute():
        raise HelperError(f"{location} has an unsupported directory; canonical absolute path required")
    try:
        resolved = _require_directory(path, location)
    except HelperError as exc:
        raise HelperError(
            f"{location} has an unsupported directory; canonical absolute path required"
        ) from exc
    if resolved == Path(resolved.anchor) or value != str(resolved):
        raise HelperError(f"{location} has an unsupported directory; canonical absolute path required")


def _validate_codex_config_argument(value: str, location: str) -> None:
    if "=" not in value:
        raise HelperError(f"{location} has an unsupported Codex configuration override")
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
        raise HelperError(f"{location} uses an unsupported Codex configuration override")


def _validate_recipe_argument_value(schema: str, value: str, location: str) -> None:
    if schema == "model":
        valid = MODEL_ID_RE.fullmatch(value) is not None
    elif schema == "effort":
        valid = value in {"low", "medium", "high", "xhigh", "max"}
    elif schema == "codex-sandbox":
        valid = value in {"read-only", "workspace-write", "danger-full-access"}
    elif schema == "codex-approval":
        valid = value in {"on-request", "never"}
    elif schema == "claude-permission":
        valid = value in {
            "acceptEdits",
            "auto",
            "bypassPermissions",
            "manual",
            "dontAsk",
            "plan",
        }
    elif schema == "claude-spawn-tools":
        tools = [item for item in re.split(r"[\s,]+", value) if item]
        valid = bool(tools) and set(tools) <= {"Agent", "Task"}
    elif schema == "gemini-approval":
        valid = value in {"default", "auto_edit", "yolo", "plan"}
    elif schema == "absolute-directory":
        _validate_absolute_directory_argument(value, location)
        return
    elif schema == "codex-config":
        _validate_codex_config_argument(value, location)
        return
    else:  # pragma: no cover - package-owned schema programming error
        raise HelperError(f"{location} has an unknown package argument schema")
    if not valid:
        raise HelperError(f"{location} has an unsupported value")


def _validate_recipe_arguments(kind: str, args: list[str], location: str) -> None:
    schema = RECIPE_ARGUMENT_SCHEMAS.get(kind)
    if schema is None:
        raise HelperError(f"{location}.kind is not supported by the safe recipe schema")
    seen: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    seen_codex_config_keys: set[str] = set()
    index = 0
    while index < len(args):
        option = args[index]
        value_schema = schema.get(option)
        if value_schema is None:
            raise HelperError(f"{location}.args has an unsupported option at index {index}")
        if option in seen and (kind, option) not in REPEATABLE_RECIPE_ARGUMENTS:
            raise HelperError(f"{location}.args repeats a non-repeatable option")
        seen.add(option)
        index += 1
        if value_schema == "flag":
            continue
        if index >= len(args):
            raise HelperError(f"{location}.args option at index {index - 1} requires a value")
        _validate_recipe_argument_value(
            value_schema,
            args[index],
            f"{location}.args value at index {index}",
        )
        pair = (option, args[index])
        if pair in seen_pairs:
            raise HelperError(f"{location}.args repeats an option value")
        seen_pairs.add(pair)
        if value_schema == "codex-config":
            config_key = args[index].split("=", 1)[0]
            if config_key in seen_codex_config_keys:
                raise HelperError(f"{location}.args repeats a Codex configuration key")
            seen_codex_config_keys.add(config_key)
        index += 1


def _validate_recipe(
    value: Any,
    *,
    location: str,
    require_description: bool,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HelperError(f"{location} must be a TOML table")
    allowed = {"kind", "args"}
    if require_description:
        allowed.add("description")
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise HelperError(f"{location} has unsupported keys: {', '.join(sorted(unknown))}")
    if missing:
        raise HelperError(f"{location} is missing keys: {', '.join(sorted(missing))}")
    kind = value["kind"]
    args = value["args"]
    if not isinstance(kind, str) or not _is_populated(kind):
        raise HelperError(f"{location}.kind must be a non-placeholder string")
    if (
        not isinstance(args, list)
        or not args
        or len(args) > MAX_RECIPE_ARGUMENTS
        or any(not isinstance(arg, str) or not _is_populated(arg) for arg in args)
        or any(len(arg.encode("utf-8")) > MAX_RECIPE_ARGUMENT_BYTES for arg in args)
    ):
        raise HelperError(
            f"{location}.args must be a bounded nonempty array of non-placeholder strings"
        )
    if any(SENSITIVE_LITERAL_RE.search(arg) for arg in args):
        raise HelperError(f"{location}.args contains an unsupported sensitive literal")
    _validate_recipe_arguments(kind, args, location)
    result: dict[str, Any] = {"kind": kind, "args": args}
    if require_description:
        description = value["description"]
        if not isinstance(description, str) or not _is_populated(description):
            raise HelperError(f"{location}.description must be a non-placeholder string")
        result["description"] = description
    return result


def _parse_project_config(data: bytes, label: str) -> dict[str, Any]:
    text = _decode_safe_text(data, label)
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise HelperError(f"invalid project config TOML: {exc}") from exc
    if set(config) != {"version", "roles", "peer_recipes"}:
        unknown = set(config) - {"version", "roles", "peer_recipes"}
        missing = {"version", "roles", "peer_recipes"} - set(config)
        details: list[str] = []
        if unknown:
            details.append(f"unsupported keys: {', '.join(sorted(unknown))}")
        if missing:
            details.append(f"missing keys: {', '.join(sorted(missing))}")
        raise HelperError("invalid project config top level (" + "; ".join(details) + ")")
    if config["version"] != PROJECT_CONFIG_VERSION:
        raise HelperError(
            f"project config version must be {PROJECT_CONFIG_VERSION}, got {config['version']!r}"
        )
    roles = config["roles"]
    if not isinstance(roles, dict):
        raise HelperError("roles must be a TOML table")
    unknown_roles = set(roles) - {"lead", "supervisor"}
    if unknown_roles:
        raise HelperError(f"roles has unsupported keys: {', '.join(sorted(unknown_roles))}")
    if "lead" not in roles:
        raise HelperError("roles.lead is required")
    validated_roles = {
        "lead": _validate_recipe(roles["lead"], location="roles.lead", require_description=False)
    }
    if "supervisor" in roles:
        validated_roles["supervisor"] = _validate_recipe(
            roles["supervisor"],
            location="roles.supervisor",
            require_description=False,
        )
    peer_recipes = config["peer_recipes"]
    if not isinstance(peer_recipes, dict) or not peer_recipes:
        raise HelperError("peer_recipes must be a nonempty TOML table")
    validated_peers: dict[str, Any] = {}
    for name, recipe in peer_recipes.items():
        if not isinstance(name, str) or not _is_populated(name):
            raise HelperError("every peer_recipes key must be a non-placeholder string")
        validated_peers[name] = _validate_recipe(
            recipe,
            location=f"peer_recipes.{name}",
            require_description=True,
        )
    return {
        "version": PROJECT_CONFIG_VERSION,
        "roles": validated_roles,
        "peer_recipes": validated_peers,
    }


def _parse_protocol(data: bytes, label: str) -> dict[str, str]:
    text = _decode_safe_text(data, label)
    headings = list(re.finditer(r"(?m)^##\s+(\d+)\.[^\r\n]*$", text))
    sections = [int(match.group(1)) for match in headings]
    expected = list(range(1, 13))
    if sections != expected:
        raise HelperError(
            "workspace protocol numbered sections must appear exactly once in order 1 through 12"
        )
    expected_sections = {
        field: section_number
        for section_number, fields in enumerate(PROTOCOL_LABELS, 1)
        for field in fields
    }
    occurrences: dict[str, list[tuple[int, str]]] = {
        field: [] for field in expected_sections
    }
    for index, heading in enumerate(headings):
        section_number = int(heading.group(1))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():end]
        for line in body.splitlines():
            match = re.match(r"^[ \t]*-[ \t]+(.+?):[ \t]*(.*?)[ \t]*$", line)
            if match and match.group(1) in occurrences:
                occurrences[match.group(1)].append((section_number, match.group(2).strip()))

    values: dict[str, str] = {}
    for field, expected_section in expected_sections.items():
        found = occurrences[field]
        if not found:
            raise HelperError(
                f"workspace protocol section {expected_section} is missing required label {field}"
            )
        if len(found) != 1:
            raise HelperError(f"workspace protocol repeats required label {field}")
        actual_section, value = found[0]
        if actual_section != expected_section:
            raise HelperError(
                f"workspace protocol label {field} belongs in section {expected_section}, "
                f"not section {actual_section}"
            )
        if not _is_populated(value):
            raise HelperError(
                f"workspace protocol section {expected_section} requires a populated value for {field}"
            )
        values[field] = value
    return {
        field: values[field]
        for field in ("Repository root", *LANGUAGE_FIELDS)
    }


def _require_protocol_repository(
    protocol_values: dict[str, str],
    repository: Path,
) -> None:
    configured = protocol_values["Repository root"]
    configured_path = Path(configured)
    if not configured_path.is_absolute():
        raise HelperError("workspace protocol Repository root must be an absolute directory")
    resolved = _require_directory(configured_path, "workspace protocol Repository root")
    if configured != str(resolved):
        raise HelperError("workspace protocol Repository root must be canonical")
    if resolved != repository:
        raise HelperError("workspace protocol Repository root does not match the repository root")


def _require_expected_sha256(value: str, label: str) -> str:
    if SHA256_RE.fullmatch(value) is None:
        raise HelperError(f"{label} must be a lowercase SHA-256 digest")
    return value


def command_validate_project(args: argparse.Namespace) -> dict[str, Any]:
    root = _require_directory(Path(args.project_root), "project root")
    canonical_config = root / ".orchestration/herdr-orchestrator.toml"
    canonical_protocol = root / ".orchestration/workspace-protocol.md"
    config_path = Path(args.config) if args.config else canonical_config
    protocol_path = Path(args.protocol) if args.protocol else canonical_protocol
    if not config_path.is_absolute():
        config_path = root / config_path
    if not protocol_path.is_absolute():
        protocol_path = root / protocol_path
    config_path = _require_file(config_path, "project config")
    protocol_path = _require_file(protocol_path, "workspace protocol")
    if config_path != canonical_config or protocol_path != canonical_protocol:
        raise HelperError("project config and workspace protocol must use their canonical project paths")
    config_data = _read(config_path, "project config")
    protocol_data = _read(protocol_path, "workspace protocol")
    config = _parse_project_config(config_data, str(config_path))
    protocol_values = _parse_protocol(protocol_data, str(protocol_path))
    _require_protocol_repository(protocol_values, root)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "validate-project",
        "project_root": str(root),
        "config": {
            "path": str(config_path),
            "bytes": len(config_data),
            "sha256": _sha256(config_data),
            "version": config["version"],
        },
        "protocol": {
            "path": str(protocol_path),
            "bytes": len(protocol_data),
            "sha256": _sha256(protocol_data),
        },
        "languages": {
            "live": protocol_values[LANGUAGE_FIELDS[0]],
            "artifact": protocol_values[LANGUAGE_FIELDS[1]],
        },
        "recipes": {
            "lead": config["roles"]["lead"],
            "supervisor": config["roles"].get("supervisor"),
            "peers": [
                {"name": name, **recipe}
                for name, recipe in config["peer_recipes"].items()
            ],
        },
    }


def _parse_asset(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise HelperError(f"asset must use NAME=PATH: {raw}")
    name, path_text = raw.split("=", 1)
    if ASSET_NAME_RE.fullmatch(name) is None:
        raise HelperError(
            f"asset name must match {ASSET_NAME_RE.pattern!r} and contain no directory separator: {name}"
        )
    if not path_text:
        raise HelperError(f"asset path is empty for {name}")
    return name, _require_file(Path(path_text), f"asset {name}")


def _asset_entry(name: str, data: bytes) -> dict[str, Any]:
    return {
        "name": name,
        "path": (Path("context/cards/assets") / name).as_posix(),
        "bytes": len(data),
        "sha256": _sha256(data),
    }


def _remove_created_directories(paths: list[Path]) -> None:
    for path in reversed(paths):
        try:
            path.rmdir()
        except OSError:
            pass


def _validate_run_container(common: Path, base: Path, runs: Path, destination: Path) -> None:
    for path, label in ((base, "run base"), (runs, "runs path"), (destination, "run destination")):
        if path.is_symlink():
            raise HelperError(f"{label} must not be a symlink: {path}")
    if base.exists():
        if not base.is_dir():
            raise HelperError(f"run base is not a directory: {base}")
        if not base.resolve().is_relative_to(common):
            raise HelperError(f"run base escapes the Git common directory: {base}")
    if runs.exists():
        if not runs.is_dir():
            raise HelperError(f"runs path is not a directory: {runs}")
        if not runs.resolve().is_relative_to(common):
            raise HelperError(f"runs path escapes the Git common directory: {runs}")
    if destination.exists():
        raise HelperError(f"run already exists: {destination}")
    # RUN_ID_RE excludes separators and traversal, while these exact parents
    # make the intended publication path checkable before any staged write.
    if base.parent != common or runs.parent != base or destination.parent != runs:
        raise HelperError(f"run destination escapes the Git common directory: {destination}")


def command_init_run(args: argparse.Namespace) -> dict[str, Any]:
    common = _require_directory(Path(args.git_common_dir), "Git common directory")
    repository = _require_directory(Path(args.repository_root), "repository root")
    expected_config_sha256 = _require_expected_sha256(
        args.expected_project_config_sha256,
        "expected project config SHA-256",
    )
    expected_protocol_sha256 = _require_expected_sha256(
        args.expected_workspace_protocol_sha256,
        "expected workspace protocol SHA-256",
    )
    if RUN_ID_RE.fullmatch(args.run_id) is None:
        raise HelperError(
            f"run ID must match {RUN_ID_RE.pattern!r}: {args.run_id!r}"
        )
    task_path = _require_file(Path(args.human_task_file), "Human task file")
    before_path = _require_file(Path(args.before_state_file), "before-state file")
    project_config_path = _require_file(
        Path(args.project_config_file), "project config snapshot source"
    )
    workspace_protocol_path = _require_file(
        Path(args.workspace_protocol_file), "workspace protocol snapshot source"
    )
    canonical_config_path = repository / ".orchestration/herdr-orchestrator.toml"
    canonical_protocol_path = repository / ".orchestration/workspace-protocol.md"
    if (
        project_config_path != canonical_config_path
        or workspace_protocol_path != canonical_protocol_path
    ):
        raise HelperError(
            "project config and workspace protocol snapshot sources must use their canonical repository paths"
        )
    packaged_helper = Path(__file__).resolve().with_name("herdr_balanced_split.py")
    helper_path = _require_file(
        Path(args.layout_helper) if args.layout_helper else packaged_helper,
        "layout helper",
    )
    orchestration_helper_path = _require_file(Path(__file__), "orchestration helper")
    task_data = _read(task_path, "Human task file")
    if not task_data:
        raise HelperError("Human task file must not be empty")
    _decode_safe_text(task_data, "Human task file")
    before_data = _read(before_path, "before-state file")
    _decode_safe_text(before_data, "before-state file")
    project_config_data = _read(project_config_path, "project config snapshot source")
    workspace_protocol_data = _read(
        workspace_protocol_path, "workspace protocol snapshot source"
    )
    if _sha256(project_config_data) != expected_config_sha256:
        raise HelperError("project config changed after preflight validation")
    if _sha256(workspace_protocol_data) != expected_protocol_sha256:
        raise HelperError("workspace protocol changed after preflight validation")
    _parse_project_config(project_config_data, str(project_config_path))
    protocol_values = _parse_protocol(
        workspace_protocol_data,
        str(workspace_protocol_path),
    )
    _require_protocol_repository(protocol_values, repository)
    helper_data = _read(helper_path, "layout helper")
    orchestration_helper_data = _read(orchestration_helper_path, "orchestration helper")

    asset_sources: list[tuple[str, Path, bytes]] = []
    asset_names: set[str] = set()
    for raw in args.asset or []:
        name, source_path = _parse_asset(raw)
        if name in asset_names:
            raise HelperError(f"duplicate asset name: {name}")
        asset_names.add(name)
        data = _read(source_path, f"asset {name}")
        asset_sources.append((name, source_path, data))

    base = common / "herdr-orchestrator"
    runs = base / "runs"
    destination = runs / args.run_id
    _validate_run_container(common, base, runs, destination)

    staged = Path(tempfile.mkdtemp(prefix=".herdr-run-", dir=common))
    created_directories: list[Path] = []
    published = False
    try:
        for relative in (
            "context/cards/assets",
            "assignments",
            "reports/inbox",
            "supervisor",
            "tools",
        ):
            (staged / relative).mkdir(parents=True, exist_ok=True)
        _write_staged(staged / "human-task.md", task_data)
        _write_staged(staged / "before-state.txt", before_data)
        _write_staged(staged / "events.jsonl", b"")
        _write_staged(staged / "context/project-config.toml", project_config_data)
        _write_staged(
            staged / "context/workspace-protocol.md", workspace_protocol_data
        )
        _write_staged(staged / "context/cards/.stage-assets.lock", b"")
        _write_staged(staged / "tools/herdr_balanced_split.py", helper_data, mode=0o755)
        _write_staged(
            staged / "tools/herdr_orchestrator.py",
            orchestration_helper_data,
            mode=0o755,
        )

        asset_entries: list[dict[str, Any]] = []
        for name, source_path, data in asset_sources:
            relative = Path("context/cards/assets") / name
            _write_staged(staged / relative, data)
            asset_entries.append(_asset_entry(name, data))
        cards_manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": args.run_id,
            "assets": asset_entries,
        }
        _write_staged(staged / "context/cards/manifest.json", _json_bytes(cards_manifest))

        core_files = {
            "human_task": ("human-task.md", task_data),
            "before_state": ("before-state.txt", before_data),
            "project_config": ("context/project-config.toml", project_config_data),
            "workspace_protocol": (
                "context/workspace-protocol.md",
                workspace_protocol_data,
            ),
            "stage_assets_lock": ("context/cards/.stage-assets.lock", b""),
            "layout_helper": ("tools/herdr_balanced_split.py", helper_data),
            "orchestration_helper": (
                "tools/herdr_orchestrator.py",
                orchestration_helper_data,
            ),
        }
        run_manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": args.run_id,
            "repository_root": str(repository),
            "project_sources": {
                "project_config": str(project_config_path),
                "workspace_protocol": str(workspace_protocol_path),
            },
            "artifacts": {
                name: {"path": path, "bytes": len(data), "sha256": _sha256(data)}
                for name, (path, data) in core_files.items()
            },
        }
        _write_staged(staged / "run-manifest.json", _json_bytes(run_manifest))
        _fsync_tree_directories(staged)

        if not base.exists():
            base.mkdir()
            created_directories.append(base)
        elif base.is_symlink() or not base.is_dir():
            raise HelperError(f"run base is not a real directory: {base}")
        if not runs.exists():
            runs.mkdir()
            created_directories.append(runs)
        elif runs.is_symlink() or not runs.is_dir():
            raise HelperError(f"runs path is not a real directory: {runs}")
        if destination.exists():
            raise HelperError(f"run already exists: {destination}")
        os.rename(staged, destination)
        published = True
        _fsync_directory(runs)
        _fsync_directory(base)
        _fsync_directory(common)
    except HelperError:
        raise
    except OSError as exc:
        raise HelperError(f"could not atomically initialize run {destination}: {exc}") from exc
    finally:
        if not published:
            shutil.rmtree(staged, ignore_errors=True)
            _remove_created_directories(created_directories)

    manifest_data = _read(destination / "run-manifest.json", "published run manifest")
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "init-run",
        "run_id": args.run_id,
        "run_directory": str(destination),
        "manifest": {
            "path": str(destination / "run-manifest.json"),
            "bytes": len(manifest_data),
            "sha256": _sha256(manifest_data),
        },
        "asset_count": len(asset_entries),
    }


def _load_cards_manifest(path: Path) -> dict[str, Any]:
    raw = _read(path, "context-card manifest")
    try:
        manifest = json.loads(_decode_utf8(raw, "context-card manifest"))
    except json.JSONDecodeError as exc:
        raise HelperError(f"invalid context-card manifest JSON: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema_version", "run_id", "assets"}
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != SCHEMA_VERSION
        or not isinstance(manifest.get("run_id"), str)
        or RUN_ID_RE.fullmatch(manifest.get("run_id", "")) is None
        or not isinstance(manifest.get("assets"), list)
    ):
        raise HelperError("context-card manifest has an unsupported schema")
    names: set[str] = set()
    for index, entry in enumerate(manifest["assets"]):
        if not isinstance(entry, dict):
            raise HelperError(f"context-card manifest asset {index} must be an object")
        required = {"name", "path", "bytes", "sha256"}
        if set(entry) != required:
            raise HelperError(f"context-card manifest asset {index} has an unsupported schema")
        name = entry["name"]
        expected_path = (Path("context/cards/assets") / str(name)).as_posix()
        if (
            not isinstance(name, str)
            or ASSET_NAME_RE.fullmatch(name) is None
            or entry["path"] != expected_path
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 0
            or not isinstance(entry["sha256"], str)
            or SHA256_RE.fullmatch(entry["sha256"]) is None
        ):
            raise HelperError(f"context-card manifest asset {index} is invalid")
        if name in names:
            raise HelperError(f"context-card manifest repeats asset name: {name}")
        names.add(name)
    return manifest


def _load_run_manifest(path: Path) -> dict[str, Any]:
    raw = _read(path, "run manifest")
    try:
        manifest = json.loads(_decode_utf8(raw, "run manifest"))
    except json.JSONDecodeError as exc:
        raise HelperError(f"invalid run manifest JSON: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {
            "schema_version",
            "run_id",
            "repository_root",
            "project_sources",
            "artifacts",
        }
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != SCHEMA_VERSION
        or not isinstance(manifest.get("run_id"), str)
        or RUN_ID_RE.fullmatch(manifest.get("run_id", "")) is None
        or not isinstance(manifest.get("repository_root"), str)
        or not manifest.get("repository_root")
        or not isinstance(manifest.get("project_sources"), dict)
        or not isinstance(manifest.get("artifacts"), dict)
    ):
        raise HelperError("run manifest has an unsupported schema")
    repository = Path(manifest["repository_root"])
    expected_sources = {
        "project_config": str(repository / ".orchestration/herdr-orchestrator.toml"),
        "workspace_protocol": str(repository / ".orchestration/workspace-protocol.md"),
    }
    if manifest["project_sources"] != expected_sources:
        raise HelperError("run manifest project sources do not match its repository root")
    expected_artifacts = {
        "human_task": "human-task.md",
        "before_state": "before-state.txt",
        "project_config": "context/project-config.toml",
        "workspace_protocol": "context/workspace-protocol.md",
        "stage_assets_lock": "context/cards/.stage-assets.lock",
        "layout_helper": "tools/herdr_balanced_split.py",
        "orchestration_helper": "tools/herdr_orchestrator.py",
    }
    if set(manifest["artifacts"]) != set(expected_artifacts):
        raise HelperError("run manifest has an unsupported artifact set")
    for name, expected_path in expected_artifacts.items():
        artifact = manifest["artifacts"][name]
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"path", "bytes", "sha256"}
            or artifact.get("path") != expected_path
            or type(artifact.get("bytes")) is not int
            or artifact.get("bytes", -1) < 0
            or not isinstance(artifact.get("sha256"), str)
            or SHA256_RE.fullmatch(artifact.get("sha256", "")) is None
        ):
            raise HelperError(f"run manifest artifact is invalid: {name}")
    return manifest


def _require_run_child_directory(path: Path, run_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise HelperError(f"{label} must not be a symlink: {path}")
    resolved = _require_directory(path, label)
    if not resolved.is_relative_to(run_dir):
        raise HelperError(f"{label} escapes the run directory: {path}")
    return resolved


def _require_staged_asset(path: Path, assets_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise HelperError(f"{label} must not be a symlink: {path}")
    resolved = _require_file(path, label)
    if resolved.parent != assets_dir:
        raise HelperError(f"{label} escapes the context-card assets directory: {path}")
    return resolved


def _verify_run_artifacts(run_dir: Path, manifest: dict[str, Any]) -> None:
    repository_path = Path(manifest["repository_root"])
    if not repository_path.is_absolute():
        raise HelperError("run manifest repository_root must be absolute")
    repository = _require_directory(repository_path, "run manifest repository root")
    if str(repository) != manifest["repository_root"]:
        raise HelperError("run manifest repository_root must be canonical")
    for name, artifact in manifest["artifacts"].items():
        path = run_dir / artifact["path"]
        if path.is_symlink():
            raise HelperError(f"run artifact must not be a symlink: {name}")
        resolved = _require_file(path, f"run artifact {name}")
        if not resolved.is_relative_to(run_dir):
            raise HelperError(f"run artifact escapes the run directory: {name}")
        data = _read(resolved, f"run artifact {name}")
        if len(data) != artifact["bytes"] or _sha256(data) != artifact["sha256"]:
            raise HelperError(f"run artifact does not match its manifest: {name}")


@contextmanager
def _exclusive_stage_lock(path: Path):
    if path.is_symlink():
        raise HelperError(f"stage-assets lock must not be a symlink: {path}")
    lock_path = _require_file(path, "stage-assets lock")
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags)
    except OSError as exc:
        raise HelperError(f"could not open stage-assets lock: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise HelperError("stage-assets lock is not a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError as exc:
            raise HelperError(f"could not acquire stage-assets lock: {exc}") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _selection_output_path(raw: str, run_dir: Path, assets_dir: Path) -> Path:
    requested = Path(raw).expanduser()
    if not requested.is_absolute():
        requested = run_dir / requested
    try:
        parent = requested.parent.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"selection output parent is not a directory: {exc}") from exc
    target = parent / requested.name
    if not parent.is_dir() or not target.is_relative_to(run_dir):
        raise HelperError("selection output must stay inside the run directory")
    if parent == assets_dir:
        raise HelperError("selection output must not be placed in the card assets directory")
    if target.is_symlink():
        raise HelperError(f"selection output must not be a symlink: {target}")
    return target


def _stage_assets_locked(
    args: argparse.Namespace,
    run_dir: Path,
    cards_dir: Path,
) -> dict[str, Any]:
    run_manifest_path = run_dir / "run-manifest.json"
    if run_manifest_path.is_symlink():
        raise HelperError(f"run manifest must not be a symlink: {run_manifest_path}")
    run_manifest_path = _require_file(run_manifest_path, "run manifest")
    run_manifest = _load_run_manifest(run_manifest_path)
    _verify_run_artifacts(run_dir, run_manifest)
    assets_dir = _require_run_child_directory(
        cards_dir / "assets", run_dir, "context-card assets directory"
    )
    manifest_path = cards_dir / "manifest.json"
    if manifest_path.is_symlink():
        raise HelperError(f"context-card manifest must not be a symlink: {manifest_path}")
    manifest_path = _require_file(manifest_path, "context-card manifest")
    manifest = _load_cards_manifest(manifest_path)
    if run_manifest["run_id"] != manifest["run_id"] or manifest["run_id"] != run_dir.name:
        raise HelperError("run directory, run manifest, and context-card manifest IDs disagree")

    requested: list[tuple[str, Path, bytes]] = []
    requested_names: set[str] = set()
    for raw in args.asset:
        name, source_path = _parse_asset(raw)
        if name in requested_names:
            raise HelperError(f"duplicate asset name: {name}")
        requested_names.add(name)
        requested.append((name, source_path, _read(source_path, f"asset {name}")))

    existing = {entry["name"]: entry for entry in manifest["assets"]}
    for name, entry in existing.items():
        staged_path = _require_staged_asset(
            run_dir / entry["path"], assets_dir, f"staged asset {name}"
        )
        staged_data = _read(staged_path, f"staged asset {name}")
        if len(staged_data) != entry["bytes"] or _sha256(staged_data) != entry["sha256"]:
            raise HelperError(f"staged asset does not match its manifest: {name}")

    new_assets: list[tuple[Path, bytes]] = []
    new_entries: list[dict[str, Any]] = []
    selected_entries: list[dict[str, Any]] = []
    idempotent = 0
    recovered = 0
    for name, _source_path, data in requested:
        digest = _sha256(data)
        destination = assets_dir / name
        if name in existing:
            entry = existing[name]
            if digest != entry["sha256"] or len(data) != entry["bytes"]:
                raise HelperError(f"asset overwrite or digest mismatch is forbidden: {name}")
            idempotent += 1
            selected_entries.append(entry)
            continue
        if destination.is_symlink():
            raise HelperError(f"unmanifested staged asset must not be a symlink: {destination}")
        if destination.exists():
            orphan = _require_staged_asset(destination, assets_dir, f"unmanifested asset {name}")
            orphan_data = _read(orphan, f"unmanifested asset {name}")
            if orphan_data != data:
                raise HelperError(f"unmanifested staged asset has a digest mismatch: {name}")
            recovered += 1
        else:
            new_assets.append((destination, data))
        entry = _asset_entry(name, data)
        new_entries.append(entry)
        selected_entries.append(entry)

    updated = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "assets": sorted(
            [*manifest["assets"], *new_entries], key=lambda entry: entry["name"]
        ),
    }
    updated_data = _json_bytes(updated)
    selection_path: Optional[Path] = None
    selection_data: Optional[bytes] = None
    selection_exists = False
    if args.selection_output:
        selection_path = _selection_output_path(args.selection_output, run_dir, assets_dir)
        protected_paths = {
            run_dir / artifact["path"] for artifact in run_manifest["artifacts"].values()
        }
        protected_paths.update({manifest_path, run_manifest_path})
        if selection_path in protected_paths:
            raise HelperError("selection output conflicts with authoritative run evidence")
        selection = {
            "schema_version": SCHEMA_VERSION,
            "run_id": manifest["run_id"],
            "assets": sorted(selected_entries, key=lambda entry: entry["name"]),
        }
        selection_data = _json_bytes(selection)
        if selection_path.exists():
            if not selection_path.is_file():
                raise HelperError(f"selection output is not a regular file: {selection_path}")
            if _read(selection_path, "existing selection output") != selection_data:
                raise HelperError("existing selection output differs from the requested selection")
            selection_exists = True

    for destination, data in new_assets:
        _atomic_write(destination, data)
    if new_entries:
        _atomic_write(manifest_path, updated_data, replace=True)
    final_data = updated_data if new_entries else _read(manifest_path, "context-card manifest")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "stage-assets",
        "run_directory": str(run_dir),
        "added": len(new_entries),
        "idempotent": idempotent,
        "recovered": recovered,
        "asset_count": len(updated["assets"]),
        "manifest": {
            "path": str(manifest_path),
            "bytes": len(final_data),
            "sha256": _sha256(final_data),
        },
    }
    if selection_path is not None and selection_data is not None:
        if not selection_exists:
            _atomic_write(selection_path, selection_data)
        result["selection"] = {
            "path": str(selection_path),
            "bytes": len(selection_data),
            "sha256": _sha256(selection_data),
            "idempotent": selection_exists,
            "asset_count": len(selected_entries),
        }
    return result


def command_stage_assets(args: argparse.Namespace) -> dict[str, Any]:
    raw_run_dir = Path(args.run_dir).expanduser()
    if not raw_run_dir.is_absolute():
        raise HelperError("run directory must be absolute")
    if raw_run_dir.is_symlink():
        raise HelperError(f"run directory must not be a symlink: {raw_run_dir}")
    run_dir = _require_directory(raw_run_dir, "run directory")
    cards_dir = _require_run_child_directory(
        run_dir / "context/cards", run_dir, "context cards directory"
    )
    with _exclusive_stage_lock(cards_dir / ".stage-assets.lock"):
        return _stage_assets_locked(args, run_dir, cards_dir)


def _parse_source(raw: str, option: str) -> tuple[str, Path]:
    direct = Path(raw).expanduser()
    if direct.is_file():
        label, path = direct.name, _require_file(direct, option)
        _validate_source_label(label, option)
        return label, path
    if "=" not in raw:
        label, path = direct.name, _require_file(direct, option)
        _validate_source_label(label, option)
        return label, path
    label, path_text = raw.split("=", 1)
    _validate_source_label(label, option)
    if not path_text:
        raise HelperError(f"{option} path is empty")
    return label, _require_file(Path(path_text), option)


def _validate_source_label(label: str, option: str) -> None:
    if (
        not label
        or len(label) > 200
        or any(unicodedata.category(character) == "Cc" for character in label)
    ):
        raise HelperError(f"{option} label must be one nonempty line of at most 200 characters")


def _load_sources(values: list[str], option: str) -> list[Source]:
    sources: list[Source] = []
    for raw in values:
        label, path = _parse_source(raw, option)
        data = _read(path, option)
        _decode_safe_text(data, f"{option} {path}")
        sources.append(Source(label=label, path=path, data=data))
    return sources


def _render_layer(title: str, sources: list[Source]) -> bytes:
    pieces = [f"<!-- BEGIN HERDR LAYER: {title.upper()} -->\n\n## {title}\n\n".encode()]
    for index, source in enumerate(sources, 1):
        pieces.append(f"### Source {index}: {source.label}\n\n".encode("utf-8"))
        pieces.append(source.data)
        if not source.data.endswith(b"\n"):
            pieces.append(b"\n")
        pieces.append(b"\n")
    pieces.append(f"<!-- END HERDR LAYER: {title.upper()} -->\n".encode())
    return b"".join(pieces)


def _positive_limit(value: int, label: str) -> int:
    if value <= 0:
        raise HelperError(f"{label} must be greater than zero")
    return value


def _prompt_limit(value: int) -> int:
    maximum = _positive_limit(value, "max bytes")
    if maximum > SAFE_PROMPT_MAX_BYTES:
        raise HelperError(
            f"max bytes cannot exceed the safe single-argument ceiling of {SAFE_PROMPT_MAX_BYTES}"
        )
    return maximum


def command_pack(args: argparse.Namespace) -> dict[str, Any]:
    maximum = _prompt_limit(args.max_bytes)
    pack_ceiling = maximum - DELIVERY_ENVELOPE_RESERVE_BYTES
    if pack_ceiling <= 0:
        raise HelperError("max bytes leaves no room after reserving delivery-envelope framing")
    output = _check_output_path(Path(args.output), replace=False)
    layers = (
        ("Role Profile", _load_sources(args.role_source, "role source")),
        ("Workspace Protocol", _load_sources(args.protocol_source, "protocol source")),
        ("Assignment", _load_sources(args.assignment_source, "assignment source")),
    )
    all_sources = [source for _, sources in layers for source in sources]
    resolved_paths = [source.path for source in all_sources]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise HelperError("each context source path must appear exactly once across all layers")
    labels = [source.label for source in all_sources]
    if len(set(labels)) != len(labels):
        raise HelperError("each context source label must be unique")
    if output in resolved_paths:
        raise HelperError("pack output must not overwrite a context source")

    heading = f"# Herdr Context Pack\n\nRole: {args.role}\n\n".encode("utf-8")
    pack = heading + b"\n\n".join(_render_layer(title, sources) for title, sources in layers)
    if len(pack) > pack_ceiling:
        raise HelperError(
            f"context pack is {len(pack)} bytes, exceeding the {pack_ceiling}-byte "
            "ceiling after reserving delivery-envelope framing"
        )
    _atomic_write(output, pack)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "pack",
        "role": args.role,
        "path": str(output),
        "bytes": len(pack),
        "sha256": _sha256(pack),
        "max_bytes": maximum,
        "pack_ceiling_bytes": pack_ceiling,
        "reserved_delivery_bytes": DELIVERY_ENVELOPE_RESERVE_BYTES,
        "layers": [
            {
                "name": title,
                "source_count": len(sources),
                "sources": [
                    {
                        "label": source.label,
                        "path": str(source.path),
                        "bytes": len(source.data),
                        "sha256": _sha256(source.data),
                    }
                    for source in sources
                ],
            }
            for title, sources in layers
        ],
    }


def _validate_live_language(value: str) -> str:
    language = value.strip()
    if not _is_populated(language):
        raise HelperError("live language must be an explicit non-placeholder value")
    if len(language.encode("utf-8")) > 200 or any(
        unicodedata.category(character) == "Cc" for character in language
    ):
        raise HelperError("live language must be one safe line of at most 200 UTF-8 bytes")
    return language


def _validate_program(value: str, label: str) -> str:
    if not value or any(unicodedata.category(character) == "Cc" for character in value):
        raise HelperError(f"{label} must be one safe nonempty argument")
    return value


def _envelope_line(
    *,
    value: Optional[str],
    file_value: Optional[str],
    language: str,
    position: str,
) -> str:
    if value is not None and file_value is not None:
        raise HelperError(f"{position} envelope accepts either text or a file, not both")
    if file_value is not None:
        data = _read(Path(file_value), f"{position} envelope file")
        line = _decode_safe_text(data, f"{position} envelope file").strip()
    elif value is not None:
        line = value.strip()
    else:
        raise HelperError(f"{position} envelope is required")
    if not line or len(line.encode("utf-8")) > MAX_ENVELOPE_LINE_BYTES or any(
        unicodedata.category(character) == "Cc" for character in line
    ):
        raise HelperError(
            f"{position} envelope must be one safe nonempty line of at most "
            f"{MAX_ENVELOPE_LINE_BYTES} UTF-8 bytes"
        )
    if language.casefold() not in line.casefold():
        raise HelperError(
            f"{position} envelope must contain the exact live-language value {language!r}"
        )
    return line


def _delivery_payload(context: bytes, opening: str, closing: str) -> bytes:
    digest = _sha256(context)
    opening = (
        f"{opening}\n"
        f"--- BEGIN SAVED CONTEXT sha256={digest} ---\n"
    ).encode("utf-8")
    closing = (
        f"\n--- END SAVED CONTEXT sha256={digest} ---\n"
        f"{closing}"
    ).encode("utf-8")
    return opening + context + closing


def _new_receipt_path(raw: str) -> Path:
    requested = Path(raw).expanduser()
    try:
        parent = requested.parent.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"receipt parent is not a writable directory: {exc}") from exc
    target = parent / requested.name
    if os.path.lexists(target):
        raise HelperError(
            f"delivery receipt already exists and must be reconciled before any redelivery: {target}"
        )
    return target


def _restore_prepared_receipt(path: Path, prepared_data: bytes) -> None:
    try:
        current = _read(path, "delivery receipt") if path.is_file() else None
    except HelperError:
        current = None
    if current == prepared_data:
        return
    _atomic_write(path, prepared_data, replace=True)


def command_deliver(args: argparse.Namespace) -> dict[str, Any]:
    maximum = _prompt_limit(args.max_bytes)
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        raise HelperError("timeout seconds must be finite and greater than zero")
    if AGENT_NAME_RE.fullmatch(args.agent) is None:
        raise HelperError(f"agent name must match {AGENT_NAME_RE.pattern!r}: {args.agent!r}")
    herdr_program = _validate_program(args.herdr, "Herdr executable")
    context_path = _require_file(Path(args.context), "context pack")
    context = _read(context_path, "context pack")
    context_text = _decode_safe_text(context, "context pack")
    language = _validate_live_language(args.live_language)
    opening = _envelope_line(
        value=args.opening,
        file_value=args.opening_file,
        language=language,
        position="opening",
    )
    closing = _envelope_line(
        value=args.closing,
        file_value=args.closing_file,
        language=language,
        position="closing",
    )
    payload = _delivery_payload(context, opening, closing)
    if len(payload) > maximum:
        raise HelperError(
            f"delivery payload is {len(payload)} bytes, exceeding the {maximum}-byte ceiling"
        )
    receipt_path = _new_receipt_path(args.receipt)
    attempt_id = secrets.token_hex(16)
    prepared = {
        "schema_version": SCHEMA_VERSION,
        "state": "prepared",
        "attempt_id": attempt_id,
        "agent": args.agent,
        "context": {
            "path": str(context_path),
            "bytes": len(context),
            "sha256": _sha256(context),
        },
        "payload": {"bytes": len(payload), "sha256": _sha256(payload)},
        "envelope": {
            "opening_sha256": _sha256(opening.encode("utf-8")),
            "closing_sha256": _sha256(closing.encode("utf-8")),
            "live_language_sha256": _sha256(language.encode("utf-8")),
        },
        "transport": {
            "program": herdr_program,
            "argv_shape": ["agent", "prompt", "<agent>", "<payload>"],
        },
    }
    prepared_data = _json_bytes(prepared)
    _atomic_write(receipt_path, prepared_data)

    command = [herdr_program, "agent", "prompt", args.agent, payload.decode("utf-8")]
    try:
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HelperError(f"Herdr executable not found: {herdr_program}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HelperError(
            "Herdr prompt command timed out; delivery state is unknown and must be reconciled"
        ) from exc
    except OSError as exc:
        raise HelperError(f"could not execute Herdr prompt command: {exc}") from exc

    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if completed.returncode != 0:
        raise HelperError(
            "Herdr prompt failed with exit status "
            f"{completed.returncode} (stdout_sha256={_sha256(stdout)}, "
            f"stderr_sha256={_sha256(stderr)})"
        )
    receipt = {
        **prepared,
        "state": "accepted",
        "accepted": True,
        "transport": {
            **prepared["transport"],
            "returncode": completed.returncode,
            "stdout_bytes": len(stdout),
            "stdout_sha256": _sha256(stdout),
            "stderr_bytes": len(stderr),
            "stderr_sha256": _sha256(stderr),
        },
    }
    receipt_data = _json_bytes(receipt)
    try:
        _atomic_write(receipt_path, receipt_data, replace=True)
    except HelperError as exc:
        try:
            _restore_prepared_receipt(receipt_path, prepared_data)
        except HelperError as restore_exc:
            raise HelperError(
                "delivery was accepted but receipt finalization failed and receipt state is "
                f"uncertain; reconcile attempt {attempt_id}: {restore_exc}"
            ) from exc
        raise HelperError(
            f"delivery was accepted but receipt remains prepared; reconcile attempt {attempt_id}"
        ) from exc
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "deliver",
        **receipt,
        "receipt": {
            "path": str(receipt_path),
            "bytes": len(receipt_data),
            "sha256": _sha256(receipt_data),
        },
    }
    # context_text is deliberately kept local: it proves the exact argument was
    # UTF-8 without ever printing the prompt or captured subprocess output.
    del context_text
    return result


def _catalog_projection(raw: bytes, label: str) -> dict[str, Any]:
    text = _decode_utf8(raw, label)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HelperError(f"Codex model catalog is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("models"), list):
        raise HelperError("Codex model catalog must contain a models array")
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, model in enumerate(document["models"]):
        if not isinstance(model, dict):
            raise HelperError(f"Codex model catalog entry {index} must be an object")
        identifier = model.get("slug")
        if not isinstance(identifier, str) or not identifier:
            raise HelperError(f"Codex model catalog entry {index} has no slug")
        if identifier in seen:
            raise HelperError(f"Codex model catalog has duplicate slug: {identifier}")
        seen.add(identifier)
        raw_levels = model.get("supported_reasoning_levels")
        if not isinstance(raw_levels, list):
            raise HelperError(f"Codex model {identifier} supported_reasoning_levels is not an array")
        levels: list[str] = []
        for level_index, level in enumerate(raw_levels):
            effort = level.get("effort") if isinstance(level, dict) else level
            if not isinstance(effort, str) or not effort:
                raise HelperError(
                    f"Codex model {identifier} reasoning level {level_index} has no effort"
                )
            if effort in levels:
                raise HelperError(f"Codex model {identifier} repeats reasoning effort {effort}")
            levels.append(effort)
        default = model.get("default_reasoning_level")
        if levels and (not isinstance(default, str) or default not in levels):
            raise HelperError(
                f"Codex model {identifier} default reasoning level is missing or unsupported"
            )
        if not levels and default is not None:
            raise HelperError(
                f"Codex model {identifier} has a default reasoning level but no supported levels"
            )
        raw_tiers = model.get("service_tiers", [])
        if not isinstance(raw_tiers, list):
            raise HelperError(f"Codex model {identifier} service_tiers must be an array")
        tiers: list[str] = []
        for tier in raw_tiers:
            tier_id = tier.get("id") if isinstance(tier, dict) else tier
            if not isinstance(tier_id, str) or not tier_id:
                raise HelperError(f"Codex model {identifier} has an invalid service tier")
            if tier_id not in tiers:
                tiers.append(tier_id)
        projected.append(
            {
                "id": identifier,
                "default_reasoning_level": default,
                "reasoning_levels": levels,
                "service_tiers": tiers,
            }
        )
    if not projected:
        raise HelperError("Codex model catalog is empty")
    return {"schema_version": SCHEMA_VERSION, "models": projected}


def command_codex_models(args: argparse.Namespace) -> dict[str, Any]:
    output = _check_output_path(Path(args.output), replace=args.replace)
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        raise HelperError("timeout seconds must be finite and greater than zero")
    if args.catalog_file:
        if args.bundled:
            raise HelperError("--bundled cannot be combined with --catalog-file")
        catalog_path = _require_file(Path(args.catalog_file), "Codex model catalog file")
        if catalog_path == output:
            raise HelperError("Codex projection output must not overwrite its raw catalog source")
        raw = _read(catalog_path, "Codex model catalog file")
        source = {"kind": "file", "path": str(catalog_path), "sha256": _sha256(raw)}
    else:
        codex_program = _validate_program(args.codex, "Codex executable")
        command = [codex_program, "debug", "models"]
        if args.bundled:
            command.append("--bundled")
        try:
            completed = subprocess.run(
                command,
                shell=False,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise HelperError(f"Codex executable not found: {codex_program}") from exc
        except subprocess.TimeoutExpired as exc:
            raise HelperError("Codex model catalog command timed out") from exc
        except OSError as exc:
            raise HelperError(f"could not execute Codex model catalog command: {exc}") from exc
        stderr = completed.stderr or b""
        if completed.returncode != 0:
            raise HelperError(
                "Codex model catalog command failed with exit status "
                f"{completed.returncode} (stderr_sha256={_sha256(stderr)})"
            )
        raw = completed.stdout or b""
        source = {
            "kind": "command",
            "program": codex_program,
            "bundled": bool(args.bundled),
            "raw_bytes": len(raw),
            "raw_sha256": _sha256(raw),
            "stderr_bytes": len(stderr),
            "stderr_sha256": _sha256(stderr),
        }
    projection = _catalog_projection(raw, "Codex model catalog")
    projection_data = _json_bytes(projection)
    _atomic_write(output, projection_data, replace=args.replace)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "codex-models",
        "path": str(output),
        "bytes": len(projection_data),
        "sha256": _sha256(projection_data),
        "model_count": len(projection["models"]),
        "source": source,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Herdr projects, initialize run evidence, assemble bounded "
            "three-layer context packs, and deliver them without printing payloads."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-project",
        help="strictly validate version-2 project config and the 12-section protocol",
    )
    validate.add_argument("--project-root", required=True)
    validate.add_argument(
        "--config",
        help="config path; relative paths are resolved from project root",
    )
    validate.add_argument(
        "--protocol",
        help="protocol path; relative paths are resolved from project root",
    )
    validate.set_defaults(handler=command_validate_project)

    init_run = subparsers.add_parser(
        "init-run",
        help="atomically initialize a run and stage opaque context-card assets",
    )
    init_run.add_argument("--git-common-dir", required=True)
    init_run.add_argument("--run-id", required=True)
    init_run.add_argument("--repository-root", required=True)
    init_run.add_argument("--human-task-file", required=True)
    init_run.add_argument("--before-state-file", required=True)
    init_run.add_argument("--project-config-file", required=True)
    init_run.add_argument("--workspace-protocol-file", required=True)
    init_run.add_argument(
        "--expected-project-config-sha256",
        required=True,
        help="preflight validate-project digest for the canonical project config",
    )
    init_run.add_argument(
        "--expected-workspace-protocol-sha256",
        required=True,
        help="preflight validate-project digest for the canonical workspace protocol",
    )
    init_run.add_argument(
        "--layout-helper",
        help="layout helper to stage; defaults to the sibling packaged helper",
    )
    init_run.add_argument(
        "--asset",
        action="append",
        metavar="NAME=PATH",
        help="opaque card asset to stage byte-for-byte; repeat for more assets",
    )
    init_run.set_defaults(handler=command_init_run)

    stage_assets = subparsers.add_parser(
        "stage-assets",
        help="add immutable opaque assets to an existing run with digest verification",
    )
    stage_assets.add_argument("--run-dir", required=True, help="absolute initialized run directory")
    stage_assets.add_argument(
        "--asset",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="opaque card asset to add or verify idempotently; repeat for more assets",
    )
    stage_assets.add_argument(
        "--selection-output",
        help="write an immutable filtered manifest for only the requested assets inside the run",
    )
    stage_assets.set_defaults(handler=command_stage_assets)

    pack = subparsers.add_parser(
        "pack",
        help="atomically assemble Role Profile -> Workspace Protocol -> Assignment",
    )
    pack.add_argument("--role", choices=("lead", "peer", "supervisor"), required=True)
    pack.add_argument("--output", required=True)
    pack.add_argument(
        "--role-source",
        action="append",
        required=True,
        metavar="PATH_OR_LABEL=PATH",
        help="ordered Role Profile source; repeat to concatenate sources",
    )
    pack.add_argument(
        "--protocol-source",
        action="append",
        required=True,
        metavar="PATH_OR_LABEL=PATH",
        help="ordered Workspace Protocol source; repeat to concatenate sources",
    )
    pack.add_argument(
        "--assignment-source",
        action="append",
        required=True,
        metavar="PATH_OR_LABEL=PATH",
        help="ordered Assignment source; repeat to concatenate sources",
    )
    pack.add_argument("--max-bytes", type=int, default=DEFAULT_PROMPT_MAX_BYTES)
    pack.set_defaults(handler=command_pack)

    deliver = subparsers.add_parser(
        "deliver",
        help="deliver one saved context pack via a shell-free Herdr argument vector",
    )
    deliver.add_argument("--agent", required=True)
    deliver.add_argument("--context", required=True)
    deliver.add_argument("--live-language", required=True)
    opening_group = deliver.add_mutually_exclusive_group(required=True)
    opening_group.add_argument(
        "--opening",
        help="localized first envelope line; must contain the exact live-language value",
    )
    opening_group.add_argument(
        "--opening-file",
        help="UTF-8 file containing the localized first envelope line",
    )
    closing_group = deliver.add_mutually_exclusive_group(required=True)
    closing_group.add_argument(
        "--closing",
        help="localized final envelope line; must contain the exact live-language value",
    )
    closing_group.add_argument(
        "--closing-file",
        help="UTF-8 file containing the localized final envelope line",
    )
    deliver.add_argument("--herdr", default="herdr", help="Herdr executable or absolute path")
    deliver.add_argument("--receipt", required=True, help="new digest-only JSON receipt path")
    deliver.add_argument("--max-bytes", type=int, default=DEFAULT_PROMPT_MAX_BYTES)
    deliver.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    )
    deliver.set_defaults(handler=command_deliver)

    models = subparsers.add_parser(
        "codex-models",
        help="write a compact model/effort projection without printing the raw catalog",
    )
    models.add_argument("--output", required=True)
    catalog_source = models.add_mutually_exclusive_group()
    catalog_source.add_argument(
        "--codex", default="codex", help="Codex executable or absolute path"
    )
    catalog_source.add_argument(
        "--catalog-file", help="parse a captured raw catalog instead of executing Codex"
    )
    models.add_argument("--bundled", action="store_true", help="pass --bundled to codex debug models")
    models.add_argument("--replace", action="store_true", help="atomically replace output")
    models.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    )
    models.set_defaults(handler=command_codex_models)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except HelperError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
