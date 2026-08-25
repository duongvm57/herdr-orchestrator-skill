#!/usr/bin/env python3
"""Thin Herdr runtime for starting and coordinating orchestration agents."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from typing import Any, Sequence

import herdr_orchestrator as core


AGENT_NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}\Z")
DEFAULT_TIMEOUT_MS = 120_000


class RuntimeError_(RuntimeError):
    """A user-actionable runtime failure."""


class CommandFailure(RuntimeError_):
    def __init__(self, argv: Sequence[str], completed: subprocess.CompletedProcess[str]):
        self.argv = tuple(argv)
        self.completed = completed
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        super().__init__(f"Herdr command failed ({completed.returncode}): {detail}")


def _run(argv: Sequence[str], *, timeout_seconds: float = 30.0) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RuntimeError_(f"executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError_(f"command timed out: {' '.join(argv[:3])}") from exc
    except OSError as exc:
        raise RuntimeError_(f"could not execute {argv[0]}: {exc}") from exc
    if completed.returncode != 0:
        raise CommandFailure(argv, completed)
    return completed


def _run_json(argv: Sequence[str], *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    completed = _run(argv, timeout_seconds=timeout_seconds)
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError_(f"Herdr returned invalid JSON for {' '.join(argv[:3])}") from exc
    if not isinstance(document, dict):
        raise RuntimeError_(f"Herdr returned a non-object result for {' '.join(argv[:3])}")
    return document


def _result(document: dict[str, Any], label: str) -> dict[str, Any]:
    value = document.get("result")
    if not isinstance(value, dict):
        raise RuntimeError_(f"{label} response has no result object")
    return value


def _herdr_executable(raw: str) -> str:
    resolved = shutil.which(raw)
    if resolved is None:
        raise RuntimeError_(f"Herdr executable not found: {raw}")
    return str(Path(resolved).resolve())


def _project_root(raw: str | None) -> Path:
    value = raw or os.environ.get("HERDR_ORCHESTRATOR_PROJECT_ROOT")
    if not value:
        raise RuntimeError_(
            "project root is required; pass --project-root or launch from an orchestrator pane"
        )
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RuntimeError_(f"project root is unavailable: {value}: {exc}") from exc
    if not root.is_dir():
        raise RuntimeError_(f"project root is not a directory: {root}")
    return root


def _load_project(root: Path) -> tuple[dict[str, Any], str]:
    config_path = root / ".orchestration/herdr-orchestrator.toml"
    protocol_path = root / ".orchestration/workspace-protocol.md"
    config = core._parse_project_config(core._read(config_path, "project config"), "project config")
    protocol_data = core._read(protocol_path, "Workspace Protocol")
    protocol = core._parse_protocol(protocol_data, "Workspace Protocol")
    core._require_protocol_repository(protocol, root)
    return config, core._decode_safe_text(protocol_data, "Workspace Protocol")


def _role_profile(role: str) -> str:
    path = Path(__file__).resolve().parent.parent / "references" / "roles" / f"{role}.md"
    return core._decode_safe_text(core._read(path, f"{role} role profile"), f"{role} role profile")


def _safe_text(value: str, label: str, *, limit: int = 48_000) -> str:
    if not value.strip() or "\0" in value or len(value.encode("utf-8")) > limit:
        raise RuntimeError_(f"{label} must be nonempty and at most {limit} UTF-8 bytes")
    return value.strip()


def _cwd(root: Path, raw: str | None) -> Path:
    requested = root if raw is None else Path(raw).expanduser()
    if not requested.is_absolute():
        requested = root / requested
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError_(f"agent cwd is unavailable: {requested}: {exc}") from exc
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise RuntimeError_("agent cwd must be a directory inside the configured project root")
    return resolved


def _agent_name(role: str) -> str:
    prefix = {"lead": "lead", "peer": "peer", "supervisor": "supervisor"}[role]
    return f"herdr-{prefix}-{secrets.token_hex(3)}"


def _current_rect(herdr: str) -> dict[str, int]:
    current_id = os.environ.get("HERDR_PANE_ID")
    if not current_id:
        raise RuntimeError_("HERDR_PANE_ID is required")
    layout = _result(
        _run_json([herdr, "pane", "layout", "--current"]),
        "Herdr pane layout",
    ).get("layout")
    if not isinstance(layout, dict) or not isinstance(layout.get("panes"), list):
        raise RuntimeError_("Herdr pane layout is malformed")
    for pane in layout["panes"]:
        if isinstance(pane, dict) and pane.get("pane_id") == current_id:
            rect = pane.get("rect")
            if isinstance(rect, dict):
                try:
                    return {key: int(rect[key]) for key in ("width", "height")}
                except (KeyError, TypeError, ValueError):
                    break
    raise RuntimeError_("current pane is absent from its Herdr layout")


def _split(herdr: str, root: Path, cwd: Path) -> str:
    rect = _current_rect(herdr)
    direction = "right" if rect["width"] >= rect["height"] * 2 else "down"
    document = _run_json(
        [
            herdr,
            "pane",
            "split",
            "--current",
            "--direction",
            direction,
            "--cwd",
            str(cwd),
            "--env",
            f"HERDR_ORCHESTRATOR_PROJECT_ROOT={root}",
            "--no-focus",
        ]
    )
    pane = _result(document, "Herdr pane split").get("pane")
    if not isinstance(pane, dict) or not isinstance(pane.get("pane_id"), str):
        raise RuntimeError_("Herdr pane split returned no pane ID")
    return pane["pane_id"]


def _peer_profiles(config: dict[str, Any]) -> str:
    return "\n".join(
        f"- {name}: {recipe['description']}"
        for name, recipe in sorted(config["peer_recipes"].items())
    )


def _operation_contract(root: Path, *, include_peer_start: bool) -> str:
    script = Path(__file__).resolve()
    common = f'python3 "{script}"'
    operations = [
        f'- Read a settled agent: `{common} result --agent <name>`',
        f'- Continue an agent: `{common} prompt --agent <name> --text "<message>" --wait`',
    ]
    if include_peer_start:
        operations.insert(
            0,
            f'- Start a Peer: `{common} start --role peer --profile <profile> '
            f'--project-root "{root}" --task "<bounded task>"`',
        )
    return "\n".join(operations)


def _prompt_for(
    role: str,
    task: str,
    root: Path,
    config: dict[str, Any],
    protocol: str,
    *,
    profile: str | None,
    constraints: str | None,
) -> str:
    profile_text = _role_profile(role)
    if role == "lead":
        assignment = (
            f"## Human task\n\n{task}\n\n"
            f"## Available Peer profiles\n\n{_peer_profiles(config)}\n\n"
            f"## Runtime operations\n\n{_operation_contract(root, include_peer_start=True)}"
        )
        protocol_text = protocol
    elif role == "peer":
        assert profile is not None
        applicable = constraints or "Follow the bounded task, configured profile authority, and repository instructions."
        assignment = (
            f"## Bounded Assignment\n\nDisposition: Peer\nProfile: {profile}\n"
            f"Profile description: {config['peer_recipes'][profile]['description']}\n\n"
            f"Task:\n{task}\n\n## Result contract\n\n"
            "Return the bounded result in your normal agent response."
        )
        protocol_text = f"## Applicable protocol constraints\n\n{applicable}"
    else:
        assignment = f"## Observation scope\n\n{task}"
        protocol_text = (
            protocol
            if constraints == "full-protocol"
            else "## Applicable protocol constraints\n\nObserve only the assigned scope; project mutation and Peer orchestration are outside this mandate."
        )
    return (
        f"# Role Profile\n\n{profile_text}\n\n"
        f"# Workspace Protocol\n\n{protocol_text}\n\n"
        f"# Assignment\n\n{assignment}\n"
    )


def _recipe(config: dict[str, Any], role: str, profile: str | None) -> tuple[str | None, dict[str, Any]]:
    if role == "lead":
        recipe = config["roles"]["lead"]
        core.get_adapter(recipe["kind"]).validate_control_plane(recipe["args"], "roles.lead")
        return None, recipe
    if role == "supervisor":
        recipe = config["roles"].get("supervisor")
        if recipe is None:
            raise RuntimeError_("this project has no configured Supervisor recipe")
        core.get_adapter(recipe["kind"]).validate_control_plane(
            recipe["args"], "roles.supervisor"
        )
        return None, recipe
    if not profile or PROFILE_RE.fullmatch(profile) is None:
        raise RuntimeError_("Peer start requires one exact configured --profile")
    recipe = config["peer_recipes"].get(profile)
    if recipe is None:
        choices = ", ".join(sorted(config["peer_recipes"]))
        raise RuntimeError_(f"unknown Peer profile {profile!r}; available: {choices}")
    return profile, recipe


def _is_agent_not_ready(error: CommandFailure) -> bool:
    return "agent_not_ready" in (error.completed.stderr + error.completed.stdout)


def _is_agent_blocked(error: CommandFailure) -> bool:
    return "agent_blocked" in (error.completed.stderr + error.completed.stdout)


def _agent_snapshot(herdr: str, agent: str, *, lines: int = 120) -> dict[str, Any]:
    info = _result(_run_json([herdr, "agent", "get", agent]), "Herdr agent get").get("agent")
    if not isinstance(info, dict):
        raise RuntimeError_("Herdr agent get returned no agent")
    output = _run(
        [herdr, "agent", "read", agent, "--source", "recent-unwrapped", "--lines", str(lines)]
    ).stdout
    return {
        "agent": agent,
        "pane_id": info.get("pane_id"),
        "state": info.get("agent_status", "unknown"),
        "output": output,
    }


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("HERDR_ENV") != "1":
        raise RuntimeError_("HERDR_ENV=1 is required")
    herdr = _herdr_executable(args.herdr)
    root = _project_root(args.project_root)
    config, protocol = _load_project(root)
    profile, recipe = _recipe(config, args.role, args.profile)
    cwd = _cwd(root, args.cwd)
    task = _safe_text(args.task, "task")
    constraints = _safe_text(args.constraints, "constraints") if args.constraints else None
    name = args.name or _agent_name(args.role)
    if AGENT_NAME_RE.fullmatch(name) is None:
        raise RuntimeError_(f"agent name must match {AGENT_NAME_RE.pattern!r}")
    pane = _split(herdr, root, cwd)
    start_argv = [
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
    ]
    try:
        _run(start_argv, timeout_seconds=300.0)
    except CommandFailure as exc:
        if not _is_agent_not_ready(exc):
            raise
        snapshot = _agent_snapshot(herdr, name)
        if snapshot["state"] not in {"idle", "done", "blocked"}:
            try:
                _run_json(
                    [herdr, "agent", "wait", name, "--timeout", "30000"],
                    timeout_seconds=35.0,
                )
            except (CommandFailure, RuntimeError_):
                pass
            snapshot = _agent_snapshot(herdr, name)
        if snapshot["state"] not in {"idle", "done"}:
            return {
                "command": "start",
                "status": "blocked_startup",
                "role": args.role,
                "profile": profile,
                **snapshot,
            }
    prompt = _prompt_for(
        args.role,
        task,
        root,
        config,
        protocol,
        profile=profile,
        constraints=constraints,
    )
    try:
        _run([herdr, "agent", "prompt", name, prompt])
    except CommandFailure as exc:
        if not _is_agent_blocked(exc):
            raise
        return {
            "command": "start",
            "status": "blocked_startup",
            "role": args.role,
            "profile": profile,
            **_agent_snapshot(herdr, name),
        }
    if args.focus:
        _run([herdr, "agent", "focus", name])
    return {
        "command": "start",
        "status": "prompted",
        "role": args.role,
        "profile": profile,
        "agent": name,
        "pane_id": pane,
    }


def command_result(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("HERDR_ENV") != "1":
        raise RuntimeError_("HERDR_ENV=1 is required")
    herdr = _herdr_executable(args.herdr)
    argv = [herdr, "agent", "wait", args.agent, "--timeout", str(args.timeout)]
    wait = _result(
        _run_json(argv, timeout_seconds=args.timeout / 1000 + 5),
        "Herdr agent wait",
    )
    return {"command": "result", "wait": wait, **_agent_snapshot(herdr, args.agent, lines=args.lines)}


def command_prompt(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("HERDR_ENV") != "1":
        raise RuntimeError_("HERDR_ENV=1 is required")
    herdr = _herdr_executable(args.herdr)
    text = _safe_text(args.text, "message")
    argv = [herdr, "agent", "prompt", args.agent, text]
    if args.wait:
        argv.extend(["--wait", "--timeout", str(args.timeout)])
    try:
        response = _result(
            _run_json(argv, timeout_seconds=(args.timeout / 1000 + 5) if args.wait else 30.0),
            "Herdr agent prompt",
        )
    except CommandFailure as exc:
        if not _is_agent_blocked(exc):
            raise
        return {"command": "prompt", "status": "blocked", **_agent_snapshot(herdr, args.agent, lines=args.lines)}
    result: dict[str, Any] = {"command": "prompt", "delivery": response, "agent": args.agent}
    if args.wait:
        result.update(_agent_snapshot(herdr, args.agent, lines=args.lines))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--herdr", default="herdr", help="Herdr executable")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start and prompt one fresh orchestration agent")
    start.add_argument("--role", choices=("lead", "peer", "supervisor"), required=True)
    start.add_argument("--project-root")
    start.add_argument("--profile")
    start.add_argument("--task", required=True)
    start.add_argument("--constraints")
    start.add_argument("--cwd")
    start.add_argument("--name")
    start.add_argument("--focus", action="store_true")
    start.set_defaults(handler=command_start)

    result = subparsers.add_parser("result", help="wait for and read one agent")
    result.add_argument("--agent", required=True)
    result.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS)
    result.add_argument("--lines", type=int, default=120)
    result.set_defaults(handler=command_result)

    prompt = subparsers.add_parser("prompt", help="send one continuation to an agent")
    prompt.add_argument("--agent", required=True)
    prompt.add_argument("--text", required=True)
    prompt.add_argument("--wait", action="store_true")
    prompt.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS)
    prompt.add_argument("--lines", type=int, default=120)
    prompt.set_defaults(handler=command_prompt)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "timeout", DEFAULT_TIMEOUT_MS) <= 0:
        raise RuntimeError_("timeout must be greater than zero")
    if getattr(args, "lines", 120) <= 0:
        raise RuntimeError_("lines must be greater than zero")
    result = args.handler(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError_, core.HelperError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
