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
import shutil
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
# The helper can be installed next to the harness package.  Do this before the
# local import so inspection/rendering never leaves __pycache__ in that skill.
sys.dont_write_bytecode = True
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
PROJECT_CONFIG_VERSION = 4
ASSIGNMENT_SCHEMA_VERSION = 2
CANDIDATE_SCHEMA_VERSION = 2
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
ROUTED_DISPOSITIONS = frozenset({"engineer", "reviewer", "architect"})
COST_CLASSES = frozenset({"standard", "elevated"})
CONVERGENCE_DECISIONS = frozenset({"continue", "re-architect", "escalate", "block"})
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
    project_root: str
    worktree: dict[str, str] | None
    objective: str
    owned_scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    authority: str
    disposition: str
    recipe: str | None
    verification: tuple[str, ...]
    dependencies: tuple[str, ...]
    languages: dict[str, str]
    topology_rationale: str | None
    candidate: dict[str, str] | None
    review_cycle: int
    prior_review: dict[str, str] | None
    convergence_assessment: dict[str, Any] | None
    cost_approval: str | None


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
    required = {"kind", "args", "cost_class"} | ({"description"} if description else set())
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
    cost_class = value["cost_class"]
    if cost_class not in COST_CLASSES:
        raise HelperError(f"{location}.cost_class must be standard or elevated")
    result["cost_class"] = cost_class
    return result


def _parse_project_config(data: bytes, label: str) -> dict[str, Any]:
    try:
        config = tomllib.loads(_safe_text(data, label))
    except tomllib.TOMLDecodeError as exc:
        raise HelperError(f"invalid project config TOML: {exc}") from exc
    if set(config) != {"version", "assessment_after_cycles", "roles", "peer_recipes", "routing"}:
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
    threshold = config["assessment_after_cycles"]
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1 or threshold > 32:
        raise HelperError("assessment_after_cycles must be an integer from 1 through 32")
    routing = config["routing"]
    if not isinstance(routing, dict) or set(routing) != {"engineer", "reviewer", "architect", "default"}:
        raise HelperError("routing must contain exactly engineer, reviewer, architect, and default")
    validated_routes: dict[str, dict[str, Any]] = {}
    for disposition, route in routing.items():
        if not isinstance(route, dict) or set(route) != {"default_recipe", "allowed_recipes"}:
            raise HelperError(f"routing.{disposition} must contain exactly default_recipe and allowed_recipes")
        default_recipe = _populated(route["default_recipe"], f"routing.{disposition}.default_recipe")
        allowed_recipes = _text_list(route["allowed_recipes"], f"routing.{disposition}.allowed_recipes", 1)
        if default_recipe not in allowed_recipes or any(recipe not in validated_peers for recipe in allowed_recipes):
            raise HelperError(f"routing.{disposition} must use configured peer_recipes and include its default_recipe")
        validated_routes[disposition] = {"default_recipe": default_recipe, "allowed_recipes": list(allowed_recipes)}
    result = {"version": PROJECT_CONFIG_VERSION, "assessment_after_cycles": threshold, "roles": {"lead": _validate_recipe(roles["lead"], "roles.lead", False, control_plane=True)}, "peer_recipes": validated_peers, "routing": validated_routes}
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
            value = matches[0]
            if field == "Repository root" and value.startswith("`") and value.endswith("`") and value.count("`") == 2:
                value = value[1:-1]
            values[field] = _populated(value, f"workspace protocol {field}")
    return {field: values[field] for field in ("Repository root", *LANGUAGE_FIELDS)}


def command_validate_project(args: argparse.Namespace) -> dict[str, Any]:
    root = _require_directory(Path(args.project_root), "project root")
    config_path = _require_file(Path(args.config) if args.config else root / ".orchestration/herdr-orchestrator.toml", "project config")
    protocol_path = _require_file(Path(args.protocol) if args.protocol else root / ".orchestration/workspace-protocol.md", "workspace protocol")
    config_data, protocol_data = _read(config_path, "project config"), _read(protocol_path, "workspace protocol")
    config, protocol = _parse_project_config(config_data, str(config_path)), _parse_protocol(protocol_data, str(protocol_path))
    protocol_root = _canonical_runtime_path(protocol["Repository root"], "workspace protocol Repository root")
    if protocol_root != root and not _same_git_worktree_repository(root, protocol_root):
        raise HelperError("workspace protocol Repository root must be this canonical project root")
    return {"schema_version": SCHEMA_VERSION, "command": "validate-project", "project_root": str(root), "protocol_repository_root": str(protocol_root), "config": {"path": str(config_path), "sha256": _sha256(config_data), "version": config["version"], "assessment_after_cycles": config["assessment_after_cycles"]}, "protocol": {"path": str(protocol_path), "sha256": _sha256(protocol_data)}, "languages": {"live": protocol[LANGUAGE_FIELDS[0]], "artifact": protocol[LANGUAGE_FIELDS[1]]}, "recipes": {"lead": config["roles"]["lead"], "supervisor": config["roles"].get("supervisor"), "peers": [{"name": name, **recipe} for name, recipe in config["peer_recipes"].items()], "routing": config["routing"]}}


RUNTIME_BINDING_SCHEMA_VERSION = 2
RUNTIME_BINDING_ROLES = frozenset({"launcher", "lead", "peer", "supervisor"})
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
        raise HelperError("runtime binding.role must be launcher, lead, peer, or supervisor")
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
    assignment: Assignment | None = None,
) -> list[dict[str, str]]:
    environment = [
        ("HERDR_ORCHESTRATOR_PROJECT_ROOT", str(binding.project_root)),
        ("HERDR_ORCHESTRATOR_HELPER", str(binding.helper)),
        ("HERDR_ORCHESTRATOR_ROLE", role),
        ("PYTHONDONTWRITEBYTECODE", "1"),
        *(
            (("HERDR_ORCHESTRATOR_ASSIGNMENT_ID", assignment.assignment_id),
             ("HERDR_ORCHESTRATOR_OWNER", assignment.owner))
            if assignment is not None else ()
        ),
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
        raise HelperError("role must be launcher, lead, peer, or supervisor")
    assignment = None
    if args.assignment is not None:
        if role != "peer":
            raise HelperError("--assignment is only valid for a Peer pane projection")
        assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
        if assignment.project_root != str(binding.project_root):
            raise HelperError("Peer pane Assignment project_root must match the runtime binding")
    projection = {
        "schema_version": RUNTIME_BINDING_SCHEMA_VERSION,
        "role": role,
        "harness": adapter.kind,
        "source_pane_id": binding.herdr_pane_id,
        "pane_environment": _runtime_pane_environment(binding, role, adapter_environment, assignment),
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


def _require_capability(allowed_roles: frozenset[str], *, project_root: Path | None = None) -> str:
    """Reject accidental use of a child/foreign pane as an SLP control role.

    This is intentionally a binding-contamination guard, not a claim that raw
    Herdr commands are an ACL.  Pure document validators do not call it.
    """
    role = os.environ.get("HERDR_ORCHESTRATOR_ROLE")
    pane = os.environ.get("HERDR_PANE_ID")
    bound_pane = os.environ.get("HERDR_ORCHESTRATOR_PANE_ID")
    bound_root = os.environ.get("HERDR_ORCHESTRATOR_PROJECT_ROOT")
    helper = os.environ.get("HERDR_ORCHESTRATOR_HELPER")
    if role not in allowed_roles:
        raise HelperError("this command requires a bound role with the required capability")
    if not pane or RUNTIME_HANDLE_RE.fullmatch(pane) is None:
        raise HelperError("this command requires the exact Herdr-managed HERDR_PANE_ID")
    if bound_pane is None or _runtime_handle(bound_pane, "HERDR_ORCHESTRATOR_PANE_ID") != pane:
        raise HelperError("this command requires HERDR_ORCHESTRATOR_PANE_ID to match the exact HERDR_PANE_ID")
    if helper is None or _canonical_runtime_path(helper, "HERDR_ORCHESTRATOR_HELPER") != Path(__file__).resolve():
        raise HelperError("this command requires the canonical bound HERDR_ORCHESTRATOR_HELPER")
    if project_root is not None:
        if bound_root is None or _canonical_runtime_path(bound_root, "HERDR_ORCHESTRATOR_PROJECT_ROOT") != project_root:
            raise HelperError("this command requires a bound canonical project root")
    return role


def _route_for_assignment(config: dict[str, Any], assignment: Assignment) -> dict[str, Any]:
    if assignment.disposition.lower() == "reviewer" and assignment.authority != "read-only":
        raise HelperError("Reviewer Assignments must be read-only")
    if assignment.review_cycle > config["assessment_after_cycles"] and assignment.convergence_assessment is None:
        raise HelperError("review_cycle beyond assessment_after_cycles requires convergence_assessment")
    disposition = assignment.disposition.strip().lower()
    route_name = disposition if disposition in ROUTED_DISPOSITIONS else "default"
    route = config["routing"][route_name]
    recipe_name = assignment.recipe or route["default_recipe"]
    if recipe_name not in route["allowed_recipes"]:
        raise HelperError(f"assignment recipe is not allowed for routing.{route_name}")
    recipe = config["peer_recipes"].get(recipe_name)
    if recipe is None:
        raise HelperError("assignment recipe must name an exact configured peer_recipes entry")
    if recipe["cost_class"] == "elevated" and assignment.cost_approval is None:
        raise HelperError("elevated recipe requires verbatim Human cost approval in Assignment.cost_approval")
    if recipe["cost_class"] == "standard" and assignment.cost_approval is not None:
        raise HelperError("standard recipe must not carry elevated-cost approval evidence")
    return {"name": route_name, "default_recipe": route["default_recipe"], "allowed_recipes": route["allowed_recipes"], "recipe_name": recipe_name, "recipe": recipe}


def _assignment_worktree(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"kind", "workspace_id", "source_project_root"}:
        raise HelperError("worktree must be null or contain exactly kind, workspace_id, and source_project_root")
    if _required_text(value["kind"], "worktree.kind") != "herdr_worktree":
        raise HelperError("worktree.kind must be herdr_worktree")
    return {
        "kind": "herdr_worktree",
        "workspace_id": _runtime_handle(_required_text(value["workspace_id"], "worktree.workspace_id"), "worktree.workspace_id"),
        "source_project_root": str(_canonical_runtime_path(value["source_project_root"], "worktree.source_project_root")),
    }


def command_start_peer(args: argparse.Namespace) -> dict[str, Any]:
    """Start one configured Peer without reconstructing its native recipe."""
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    project_root = _require_directory(Path(assignment.project_root), "assignment project root")
    _require_capability(frozenset({"lead"}), project_root=project_root)
    validation = command_validate_project(argparse.Namespace(project_root=str(project_root), config=None, protocol=None))
    config = _parse_project_config(_read(project_root / ".orchestration/herdr-orchestrator.toml", "project config"), "project config")
    route = _route_for_assignment(config, assignment)
    recipe = route["recipe"]
    name = _runtime_handle(assignment.owner, "assignment.owner")
    pane = _runtime_handle(args.pane, "pane")
    native_args = list(recipe["args"])
    herdr_argv = [
        "herdr", "agent", "start", name, "--kind", recipe["kind"], "--pane", pane,
        "--", *native_args,
    ]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "start-peer",
        "assignment_id": assignment.assignment_id,
        "project_root": assignment.project_root,
        "disposition": assignment.disposition,
        "routing": {"name": route["name"], "default_recipe": route["default_recipe"]},
        "recipe": {"name": route["recipe_name"], "kind": recipe["kind"], "args": native_args, "cost_class": recipe["cost_class"]},
        "cost_approval": assignment.cost_approval,
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
    project_root = _require_directory(Path(args.project_root), "project root")
    _require_capability(frozenset({"launcher", "lead", "supervisor"}), project_root=project_root)
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
        "project_root": str(project_root),
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


def _candidate_document_from_value(value: Any, label: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Read the canonical v2 candidate envelope; raw identities are never review evidence."""
    if isinstance(value, dict) and "candidate" in value:
        required = {"schema_version", "candidate", "synthetic_commit", "artifact_scope", "excluded_path_prefixes", "diff"}
        if set(value) != required:
            raise HelperError(f"{label} has unsupported or missing fields")
        if value["schema_version"] != CANDIDATE_SCHEMA_VERSION:
            raise HelperError(f"{label}.schema_version must be {CANDIDATE_SCHEMA_VERSION}")
        candidate = _candidate_from_document(value["candidate"])
        if candidate is None:
            raise HelperError(f"{label}.candidate must be immutable")
        if candidate["kind"] != "git_tree":
            raise HelperError(f"{label}.candidate must be a canonical Git tree candidate")
        synthetic_commit = _required_text(value["synthetic_commit"], f"{label}.synthetic_commit")
        if GIT_COMMIT_RE.fullmatch(synthetic_commit) is None:
            raise HelperError(f"{label}.synthetic_commit must be an exact lowercase 40-character hash")
        scope = _required_text(value["artifact_scope"], f"{label}.artifact_scope")
        if scope != "project-worktree-excluding-project-control":
            raise HelperError(f"{label}.artifact_scope must be the canonical application scope")
        prefixes = _text_list(value["excluded_path_prefixes"], f"{label}.excluded_path_prefixes", 1)
        if tuple(prefixes) != CANDIDATE_EXCLUDED_PREFIXES:
            raise HelperError(f"{label}.excluded_path_prefixes must use the canonical project-control exclusions")
        diff = value["diff"]
        if not isinstance(diff, dict) or set(diff) != {"path", "sha256", "bytes"}:
            raise HelperError(f"{label}.diff must contain exactly path, sha256, and bytes")
        diff_path = _canonical_relative_path(diff["path"], f"{label}.diff.path")
        if not diff_path.startswith(".orchestration/candidates/") or not diff_path.endswith(".diff"):
            raise HelperError(f"{label}.diff.path must be a candidate-specific immutable diff path")
        if not isinstance(diff["bytes"], int) or isinstance(diff["bytes"], bool) or diff["bytes"] < 0 or diff["bytes"] > MAX_CANDIDATE_DIFF_BYTES:
            raise HelperError(f"{label}.diff.bytes is invalid")
        diff_sha256 = _required_text(diff["sha256"], f"{label}.diff.sha256")
        if SHA256_RE.fullmatch(diff_sha256) is None:
            raise HelperError(f"{label}.diff.sha256 must be a lowercase SHA-256 digest")
        return candidate, {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "candidate": candidate,
            "synthetic_commit": synthetic_commit,
            "artifact_scope": scope,
            "excluded_path_prefixes": list(prefixes),
            "diff": {"path": diff_path, "sha256": diff_sha256, "bytes": diff["bytes"]},
        }
    raise HelperError(f"{label} must be a canonical candidate document")


def _assignment_from_document(value: Any) -> Assignment:
    fields = {"schema_version", "assignment_id", "role", "parent", "owner", "project_root", "worktree", "objective", "owned_scope", "exclusions", "authority", "disposition", "recipe", "verification", "dependencies", "languages", "topology_rationale", "candidate", "review_cycle", "prior_review", "convergence_assessment", "cost_approval"}
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
    project_root = str(_canonical_runtime_path(value["project_root"], "project_root"))
    worktree = _assignment_worktree(value["worktree"])
    authority = _required_text(value["authority"], "authority")
    scope = tuple(_canonical_scope(item, f"owned_scope[{index}]") for index, item in enumerate(_text_list(value["owned_scope"], "owned_scope")))
    if authority not in {"read-only", "write"} or len(set(scope)) != len(scope) or (authority == "write" and not scope):
        raise HelperError("assignment authority or owned_scope is invalid")
    candidate = _candidate_from_document(value["candidate"])
    disposition = _required_text(value["disposition"], "disposition")
    if disposition.lower() == "peer":
        raise HelperError("disposition must describe work, not repeat role=peer")
    recipe = value["recipe"]
    if recipe is not None:
        recipe = _required_text(recipe, "recipe")
    rationale = value["topology_rationale"]
    if rationale is not None:
        rationale = _required_text(rationale, "topology_rationale")
    cycle = value["review_cycle"]
    if not isinstance(cycle, int) or isinstance(cycle, bool) or cycle < 1 or cycle > 1024:
        raise HelperError("review_cycle must be a positive bounded integer")
    prior_review = value["prior_review"]
    prior_fields = ("reviewer_assignment_id", "reviewer_assignment_sha256", "reviewer_handback_sha256")
    if cycle == 1:
        if prior_review is not None:
            raise HelperError("prior_review must be null for review_cycle 1")
    elif not isinstance(prior_review, dict) or set(prior_review) != set(prior_fields):
        raise HelperError("prior_review must bind exact prior Reviewer Assignment and handback digests after cycle 1")
    if prior_review is not None:
        prior_review = {
            field: _required_text(prior_review[field], f"prior_review.{field}")
            for field in prior_fields
        }
        if ASSIGNMENT_ID_RE.fullmatch(prior_review["reviewer_assignment_id"]) is None or any(
            SHA256_RE.fullmatch(prior_review[field]) is None
            for field in ("reviewer_assignment_sha256", "reviewer_handback_sha256")
        ):
            raise HelperError("prior_review must use an exact Reviewer Assignment id and lowercase Assignment/handback SHA-256 digests")
    assessment = value["convergence_assessment"]
    if assessment is not None:
        if not isinstance(assessment, dict) or set(assessment) != {"mechanisms", "decision", "rationale"}:
            raise HelperError("convergence_assessment must contain exactly mechanisms, decision, and rationale")
        mechanisms = assessment["mechanisms"]
        if not isinstance(mechanisms, list) or not mechanisms or len(mechanisms) > 64:
            raise HelperError("convergence_assessment.mechanisms must be a bounded nonempty array")
        grouped_findings: list[dict[str, Any]] = []
        for index, mechanism in enumerate(mechanisms):
            label = f"convergence_assessment.mechanisms[{index}]"
            if not isinstance(mechanism, dict) or set(mechanism) != {"mechanism", "findings"}:
                raise HelperError(f"{label} must contain exactly mechanism and findings")
            grouped_findings.append({
                "mechanism": _required_text(mechanism["mechanism"], f"{label}.mechanism"),
                "findings": list(_text_list(mechanism["findings"], f"{label}.findings", 1)),
            })
        decision = _required_text(assessment["decision"], "convergence_assessment.decision")
        if decision not in CONVERGENCE_DECISIONS:
            raise HelperError("convergence_assessment.decision must be continue, re-architect, escalate, or block")
        assessment = {
            "mechanisms": grouped_findings,
            "decision": decision,
            "rationale": _required_text(assessment["rationale"], "convergence_assessment.rationale"),
        }
    cost_approval = value["cost_approval"]
    if cost_approval is not None:
        cost_approval = _required_text(cost_approval, "cost_approval")
    return Assignment(assignment_id, role, parent, owner, project_root, worktree, _required_text(value["objective"], "objective"), scope, _text_list(value["exclusions"], "exclusions"), authority, disposition, recipe, _text_list(value["verification"], "verification", 1), _text_list(value["dependencies"], "dependencies"), _string_map(value["languages"], "languages", {"live", "artifact"}), rationale, candidate, cycle, prior_review, assessment, cost_approval)


def _assignment_document(assignment: Assignment) -> dict[str, Any]:
    return {"schema_version": ASSIGNMENT_SCHEMA_VERSION, "assignment_id": assignment.assignment_id, "role": assignment.role, "parent": assignment.parent, "owner": assignment.owner, "project_root": assignment.project_root, "worktree": assignment.worktree, "objective": assignment.objective, "owned_scope": list(assignment.owned_scope), "exclusions": list(assignment.exclusions), "authority": assignment.authority, "disposition": assignment.disposition, "recipe": assignment.recipe, "verification": list(assignment.verification), "dependencies": list(assignment.dependencies), "languages": assignment.languages, "topology_rationale": assignment.topology_rationale, "candidate": assignment.candidate, "review_cycle": assignment.review_cycle, "prior_review": assignment.prior_review, "convergence_assessment": assignment.convergence_assessment, "cost_approval": assignment.cost_approval}


def command_validate_assignment(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    if args.structural_only:
        if args.project_root:
            raise HelperError("--structural-only cannot be combined with --project-root")
        return _assignment_document(assignment)
    root = _require_directory(Path(args.project_root), "project root") if args.project_root else _require_directory(
        Path(assignment.project_root), "assignment project root"
    )
    if str(root) != assignment.project_root:
        raise HelperError("assignment project_root does not match validation project root")
    config = _parse_project_config(
        _read(root / ".orchestration/herdr-orchestrator.toml", "project config"), "project config"
    )
    _route_for_assignment(config, assignment)
    return _assignment_document(assignment)


def command_validate_control_role_launch(args: argparse.Namespace) -> dict[str, Any]:
    """Validate the Human cost decision before a Lead/Supervisor native launch."""
    root = _require_directory(Path(args.project_root), "project root")
    config = _parse_project_config(
        _read(root / ".orchestration/herdr-orchestrator.toml", "project config"), "project config"
    )
    role = _required_text(args.role, "role")
    recipe = config["roles"].get(role)
    if recipe is None:
        raise HelperError("control role must name a configured lead or supervisor")
    approval = _required_text(args.cost_approval, "cost approval") if args.cost_approval else None
    if recipe["cost_class"] == "elevated" and approval is None:
        raise HelperError("elevated control-role recipe requires verbatim Human cost approval")
    if recipe["cost_class"] == "standard" and approval is not None:
        raise HelperError("standard control-role recipe must not carry elevated-cost approval")
    return {"command": "validate-control-role-launch", "project_root": str(root), "role": role, "recipe": recipe, "cost_approval": approval}


def command_render_assignment(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    profile = _safe_text(_read(Path(args.role_profile), "role profile"), "role profile")
    protocol = _safe_text(_read(Path(args.applicable_protocol), "applicable protocol projection"), "applicable protocol projection")
    headings = [int(match.group(1)) for match in re.finditer(r"(?m)^##\s+(\d+)\.", protocol)]
    if headings == list(range(1, 13)):
        raise HelperError("Peer applicable protocol projection must not be the full Workspace Protocol")
    rendered = f"# Role Profile\n\n{profile}\n\n# Applicable Protocol Constraints\n\n{protocol}\n\n# Assignment\n\n```json\n{json.dumps(_assignment_document(assignment), ensure_ascii=False, indent=2)}\n```\n\nReturn a structured handback with this exact assignment_id. Its JSON object has exactly assignment_id, outcome, evidence, impact, and need; every value is a non-empty string; prompt delivery and Herdr lifecycle are not assignment completion.\n"
    output = Path(args.output).expanduser()
    expected_parent = Path(assignment.project_root) / ".orchestration" / "prompts"
    if not output.is_absolute():
        output = output.resolve()
    if output.parent != expected_parent:
        raise HelperError("rendered Assignment output must be directly inside <project_root>/.orchestration/prompts")
    expected_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _atomic_write(output, rendered.encode(), args.replace)
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
            if left.project_root == right.project_root:
                raise HelperError("concurrent writer Assignments require distinct project_root worktrees")
    if len(writers) >= 2:
        if args.worktree_list is None:
            raise HelperError("concurrent writer validation requires captured Herdr worktree list evidence; dispatch is blocked")
        integration_roots: set[str] = set()
        for writer in writers:
            if writer.worktree is None:
                raise HelperError("concurrent writer Assignment requires Herdr worktree allocation metadata; dispatch is blocked")
            integration_root = writer.worktree["source_project_root"]
            if writer.project_root == integration_root or not _same_git_worktree_repository(
                Path(writer.project_root), Path(integration_root)
            ):
                raise HelperError("concurrent writer project_root must be a linked Git worktree of its integration root")
            integration_roots.add(integration_root)
        if len(integration_roots) != 1:
            raise HelperError("concurrent writer worktrees must name one shared integration root")
        _validate_herdr_worktree_list(
            _json_document(Path(args.worktree_list), "Herdr worktree list"), writers, integration_roots.pop()
        )
    return {"assignment_ids": [assignment.assignment_id for assignment in assignments], "writer_assignment_ids": [assignment.assignment_id for assignment in writers], "writer_project_roots": {assignment.assignment_id: assignment.project_root for assignment in writers}, "writer_workspaces": {assignment.assignment_id: assignment.worktree["workspace_id"] for assignment in writers if assignment.worktree is not None}, "topology_rationales": {assignment.assignment_id: assignment.topology_rationale for assignment in assignments}}


def _validate_herdr_worktree_list(value: Any, writers: list[Assignment], integration_root: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
        raise HelperError("Herdr worktree list must be a native JSON object with result")
    result = value["result"]
    if result.get("type") != "worktree_list" or not isinstance(result.get("source"), dict) or not isinstance(result.get("worktrees"), list):
        raise HelperError("Herdr worktree list has unsupported or missing fields")
    source_root = str(_canonical_runtime_path(result["source"].get("repo_root"), "Herdr worktree list source.repo_root"))
    if source_root != integration_root:
        raise HelperError("Herdr worktree list source.repo_root does not match the concurrent integration root")
    bindings: set[tuple[str, str]] = set()
    for index, worktree in enumerate(result["worktrees"]):
        if not isinstance(worktree, dict):
            raise HelperError(f"Herdr worktree list worktrees[{index}] must be an object")
        try:
            path = str(_canonical_runtime_path(worktree["path"], f"Herdr worktree list worktrees[{index}].path"))
            workspace_id = _runtime_handle(_required_text(worktree["open_workspace_id"], f"Herdr worktree list worktrees[{index}].open_workspace_id"), f"Herdr worktree list worktrees[{index}].open_workspace_id")
        except KeyError as exc:
            raise HelperError(f"Herdr worktree list worktrees[{index}] has unsupported or missing fields") from exc
        bindings.add((path, workspace_id))
    missing = [assignment.assignment_id for assignment in writers if (assignment.project_root, assignment.worktree["workspace_id"] if assignment.worktree is not None else "") not in bindings]
    if missing:
        raise HelperError("Herdr worktree list does not bind every concurrent writer project_root and workspace_id: " + ", ".join(missing))


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


def _git_common_directory(project_root: Path, label: str) -> Path:
    raw = Path(_git_text(project_root, ["rev-parse", "--git-common-dir"], label))
    path = raw if raw.is_absolute() else project_root / raw
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"{label} has no resolvable Git common directory") from exc


def _git_worktree_root(project_root: Path, label: str) -> Path:
    reported = Path(_git_text(project_root, ["rev-parse", "--show-toplevel"], label))
    try:
        root = reported.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"{label} has no resolvable Git worktree root") from exc
    if root != project_root:
        raise HelperError(f"{label} must be a Git worktree root")
    return root


def _same_git_worktree_repository(project_root: Path, protocol_root: Path) -> bool:
    """Accept a declared canonical root only for a sibling checkout of one Git repo."""
    try:
        _git_worktree_root(project_root, "project Git repository")
        _git_worktree_root(protocol_root, "workspace protocol Git repository")
        return _git_common_directory(project_root, "project Git repository") == _git_common_directory(protocol_root, "workspace protocol Git repository")
    except HelperError:
        return False


def _legacy_candidate_object_directory(project_root: Path) -> Path | None:
    """Return the former worktree-local store only for one safe migration."""
    legacy = project_root / ".orchestration" / "candidate-objects"
    if not legacy.exists():
        return None
    try:
        resolved = legacy.resolve(strict=True)
        orchestration = (project_root / ".orchestration").resolve(strict=True)
        resolved.relative_to(orchestration)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"legacy candidate object storage is unavailable: {legacy}: {exc}") from exc
    if not resolved.is_dir() or resolved.is_symlink():
        raise HelperError(f"legacy candidate object storage is not a directory: {resolved}")
    return resolved


def _files_match(source: Path, target: Path) -> bool:
    """Compare a legacy object without trusting its path or metadata."""
    try:
        if source.stat().st_size != target.stat().st_size:
            return False
        with source.open("rb") as source_stream, target.open("rb") as target_stream:
            while True:
                source_chunk = source_stream.read(1024 * 1024)
                target_chunk = target_stream.read(1024 * 1024)
                if source_chunk != target_chunk:
                    return False
                if not source_chunk:
                    return True
    except OSError as exc:
        raise HelperError(f"could not verify legacy candidate object migration: {exc}") from exc


def _migrate_legacy_candidate_object_directory(legacy: Path, target: Path) -> None:
    """Copy, verify, then remove the old worktree-visible private object store."""
    try:
        for source in sorted(legacy.rglob("*")):
            relative = source.relative_to(legacy)
            destination = target / relative
            if source.is_symlink():
                raise HelperError(f"legacy candidate object storage contains a symlink: {relative}")
            if source.is_dir():
                destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if not source.is_file():
                raise HelperError(f"legacy candidate object storage contains a non-file: {relative}")
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if destination.exists():
                if destination.is_symlink() or not destination.is_file() or not _files_match(source, destination):
                    raise HelperError(f"legacy candidate object conflicts with common metadata store: {relative}")
                continue
            shutil.copyfile(source, destination, follow_symlinks=False)
            if not _files_match(source, destination):
                raise HelperError(f"legacy candidate object migration did not preserve {relative}")
        shutil.rmtree(legacy)
    except HelperError:
        raise
    except OSError as exc:
        raise HelperError(f"could not migrate legacy candidate object storage: {exc}") from exc


def _candidate_object_directory(project_root: Path, *, create: bool) -> Path:
    """Return the private candidate object store under common Git metadata.

    Candidate objects must be outside every worktree: otherwise a normal Git
    status mistakes immutable review data for application changes.  The common
    directory is shared deliberately by sibling worktrees of one repository,
    while the ``herdr-orchestrator`` namespace keeps this private store
    separate from Git's normal ``objects`` database.
    """
    common = _git_common_directory(project_root, "project Git common directory")
    path = common / "herdr-orchestrator" / "candidate-objects"
    legacy = _legacy_candidate_object_directory(project_root)
    try:
        if path.is_symlink():
            raise HelperError(f"candidate object storage must not be a symlink: {path}")
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if legacy is not None:
                _migrate_legacy_candidate_object_directory(legacy, path)
        resolved = path.resolve(strict=True)
        resolved.relative_to(common)
    except FileNotFoundError as exc:
        if legacy is not None:
            # Existing candidates remain inspectable without a write.  The next
            # freeze invokes the create path above, verifies the copy, and
            # removes this worktree-visible compatibility store.
            return legacy
        raise HelperError(
            f"candidate object storage is missing: {path}; it is required to read the immutable candidate"
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise HelperError(f"candidate object storage is unavailable: {path}: {exc}") from exc
    if resolved == common or not resolved.is_dir():
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
    """Keep candidate writes out of worktrees and normal Git objects."""
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


def _git_commit_exists_in_environment(project_root: Path, commit: str, environment: dict[str, str]) -> bool:
    return subprocess.run(
        ["git", "-C", str(project_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False, capture_output=True, env=environment,
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


def _verify_candidate_document(project_root: Path, candidate: dict[str, str], document: dict[str, Any], label: str) -> bytes:
    _verify_candidate(project_root, candidate, label)
    _verify_synthetic_candidate_commit(project_root, candidate, document["synthetic_commit"], label)
    diff_path = _require_file(project_root / document["diff"]["path"], f"{label} immutable diff")
    try:
        diff_path.relative_to(project_root / ".orchestration" / "candidates")
    except ValueError as exc:
        raise HelperError(f"{label} immutable diff escapes candidate storage") from exc
    diff = _read(diff_path, f"{label} immutable diff")
    if len(diff) != document["diff"]["bytes"] or _sha256(diff) != document["diff"]["sha256"]:
        raise HelperError(f"{label} immutable diff digest is corrupt")
    if diff != _candidate_diff(project_root, candidate):
        raise HelperError(f"{label} immutable diff does not match the exact candidate")
    return diff


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


def _candidate_document(candidate: dict[str, str], synthetic_commit: str, diff_path: str, diff: bytes) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate": candidate,
        "synthetic_commit": synthetic_commit,
        "artifact_scope": "project-worktree-excluding-project-control",
        "excluded_path_prefixes": list(CANDIDATE_EXCLUDED_PREFIXES),
        "diff": {"path": diff_path, "sha256": _sha256(diff), "bytes": len(diff)},
    }


def _candidate_path_is_excluded(path: bytes) -> bool:
    if any(part == b"__pycache__" for part in path.split(b"/")):
        return True
    return path.endswith((b".pyc", b".pyo")) or any(
        path == prefix.encode("utf-8") or path.startswith(prefix.encode("utf-8") + b"/")
        for prefix in CANDIDATE_EXCLUDED_PREFIXES
    )


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
            ["add", "-u", "--", ".", *(f":(exclude){path}" for path in CANDIDATE_EXCLUDED_PREFIXES)],
            "candidate tracked-path update",
            environment=environment,
        )
        untracked = _git(
            project_root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            "candidate untracked-path traversal",
            environment=environment,
        ).stdout
        application_paths = [path for path in untracked.split(b"\0") if path and not _candidate_path_is_excluded(path)]
        if application_paths:
            _git(
                project_root,
                ["add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"],
                "candidate untracked-path update",
                environment=environment,
                input_data=b"\0".join(application_paths) + b"\0",
            )
        tree = _git_text(project_root, ["write-tree"], "candidate tree freeze", environment=environment)
    if GIT_COMMIT_RE.fullmatch(tree) is not None:
        _ensure_candidate_tree_stored(project_root, tree)
    if GIT_COMMIT_RE.fullmatch(tree) is None or not _candidate_tree_is_stored(project_root, tree):
        raise HelperError("candidate freeze did not produce an immutable Git tree")
    return tree


def _synthetic_candidate_commit(project_root: Path, candidate: dict[str, str]) -> str:
    """Create a reproducible review commit entirely in the candidate object store."""
    base_time = _git_text(project_root, ["show", "-s", "--format=%aI", candidate["base_commit"]], "candidate base timestamp")
    environment = _candidate_git_environment(project_root, create=True)
    environment.update({
        "GIT_AUTHOR_NAME": "Herdr Candidate",
        "GIT_AUTHOR_EMAIL": "herdr-candidate@invalid",
        "GIT_COMMITTER_NAME": "Herdr Candidate",
        "GIT_COMMITTER_EMAIL": "herdr-candidate@invalid",
        "GIT_AUTHOR_DATE": base_time,
        "GIT_COMMITTER_DATE": base_time,
    })
    message = f"Herdr candidate {candidate['tree']}\n".encode()
    commit = _git_text(
        project_root,
        ["commit-tree", candidate["tree"], "-p", candidate["base_commit"]],
        "candidate synthetic commit",
        environment=environment,
        input_data=message,
    )
    if GIT_COMMIT_RE.fullmatch(commit) is None:
        raise HelperError("candidate synthetic commit did not produce an exact Git commit")
    return commit


def _verify_synthetic_candidate_commit(project_root: Path, candidate: dict[str, str], commit: str, label: str) -> None:
    environment = _candidate_git_environment(project_root, create=False)
    if not _git_commit_exists_in_environment(project_root, commit, environment):
        raise HelperError(f"{label} synthetic commit is absent from candidate object storage")
    parent = _git_text(project_root, ["show", "-s", "--format=%P", commit], f"{label} synthetic commit", environment=environment)
    tree = _git_text(project_root, ["show", "-s", "--format=%T", commit], f"{label} synthetic commit", environment=environment)
    if parent != candidate["base_commit"] or tree != candidate["tree"]:
        raise HelperError(f"{label} synthetic commit does not bind the exact base and candidate tree")


def command_freeze_candidate(args: argparse.Namespace) -> dict[str, Any]:
    """Atomically freeze a tree, synthetic review commit, immutable diff, and projection."""
    project_root = _repository_root(Path(args.project_root))
    _require_capability(frozenset({"lead"}), project_root=project_root)
    base_commit = _git_text(project_root, ["rev-parse", "HEAD"], "candidate base commit")
    tree = _freeze_application_tree(project_root, base_commit)
    candidate = {"kind": "git_tree", "base_commit": base_commit, "tree": tree}
    synthetic_commit = _synthetic_candidate_commit(project_root, candidate)
    _verify_synthetic_candidate_commit(project_root, candidate, synthetic_commit, "candidate")
    diff = _candidate_diff(project_root, candidate)
    diff_relative = f".orchestration/candidates/{synthetic_commit}.diff"
    diff_path = project_root / diff_relative
    if diff_path.exists():
        existing = _read(diff_path, "candidate-specific immutable diff")
        if existing != diff:
            raise HelperError("candidate-specific immutable diff path already exists with different content")
    else:
        diff_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _atomic_write(diff_path, diff)
    document = _candidate_document(candidate, synthetic_commit, diff_relative, diff)
    document_data = (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode()
    target = _check_output(project_root / ".orchestration/current-candidate.json", replace=True)
    temporary: Path | None = None
    try:
        descriptor, raw = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(raw)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document_data)
            stream.flush()
            os.fsync(stream.fileno())
        persisted_candidate, persisted_document = _candidate_document_from_value(
            _json_document(temporary, "staged candidate publication"),
            "staged candidate publication",
        )
        assert persisted_document is not None
        _verify_candidate_document(project_root, persisted_candidate, persisted_document, "staged candidate publication")
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise HelperError(f"could not publish current candidate: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "command": "freeze-candidate",
        "path": str(target),
        "document_sha256": _sha256(document_data),
        "candidate": candidate,
        "synthetic_commit": synthetic_commit,
        "diff_path": str(diff_path),
        "diff_sha256": _sha256(diff),
        "head_unchanged": base_commit,
        "real_index": "not used",
        "object_store": str(_candidate_object_directory(project_root, create=False)),
    }


def _new_absolute_directory(path: str, label: str) -> Path:
    requested = Path(path)
    if not requested.is_absolute():
        raise HelperError(f"{label} must be a new canonical absolute path")
    parent = _require_directory(requested.parent, f"{label} parent")
    target = parent / requested.name
    if str(target) != str(requested) or target.exists():
        raise HelperError(f"{label} must be a new canonical absolute path")
    return target


def _git_worktree_roots(project_root: Path) -> tuple[Path, ...]:
    """List every worktree of this repository so a projection cannot pollute one."""
    raw = _git_text(project_root, ["worktree", "list", "--porcelain"], "candidate materialization worktree list")
    roots: list[Path] = []
    for line in raw.splitlines():
        if line.startswith("worktree "):
            try:
                roots.append(Path(line.removeprefix("worktree ")).resolve(strict=True))
            except (OSError, RuntimeError, ValueError) as exc:
                raise HelperError("candidate materialization worktree list has an unresolved path") from exc
    if not roots:
        raise HelperError("candidate materialization worktree list has no worktree roots")
    return tuple(roots)


def _require_reviewer_peer_binding(role: str, assignment: Assignment) -> None:
    if role != "peer":
        return
    if os.environ.get("HERDR_ORCHESTRATOR_ASSIGNMENT_ID") != assignment.assignment_id:
        raise HelperError("Reviewer materialization requires the pane-bound exact Assignment id")
    if os.environ.get("HERDR_ORCHESTRATOR_OWNER") != assignment.owner:
        raise HelperError("Reviewer materialization requires the pane-bound exact Assignment owner")


def command_materialize_candidate(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "review assignment"))
    project_root = _repository_root(Path(assignment.project_root))
    role = _require_capability(frozenset({"lead", "peer"}), project_root=project_root)
    if assignment.disposition.lower() != "reviewer" or assignment.authority != "read-only":
        raise HelperError("materialization requires a read-only Reviewer Assignment")
    _require_reviewer_peer_binding(role, assignment)
    current_path = project_root / ".orchestration/current-candidate.json"
    current, document = _candidate_document_from_value(_json_document(current_path, "current candidate"), "current candidate")
    if assignment.candidate != current:
        raise HelperError("review assignment candidate is stale; materialization requires the exact current candidate")
    assert document is not None
    diff = _verify_candidate_document(project_root, current, document, "current candidate")
    target = _new_absolute_directory(args.output, "materialized candidate output")
    for worktree_root in _git_worktree_roots(project_root):
        try:
            target.relative_to(worktree_root)
        except ValueError:
            continue
        raise HelperError("materialized candidate output must be outside every project worktree")
    try:
        initialized = subprocess.run(["git", "init", "-q", str(target)], check=False, capture_output=True)
    except OSError as exc:
        raise HelperError(f"materialized candidate repository initialization could not invoke Git: {exc}") from exc
    if initialized.returncode:
        raise HelperError("materialized candidate repository initialization failed")
    try:
        packed = _git(
            project_root,
            ["pack-objects", "--stdout", "--revs"],
            "candidate materialization pack",
            environment=_candidate_git_environment(project_root, create=False),
            input_data=(document["synthetic_commit"] + "\n").encode(),
        ).stdout
        _git(target, ["index-pack", "--stdin", "--fix-thin"], "candidate materialization object import", input_data=packed)
        _git(target, ["checkout", "-q", "--detach", document["synthetic_commit"]], "candidate materialization checkout")
        if _git_text(target, ["status", "--porcelain"], "candidate materialization cleanliness"):
            raise HelperError("candidate materialization checkout is not clean")
        if _git_text(target, ["rev-parse", "HEAD"], "candidate materialization HEAD") != document["synthetic_commit"]:
            raise HelperError("candidate materialization HEAD does not bind the synthetic candidate commit")
    except Exception:
        # The destination remains diagnosable; do not delete user-visible paths
        # that may have captured evidence from a failed filesystem operation.
        raise
    git_metadata = target / ".git"
    for root, directories, files in os.walk(target):
        directory = Path(root)
        if directory == git_metadata or git_metadata in directory.parents:
            continue
        for name in files:
            (directory / name).chmod(0o444)
        # Leave directories writable: tests/builds need cache and output paths,
        # and normal recursive cleanup needs writable parents. Source blobs stay
        # read-only; the receipt plus synthetic commit remain the authority.
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "command": "materialize-candidate",
        "assignment_id": assignment.assignment_id,
        "base_commit": current["base_commit"],
        "synthetic_commit": document["synthetic_commit"],
        "tree": current["tree"],
        "path": str(target),
        "candidate_document_sha256": _sha256(_read(current_path, "current candidate")),
        "diff_sha256": _sha256(diff),
        "diff_bytes": len(diff),
        "read_only": True,
        "filesystem_permissions": "application-files-read-only-directories-writable-git-metadata-writable",
    }


def command_validate_review(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "review assignment"))
    project_root = _repository_root(Path(args.project_root))
    current, document = _candidate_document_from_value(
        _json_document(Path(args.current_candidate), "current candidate"), "current candidate"
    )
    assert document is not None
    if assignment.project_root != str(project_root):
        raise HelperError("review Assignment project_root does not match the validation project root")
    _verify_candidate_document(project_root, current, document, "current candidate")
    return _validate_review_assignment(assignment, project_root, current)


def _validate_review_assignment(assignment: Assignment, project_root: Path, current: dict[str, str]) -> dict[str, Any]:
    if assignment.role != "peer" or assignment.authority != "read-only" or assignment.disposition.lower() != "reviewer" or assignment.candidate is None:
        raise HelperError("review requires a read-only Reviewer assignment with an immutable candidate")
    if assignment.project_root != str(project_root):
        raise HelperError("review Assignment project_root does not match the candidate project root")
    config = _parse_project_config(
        _read(project_root / ".orchestration/herdr-orchestrator.toml", "project config"), "project config"
    )
    _route_for_assignment(config, assignment)
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
    _require_capability(frozenset({"lead", "launcher"}), project_root=project_root)
    candidate_path = project_root / ".orchestration/current-candidate.json"
    current_candidate, candidate_document = _candidate_document_from_value(
        _json_document(candidate_path, "current candidate"), "current candidate"
    )
    assert candidate_document is not None
    _verify_candidate_document(project_root, current_candidate, candidate_document, "current candidate")
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
    pane_binding.add_argument("--assignment")
    pane_binding.add_argument("--output", required=True)
    pane_binding.add_argument("--replace", action="store_true")
    pane_binding.set_defaults(handler=command_render_runtime_binding_pane)
    peer_start = commands.add_parser("start-peer")
    peer_start.add_argument("--assignment", required=True)
    peer_start.add_argument("--pane", required=True)
    peer_start.add_argument("--dry-run", action="store_true")
    peer_start.set_defaults(handler=command_start_peer)
    prompt = commands.add_parser("submit-prompt")
    prompt.add_argument("--agent", required=True)
    prompt.add_argument("--prompt-file", required=True)
    prompt.add_argument("--project-root", required=True)
    prompt.set_defaults(handler=command_submit_prompt)
    assignment = commands.add_parser("validate-assignment")
    assignment.add_argument("--assignment", required=True)
    assignment.add_argument("--project-root")
    assignment.add_argument("--structural-only", action="store_true")
    assignment.set_defaults(handler=command_validate_assignment)
    control = commands.add_parser("validate-control-role-launch")
    control.add_argument("--project-root", required=True)
    control.add_argument("--role", required=True)
    control.add_argument("--cost-approval")
    control.set_defaults(handler=command_validate_control_role_launch)
    render = commands.add_parser("render-assignment")
    render.add_argument("--assignment", required=True); render.add_argument("--role-profile", required=True); render.add_argument("--applicable-protocol", required=True); render.add_argument("--output", required=True); render.add_argument("--replace", action="store_true")
    render.set_defaults(handler=command_render_assignment)
    delegation = commands.add_parser("validate-delegation")
    delegation.add_argument("--assignment", action="append", required=True)
    delegation.add_argument("--worktree-list")
    delegation.set_defaults(handler=command_validate_delegation)
    freeze = commands.add_parser("freeze-candidate")
    freeze.add_argument("--project-root", default=".")
    freeze.set_defaults(handler=command_freeze_candidate)
    materialize = commands.add_parser("materialize-candidate")
    materialize.add_argument("--assignment", required=True)
    materialize.add_argument("--output", required=True)
    materialize.set_defaults(handler=command_materialize_candidate)
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
