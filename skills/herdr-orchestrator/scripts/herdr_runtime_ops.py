"""High-level, harness-neutral Herdr runtime lifecycle operations.

The Launcher binds infrastructure truth once. Lead and Peer wrappers then call
these operations with project decisions or technical results; they never need
Herdr CLI syntax, mailbox layout, pack construction, or evidence mechanics.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


RUNTIME_SCHEMA_VERSION = 1
REQUEST_SCHEMA_VERSION = 1
COMMAND_TIMEOUT_SECONDS = 30.0
NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
GIT_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,64}\Z")
READ_ONLY_DISPOSITIONS = frozenset(
    {"architect", "reviewer", "scout", "proof auditor"}
)
ALLOWED_DISPOSITIONS = frozenset(
    {
        "engineer",
        "architect",
        "reviewer",
        "scout",
        "proof auditor",
        "feature owner",
    }
)
RESULT_LIST_FIELDS = (
    "changed",
    "verification",
    "findings",
    "risks",
    "unfinished_dependencies",
)
SUPERVISOR_FIELDS = (
    "observation",
    "evidence",
    "suspected_mechanism",
    "impact",
    "question",
    "recommendation",
    "escalation",
    "protocol_candidate",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _run_dir(core: ModuleType, raw: str) -> Path:
    requested = Path(raw).expanduser()
    if not requested.is_absolute():
        raise core.HelperError("run directory must be absolute")
    run_dir = core._require_directory(requested, "run directory")
    manifest = core._load_run_manifest(run_dir / "run-manifest.json")
    core._verify_run_artifacts(run_dir, manifest)
    if manifest["run_id"] != run_dir.name:
        raise core.HelperError("run directory and run manifest IDs disagree")
    return run_dir


def _load_json(core: ModuleType, path: Path, label: str) -> dict[str, Any]:
    raw = core._read(path, label)
    try:
        value = json.loads(core._decode_utf8(raw, label))
    except json.JSONDecodeError as exc:
        raise core.HelperError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise core.HelperError(f"{label} must be a JSON object")
    return value


def _safe_text(core: ModuleType, value: Any, label: str, *, maximum: int = 20_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise core.HelperError(f"{label} must be a nonempty string")
    text = value.strip()
    if len(text.encode("utf-8")) > maximum or "\0" in text:
        raise core.HelperError(f"{label} exceeds its safe text boundary")
    return text


def _string_list(
    core: ModuleType,
    value: Any,
    label: str,
    *,
    required: bool = False,
) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value):
        raise core.HelperError(f"{label} must be a {'nonempty ' if required else ''}array")
    if len(value) > 128:
        raise core.HelperError(f"{label} has too many entries")
    return [_safe_text(core, item, f"{label}[{index}]", maximum=4_000) for index, item in enumerate(value)]


def _run_process(
    core: ModuleType,
    argv: list[str],
    label: str,
    *,
    timeout: float = COMMAND_TIMEOUT_SECONDS,
    json_output: bool = False,
) -> Any:
    try:
        completed = subprocess.run(
            argv,
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise core.HelperError(f"{label} executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise core.HelperError(f"{label} timed out") from exc
    except OSError as exc:
        raise core.HelperError(f"could not execute {label}: {exc}") from exc
    if completed.returncode != 0:
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        raise core.HelperError(
            f"{label} failed with exit status {completed.returncode} "
            f"(stdout_sha256={_sha256(stdout)}, stderr_sha256={_sha256(stderr)})"
        )
    if not json_output:
        return completed
    try:
        value = json.loads((completed.stdout or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise core.HelperError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise core.HelperError(f"{label} returned a non-object JSON value")
    return value


def _canonical_executable(core: ModuleType, raw: str) -> str:
    value = _safe_text(core, raw, "Herdr executable", maximum=4_096)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        resolved = shutil.which(value)
        if resolved is None:
            raise core.HelperError(f"Herdr executable not found: {value}")
        candidate = Path(resolved)
    try:
        candidate = candidate.resolve(strict=True)
    except OSError as exc:
        raise core.HelperError(f"Herdr executable is unavailable: {candidate}: {exc}") from exc
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise core.HelperError(f"Herdr executable is not executable: {candidate}")
    return str(candidate)


def _herdr_result(core: ModuleType, document: dict[str, Any], label: str) -> dict[str, Any]:
    if "error" in document:
        raise core.HelperError(f"{label} returned an error")
    result = document.get("result")
    if not isinstance(result, dict):
        raise core.HelperError(f"{label} response has no result object")
    return result


def _agent_inventory(core: ModuleType, herdr: str) -> list[dict[str, Any]]:
    document = _run_process(
        core,
        [herdr, "agent", "list"],
        "Herdr agent list",
        json_output=True,
    )
    result = _herdr_result(core, document, "Herdr agent list")
    agents = result.get("agents")
    if not isinstance(agents, list) or any(not isinstance(item, dict) for item in agents):
        raise core.HelperError("Herdr agent list has an invalid agents array")
    return agents


def _unique_agent_name(core: ModuleType, herdr: str, prefix: str) -> str:
    prefix = re.sub(r"[^a-z0-9]+", "-", prefix.casefold()).strip("-") or "peer"
    prefix = prefix[:23].rstrip("-")
    existing = {
        item.get("name")
        for item in _agent_inventory(core, herdr)
        if isinstance(item.get("name"), str)
    }
    for _ in range(20):
        candidate = f"{prefix}-{secrets.token_hex(3)}"
        if NAME_RE.fullmatch(candidate) is not None and candidate not in existing:
            return candidate
    raise core.HelperError("could not allocate a collision-free agent name")


def _discover_repositories(core: ModuleType, root: Path) -> list[dict[str, str]]:
    repositories: list[Path] = []
    for current, directories, files in os.walk(root):
        directories[:] = [
            name
            for name in directories
            if name not in {".git", ".orchestration", "node_modules", ".venv", "venv"}
        ]
        path = Path(current)
        if (path / ".git").exists():
            repositories.append(path.resolve())
    if root not in repositories:
        repositories.insert(0, root)
    repositories = list(dict.fromkeys(repositories))
    result: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for repository in repositories:
        relative = repository.relative_to(root)
        identifier = "root" if relative == Path(".") else relative.as_posix()
        if identifier in used_ids:
            continue
        used_ids.add(identifier)
        git_common = _run_process(
            core,
            ["git", "-C", str(repository), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            f"Git common-directory discovery for {identifier}",
        ).stdout.decode("utf-8").strip()
        result.append(
            {
                "id": identifier,
                "path": str(repository),
                "git_common_dir": str(Path(git_common).resolve()),
            }
        )
    return result


def _append_event(core: ModuleType, run_dir: Path, event: dict[str, Any]) -> None:
    path = run_dir / "events.jsonl"
    descriptor = os.open(path, os.O_RDWR | os.O_APPEND)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        data = _json_bytes(event)
        os.write(descriptor, data)
        os.fsync(descriptor)
    except OSError as exc:
        raise core.HelperError(f"could not append run event: {exc}") from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _split_pane(
    core: ModuleType,
    run_dir: Path,
    herdr: str,
    anchor: str,
    cwd: Path,
) -> str:
    helper = run_dir / "tools/herdr_balanced_split.py"
    document = _run_process(
        core,
        [
            os.fspath(Path(os.sys.executable)),
            str(helper),
            "--state",
            str(run_dir / "tools/layout-state.json"),
            "--cwd",
            str(cwd),
            "--anchor",
            anchor,
            "--herdr",
            herdr,
        ],
        "run-local layout helper",
        json_output=True,
    )
    pane = document.get("new_pane_id")
    if not isinstance(pane, str) or not pane:
        raise core.HelperError("layout helper did not return one new pane")
    return pane


def _load_runtime(core: ModuleType, run_dir: Path) -> dict[str, Any]:
    runtime = _load_json(core, run_dir / "runtime-manifest.json", "runtime manifest")
    required = {
        "schema_version",
        "run_id",
        "project",
        "lead",
        "repositories",
        "peer_profiles",
        "fallback_peer_profile",
        "languages",
        "operations",
        "operation_contracts",
        "herdr_executable",
    }
    if set(runtime) != required or runtime.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise core.HelperError("runtime manifest has an unsupported schema")
    if runtime.get("run_id") != run_dir.name:
        raise core.HelperError("runtime manifest belongs to another run")
    return runtime


def _render_runtime_manifest(
    core: ModuleType,
    run_dir: Path,
    herdr: str,
    lead_name: str,
    lead_pane: str,
) -> dict[str, Any]:
    config_data = core._read(run_dir / "context/project-config.toml", "run config")
    config = core._parse_project_config(config_data, "run config")
    protocol_data = core._read(run_dir / "context/workspace-protocol.md", "run protocol")
    protocol = core._parse_protocol(protocol_data, "run protocol")
    repository = core._require_directory(
        Path(core._load_run_manifest(run_dir / "run-manifest.json")["repository_root"]),
        "run repository",
    )
    lead_operations = [
        os.fspath(Path(os.sys.executable)),
        str(run_dir / "tools/herdr_lead_ops.py"),
    ]
    peer_operations = [
        os.fspath(Path(os.sys.executable)),
        str(run_dir / "tools/herdr_peer_ops.py"),
    ]
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "project": {"root": str(repository)},
        "lead": {"name": lead_name, "pane_id": lead_pane},
        "repositories": _discover_repositories(core, repository),
        "peer_profiles": [
            {"name": name, "description": recipe["description"], "kind": recipe["kind"]}
            for name, recipe in config["peer_recipes"].items()
        ],
        "fallback_peer_profile": config["fallback_peer_recipe"],
        "languages": {
            "live": protocol[core.LANGUAGE_FIELDS[0]],
            "artifact": protocol[core.LANGUAGE_FIELDS[1]],
        },
        "operations": {
            "lead": lead_operations,
            "peer": peer_operations,
        },
        "operation_contracts": {
            "lead": {
                "launch_peer": {
                    "argv": [
                        *lead_operations,
                        "launch-peer",
                        "--request",
                        "<absolute-request.json>",
                    ],
                    "allowed_dispositions": [
                        "Engineer",
                        "Architect",
                        "Scout",
                        "Proof Auditor",
                        "Feature Owner",
                    ],
                    "request_example": {
                        "schema_version": REQUEST_SCHEMA_VERSION,
                        "task_id": "bounded-task",
                        "disposition": "Engineer",
                        "objective": "Own one bounded outcome",
                        "repository": "root",
                        "profile": config["fallback_peer_recipe"],
                        "project_write": True,
                        "owned_scope": ["relative/path/**"],
                        "excluded_scope": [],
                        "verification": ["exact command or acceptance check"],
                        "dependencies": [],
                        "constraints": [],
                    },
                },
                "launch_reviewer": {
                    "argv": [
                        *lead_operations,
                        "launch-reviewer",
                        "--request",
                        "<absolute-request.json>",
                    ],
                    "request_example": {
                        "schema_version": REQUEST_SCHEMA_VERSION,
                        "task_id": "review-candidate",
                        "disposition": "Reviewer",
                        "objective": "Falsify the exact candidate",
                        "repository": "root",
                        "profile": config["fallback_peer_recipe"],
                        "project_write": False,
                        "owned_scope": [],
                        "excluded_scope": [],
                        "verification": ["inspect the exact candidate"],
                        "dependencies": [],
                        "constraints": [],
                        "exact_candidate": "commit <full-git-commit-hash>",
                    },
                },
                "wait": [*lead_operations, "wait", "--agent", "<peer-name>"],
                "collect": [*lead_operations, "collect", "--agent", "<peer-name>"],
                "followup": [
                    *lead_operations,
                    "followup",
                    "--agent",
                    "<peer-name>",
                    "--message",
                    "<absolute-message-file>",
                ],
            },
        },
        "herdr_executable": herdr,
    }


def _start_agent(
    core: ModuleType,
    herdr: str,
    name: str,
    pane: str,
    recipe: dict[str, Any],
) -> None:
    _run_process(
        core,
        [
            herdr,
            "agent",
            "start",
            name,
            "--kind",
            recipe["kind"],
            "--pane",
            pane,
            "--",
            *recipe["args"],
        ],
        f"Herdr start for {name}",
        timeout=300.0,
    )


def _require_ready_agent(
    core: ModuleType,
    herdr: str,
    name: str,
    pane: str,
) -> None:
    document = _run_process(
        core,
        [herdr, "agent", "get", name],
        f"Herdr agent inspection for {name}",
        json_output=True,
    )
    agent = _herdr_result(core, document, f"Herdr agent inspection for {name}").get("agent")
    if not isinstance(agent, dict):
        raise core.HelperError("Herdr agent inspection returned no agent")
    if agent.get("name") != name or agent.get("pane_id") != pane:
        raise core.HelperError("Lead recovery identity differs from the runtime manifest")
    if agent.get("launch_pending") or not agent.get("interactive_ready"):
        raise core.HelperError("Lead is not interactively ready; resolve native startup first")


def _deliver(
    core: ModuleType,
    *,
    herdr: str,
    agent: str,
    context: Path,
    language: str,
    receipt: Path,
    opening: str,
    closing: str,
) -> dict[str, Any]:
    namespace = argparse.Namespace(
        agent=agent,
        context=str(context),
        live_language=language,
        opening=opening,
        opening_file=None,
        closing=closing,
        closing_file=None,
        herdr=herdr,
        receipt=str(receipt),
        max_bytes=core.DEFAULT_PROMPT_MAX_BYTES,
        timeout_seconds=core.DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    )
    return core.command_deliver(namespace)


def command_start_lead(args: argparse.Namespace, *, core: ModuleType) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    runtime_path = run_dir / "runtime-manifest.json"
    context = run_dir / "context/lead.md"
    if runtime_path.exists():
        if not args.resume:
            raise core.HelperError(
                "runtime manifest already exists; use --resume only after resolving native startup"
            )
        if args.repository_authority_file or args.lead_name:
            raise core.HelperError("Lead resume uses the immutable existing runtime binding")
        if (run_dir / "launcher-handoff.md").exists() or (run_dir / "lead-delivery-receipt.json").exists():
            raise core.HelperError("Lead launch progressed past startup; reconcile delivery evidence")
        runtime = _load_runtime(core, run_dir)
        runtime_data = core._read(runtime_path, "runtime manifest")
        herdr = runtime["herdr_executable"]
        lead_name = runtime["lead"]["name"]
        lead_pane = runtime["lead"]["pane_id"]
        context = core._require_file(context, "Lead context pack")
        context_data = core._read(context, "Lead context pack")
        pack_result = {
            "path": str(context),
            "bytes": len(context_data),
            "sha256": _sha256(context_data),
        }
        _require_ready_agent(core, herdr, lead_name, lead_pane)
    else:
        if args.resume:
            raise core.HelperError("Lead resume requires an existing prepared runtime binding")
        herdr = _canonical_executable(core, args.herdr)
        repository = core._require_directory(
            Path(core._load_run_manifest(run_dir / "run-manifest.json")["repository_root"]),
            "run repository",
        )
        config = core._parse_project_config(
            core._read(run_dir / "context/project-config.toml", "run config"),
            "run config",
        )
        core.get_adapter(config["roles"]["lead"]["kind"]).validate_control_plane(
            config["roles"]["lead"]["args"],
            "roles.lead",
        )
        lead_name = args.lead_name or _unique_agent_name(core, herdr, "herdr-lead")
        if NAME_RE.fullmatch(lead_name) is None:
            raise core.HelperError("Lead name has an unsupported form")
        lead_pane = _split_pane(core, run_dir, herdr, args.anchor_pane, repository)
        runtime = _render_runtime_manifest(core, run_dir, herdr, lead_name, lead_pane)
        runtime_data = _json_bytes(runtime)
        core._atomic_write(runtime_path, runtime_data)
        assignment_sources = [str(run_dir / "human-task.md"), str(runtime_path)]
        if args.repository_authority_file:
            assignment_sources.append(
                str(
                    core._require_file(
                        Path(args.repository_authority_file),
                        "repository authority",
                    )
                )
            )
        pack_result = core.command_pack(
            argparse.Namespace(
                role="lead",
                output=str(context),
                role_source=[str(run_dir / "context/lead-profile.md")],
                protocol_source=[str(run_dir / "context/workspace-protocol.md")],
                assignment_source=assignment_sources,
                max_bytes=core.DEFAULT_PROMPT_MAX_BYTES,
            )
        )
        _start_agent(core, herdr, lead_name, lead_pane, config["roles"]["lead"])
    _append_event(
        core,
        run_dir,
        {
            "schema_version": 1,
            "timestamp": _now(),
            "run_id": run_dir.name,
            "type": "launch",
            "actor": "Launcher",
            "lead": lead_name,
            "pane_id": lead_pane,
            "context_sha256": pack_result["sha256"],
        },
    )
    handoff = (
        f"# Launcher handoff\n\nRun: {run_dir.name}\nLead: {lead_name}\n"
        f"Pane: {lead_pane}\nRuntime manifest: {runtime_path}\n"
    ).encode("utf-8")
    core._atomic_write(run_dir / "launcher-handoff.md", handoff)
    delivery = _deliver(
        core,
        herdr=herdr,
        agent=lead_name,
        context=context,
        language=runtime["languages"]["live"],
        receipt=run_dir / "lead-delivery-receipt.json",
        opening=f"{runtime['languages']['live']}: đây là task và runtime binding đầy đủ của bạn.",
        closing=f"{runtime['languages']['live']}: bắt đầu bằng project judgment; dùng Lead operations khi cần Peer.",
    )
    if not args.no_focus:
        _run_process(core, [herdr, "agent", "focus", lead_name], "Herdr Lead focus")
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": "resume-lead" if args.resume else "start-lead",
        "run_id": run_dir.name,
        "run_directory": str(run_dir),
        "lead": {"name": lead_name, "pane_id": lead_pane},
        "runtime_manifest": {
            "path": str(runtime_path),
            "bytes": len(runtime_data),
            "sha256": _sha256(runtime_data),
        },
        "context": {key: pack_result[key] for key in ("path", "bytes", "sha256")},
        "delivery_receipt": delivery["receipt"],
    }


def _request(core: ModuleType, path: Path, *, reviewer: bool = False) -> dict[str, Any]:
    request = _load_json(core, core._require_file(path, "Peer request"), "Peer request")
    allowed = {
        "schema_version",
        "task_id",
        "disposition",
        "objective",
        "repository",
        "profile",
        "project_write",
        "owned_scope",
        "excluded_scope",
        "verification",
        "dependencies",
        "constraints",
        "exact_candidate",
    }
    unknown = set(request) - allowed
    if unknown:
        raise core.HelperError(f"Peer request has unsupported keys: {', '.join(sorted(unknown))}")
    if request.get("schema_version", REQUEST_SCHEMA_VERSION) != REQUEST_SCHEMA_VERSION:
        raise core.HelperError("Peer request has an unsupported schema version")
    disposition = _safe_text(core, request.get("disposition"), "Peer disposition").casefold()
    if disposition not in ALLOWED_DISPOSITIONS:
        raise core.HelperError("Peer request has an unsupported disposition")
    if reviewer and disposition != "reviewer":
        raise core.HelperError("launch-reviewer requires disposition Reviewer")
    objective = _safe_text(core, request.get("objective"), "Peer objective")
    project_write = request.get("project_write", disposition not in READ_ONLY_DISPOSITIONS)
    if type(project_write) is not bool:
        raise core.HelperError("project_write must be true or false")
    if disposition in READ_ONLY_DISPOSITIONS and project_write:
        raise core.HelperError(f"{disposition.title()} cannot request project write authority")
    candidate = request.get("exact_candidate")
    if disposition == "reviewer" and candidate is None:
        raise core.HelperError("Reviewer request requires exact_candidate")
    if candidate is not None:
        candidate = _safe_text(core, candidate, "exact_candidate", maximum=1_000)
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "task_id": _safe_text(core, request.get("task_id", "task"), "task_id", maximum=200),
        "disposition": disposition,
        "objective": objective,
        "repository": _safe_text(core, request.get("repository", "root"), "repository", maximum=500),
        "profile": request.get("profile"),
        "project_write": project_write,
        "owned_scope": _string_list(core, request.get("owned_scope"), "owned_scope", required=project_write),
        "excluded_scope": _string_list(core, request.get("excluded_scope"), "excluded_scope"),
        "verification": _string_list(core, request.get("verification"), "verification"),
        "dependencies": _string_list(core, request.get("dependencies"), "dependencies"),
        "constraints": _string_list(core, request.get("constraints"), "constraints"),
        "exact_candidate": candidate,
    }


def _select_repository(core: ModuleType, runtime: dict[str, Any], identifier: str) -> dict[str, str]:
    matches = [item for item in runtime["repositories"] if item.get("id") == identifier]
    if len(matches) != 1:
        choices = ", ".join(item.get("id", "?") for item in runtime["repositories"])
        raise core.HelperError(f"unknown repository {identifier!r}; available: {choices}")
    return matches[0]


def _verify_exact_candidate(
    core: ModuleType,
    repository: dict[str, str],
    candidate: str | None,
) -> str | None:
    if candidate is None:
        return None
    commit = candidate.removeprefix("commit ").strip()
    if GIT_COMMIT_RE.fullmatch(commit) is None:
        raise core.HelperError("exact_candidate must identify a Git commit")
    completed = _run_process(
        core,
        [
            "git",
            "-C",
            repository["path"],
            "rev-parse",
            "--verify",
            f"{commit}^{{commit}}",
        ],
        "exact candidate verification",
    )
    resolved = completed.stdout.decode("utf-8").strip().casefold()
    if re.fullmatch(r"[0-9a-f]{40,64}", resolved) is None:
        raise core.HelperError("exact candidate verification returned an invalid commit")
    return f"commit {resolved}"


def _select_profile(
    core: ModuleType,
    run_dir: Path,
    runtime: dict[str, Any],
    requested: Any,
) -> tuple[str, dict[str, Any]]:
    name = runtime["fallback_peer_profile"] if requested is None else _safe_text(core, requested, "profile", maximum=128)
    if PROFILE_RE.fullmatch(name) is None:
        raise core.HelperError("profile has an unsupported identifier")
    config = core._parse_project_config(
        core._read(run_dir / "context/project-config.toml", "run config"),
        "run config",
    )
    recipe = config["peer_recipes"].get(name)
    if recipe is None:
        raise core.HelperError(f"profile is not configured for this run: {name}")
    return name, recipe


def _markdown_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- none"


def _peer_assignment(
    request: dict[str, Any],
    runtime: dict[str, Any],
    agent: str,
    report_path: Path,
    result_path: Path,
) -> bytes:
    command = shlex.join(
        [*runtime["operations"]["peer"], "handoff", "--agent", agent, "--result", str(result_path)]
    )
    candidate = request["exact_candidate"] or "none"
    result_status = "DONE"
    candidate_json = "null"
    changed_json = json.dumps(request["owned_scope"] if request["project_write"] else [])
    reviewer_json = ""
    reviewer_result = ""
    if request["disposition"] == "reviewer":
        result_status = "APPROVE"
        commit = request["exact_candidate"].removeprefix("commit ")
        candidate_json = json.dumps({"kind": "git", "commit": commit})
        reviewer_json = """
  "review": {
    "procedure": "direct",
    "status": "DIRECT",
    "coverage_complete": true,
    "artifacts": []
  },"""
        reviewer_result = """
For Reviewer, top-level `status` is `APPROVE` only with complete coverage;
otherwise use `FINDINGS` and include findings. Nested `review.status` records
the procedure outcome (`DIRECT` or the applicable OCR status), not the verdict.
"""
    return f"""# Peer Assignment

Task: {request['task_id']}
Disposition: {request['disposition'].title()}
Objective: {request['objective']}
Project write: {'allowed only in owned scope' if request['project_write'] else 'denied'}
Exact candidate: {candidate}

## Owned scope
{_markdown_list(request['owned_scope'])}

## Excluded scope
{_markdown_list(request['excluded_scope'])}

## Verification
{_markdown_list(request['verification'])}

## Dependencies
{_markdown_list(request['dependencies'])}

## Handoff

Write one JSON result to `{result_path}` with this exact shape:

```json
{{
  "status": "{result_status}",
  "candidate": {candidate_json},
{reviewer_json}
  "changed": {changed_json},
  "verification": [
    {{"command": "<command>", "cwd": "<absolute cwd>", "exit_code": 0, "summary": "<result>"}}
  ],
  "findings": [],
  "risks": [],
  "unfinished_dependencies": [],
  "decision_needed": "none"
}}
```

Then run exactly:
{reviewer_result}

```text
{command}
```

For a failed premise use the same Peer operation wrapper with `reopen`,
`dependency`, or `blocked` instead of `handoff`. The durable report is created
atomically at `{report_path}` by the helper.
""".encode("utf-8")


def _peer_constraints(request: dict[str, Any], runtime: dict[str, Any], repository: dict[str, str]) -> bytes:
    return f"""# Assigned Workspace Protocol

- Repository: {repository['path']}
- Live language: {runtime['languages']['live']}
- Durable artifact language: {runtime['languages']['artifact']}
- Project write: {'owned scope only' if request['project_write'] else 'denied'}
- Native agent spawning: denied
- Owned scope: {', '.join(request['owned_scope']) or 'none'}
- Excluded scope: {', '.join(request['excluded_scope']) or 'none'}
- Additional constraints: {'; '.join(request['constraints']) or 'none'}
""".encode("utf-8")


def command_launch_peer(
    args: argparse.Namespace,
    *,
    core: ModuleType,
    reviewer: bool = False,
) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    runtime = _load_runtime(core, run_dir)
    request = _request(core, Path(args.request), reviewer=reviewer)
    repository = _select_repository(core, runtime, request["repository"])
    request["exact_candidate"] = _verify_exact_candidate(
        core,
        repository,
        request["exact_candidate"],
    )
    profile_name, recipe = _select_profile(core, run_dir, runtime, request["profile"])
    herdr = runtime["herdr_executable"]
    agent = _unique_agent_name(core, herdr, f"peer-{request['disposition']}")
    inbox = run_dir / "reports/inbox" / agent
    inbox.mkdir(mode=0o700)
    result_path = inbox / "result.json"
    report_path = inbox / "report.md"
    constraints_path = run_dir / "assignments" / f"{agent}-constraints.md"
    assignment_path = run_dir / "assignments" / f"{agent}.md"
    request_path = run_dir / "assignments" / f"{agent}-request.json"
    core._atomic_write(request_path, _json_bytes(request))
    core._atomic_write(constraints_path, _peer_constraints(request, runtime, repository))
    core._atomic_write(
        assignment_path,
        _peer_assignment(request, runtime, agent, report_path, result_path),
    )
    context = run_dir / "context" / f"{agent}.md"
    pack = core.command_pack(
        argparse.Namespace(
            role="peer",
            output=str(context),
            role_source=[str(run_dir / "context/peer-profile.md")],
            protocol_source=[str(constraints_path)],
            assignment_source=[str(assignment_path)],
            max_bytes=core.DEFAULT_PROMPT_MAX_BYTES,
        )
    )
    cwd = Path(repository["path"]) if request["project_write"] else inbox
    pane = _split_pane(core, run_dir, herdr, runtime["lead"]["pane_id"], cwd)
    record = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "agent": agent,
        "pane_id": pane,
        "disposition": request["disposition"],
        "profile": profile_name,
        "repository": repository,
        "project_write": request["project_write"],
        "request_path": str(request_path),
        "assignment_path": str(assignment_path),
        "context_path": str(context),
        "context_sha256": pack["sha256"],
        "inbox": str(inbox),
        "result_path": str(result_path),
        "report_path": str(report_path),
        "state": "prepared",
    }
    record_path = run_dir / "peers" / f"{agent}.json"
    core._atomic_write(record_path, _json_bytes(record))
    _start_agent(core, herdr, agent, pane, recipe)
    delivery = _deliver(
        core,
        herdr=herdr,
        agent=agent,
        context=context,
        language=runtime["languages"]["live"],
        receipt=inbox / "delivery-receipt.json",
        opening=f"{runtime['languages']['live']}: đây là bounded Assignment đầy đủ của bạn.",
        closing=f"{runtime['languages']['live']}: tập trung technical judgment và dùng Peer operations để handoff.",
    )
    record["state"] = "active"
    core._atomic_write(record_path, _json_bytes(record), replace=True)
    _append_event(
        core,
        run_dir,
        {
            "schema_version": 1,
            "timestamp": _now(),
            "run_id": run_dir.name,
            "type": "assignment",
            "actor": runtime["lead"]["name"],
            "peer": agent,
            "disposition": request["disposition"],
            "profile": profile_name,
            "context_sha256": pack["sha256"],
        },
    )
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": "launch-reviewer" if reviewer else "launch-peer",
        "peer": {"name": agent, "pane_id": pane, "disposition": request["disposition"]},
        "selection": {
            "profile": profile_name,
            "fallback": request["profile"] is None,
            "kind": recipe["kind"],
        },
        "repository": repository,
        "report_path": str(report_path),
        "delivery_receipt": delivery["receipt"],
    }


def _peer_record(core: ModuleType, run_dir: Path, agent: str) -> tuple[Path, dict[str, Any]]:
    if NAME_RE.fullmatch(agent) is None:
        raise core.HelperError("Peer name has an unsupported form")
    path = run_dir / "peers" / f"{agent}.json"
    record = _load_json(core, path, "Peer record")
    if record.get("run_id") != run_dir.name or record.get("agent") != agent:
        raise core.HelperError("Peer record identity does not match this run")
    return path, record


def _validated_candidate(
    core: ModuleType,
    value: Any,
    record: dict[str, Any],
) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise core.HelperError("candidate must be an object with a supported kind")
    kind = value["kind"].casefold()
    repository = Path(record["repository"]["path"])
    if kind == "git":
        if set(value) != {"kind", "commit"}:
            raise core.HelperError("git candidate requires exactly kind and commit")
        commit = _safe_text(core, value.get("commit"), "candidate commit", maximum=64)
        if GIT_COMMIT_RE.fullmatch(commit) is None:
            raise core.HelperError("candidate commit has an unsupported form")
        completed = _run_process(
            core,
            ["git", "-C", str(repository), "rev-parse", "--verify", f"{commit}^{{commit}}"],
            "Git candidate verification",
        )
        resolved = completed.stdout.decode("utf-8").strip().casefold()
        if re.fullmatch(r"[0-9a-f]{40,64}", resolved) is None:
            raise core.HelperError("Git candidate verification returned an invalid commit")
        return {"kind": "git", "commit": resolved}
    if kind == "artifact":
        if set(value) != {"kind", "path", "sha256"}:
            raise core.HelperError("artifact candidate requires exactly kind, path, and sha256")
        digest = _safe_text(core, value.get("sha256"), "candidate artifact SHA-256", maximum=64)
        if core.SHA256_RE.fullmatch(digest) is None:
            raise core.HelperError("candidate artifact SHA-256 is invalid")
        raw_path = Path(_safe_text(core, value.get("path"), "candidate artifact path", maximum=4_096))
        candidate = raw_path if raw_path.is_absolute() else repository / raw_path
        candidate = core._require_file(candidate, "candidate artifact")
        if not candidate.is_relative_to(repository):
            raise core.HelperError("candidate artifact must stay inside the assigned repository")
        data = core._read(candidate, "candidate artifact")
        if _sha256(data) != digest:
            raise core.HelperError("candidate artifact does not match its SHA-256")
        return {"kind": "artifact", "path": str(candidate), "sha256": digest}
    raise core.HelperError(f"unsupported candidate kind: {kind}")


def _validated_review(
    core: ModuleType,
    value: Any,
    record: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "procedure",
        "status",
        "coverage_complete",
        "artifacts",
    }:
        raise core.HelperError("Reviewer result requires a complete review receipt")
    procedure = _safe_text(core, value["procedure"], "review procedure", maximum=100)
    if procedure not in {"ocr-delegate", "direct"}:
        raise core.HelperError("review procedure must be ocr-delegate or direct")
    status = _safe_text(core, value["status"], "OCR status", maximum=100)
    allowed_statuses = {
        "USED",
        "SKILL_NOT_AVAILABLE",
        "OCR_UNAVAILABLE",
        "NON_GIT_CANDIDATE",
        "OCR_OUTPUT_UNSUPPORTED",
        "NO_REVIEWABLE_FILES",
        "CANDIDATE_CHANGED",
        "DIRECT",
    }
    if status not in allowed_statuses:
        raise core.HelperError("Reviewer result has an unsupported OCR status")
    coverage = value["coverage_complete"]
    if type(coverage) is not bool:
        raise core.HelperError("review coverage_complete must be true or false")
    artifacts_value = value["artifacts"]
    if not isinstance(artifacts_value, list) or len(artifacts_value) > 8:
        raise core.HelperError("review artifacts must be a bounded array")
    inbox = Path(record["inbox"])
    artifacts: list[dict[str, str]] = []
    for index, artifact in enumerate(artifacts_value):
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise core.HelperError(f"review artifact {index} has an unsupported schema")
        path = core._require_file(Path(artifact["path"]), f"review artifact {index}")
        if not path.is_relative_to(inbox):
            raise core.HelperError("review artifacts must stay inside the assigned inbox")
        digest = _safe_text(core, artifact["sha256"], f"review artifact {index} SHA-256", maximum=64)
        data = core._read(path, f"review artifact {index}")
        if core.SHA256_RE.fullmatch(digest) is None or _sha256(data) != digest:
            raise core.HelperError(f"review artifact {index} does not match its SHA-256")
        artifacts.append({"path": str(path), "sha256": digest})
    if status == "USED" and (procedure != "ocr-delegate" or len(artifacts) < 2):
        raise core.HelperError("OCR USED requires ocr-delegate and preview/rules artifacts")
    if status == "NO_REVIEWABLE_FILES" and (coverage or not artifacts):
        raise core.HelperError("NO_REVIEWABLE_FILES requires incomplete coverage and preview evidence")
    if procedure == "direct" and status not in {
        "DIRECT",
        "SKILL_NOT_AVAILABLE",
        "OCR_UNAVAILABLE",
        "NON_GIT_CANDIDATE",
        "OCR_OUTPUT_UNSUPPORTED",
        "NO_REVIEWABLE_FILES",
        "CANDIDATE_CHANGED",
    }:
        raise core.HelperError("direct review has an incompatible OCR status")
    return {
        "procedure": procedure,
        "status": status,
        "coverage_complete": coverage,
        "artifacts": artifacts,
    }


def _validated_result(
    core: ModuleType,
    raw: dict[str, Any],
    outcome: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    allowed = {"status", "candidate", "review", *RESULT_LIST_FIELDS, "decision_needed"}
    unknown = set(raw) - allowed
    if unknown:
        raise core.HelperError(f"Peer result has unsupported keys: {', '.join(sorted(unknown))}")
    status = _safe_text(core, raw.get("status", outcome), "result status", maximum=100)
    result: dict[str, Any] = {"outcome": outcome, "status": status}
    result["candidate"] = _validated_candidate(core, raw.get("candidate"), record)
    for field in RESULT_LIST_FIELDS:
        value = raw.get(field, [])
        if field == "verification" and isinstance(value, list) and all(isinstance(item, dict) for item in value):
            rendered: list[str] = []
            for index, item in enumerate(value):
                if set(item) != {"command", "cwd", "exit_code", "summary"}:
                    raise core.HelperError(
                        f"verification[{index}] requires command, cwd, exit_code, and summary"
                    )
                command = _safe_text(core, item.get("command"), f"verification[{index}].command", maximum=4_000)
                cwd = _safe_text(core, item.get("cwd"), f"verification[{index}].cwd", maximum=4_000)
                exit_code = item.get("exit_code")
                if type(exit_code) is not int:
                    raise core.HelperError(f"verification[{index}].exit_code must be an integer")
                summary = _safe_text(core, item.get("summary", "completed"), f"verification[{index}].summary", maximum=4_000)
                rendered.append(f"`{command}` (cwd `{cwd}`) -> exit {exit_code}: {summary}")
            result[field] = rendered
        else:
            result[field] = _string_list(core, value, field)
    result["decision_needed"] = _safe_text(
        core,
        raw.get("decision_needed", "none"),
        "decision_needed",
        maximum=4_000,
    )
    if record["disposition"] == "reviewer":
        result["review"] = _validated_review(core, raw.get("review"), record)
    elif raw.get("review") is not None:
        raise core.HelperError("only Reviewer results may include a review receipt")
    else:
        result["review"] = None
    return result


def _candidate_text(candidate: dict[str, str] | None) -> str:
    if candidate is None:
        return "none"
    if candidate["kind"] == "git":
        return f"Git commit `{candidate['commit']}`"
    return f"Artifact `{candidate['path']}` SHA-256 `{candidate['sha256']}`"


def _render_report(
    record: dict[str, Any],
    request: dict[str, Any],
    result: dict[str, Any],
) -> bytes:
    review_lines = ""
    if result["review"] is not None:
        review = result["review"]
        artifacts = ", ".join(
            f"`{item['path']}` SHA-256 `{item['sha256']}`"
            for item in review["artifacts"]
        ) or "none"
        review_lines = (
            f"Review procedure: {review['procedure']}\n"
            f"OCR status: {review['status']}\n"
            f"Complete coverage: {str(review['coverage_complete']).lower()}\n"
            f"Review artifacts: {artifacts}\n\n"
        )
    return f"""# PEER REPORT

## Type
{record['disposition'].title()}

## Task / Assignment / Disposition
{request['task_id']} / {request['objective']} / {record['disposition'].title()}

## Outcome or request
{result['outcome']}: {result['status']}

## Owned and changed scope
Owned:
{_markdown_list(request['owned_scope'])}

Changed:
{_markdown_list(result['changed'])}

## Artifacts and exact candidate
{_candidate_text(result['candidate'])}

## Verification commands, cwd, and results
{_markdown_list(result['verification'])}

## Findings, assumptions, and residual risks
{review_lines}{_markdown_list([*result['findings'], *result['risks']])}

## Unfinished dependencies
{_markdown_list(result['unfinished_dependencies'])}

## Decision needed from Lead
{result['decision_needed']}
""".encode("utf-8")


def command_peer_result(
    args: argparse.Namespace,
    *,
    core: ModuleType,
    outcome: str,
) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    _path, record = _peer_record(core, run_dir, args.agent)
    inbox = core._require_directory(Path(record["inbox"]), "Peer inbox")
    supplied = core._require_file(Path(args.result), "Peer result payload")
    if not supplied.is_relative_to(inbox):
        raise core.HelperError("Peer result payload must stay inside the assigned inbox")
    raw = _load_json(core, supplied, "Peer result payload")
    result = _validated_result(core, raw, outcome, record)
    request = _load_json(core, Path(record["request_path"]), "Peer request snapshot")
    if outcome == "DONE" and record["disposition"] == "reviewer":
        if result["candidate"] is None:
            raise core.HelperError("Reviewer handoff requires the exact reviewed candidate")
        expected = request["exact_candidate"].removeprefix("commit ")
        if result["candidate"] != {"kind": "git", "commit": expected}:
            raise core.HelperError("Reviewer handoff candidate differs from its Assignment")
        if result["status"] not in {"APPROVE", "FINDINGS"}:
            raise core.HelperError("Reviewer handoff status must be APPROVE or FINDINGS")
        if result["status"] == "FINDINGS" and not result["findings"]:
            raise core.HelperError("Reviewer FINDINGS handoff requires at least one finding")
        if result["status"] == "APPROVE" and not result["review"]["coverage_complete"]:
            raise core.HelperError("Reviewer APPROVE requires complete coverage")
    accepted = inbox / "result.accepted.json"
    report = Path(record["report_path"])
    receipt = inbox / "handoff-receipt.json"
    result_data = _json_bytes(result)
    report_data = _render_report(record, request, result)
    core._atomic_write(accepted, result_data)
    core._atomic_write(report, report_data)
    receipt_value = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "run_id": run_dir.name,
        "agent": args.agent,
        "outcome": outcome,
        "result": {"path": str(accepted), "bytes": len(result_data), "sha256": _sha256(result_data)},
        "report": {"path": str(report), "bytes": len(report_data), "sha256": _sha256(report_data)},
    }
    core._atomic_write(receipt, _json_bytes(receipt_value))
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": outcome.casefold(),
        "agent": args.agent,
        "outcome": outcome,
        "report": receipt_value["report"],
        "receipt": str(receipt),
    }


def command_wait(args: argparse.Namespace, *, core: ModuleType) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    runtime = _load_runtime(core, run_dir)
    _record_path, record = _peer_record(core, run_dir, args.agent)
    if record.get("state") != "active":
        raise core.HelperError("wait requires an active Peer lifecycle")
    argv = [runtime["herdr_executable"], "agent", "wait", args.agent]
    if args.timeout_seconds is not None:
        if args.timeout_seconds <= 0:
            raise core.HelperError("timeout seconds must be greater than zero")
        argv.extend(["--timeout", str(int(args.timeout_seconds * 1000))])
    document = _run_process(core, argv, f"Herdr wait for {args.agent}", timeout=(args.timeout_seconds or 3600) + 5, json_output=True)
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": "wait",
        "agent": args.agent,
        "lifecycle": document,
    }


def command_collect(args: argparse.Namespace, *, core: ModuleType) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    if not args.no_wait:
        command_wait(args, core=core)
    record_path, record = _peer_record(core, run_dir, args.agent)
    inbox = Path(record["inbox"])
    receipt = _load_json(core, inbox / "handoff-receipt.json", "Peer handoff receipt")
    report_path = core._require_file(Path(record["report_path"]), "Peer report")
    report_data = core._read(report_path, "Peer report")
    if receipt.get("report", {}).get("sha256") != _sha256(report_data):
        raise core.HelperError("Peer report does not match its handoff receipt")
    result_path = core._require_file(inbox / "result.accepted.json", "accepted Peer result")
    result_data = core._read(result_path, "accepted Peer result")
    if receipt.get("result", {}).get("sha256") != _sha256(result_data):
        raise core.HelperError("Peer result does not match its handoff receipt")
    promoted = run_dir / "reports" / f"{args.agent}.md"
    core._atomic_write(promoted, report_data)
    record["state"] = "collected"
    record["promoted_report"] = str(promoted)
    record["report_sha256"] = _sha256(report_data)
    core._atomic_write(record_path, _json_bytes(record), replace=True)
    result = json.loads(result_data.decode("utf-8"))
    _append_event(
        core,
        run_dir,
        {
            "schema_version": 1,
            "timestamp": _now(),
            "run_id": run_dir.name,
            "type": "report",
            "actor": args.agent,
            "peer": args.agent,
            "outcome": result["outcome"],
            "report_sha256": _sha256(report_data),
        },
    )
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": "collect",
        "agent": args.agent,
        "outcome": result["outcome"],
        "result": result,
        "report": {"path": str(promoted), "bytes": len(report_data), "sha256": _sha256(report_data)},
    }


def command_followup(args: argparse.Namespace, *, core: ModuleType) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    runtime = _load_runtime(core, run_dir)
    _record_path, record = _peer_record(core, run_dir, args.agent)
    if record.get("state") != "active":
        raise core.HelperError("follow-up requires an active Peer lifecycle")
    inbox = run_dir / "reports/inbox" / args.agent
    if any(inbox.glob("followup-*.json")):
        raise core.HelperError("the bounded Peer continuation has already been used")
    message_path = core._require_file(Path(args.message), "follow-up message")
    message_data = core._read(message_path, "follow-up message")
    message = core._decode_safe_text(message_data, "follow-up message")
    if not message.strip() or len(message_data) > 32 * 1024:
        raise core.HelperError("follow-up message must be nonempty and at most 32 KiB")
    completed = _run_process(
        core,
        [runtime["herdr_executable"], "agent", "prompt", args.agent, message],
        f"Herdr follow-up for {args.agent}",
    )
    receipt = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "agent": args.agent,
        "message_sha256": _sha256(message_data),
        "stdout_sha256": _sha256(completed.stdout or b""),
        "stderr_sha256": _sha256(completed.stderr or b""),
    }
    receipt_path = inbox / f"followup-{secrets.token_hex(4)}.json"
    core._atomic_write(receipt_path, _json_bytes(receipt))
    return {"schema_version": RUNTIME_SCHEMA_VERSION, "command": "followup", "receipt": str(receipt_path)}


def _supervisor_binding(
    core: ModuleType,
    run_dir: Path,
    raw_path: str,
) -> tuple[Path, dict[str, Any]]:
    path = core._require_file(Path(raw_path), "Supervisor runtime binding")
    if not path.is_relative_to(run_dir / "supervisor"):
        raise core.HelperError("Supervisor runtime binding must stay inside the run supervisor root")
    binding = _load_json(core, path, "Supervisor runtime binding")
    required = {
        "schema_version",
        "attachment_id",
        "supervisor",
        "projects",
        "notebook_root",
        "artifact_language",
        "operations",
    }
    if set(binding) != required or binding.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise core.HelperError("Supervisor runtime binding has an unsupported schema")
    attachment = _safe_text(core, binding.get("attachment_id"), "attachment_id", maximum=32)
    if NAME_RE.fullmatch(attachment) is None:
        raise core.HelperError("attachment_id has an unsupported form")
    notebook = core._require_directory(Path(binding["notebook_root"]), "Supervisor notebook root")
    if not notebook.is_relative_to(run_dir / "supervisor"):
        raise core.HelperError("Supervisor notebook root escapes the run supervisor boundary")
    if not isinstance(binding.get("projects"), list) or not binding["projects"]:
        raise core.HelperError("Supervisor binding requires at least one project binding")
    for index, project in enumerate(binding["projects"]):
        if not isinstance(project, dict) or set(project) != {"project_id", "run_id", "evidence_root"}:
            raise core.HelperError(f"Supervisor project binding {index} has an unsupported schema")
        _safe_text(core, project.get("project_id"), f"projects[{index}].project_id", maximum=200)
        _safe_text(core, project.get("run_id"), f"projects[{index}].run_id", maximum=128)
        core._require_directory(Path(project["evidence_root"]), f"projects[{index}].evidence_root")
    _safe_text(core, binding.get("supervisor"), "supervisor", maximum=32)
    _safe_text(core, binding.get("artifact_language"), "artifact_language", maximum=200)
    operations = binding.get("operations")
    if not isinstance(operations, list) or not operations or any(not isinstance(item, str) or not item for item in operations):
        raise core.HelperError("Supervisor operations binding must be a nonempty argument vector")
    return notebook, binding


def command_supervisor_record(
    args: argparse.Namespace,
    *,
    core: ModuleType,
    record_type: str,
) -> dict[str, Any]:
    run_dir = _run_dir(core, args.run_dir)
    notebook, binding = _supervisor_binding(core, run_dir, args.binding)
    payload_path = core._require_file(Path(args.payload), "Supervisor observation payload")
    if not payload_path.is_relative_to(notebook):
        raise core.HelperError("Supervisor payload must stay inside the assigned notebook root")
    payload = _load_json(core, payload_path, "Supervisor observation payload")
    if set(payload) != set(SUPERVISOR_FIELDS):
        raise core.HelperError("Supervisor observation payload has an unsupported schema")
    values = {
        field: _safe_text(core, payload[field], field, maximum=20_000)
        for field in SUPERVISOR_FIELDS
    }
    observation_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{secrets.token_hex(3)}"
    observations = notebook / "observations"
    observations.mkdir(mode=0o700, exist_ok=True)
    observation_path = observations / f"{observation_id}.md"
    body = f"""# Supervisor {record_type.replace('_', ' ')}

- Attachment: {binding['attachment_id']}
- Supervisor: {binding['supervisor']}
- Projects: {', '.join(item['project_id'] for item in binding['projects'])}
- Observation: {values['observation']}
- Evidence: {values['evidence']}
- Suspected mechanism: {values['suspected_mechanism']}
- Impact: {values['impact']}
- Question: {values['question']}
- Recommendation: {values['recommendation']}
- Escalation: {values['escalation']}
- Protocol candidate: {values['protocol_candidate']}
""".encode("utf-8")
    core._atomic_write(observation_path, body)
    receipt_value = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "record_type": record_type,
        "attachment_id": binding["attachment_id"],
        "observation": {
            "path": str(observation_path),
            "bytes": len(body),
            "sha256": _sha256(body),
        },
        "human_attention": record_type == "human_attention",
        "handoff_recommendation": record_type == "handoff_recommendation",
        "lead_notified": False,
    }
    receipt_path = observations / f"{observation_id}.receipt.json"
    core._atomic_write(receipt_path, _json_bytes(receipt_value))
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "command": f"supervisor-{record_type.replace('_', '-')}",
        **receipt_value,
        "receipt": str(receipt_path),
    }


def register_commands(subparsers: Any, core: ModuleType) -> None:
    start = subparsers.add_parser(
        "start-lead",
        help="start and deliver one Lead from an initialized run using a runtime manifest",
    )
    start.add_argument("--run-dir", required=True)
    start.add_argument("--anchor-pane", required=True)
    start.add_argument("--herdr", default="herdr")
    start.add_argument("--lead-name")
    start.add_argument("--repository-authority-file")
    start.add_argument(
        "--resume",
        action="store_true",
        help="finish a prepared Lead launch after native interactive startup is resolved",
    )
    start.add_argument("--no-focus", action="store_true")
    start.set_defaults(handler=lambda args: command_start_lead(args, core=core))

    launch = subparsers.add_parser("lead-launch-peer", help="launch one bounded Peer from a typed request")
    launch.add_argument("--run-dir", required=True)
    launch.add_argument("--request", required=True)
    launch.set_defaults(handler=lambda args: command_launch_peer(args, core=core))

    reviewer = subparsers.add_parser("lead-launch-reviewer", help="launch one Reviewer bound to an exact candidate")
    reviewer.add_argument("--run-dir", required=True)
    reviewer.add_argument("--request", required=True)
    reviewer.set_defaults(handler=lambda args: command_launch_peer(args, core=core, reviewer=True))

    wait = subparsers.add_parser("lead-wait", help="wait for one exact run-owned Peer")
    wait.add_argument("--run-dir", required=True)
    wait.add_argument("--agent", required=True)
    wait.add_argument("--timeout-seconds", type=float)
    wait.set_defaults(handler=lambda args: command_wait(args, core=core))

    collect = subparsers.add_parser("lead-collect", help="wait for and collect one exact Peer report")
    collect.add_argument("--run-dir", required=True)
    collect.add_argument("--agent", required=True)
    collect.add_argument("--timeout-seconds", type=float)
    collect.add_argument("--no-wait", action="store_true")
    collect.set_defaults(handler=lambda args: command_collect(args, core=core))

    followup = subparsers.add_parser("lead-followup", help="send one bounded follow-up from a file")
    followup.add_argument("--run-dir", required=True)
    followup.add_argument("--agent", required=True)
    followup.add_argument("--message", required=True)
    followup.set_defaults(handler=lambda args: command_followup(args, core=core))

    for command, outcome in (
        ("peer-handoff", "DONE"),
        ("peer-reopen", "REOPEN_REQUEST"),
        ("peer-dependency", "DEPENDENCY_REQUEST"),
        ("peer-blocked", "BLOCKED"),
    ):
        parser = subparsers.add_parser(command, help=f"persist a validated {outcome} Peer result")
        parser.add_argument("--run-dir", required=True)
        parser.add_argument("--agent", required=True)
        parser.add_argument("--result", required=True)
        parser.set_defaults(
            handler=lambda args, selected=outcome: command_peer_result(
                args,
                core=core,
                outcome=selected,
            )
        )

    for command, record_type in (
        ("supervisor-record", "observation"),
        ("supervisor-human-attention", "human_attention"),
        ("supervisor-recommend-handoff", "handoff_recommendation"),
    ):
        parser = subparsers.add_parser(command, help=f"persist one {record_type} Supervisor record")
        parser.add_argument("--run-dir", required=True)
        parser.add_argument("--binding", required=True)
        parser.add_argument("--payload", required=True)
        parser.set_defaults(
            handler=lambda args, selected=record_type: command_supervisor_record(
                args,
                core=core,
                record_type=selected,
            )
        )
