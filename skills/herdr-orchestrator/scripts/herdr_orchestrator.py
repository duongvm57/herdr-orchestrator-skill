#!/usr/bin/env python3
"""Validate Herdr project policy and render SLP contracts.

This helper has no pane, process, session, wait, prompt, or lifecycle control.
Those mechanics belong to installed Herdr and its release-matched Agent Skill.
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

from herdr_harnesses import ADAPTERS, VERIFIED_HARNESS_KINDS, HarnessError, get_adapter


SCHEMA_VERSION = 1
PROJECT_CONFIG_VERSION = 3
ASSIGNMENT_SCHEMA_VERSION = 1
MAX_RECIPE_ARGUMENTS = 64
MAX_RECIPE_ARGUMENT_BYTES = 1024
PLACEHOLDER_RE = re.compile(r"^\s*(?:todo|tbd|unknown|n/?a|yyyy-mm-dd)\s*$", re.I)
SENSITIVE_LITERAL_RE = re.compile(
    r"(?i)(?:\bsk-[a-z0-9][a-z0-9_-]{8,}\b|\b(?:api[-_]?key|access[-_]?token|"
    r"password|secret|credential)\b|\bbearer\s+|(?:\$|%)[{A-Za-z_][^}\r\n]*|@[A-Za-z0-9_./~-]+)"
)
ASSIGNMENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SEMANTIC_OUTCOMES = frozenset({"COMPLETE", "REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED"})
LANGUAGE_FIELDS = ("Live orchestration language", "Durable Markdown artifact language")
PROTOCOL_LABELS: tuple[tuple[str, ...], ...] = (
    ("Owner", "Version", "Last reviewed", "Repository root", "Readers", *LANGUAGE_FIELDS),
    ("Criticality", "Dominant risks", "Expensive-to-reverse decisions", "External side effects", "Model/cost budget"),
    ("Lead may decide", "Human must decide", "Edit/commit/push/deploy/publish authority", "Scope-expansion boundary", "Architecture contracts reserved for Human review", "Prohibited without explicit Human authority"),
    ("Tiny", "Bounded implementation", "Cross-module or lifecycle-sensitive", "Architecture lock-in", "Subjective/product evidence"),
    ("Configured recipe capabilities and access constraints", "Selection by Assignment risk, independence, cost, and required access", "Recipe reuse or mixing across dynamically created Peers", "Specialized miss, configured fallback recipe, and out-of-envelope escalation"),
    ("Fresh Architect required when", "Fresh Reviewer required when", "Sealed council allowed when", "Same-Engineer correction rule"),
    ("One writer per moving scope", "Worktree rules for concurrent writers", "Exclusive resources", "Handback and integration owner"),
    ("Allowed identity forms (commit or deterministic base/diff/artifact digest)", "Candidate freeze and replacement rules"),
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
    if value["kind"] == "frozen_snapshot":
        candidate = _string_map(value, "candidate", {"kind", "base_commit", "artifact_path", "sha256"})
        if GIT_COMMIT_RE.fullmatch(candidate["base_commit"]) is None:
            raise HelperError("candidate frozen snapshot base_commit must be an exact lowercase 40-character hash")
        if SHA256_RE.fullmatch(candidate["sha256"]) is None:
            raise HelperError("candidate frozen snapshot sha256 must be a lowercase SHA-256 digest")
        artifact = candidate["artifact_path"]
        if artifact.startswith("/") or "\\" in artifact or any(part in {"", ".", ".."} for part in artifact.split("/")):
            raise HelperError("candidate frozen snapshot artifact_path must be a canonical project-relative path")
        return candidate
    raise HelperError("candidate.kind must be git_commit or frozen_snapshot")


def _json_document(path: Path, label: str) -> Any:
    try:
        return json.loads(_safe_text(_read(path, label), label))
    except json.JSONDecodeError as exc:
        raise HelperError(f"{label} must be valid JSON: {exc}") from exc


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


def _git_commit_exists(project_root: Path, commit: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(project_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _verify_candidate(project_root: Path, candidate: dict[str, str], label: str) -> None:
    if candidate["kind"] == "git_commit":
        if not _git_commit_exists(project_root, candidate["value"]):
            raise HelperError(f"{label} Git commit must exist in project root")
        return
    if not _git_commit_exists(project_root, candidate["base_commit"]):
        raise HelperError(f"{label} frozen snapshot base commit must exist in project root")
    snapshot = _require_file(project_root / candidate["artifact_path"], f"{label} frozen snapshot artifact")
    if _sha256(_read(snapshot, f"{label} frozen snapshot artifact")) != candidate["sha256"]:
        raise HelperError(f"{label} frozen snapshot artifact digest does not match its immutable candidate")


def command_validate_review(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "review assignment"))
    project_root = _require_directory(Path(args.project_root), "project root")
    current = _candidate_from_document(_json_document(Path(args.current_candidate), "current candidate"))
    if current is None:
        raise HelperError("current candidate must be an immutable candidate document")
    if assignment.role != "peer" or assignment.authority != "read-only" or assignment.disposition.lower() != "reviewer" or assignment.candidate is None:
        raise HelperError("review requires a read-only Reviewer assignment with an immutable candidate")
    candidate = assignment.candidate
    _verify_candidate(project_root, candidate, "review candidate")
    _verify_candidate(project_root, current, "current candidate")
    if candidate != current:
        raise HelperError("review candidate is stale; create a new candidate and fresh review assignment")
    return {"assignment_id": assignment.assignment_id, "candidate": candidate, "review_applicable": True}


def command_validate_handback(args: argparse.Namespace) -> dict[str, Any]:
    assignment = _assignment_from_document(_json_document(Path(args.assignment), "assignment"))
    handback = _json_document(Path(args.handback), "handback")
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
    return {"assignment_id": assignment.assignment_id, "handback": result, "completion": "semantic_handback"}


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
    assignment = commands.add_parser("validate-assignment")
    assignment.add_argument("--assignment", required=True)
    assignment.set_defaults(handler=command_validate_assignment)
    render = commands.add_parser("render-assignment")
    render.add_argument("--assignment", required=True); render.add_argument("--role-profile", required=True); render.add_argument("--applicable-protocol", required=True); render.add_argument("--output", required=True); render.add_argument("--replace", action="store_true")
    render.set_defaults(handler=command_render_assignment)
    delegation = commands.add_parser("validate-delegation")
    delegation.add_argument("--assignment", action="append", required=True)
    delegation.set_defaults(handler=command_validate_delegation)
    review = commands.add_parser("validate-review")
    review.add_argument("--assignment", required=True); review.add_argument("--current-candidate", required=True); review.add_argument("--project-root", default=".")
    review.set_defaults(handler=command_validate_review)
    handback = commands.add_parser("validate-handback")
    handback.add_argument("--assignment", required=True); handback.add_argument("--handback", required=True)
    handback.set_defaults(handler=command_validate_handback)
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
