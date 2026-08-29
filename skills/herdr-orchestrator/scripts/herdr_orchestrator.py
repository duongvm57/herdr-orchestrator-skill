#!/usr/bin/env python3
"""Validate Herdr project policy and render SLP contracts.

This helper has no pane, session, wait, or lifecycle control. Its only Herdr
calls are recipe-bound Peer start and one-shot prompt submission: each passes a
bounded direct argv to Herdr. All other mechanics belong to installed Herdr
and its release-matched Agent Skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence


if sys.version_info < (3, 11):
    sys.stderr.write("error: herdr_orchestrator.py requires Python 3.11 or newer\n")
    raise SystemExit(2)

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from herdr_harnesses import (
    ADAPTERS,
    VERIFIED_HARNESS_KINDS,
    HarnessError,
    RuntimeBinding,
    get_adapter,
)


SCHEMA_VERSION = 1
PROJECT_CONFIG_VERSION = 3
ASSIGNMENT_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 1
MAX_RECIPE_ARGUMENTS = 64
MAX_RECIPE_ARGUMENT_BYTES = 1024
MAX_NATIVE_DIAGNOSTIC_BYTES = 4096
PLACEHOLDER_RE = re.compile(r"^\s*(?:todo|tbd|unknown|n/?a|yyyy-mm-dd)\s*$", re.I)
SENSITIVE_LITERAL_RE = re.compile(
    r"(?i)(?:\bsk-[a-z0-9][a-z0-9_-]{8,}\b|\b(?:api[-_]?key|access[-_]?token|"
    r"password|secret|credential)\b|\bbearer\s+|(?:\$|%)[{A-Za-z_][^}\r\n]*|@[A-Za-z0-9_./~-]+)"
)
ASSIGNMENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
RUNTIME_HANDLE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SEMANTIC_OUTCOMES = frozenset({"COMPLETE", "REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED"})
CANDIDATE_EXCLUDED_PREFIXES = (
    ".orchestration",
    ".codex",
    ".claude",
    ".agents",
    ".cursor",
    "skills-lock.json",
)
MAX_CANDIDATE_DIFF_BYTES = 16 * 1024 * 1024
LANGUAGE_FIELDS = ("Live orchestration language", "Durable Markdown artifact language")
PROTOCOL_LABELS: tuple[tuple[str, ...], ...] = (
    ("Owner", "Version", "Last reviewed", "Repository root", "Readers", *LANGUAGE_FIELDS),
    ("Criticality", "Dominant risks", "Expensive-to-reverse decisions", "External side effects", "Model/cost budget"),
    ("Lead may decide", "Human must decide", "Edit/commit/push/deploy/publish authority", "Scope-expansion boundary", "Architecture contracts reserved for Human review", "Prohibited without explicit Human authority"),
    ("Tiny", "Bounded implementation", "Cross-module or lifecycle-sensitive", "Architecture lock-in", "Subjective/product evidence"),
    ("Configured recipe capabilities and access constraints", "Selection by Assignment risk, independence, cost, and required access", "Recipe reuse or mixing across dynamically created Peers", "Specialized miss, configured fallback recipe, and out-of-envelope escalation"),
    ("Fresh Architect required when", "Fresh Reviewer required when", "Sealed council allowed when", "Same-Engineer correction rule"),
    ("One writer per moving scope", "Worktree rules for concurrent writers", "Exclusive resources", "Handback and integration owner"),
    ("Allowed identity forms (Git commit or Git tree with exact base commit)", "Candidate freeze and replacement rules"),
    ("Checks by task class", "Independent falsification expectations", "Subjective/Human evidence", "Minimum evidence required for Lead verdict", "Residual risk reporting"),
    ("`REOPEN_REQUEST` for failed foundations or premises", "`DEPENDENCY_REQUEST` for another owner, API, scope, or prerequisite", "`BLOCKED` for missing authority, external state, or Human decision"),
    ("Signal, evidence, suspected mechanism, open question, allowed response", "Supervisor observation retention/export policy", "Supervisor project-read/notebook-write boundary", "Repeated-failure prerequisite check"),
    ("Review trigger and date", "Human approval required for material authority changes", "Version-history practice", "Repeated evidence required before promoting a protocol candidate"),
)


class HelperError(Exception):
    """A bounded, user-actionable validation failure."""


@dataclass(frozen=True)
class Assignment:
    assignment_id: str
    role: str
    parent: dict[str, str]
    owner: str
    objective: str
    owned_scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    authority: str
    disposition: str
    recipe: str
    verification: tuple[str, ...]
    dependencies: tuple[str, ...]
    languages: dict[str, str]
    topology_rationale: str | None
    candidate: dict[str, str] | None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode())


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
    try:
        return _require_file(path, label).read_bytes()
    except OSError as exc:
        raise HelperError(f"could not read {label}: {exc}") from exc


def _safe_text(data: bytes, label: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HelperError(f"{label} must be UTF-8: byte {exc.start}") from exc
    if any(unicodedata.category(char) == "Cc" and char not in "\t\r\n" for char in text):
        raise HelperError(f"{label} contains a forbidden control character")
    return text


def _safe_diagnostic_text(data: bytes, label: str) -> str:
    """Return bounded native diagnostics without changing command semantics.

    Native side-effect success is authoritative.  Diagnostics are best-effort
    reporting only, so malformed output must never turn that success into an
    ambiguous helper failure.
    """
    try:
        raw = bytes(data)
        text = raw[:MAX_NATIVE_DIAGNOSTIC_BYTES].decode("utf-8", errors="replace")
        sanitized = "".join(
            char if unicodedata.category(char) != "Cc" or char in "\t\r\n"
            else f"\\x{ord(char):02x}"
            for char in text
        )
        if len(raw) > MAX_NATIVE_DIAGNOSTIC_BYTES:
            sanitized += "\n[truncated native diagnostic]"
        return sanitized
    except Exception:
        # `subprocess.run(..., capture_output=True)` supplies bytes, but retain
        # the reporting-only boundary even if an unexpected object reaches it.
        return f"[{label} diagnostic unavailable]"


def _check_output(path: Path, replace: bool) -> Path:
    parent = _require_directory(path.expanduser().parent, "output parent")
    target = parent / path.name
    if target.exists() and not replace:
        raise HelperError(f"output already exists: {target}")
    return target


def _atomic_write(path: Path, data: bytes, replace: bool = False) -> None:
    target = _check_output(path, replace)
    temporary: Path | None = None
    try:
        fd, raw = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(raw)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            os.link(temporary, target, follow_symlinks=False)
            temporary.unlink()
        temporary = None
    except FileExistsError as exc:
        raise HelperError(f"output already exists: {target}") from exc
    except OSError as exc:
        raise HelperError(f"could not write {target}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _populated(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or PLACEHOLDER_RE.fullmatch(value) or re.search(r"<[^>\r\n]+>", value):
        raise HelperError(f"{label} must be a non-placeholder string")
    return value


def _validate_recipe(value: Any, location: str, description: bool, control_plane: bool = False) -> dict[str, Any]:
    required = {"kind", "args"} | ({"description"} if description else set())
    allowed = required | {"approval_required"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - allowed:
        raise HelperError(f"{location} must contain required fields: {', '.join(sorted(required))}")
    kind = _populated(value["kind"], f"{location}.kind")
    args = value["args"]
    if not isinstance(args, list) or not args or len(args) > MAX_RECIPE_ARGUMENTS:
        raise HelperError(f"{location}.args must be a bounded nonempty array")
    if any(not isinstance(arg, str) or not arg or len(arg.encode()) > MAX_RECIPE_ARGUMENT_BYTES or SENSITIVE_LITERAL_RE.search(arg) for arg in args):
        raise HelperError(f"{location}.args contains an invalid or sensitive argument")
    approval_required = value.get("approval_required", False)
    if not isinstance(approval_required, bool):
        raise HelperError(f"{location}.approval_required must be a boolean")
    never_approval = "--ask-for-approval=never" in args or any(
        args[index:index + 2] == ["--ask-for-approval", "never"]
        for index in range(len(args) - 1)
    )
    if approval_required and never_approval:
        raise HelperError(f"{location} requires approval but native args disable it")
    try:
        adapter = get_adapter(kind)
        adapter.validate_arguments(args, location)
        if control_plane:
            adapter.validate_control_plane(args, location)
    except HarnessError as exc:
        raise HelperError(str(exc)) from exc
    result: dict[str, Any] = {"kind": kind, "args": args}
    if approval_required:
        result["approval_required"] = True
    if description:
        result["description"] = _populated(value["description"], f"{location}.description")
    return result


def _parse_project_config(data: bytes, label: str) -> dict[str, Any]:
    try:
        config = tomllib.loads(_safe_text(data, label))
    except tomllib.TOMLDecodeError as exc:
        raise HelperError(f"invalid project config TOML: {exc}") from exc
    if set(config) != {"version", "fallback_peer_recipe", "roles", "peer_recipes"}:
        raise HelperError("invalid project config top level")
    if config["version"] != PROJECT_CONFIG_VERSION:
        raise HelperError(f"project config version must be {PROJECT_CONFIG_VERSION}")
    roles = config["roles"]
    if not isinstance(roles, dict) or set(roles) - {"lead", "supervisor"} or "lead" not in roles:
        raise HelperError("roles must contain lead and optional supervisor only")
    peers = config["peer_recipes"]
    if not isinstance(peers, dict) or not peers:
        raise HelperError("peer_recipes must be a nonempty TOML table")
    validated_peers = {name: _validate_recipe(recipe, f"peer_recipes.{name}", True) for name, recipe in peers.items() if isinstance(name, str) and name}
    if len(validated_peers) != len(peers):
        raise HelperError("peer_recipes keys must be nonempty strings")
    fallback = _populated(config["fallback_peer_recipe"], "fallback_peer_recipe")
    if fallback not in validated_peers:
        raise HelperError("fallback_peer_recipe must name an exact peer_recipes entry")
    result = {"version": PROJECT_CONFIG_VERSION, "fallback_peer_recipe": fallback, "roles": {"lead": _validate_recipe(roles["lead"], "roles.lead", False, control_plane=True)}, "peer_recipes": validated_peers}
    if "supervisor" in roles:
        result["roles"]["supervisor"] = _validate_recipe(roles["supervisor"], "roles.supervisor", False, control_plane=True)
    return result


def _parse_protocol(data: bytes, label: str) -> dict[str, str]:
    text = _safe_text(data, label)
    headings = list(re.finditer(r"(?m)^##\s+(\d+)\.[^\r\n]*$", text))
    if [int(match.group(1)) for match in headings] != list(range(1, 13)):
        raise HelperError("workspace protocol numbered sections must appear exactly once in order 1 through 12")
    values: dict[str, str] = {}
    for index, heading in enumerate(headings):
        body = text[heading.end(): headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        labels = PROTOCOL_LABELS[index]
        for field in labels:
            matches = re.findall(rf"(?m)^\s*-\s+{re.escape(field)}:\s*(.*?)\s*$", body)
            if len(matches) != 1:
                raise HelperError(f"workspace protocol section {index + 1} requires one {field}")
            values[field] = _populated(matches[0], f"workspace protocol {field}")
    return {field: values[field] for field in ("Repository root", *LANGUAGE_FIELDS)}


def command_validate_project(args: argparse.Namespace) -> dict[str, Any]:
    root = _require_directory(Path(args.project_root), "project root")
    config_path = _require_file(Path(args.config) if args.config else root / ".orchestration/herdr-orchestrator.toml", "project config")
    protocol_path = _require_file(Path(args.protocol) if args.protocol else root / ".orchestration/workspace-protocol.md", "workspace protocol")
    config_data, protocol_data = _read(config_path, "project config"), _read(protocol_path, "workspace protocol")
    config, protocol = _parse_project_config(config_data, str(config_path)), _parse_protocol(protocol_data, str(protocol_path))
    if Path(protocol["Repository root"]).resolve() != root or protocol["Repository root"] != str(root):
        raise HelperError("workspace protocol Repository root must be this canonical project root")
    return {"schema_version": SCHEMA_VERSION, "command": "validate-project", "project_root": str(root), "config": {"path": str(config_path), "sha256": _sha256(config_data), "version": config["version"]}, "protocol": {"path": str(protocol_path), "sha256": _sha256(protocol_data)}, "languages": {"live": protocol[LANGUAGE_FIELDS[0]], "artifact": protocol[LANGUAGE_FIELDS[1]]}, "recipes": {"lead": config["roles"]["lead"], "supervisor": config["roles"].get("supervisor"), "fallback_peer": {"name": config["fallback_peer_recipe"], **config["peer_recipes"][config["fallback_peer_recipe"]]}, "peers": [{"name": name, **recipe} for name, recipe in config["peer_recipes"].items()]}}


RUNTIME_BINDING_SCHEMA_VERSION = 2
RUNTIME_BINDING_ROLES = frozenset({"lead", "peer", "supervisor"})
PANE_ENVIRONMENT_NAME_RE = re.compile(r"[A-Z_][A-Z0-9_]{0,127}\Z")
HERDR_MANAGED_PANE_ENVIRONMENT = frozenset({
    "HERDR_ENV",
    "HERDR_SOCKET_PATH",
    "HERDR_PANE_ID",
    "HERDR_TAB_ID",
    "HERDR_WORKSPACE_ID",
})


def _canonical_runtime_path(value: Any, label: str) -> Path:
    text = _required_text(value, label)
    if len(text.encode()) > 4096:
        raise HelperError(f"{label} exceeds the bounded path length")
    path = Path(text)
    if not path.is_absolute():
        raise HelperError(f"{label} must be a canonical absolute path")
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"{label} must be a canonical absolute path") from exc
    if text != str(resolved):
        raise HelperError(f"{label} must be a canonical absolute path")
    return resolved


def _runtime_binding_from_document(value: Any) -> RuntimeBinding:
    required = {
        "schema_version",
        "role",
        "herdr_executable",
        "herdr_socket_endpoint",
        "herdr_pane_id",
        "helper",
        "project_root",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise HelperError("runtime binding has unsupported or missing fields")
    if value["schema_version"] != RUNTIME_BINDING_SCHEMA_VERSION:
        raise HelperError(
            f"runtime binding.schema_version must be {RUNTIME_BINDING_SCHEMA_VERSION}"
        )
    role = _required_text(value["role"], "runtime binding.role")
    if role not in RUNTIME_BINDING_ROLES:
        raise HelperError("runtime binding.role must be lead, peer, or supervisor")
    executable = _require_file(
        _canonical_runtime_path(value["herdr_executable"], "runtime binding.herdr_executable"),
        "runtime binding.herdr_executable",
    )
    if not os.access(executable, os.X_OK):
        raise HelperError("runtime binding.herdr_executable must be executable")
    helper = _require_file(
        _canonical_runtime_path(value["helper"], "runtime binding.helper"),
        "runtime binding.helper",
    )
    project_root = _require_directory(
        _canonical_runtime_path(value["project_root"], "runtime binding.project_root"),
        "runtime binding.project_root",
    )
    return RuntimeBinding(
        role=role,
        herdr_executable=executable,
        herdr_socket_endpoint=_canonical_runtime_path(
            value["herdr_socket_endpoint"], "runtime binding.herdr_socket_endpoint"
        ),
        helper=helper,
        project_root=project_root,
        herdr_pane_id=_runtime_handle(
            _required_text(value["herdr_pane_id"], "runtime binding.herdr_pane_id"),
            "runtime binding.herdr_pane_id",
        ),
    )


def command_render_runtime_binding(args: argparse.Namespace) -> dict[str, Any]:
    """Render one adapter-owned native projection of bounded runtime facts."""
    binding_path = _require_file(Path(args.binding), "runtime binding")
    binding = _runtime_binding_from_document(
        _json_document(binding_path, "runtime binding")
    )
    try:
        adapter = get_adapter(_populated(args.kind, "kind"))
        projection = adapter.render_runtime_binding(binding)
    except HarnessError as exc:
        raise HelperError(str(exc)) from exc
    output = _check_output(Path(args.output), args.replace)
    data = projection.encode("utf-8")
    _atomic_write(output, data, args.replace)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "render-runtime-binding",
        "role": binding.role,
        "harness": adapter.kind,
        "path": str(output),
        "sha256": _sha256(data),
    }


def _runtime_pane_environment(
    binding: RuntimeBinding,
    role: str,
    adapter_environment: tuple[tuple[str, str], ...],
) -> list[dict[str, str]]:
    environment = [
        ("HERDR_ORCHESTRATOR_PROJECT_ROOT", str(binding.project_root)),
        ("HERDR_ORCHESTRATOR_HELPER", str(binding.helper)),
        ("HERDR_ORCHESTRATOR_ROLE", role),
        *adapter_environment,
    ]
    result: list[dict[str, str]] = []
    names: set[str] = set()
    for name, value in environment:
        if (
            not isinstance(name, str)
            or PANE_ENVIRONMENT_NAME_RE.fullmatch(name) is None
            or name in HERDR_MANAGED_PANE_ENVIRONMENT
        ):
            raise HelperError("runtime-binding pane projection has an unsupported environment name")
        if name in names:
            raise HelperError("runtime-binding pane projection repeats an environment name")
        names.add(name)
        result.append({
            "name": name,
            "value": _required_text(value, f"runtime-binding pane environment {name}"),
        })
    return result


def command_render_runtime_binding_pane(args: argparse.Namespace) -> dict[str, Any]:
    """Render direct pane environment facts without starting or managing a pane."""
    binding_path = _require_file(Path(args.binding), "runtime binding")
    binding = _runtime_binding_from_document(
        _json_document(binding_path, "runtime binding")
    )
    try:
        adapter = get_adapter(_populated(args.kind, "kind"))
        adapter_environment = adapter.project_pane_environment(binding)
    except HarnessError as exc:
        raise HelperError(str(exc)) from exc
    role = _required_text(args.role, "role")
    if role not in RUNTIME_BINDING_ROLES:
        raise HelperError("role must be lead, peer, or supervisor")
    projection = {
        "schema_version": RUNTIME_BINDING_SCHEMA_VERSION,
        "role": role,
        "harness": adapter.kind,
        "source_pane_id": binding.herdr_pane_id,
        "pane_environment": _runtime_pane_environment(binding, role, adapter_environment),
    }
    output = _check_output(Path(args.output), args.replace)
    data = (json.dumps(projection, ensure_ascii=False, sort_keys=True) + "\n").encode()
    _atomic_write(output, data, args.replace)
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "render-runtime-binding-pane",
        "role": role,
        "harness": adapter.kind,
        "path": str(output),
        "sha256": _sha256(data),
    }


def _runtime_handle(value: str, label: str) -> str:
    if RUNTIME_HANDLE_RE.fullmatch(value) is None:
        raise HelperError(f"{label} has unsupported characters")
    return value


def command_start_peer(args: argparse.Namespace) -> dict[str, Any]:
    """Start one configured Peer without reconstructing its native recipe."""
    validation = command_validate_project(args)
    recipe_name = _populated(args.recipe, "recipe")
    recipes = validation["recipes"]["peers"]
    recipe = next((item for item in recipes if item["name"] == recipe_name), None)
    if recipe is None:
        raise HelperError("recipe must name an exact configured peer_recipes entry")
    name = _runtime_handle(args.name, "name")
    pane = _runtime_handle(args.pane, "pane")
    native_args = list(recipe["args"])
    herdr_argv = [
        "herdr", "agent", "start", name, "--kind", recipe["kind"], "--pane", pane,
        "--", *native_args,
    ]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "start-peer",
        "recipe": {"name": recipe_name, "kind": recipe["kind"], "args": native_args},
        "name": name,
        "pane": pane,
        "herdr_argv": herdr_argv,
    }
    if args.dry_run:
        result["launch"] = "dry-run"
        return result
    try:
        completed = subprocess.run(herdr_argv, shell=False, check=False, capture_output=True)
    except OSError as exc:
        raise HelperError(f"configured Peer start could not invoke herdr: {exc}") from exc
    result.update({
        "launch": "executed",
        "returncode": completed.returncode,
        "stdout": _safe_diagnostic_text(completed.stdout, "Herdr Peer start stdout"),
        "stderr": _safe_diagnostic_text(completed.stderr, "Herdr Peer start stderr"),
    })
    return result


def command_submit_prompt(args: argparse.Namespace) -> dict[str, Any]:
    """Submit one already-composed prompt file without shell interpolation.

    This is deliberately a one-shot delivery boundary, not a lifecycle or wait
    abstraction.  Native Herdr remains responsible for all later observation.
    """
    name = _runtime_handle(args.agent, "agent")
    prompt_path = _require_file(Path(args.prompt_file), "prompt file")
    prompt_data = _read(prompt_path, "prompt file")
    prompt = _safe_text(prompt_data, "prompt file")
    herdr_argv = ["herdr", "agent", "prompt", name, prompt]
    try:
        completed = subprocess.run(herdr_argv, shell=False, check=False, capture_output=True)
    except OSError as exc:
        raise HelperError(f"native Herdr prompt submission could not invoke herdr: {exc}") from exc
    if completed.returncode:
        detail = _safe_diagnostic_text(completed.stderr, "Herdr prompt stderr").strip()
        raise HelperError(
            "native Herdr prompt submission failed"
            + (f" with exit status {completed.returncode}" if completed.returncode else "")
            + (f": {detail}" if detail else "")
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "command": "submit-prompt",
        "agent": name,
        "prompt_file": str(prompt_path),
        "prompt_sha256": _sha256(prompt_data),
        "prompt_bytes": len(prompt_data),
        "herdr_argv": herdr_argv[:-1] + ["<prompt-file-content>"],
        "submission": "accepted-by-native-herdr",
        "stdout": _safe_diagnostic_text(completed.stdout, "Herdr prompt stdout"),
        "stderr": _safe_diagnostic_text(completed.stderr, "Herdr prompt stderr"),
    }


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not value.strip() or "\0" in value:
        raise HelperError(f"{label} must be a nonempty string")
    return value


def _text_list(value: Any, label: str, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise HelperError(f"{label} must be an array with at least {minimum} item(s)")
    result = tuple(_required_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise HelperError(f"{label} must not repeat values")
    return result


def _string_map(value: Any, label: str, keys: set[str]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != keys:
        raise HelperError(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return {key: _required_text(value[key], f"{label}.{key}") for key in keys}


def _canonical_scope(value: Any, label: str) -> str:
    scope = _required_text(value, label)
    if scope.startswith("path:"):
        path = scope.removeprefix("path:")
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise HelperError(f"{label} must be a canonical project-relative path scope")
        return f"path:{path}"
    if scope.startswith("resource:"):
        resource = scope.removeprefix("resource:")
        if not resource or resource != resource.strip() or "\0" in resource:
            raise HelperError(f"{label} must be a canonical resource scope")
        return f"resource:{resource}"
    raise HelperError(f"{label} must start with path: or resource:")


def _candidate_from_document(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise HelperError("candidate must be a supported immutable candidate document")
    if value["kind"] == "git_commit":
        candidate = _string_map(value, "candidate", {"kind", "value"})
        if GIT_COMMIT_RE.fullmatch(candidate["value"]) is None:
            raise HelperError("candidate Git commit must be an exact lowercase 40-character hash")
        return candidate
    if value["kind"] == "git_tree":
        candidate = _string_map(value, "candidate", {"kind", "base_commit", "tree"})
        if GIT_COMMIT_RE.fullmatch(candidate["base_commit"]) is None:
            raise HelperError("candidate Git tree base_commit must be an exact lowercase 40-character hash")
        if GIT_COMMIT_RE.fullmatch(candidate["tree"]) is None:
            raise HelperError("candidate Git tree must be an exact lowercase 40-character hash")
        return candidate
    raise HelperError("candidate.kind must be git_commit or git_tree")


def _json_document(path: Path, label: str) -> Any:
    try:
        return json.loads(_safe_text(_read(path, label), label))
    except json.JSONDecodeError as exc:
        raise HelperError(f"{label} must be valid JSON: {exc}") from exc


def _canonical_relative_path(value: Any, label: str) -> str:
    path = _required_text(value, label)
    if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise HelperError(f"{label} must be a canonical project-relative path")
    return path


def _candidate_document_from_value(value: Any, label: str, *, allow_identity: bool = False) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Read the canonical candidate envelope, with raw identities only for review compatibility."""
    if isinstance(value, dict) and "candidate" in value:
        required = {"schema_version", "candidate", "artifact_scope", "excluded_path_prefixes"}
        if set(value) != required:
            raise HelperError(f"{label} has unsupported or missing fields")
        if value["schema_version"] != CANDIDATE_SCHEMA_VERSION:
            raise HelperError(f"{label}.schema_version must be {CANDIDATE_SCHEMA_VERSION}")
        candidate = _candidate_from_document(value["candidate"])
        if candidate is None:
            raise HelperError(f"{label}.candidate must be immutable")
        if candidate["kind"] != "git_tree":
            raise HelperError(f"{label}.candidate must be a canonical Git tree candidate")
        scope = _required_text(value["artifact_scope"], f"{label}.artifact_scope")
        if scope != "project-worktree-excluding-project-control":
            raise HelperError(f"{label}.artifact_scope must be the canonical application scope")
        prefixes = _text_list(value["excluded_path_prefixes"], f"{label}.excluded_path_prefixes", 1)
        if tuple(prefixes) != CANDIDATE_EXCLUDED_PREFIXES:
            raise HelperError(f"{label}.excluded_path_prefixes must use the canonical project-control exclusions")
        return candidate, {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "candidate": candidate,
            "artifact_scope": scope,
            "excluded_path_prefixes": list(prefixes),
        }
    if allow_identity:
        candidate = _candidate_from_document(value)
        if candidate is None:
            raise HelperError(f"{label} must be an immutable candidate document")
        return candidate, None
    raise HelperError(f"{label} must be a canonical candidate document")


def _assignment_from_document(value: Any) -> Assignment:
    fields = {"schema_version", "assignment_id", "role", "parent", "owner", "objective", "owned_scope", "exclusions", "authority", "disposition", "recipe", "verification", "dependencies", "languages", "topology_rationale", "candidate"}
    if not isinstance(value, dict) or set(value) != fields:
        raise HelperError("assignment has unsupported or missing fields")
    if value["schema_version"] != ASSIGNMENT_SCHEMA_VERSION:
        raise HelperError(f"assignment schema_version must be {ASSIGNMENT_SCHEMA_VERSION}")
    assignment_id = _required_text(value["assignment_id"], "assignment_id")
    if ASSIGNMENT_ID_RE.fullmatch(assignment_id) is None:
        raise HelperError("assignment_id has unsupported characters")
    role = _required_text(value["role"], "role")
    parent = _string_map(value["parent"], "parent", {"role", "id"})
    if role != "peer" or parent["role"] != "lead":
        raise HelperError("canonical Assignment is a Peer contract with Lead parentage")
    owner = _required_text(value["owner"], "owner")
    if owner == parent["id"]:
        raise HelperError("owner must name the assigned Peer, not the delegating Lead")
    authority = _required_text(value["authority"], "authority")
    scope = tuple(_canonical_scope(item, f"owned_scope[{index}]") for index, item in enumerate(_text_list(value["owned_scope"], "owned_scope")))
    if authority not in {"read-only", "write"} or len(set(scope)) != len(scope) or (authority == "write" and not scope):
        raise HelperError("assignment authority or owned_scope is invalid")
    candidate = _candidate_from_document(value["candidate"])
    disposition = _required_text(value["disposition"], "disposition")
    if disposition.lower() == "peer":
        raise HelperError("disposition must describe work, not repeat role=peer")
    rationale = value["topology_rationale"]
    if rationale is not None:
        rationale = _required_text(rationale, "topology_rationale")
    return Assignment(assignment_id, role, parent, owner, _required_text(value["objective"], "objective"), scope, _text_list(value["exclusions"], "exclusions"), authority, disposition, _required_text(value["recipe"], "recipe"), _text_list(value["verification"], "verification", 1), _text_list(value["dependencies"], "dependencies"), _string_map(value["languages"], "languages", {"live", "artifact"}), rationale, candidate)


def _assignment_document(assignment: Assignment) -> dict[str, Any]:
    return {"schema_version": ASSIGNMENT_SCHEMA_VERSION, "assignment_id": assignment.assignment_id, "role": assignment.role, "parent": assignment.parent, "owner": assignment.owner, "objective": assignment.objective, "owned_scope": list(assignment.owned_scope), "exclusions": list(assignment.exclusions), "authority": assignment.authority, "disposition": assignment.disposition, "recipe": assignment.recipe, "verification": list(assignment.verification), "dependencies": list(assignment.dependencies), "languages": assignment.languages, "topology_rationale": assignment.topology_rationale, "candidate": assignment.candidate}


def command_validate_assignment(args: argparse.Namespace) -> dict[str, Any]:
    return _assignment_document(_assignment_from_document(_json_document(Path(args.assignment), "assignment")))


def command_render_assignment(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    profile = _safe_text(_read(Path(args.role_profile), "role profile"), "role profile")
    protocol = _safe_text(_read(Path(args.applicable_protocol), "applicable protocol projection"), "applicable protocol projection")
    headings = [int(match.group(1)) for match in re.finditer(r"(?m)^##\s+(\d+)\.", protocol)]
    if headings == list(range(1, 13)):
        raise HelperError("Peer applicable protocol projection must not be the full Workspace Protocol")
    rendered = f"# Role Profile\n\n{profile}\n\n# Applicable Protocol Constraints\n\n{protocol}\n\n# Assignment\n\n```json\n{json.dumps(_assignment_document(assignment), ensure_ascii=False, indent=2)}\n```\n\nReturn a structured handback with this exact assignment_id. Its JSON object has exactly assignment_id, outcome, evidence, impact, and need; every value is a non-empty string; prompt delivery and Herdr lifecycle are not assignment completion.\n"
    _atomic_write(Path(args.output), rendered.encode(), args.replace)
    return {"schema_version": ASSIGNMENT_SCHEMA_VERSION, "command": "render-assignment", "assignment_id": assignment.assignment_id, "path": str(Path(args.output).resolve()), "sha256": _sha256(rendered.encode())}


def _scopes_overlap(left: str, right: str) -> bool:
    kind, value = left.split(":", 1)
    other_kind, other_value = right.split(":", 1)
    return kind == other_kind and (value == other_value if kind == "resource" else value == other_value or value.startswith(other_value.rstrip("/") + "/") or other_value.startswith(value.rstrip("/") + "/"))


def command_validate_delegation(args: argparse.Namespace) -> dict[str, Any]:
    assignments = [_assignment_from_document(_json_document(Path(path), "assignment")) for path in args.assignment]
    writers = [assignment for assignment in assignments if assignment.authority == "write"]
    if len({assignment.assignment_id for assignment in assignments}) != len(assignments):
        raise HelperError("active delegation map repeats assignment_id")
    for index, left in enumerate(writers):
        for right in writers[index + 1:]:
            if any(_scopes_overlap(a, b) for a in left.owned_scope for b in right.owned_scope):
                raise HelperError("moving-scope ownership conflicts require Lead reconciliation")
    return {"assignment_ids": [assignment.assignment_id for assignment in assignments], "writer_assignment_ids": [assignment.assignment_id for assignment in writers], "topology_rationales": {assignment.assignment_id: assignment.topology_rationale for assignment in assignments}}


def _git(
    project_root: Path,
    arguments: Sequence[str],
    label: str,
    *,
    environment: dict[str, str] | None = None,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), *arguments], check=False, capture_output=True,
            env=environment, input=input_data,
        )
    except OSError as exc:
        raise HelperError(f"{label} could not invoke Git: {exc}") from exc
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise HelperError(f"{label} failed" + (f": {detail}" if detail else ""))
    return completed


def _git_text(
    project_root: Path,
    arguments: Sequence[str],
    label: str,
    *,
    environment: dict[str, str] | None = None,
    input_data: bytes | None = None,
) -> str:
    return _safe_text(
        _git(project_root, arguments, label, environment=environment, input_data=input_data).stdout,
        label,
    ).strip()


def _repository_root(project_root: Path) -> Path:
    root = _require_directory(project_root, "project root")
    reported = Path(_git_text(root, ["rev-parse", "--show-toplevel"], "project Git repository"))
    try:
        repository = reported.resolve(strict=True)
    except OSError as exc:
        raise HelperError(f"project Git repository has no resolvable root: {exc}") from exc
    if repository != root:
        raise HelperError("project root must be the Git worktree root for candidate operations")
    return root


def _candidate_object_directory(project_root: Path, *, create: bool) -> Path:
    """Return the one candidate-owned Git object directory for this project."""
    path = project_root / ".orchestration" / "candidate-objects"
    try:
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
        orchestration = (project_root / ".orchestration").resolve(strict=True)
        resolved.relative_to(orchestration)
    except FileNotFoundError as exc:
        raise HelperError(
            f"candidate object storage is missing: {path}; it is required to read the immutable candidate"
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"candidate object storage is unavailable: {path}: {exc}") from exc
    if not resolved.is_dir():
        raise HelperError(f"candidate object storage is not a directory: {resolved}")
    return resolved


def _real_object_directory(project_root: Path) -> Path:
    reported = Path(_git_text(project_root, ["rev-parse", "--git-path", "objects"], "project Git object directory"))
    path = reported if reported.is_absolute() else project_root / reported
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"project Git object directory is unavailable: {path}: {exc}") from exc
    if not resolved.is_dir():
        raise HelperError(f"project Git object directory is not a directory: {resolved}")
    return resolved


def _candidate_git_environment(project_root: Path, *, create: bool) -> dict[str, str]:
    """Keep all candidate writes outside .git while reading base objects there."""
    candidate_objects = _candidate_object_directory(project_root, create=create)
    real_objects = _real_object_directory(project_root)
    environment = dict(os.environ)
    environment["GIT_OBJECT_DIRECTORY"] = str(candidate_objects)
    environment["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(real_objects)
    return environment


def _candidate_write_environment(project_root: Path) -> dict[str, str]:
    """Write only to candidate storage; do not let Git elide an alternate object."""
    environment = _candidate_git_environment(project_root, create=True)
    environment.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    return environment


def _candidate_tree_is_stored(project_root: Path, tree: str) -> bool:
    store = _candidate_object_directory(project_root, create=False)
    return (store / tree[:2] / tree[2:]).is_file()


def _ensure_candidate_tree_stored(project_root: Path, tree: str) -> None:
    """Materialize the root tree in the candidate store even when it equals base.

    Git can elide an unchanged tree because it sees the real object through the
    alternate.  The candidate contract still requires its object store to be
    present and independently readable, so retain that root tree there.
    """
    if _candidate_tree_is_stored(project_root, tree):
        return
    content = _git(
        project_root,
        ["cat-file", "tree", tree],
        "candidate tree materialization",
        environment=_candidate_git_environment(project_root, create=False),
    ).stdout
    stored = _git_text(
        project_root,
        ["hash-object", "-t", "tree", "-w", "--stdin"],
        "candidate tree materialization",
        environment=_candidate_write_environment(project_root),
        input_data=content,
    )
    if stored != tree or not _candidate_tree_is_stored(project_root, tree):
        raise HelperError("candidate tree materialization did not preserve the Git tree identity")


def _git_commit_exists(project_root: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(project_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False, capture_output=True,
    ).returncode == 0


def _git_tree_exists(project_root: Path, tree: str, *, environment: dict[str, str] | None = None) -> bool:
    return subprocess.run(
        ["git", "-C", str(project_root), "cat-file", "-e", f"{tree}^{{tree}}"],
        check=False, capture_output=True, env=environment,
    ).returncode == 0


def _verify_candidate(project_root: Path, candidate: dict[str, str], label: str) -> None:
    if candidate["kind"] == "git_commit":
        if not _git_commit_exists(project_root, candidate["value"]):
            raise HelperError(f"{label} Git commit must exist in project root")
        return
    if not _git_commit_exists(project_root, candidate["base_commit"]):
        raise HelperError(f"{label} Git tree base commit must exist in project root")
    if not _candidate_tree_is_stored(project_root, candidate["tree"]):
        raise HelperError(
            f"{label} Git tree is absent from candidate object storage; candidate storage is missing or corrupt"
        )
    if not _git_tree_exists(project_root, candidate["tree"], environment=_candidate_git_environment(project_root, create=False)):
        raise HelperError(f"{label} Git tree is unreadable from candidate object storage")


def _candidate_diff(project_root: Path, candidate: dict[str, str]) -> bytes:
    """Read the exact immutable artifact, including every changed candidate object."""
    if candidate["kind"] == "git_tree":
        completed = _git(
            project_root,
            ["diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", candidate["base_commit"], candidate["tree"]],
            "candidate immutable diff",
            environment=_candidate_git_environment(project_root, create=False),
        )
    else:
        completed = _git(project_root, ["show", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", "--format=", candidate["value"]], "candidate immutable diff")
    if len(completed.stdout) > MAX_CANDIDATE_DIFF_BYTES:
        raise HelperError(f"candidate immutable diff exceeds the bounded {MAX_CANDIDATE_DIFF_BYTES}-byte inspection limit")
    return completed.stdout


def _candidate_changed_paths(project_root: Path, candidate: dict[str, str]) -> list[str]:
    if candidate["kind"] == "git_tree":
        completed = _git(
            project_root,
            ["diff", "--no-ext-diff", "--name-only", "-z", candidate["base_commit"], candidate["tree"]],
            "candidate changed-path listing",
            environment=_candidate_git_environment(project_root, create=False),
        )
    else:
        completed = _git(project_root, ["show", "--no-ext-diff", "--format=", "--name-only", "-z", candidate["value"]], "candidate changed-path listing")
    try:
        paths = [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise HelperError(f"candidate diff path is not UTF-8: byte {exc.start}") from exc
    if len(paths) > 4096:
        raise HelperError("candidate diff exceeds the bounded 4096-path inspection limit")
    return paths


def _candidate_document(candidate: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate": candidate,
        "artifact_scope": "project-worktree-excluding-project-control",
        "excluded_path_prefixes": list(CANDIDATE_EXCLUDED_PREFIXES),
    }


def _freeze_application_tree(project_root: Path, base_commit: str) -> str:
    """Build the scoped application tree in an isolated index for both freeze and stale checks."""
    if GIT_COMMIT_RE.fullmatch(base_commit) is None:
        raise HelperError("candidate base commit must be an exact lowercase 40-character hash")
    with tempfile.TemporaryDirectory(prefix="herdr-candidate-index-") as temporary:
        index_path = str(Path(temporary) / "index")
        environment = {**_candidate_git_environment(project_root, create=True), "GIT_INDEX_FILE": index_path}
        _git(project_root, ["read-tree", f"{base_commit}^{{tree}}"], "candidate temporary index initialization", environment=environment)
        _git(
            project_root,
            ["add", "-A", "--", ".", *(f":(exclude){path}" for path in CANDIDATE_EXCLUDED_PREFIXES)],
            "candidate temporary index population",
            environment=environment,
        )
        _git(project_root, ["reset", "-q", base_commit, "--", *CANDIDATE_EXCLUDED_PREFIXES], "candidate project-control exclusion", environment=environment)
        tree = _git_text(project_root, ["write-tree"], "candidate tree freeze", environment=environment)
    if GIT_COMMIT_RE.fullmatch(tree) is not None:
        _ensure_candidate_tree_stored(project_root, tree)
    if GIT_COMMIT_RE.fullmatch(tree) is None or not _candidate_tree_is_stored(project_root, tree):
        raise HelperError("candidate freeze did not produce an immutable Git tree")
    return tree


def command_freeze_candidate(args: argparse.Namespace) -> dict[str, Any]:
    """Freeze the current application artifact as an immutable Git tree, never the real index."""
    project_root = _repository_root(Path(args.project_root))
    base_commit = _git_text(project_root, ["rev-parse", "HEAD"], "candidate base commit")
    tree = _freeze_application_tree(project_root, base_commit)
    candidate = {"kind": "git_tree", "base_commit": base_commit, "tree": tree}
    _candidate_diff(project_root, candidate)
    document = _candidate_document(candidate)
    target = project_root / ".orchestration/current-candidate.json"
    _atomic_write(target, (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode(), replace=True)
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "command": "freeze-candidate",
        "path": str(target),
        "document_sha256": _sha256(_read(target, "current candidate document")),
        "candidate": candidate,
        "head_unchanged": base_commit,
        "real_index": "not used",
        "object_store": str(_candidate_object_directory(project_root, create=False)),
    }


def command_inspect_candidate(args: argparse.Namespace) -> dict[str, Any]:
    project_root = _repository_root(Path(args.project_root))
    path = project_root / ".orchestration/current-candidate.json"
    candidate, document = _candidate_document_from_value(_json_document(path, "current candidate"), "current candidate")
    _verify_candidate(project_root, candidate, "current candidate")
    diff = _candidate_diff(project_root, candidate)
    changed_paths = _candidate_changed_paths(project_root, candidate)
    diff_path = project_root / ".orchestration/current-candidate.diff"
    _atomic_write(diff_path, diff, replace=True)
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "command": "inspect-candidate",
        "path": str(_require_file(path, "current candidate")),
        "candidate": candidate,
        "candidate_document_sha256": _sha256(_read(path, "current candidate")),
        "artifact_scope": document["artifact_scope"],
        "excluded_path_prefixes": document["excluded_path_prefixes"],
        "object_store": str(_candidate_object_directory(project_root, create=False)),
        "diff_path": str(diff_path),
        "diff_sha256": _sha256(diff),
        "diff_bytes": len(diff),
        "changed_paths": changed_paths,
    }


def command_validate_review(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "review assignment"))
    project_root = _require_directory(Path(args.project_root), "project root")
    current, _ = _candidate_document_from_value(
        _json_document(Path(args.current_candidate), "current candidate"), "current candidate", allow_identity=True
    )
    return _validate_review_assignment(assignment, project_root, current)


def _validate_review_assignment(assignment: Assignment, project_root: Path, current: dict[str, str]) -> dict[str, Any]:
    if assignment.role != "peer" or assignment.authority != "read-only" or assignment.disposition.lower() != "reviewer" or assignment.candidate is None:
        raise HelperError("review requires a read-only Reviewer assignment with an immutable candidate")
    candidate = assignment.candidate
    _verify_candidate(project_root, candidate, "review candidate")
    _verify_candidate(project_root, current, "current candidate")
    if candidate != current:
        raise HelperError("review candidate is stale; create a new candidate and fresh review assignment")
    _candidate_diff(project_root, candidate)
    return {"assignment_id": assignment.assignment_id, "candidate": candidate, "review_applicable": True}


def _handback_from_document(assignment: Assignment, handback: Any) -> dict[str, Any]:
    required = {"assignment_id", "outcome", "evidence", "impact", "need"}
    allowed = required | {"evidence_path"}
    if not isinstance(handback, dict) or not required <= set(handback) or set(handback) - allowed:
        raise HelperError("handback has unsupported or missing fields")
    if _required_text(handback["assignment_id"], "handback.assignment_id") != assignment.assignment_id:
        raise HelperError("handback assignment_id does not match the Assignment")
    if _required_text(handback["outcome"], "handback.outcome") not in SEMANTIC_OUTCOMES:
        raise HelperError("handback.outcome is not a semantic outcome")
    result = {key: _required_text(handback[key], f"handback.{key}") for key in required}
    if handback.get("evidence_path") is not None:
        evidence = _require_file(Path(_required_text(handback["evidence_path"], "handback.evidence_path")), "handback evidence")
        _read(evidence, "handback evidence")
        result["evidence_path"] = str(evidence)
    return result


def command_validate_handback(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    result = _handback_from_document(assignment, _json_document(Path(args.handback), "handback"))
    return {"assignment_id": assignment.assignment_id, "handback": result, "completion": "semantic_handback"}


def _project_evidence_file(project_root: Path, value: Any, label: str) -> Path:
    relative = _canonical_relative_path(value, label)
    path = _require_file(project_root / relative, label)
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise HelperError(f"{label} must resolve inside the project root") from exc
    return path


def _candidate_equal(value: Any, candidate: dict[str, str], label: str) -> None:
    supplied = _candidate_from_document(value)
    if supplied != candidate:
        raise HelperError(f"{label} must bind the exact current immutable candidate")


def _acceptance_from_document(value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "candidate", "candidate_document_sha256", "lead", "inspection",
        "verification", "unresolved_findings", "residual_risk", "review",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise HelperError("acceptance has unsupported or missing fields")
    if value["schema_version"] != ACCEPTANCE_SCHEMA_VERSION:
        raise HelperError(f"acceptance.schema_version must be {ACCEPTANCE_SCHEMA_VERSION}")
    candidate = _candidate_from_document(value["candidate"])
    if candidate is None:
        raise HelperError("acceptance.candidate must be immutable")
    candidate_document_sha256 = _required_text(value["candidate_document_sha256"], "acceptance.candidate_document_sha256")
    if SHA256_RE.fullmatch(candidate_document_sha256) is None:
        raise HelperError("acceptance.candidate_document_sha256 must be a lowercase SHA-256 digest")
    lead = _string_map(value["lead"], "acceptance.lead", {"role", "id"})
    if lead["role"] != "lead":
        raise HelperError("acceptance.lead.role must be lead")
    lead["id"] = _runtime_handle(lead["id"], "acceptance.lead.id")
    inspection = value["inspection"]
    if not isinstance(inspection, dict) or set(inspection) != {"candidate", "command", "result"}:
        raise HelperError("acceptance.inspection must contain exactly candidate, command, result")
    _candidate_equal(inspection["candidate"], candidate, "acceptance.inspection.candidate")
    inspection = {
        "candidate": candidate,
        "command": _required_text(inspection["command"], "acceptance.inspection.command"),
        "result": _required_text(inspection["result"], "acceptance.inspection.result"),
    }
    verification_value = value["verification"]
    if not isinstance(verification_value, list) or not verification_value:
        raise HelperError("acceptance.verification must be a nonempty array")
    verification: list[dict[str, Any]] = []
    for index, item in enumerate(verification_value):
        if not isinstance(item, dict) or set(item) != {"candidate", "command", "result"}:
            raise HelperError(f"acceptance.verification[{index}] must contain exactly candidate, command, result")
        _candidate_equal(item["candidate"], candidate, f"acceptance.verification[{index}].candidate")
        verification.append({
            "candidate": candidate,
            "command": _required_text(item["command"], f"acceptance.verification[{index}].command"),
            "result": _required_text(item["result"], f"acceptance.verification[{index}].result"),
        })
    unresolved = _text_list(value["unresolved_findings"], "acceptance.unresolved_findings")
    residual_risk = _required_text(value["residual_risk"], "acceptance.residual_risk")
    review = value["review"]
    if not isinstance(review, dict) or not isinstance(review.get("decision"), str):
        raise HelperError("acceptance.review must make an explicit review decision")
    if review["decision"] == "not_required":
        if set(review) != {"decision", "rationale"}:
            raise HelperError("acceptance.review not_required must contain exactly decision and rationale")
        review_result: dict[str, Any] = {"decision": "not_required", "rationale": _required_text(review["rationale"], "acceptance.review.rationale")}
    elif review["decision"] == "required":
        if set(review) != {"decision", "rationale", "assignment_path", "handback_path"}:
            raise HelperError("acceptance.review required must contain decision, rationale, assignment_path, handback_path")
        review_result = {
            "decision": "required",
            "rationale": _required_text(review["rationale"], "acceptance.review.rationale"),
            "assignment_path": _canonical_relative_path(review["assignment_path"], "acceptance.review.assignment_path"),
            "handback_path": _canonical_relative_path(review["handback_path"], "acceptance.review.handback_path"),
        }
    else:
        raise HelperError("acceptance.review.decision must be required or not_required")
    return {
        "candidate": candidate,
        "candidate_document_sha256": candidate_document_sha256,
        "lead": lead,
        "inspection": inspection,
        "verification": verification,
        "unresolved_findings": list(unresolved),
        "residual_risk": residual_risk,
        "review": review_result,
    }


def command_validate_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    project_root = _repository_root(Path(args.project_root))
    candidate_path = project_root / ".orchestration/current-candidate.json"
    current_candidate, _ = _candidate_document_from_value(
        _json_document(candidate_path, "current candidate"), "current candidate"
    )
    _verify_candidate(project_root, current_candidate, "current candidate")
    acceptance_path = project_root / ".orchestration/current-acceptance.json"
    acceptance = _acceptance_from_document(_json_document(acceptance_path, "acceptance"))
    if acceptance["candidate"] != current_candidate:
        raise HelperError("acceptance.candidate is stale; freeze and accept the exact current candidate")
    actual_candidate_document_sha256 = _sha256(_read(candidate_path, "current candidate"))
    if acceptance["candidate_document_sha256"] != actual_candidate_document_sha256:
        raise HelperError("acceptance.candidate_document_sha256 is stale")
    if args.lead_id and acceptance["lead"]["id"] != _runtime_handle(args.lead_id, "lead id"):
        raise HelperError("acceptance.lead.id does not match the completing Lead")
    current_tree = _freeze_application_tree(project_root, current_candidate["base_commit"])
    if current_tree != current_candidate["tree"]:
        raise HelperError("current candidate is stale; application artifact has mutated since freeze")
    _candidate_diff(project_root, current_candidate)
    review = acceptance["review"]
    review_summary: dict[str, Any] = {"decision": review["decision"]}
    if review["decision"] == "required":
        assignment_path = _project_evidence_file(project_root, review["assignment_path"], "acceptance.review.assignment_path")
        handback_path = _project_evidence_file(project_root, review["handback_path"], "acceptance.review.handback_path")
        assignment = _assignment_from_document(_json_document(assignment_path, "review assignment"))
        _validate_review_assignment(assignment, project_root, current_candidate)
        handback = _handback_from_document(assignment, _json_document(handback_path, "review handback"))
        if handback["outcome"] != "COMPLETE":
            raise HelperError("acceptance.review handback must be COMPLETE for project acceptance")
        review_summary["assignment_id"] = assignment.assignment_id
    return {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "command": "validate-acceptance",
        "acceptance": "valid",
        "candidate": current_candidate,
        "lead": acceptance["lead"],
        "review": review_summary,
        "recovery_needed": False,
    }


def command_harness_models(args: argparse.Namespace) -> dict[str, Any]:
    adapter = ADAPTERS[args.kind]
    root = _require_directory(Path(args.project_root), "project root")
    output = _check_output(Path(args.output), args.replace)
    if args.catalog_file:
        raw = _read(Path(args.catalog_file), f"{adapter.kind} model catalog")
        source: dict[str, Any] = {"kind": "file", "path": str(Path(args.catalog_file).resolve()), "sha256": _sha256(raw)}
    else:
        if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
            raise HelperError("timeout seconds must be finite and greater than zero")
        try:
            command = [args.program or adapter.kind, *adapter.catalog_command(args.catalog_mode)]
            completed = subprocess.run(command, shell=False, check=False, capture_output=True, timeout=args.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HelperError(f"{adapter.kind} model catalog command failed: {exc}") from exc
        if completed.returncode:
            raise HelperError(f"{adapter.kind} model catalog command failed with exit status {completed.returncode}")
        raw, source = completed.stdout, {"kind": "command", "program": command[0], "mode": args.catalog_mode}
    try:
        projection = adapter.project_catalog(raw, f"{adapter.kind} model catalog", SCHEMA_VERSION, root)
    except HarnessError as exc:
        raise HelperError(str(exc)) from exc
    data = (json.dumps(projection, ensure_ascii=False, sort_keys=True) + "\n").encode()
    _atomic_write(output, data, args.replace)
    return {"schema_version": SCHEMA_VERSION, "command": "harness-models", "harness": adapter.kind, "path": str(output), "sha256": _sha256(data), "model_count": len(projection["models"]), "source": source}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("validate-project")
    project.add_argument("--project-root", required=True)
    project.add_argument("--config")
    project.add_argument("--protocol")
    project.set_defaults(handler=command_validate_project)
    runtime_binding = commands.add_parser("render-runtime-binding")
    runtime_binding.add_argument("--binding", required=True)
    runtime_binding.add_argument("--kind", required=True)
    runtime_binding.add_argument("--output", required=True)
    runtime_binding.add_argument("--replace", action="store_true")
    runtime_binding.set_defaults(handler=command_render_runtime_binding)
    pane_binding = commands.add_parser("render-runtime-binding-pane")
    pane_binding.add_argument("--binding", required=True)
    pane_binding.add_argument("--kind", required=True)
    pane_binding.add_argument("--role", required=True)
    pane_binding.add_argument("--output", required=True)
    pane_binding.add_argument("--replace", action="store_true")
    pane_binding.set_defaults(handler=command_render_runtime_binding_pane)
    peer_start = commands.add_parser("start-peer")
    peer_start.add_argument("--project-root", required=True)
    peer_start.add_argument("--config")
    peer_start.add_argument("--protocol")
    peer_start.add_argument("--recipe", required=True)
    peer_start.add_argument("--name", required=True)
    peer_start.add_argument("--pane", required=True)
    peer_start.add_argument("--dry-run", action="store_true")
    peer_start.set_defaults(handler=command_start_peer)
    prompt = commands.add_parser("submit-prompt")
    prompt.add_argument("--agent", required=True)
    prompt.add_argument("--prompt-file", required=True)
    prompt.set_defaults(handler=command_submit_prompt)
    assignment = commands.add_parser("validate-assignment")
    assignment.add_argument("--assignment", required=True)
    assignment.set_defaults(handler=command_validate_assignment)
    render = commands.add_parser("render-assignment")
    render.add_argument("--assignment", required=True); render.add_argument("--role-profile", required=True); render.add_argument("--applicable-protocol", required=True); render.add_argument("--output", required=True); render.add_argument("--replace", action="store_true")
    render.set_defaults(handler=command_render_assignment)
    delegation = commands.add_parser("validate-delegation")
    delegation.add_argument("--assignment", action="append", required=True)
    delegation.set_defaults(handler=command_validate_delegation)
    freeze = commands.add_parser("freeze-candidate")
    freeze.add_argument("--project-root", default=".")
    freeze.set_defaults(handler=command_freeze_candidate)
    inspect = commands.add_parser("inspect-candidate")
    inspect.add_argument("--project-root", default=".")
    inspect.set_defaults(handler=command_inspect_candidate)
    review = commands.add_parser("validate-review")
    review.add_argument("--assignment", required=True); review.add_argument("--current-candidate", required=True); review.add_argument("--project-root", default=".")
    review.set_defaults(handler=command_validate_review)
    handback = commands.add_parser("validate-handback")
    handback.add_argument("--assignment", required=True); handback.add_argument("--handback", required=True)
    handback.set_defaults(handler=command_validate_handback)
    acceptance = commands.add_parser("validate-acceptance")
    acceptance.add_argument("--project-root", default=".")
    acceptance.add_argument("--lead-id")
    acceptance.set_defaults(handler=command_validate_acceptance)
    models = commands.add_parser("harness-models")
    models.add_argument("--kind", choices=VERIFIED_HARNESS_KINDS, required=True); models.add_argument("--output", required=True); models.add_argument("--project-root", default="."); models.add_argument("--program"); models.add_argument("--catalog-file"); models.add_argument("--catalog-mode", default="live"); models.add_argument("--replace", action="store_true"); models.add_argument("--timeout-seconds", type=float, default=30.0)
    models.set_defaults(handler=command_harness_models)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _emit(args.handler(args))
    except (HelperError, HarnessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
