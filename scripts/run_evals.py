#!/usr/bin/env python3
"""Run bounded, repeatable live evaluations of the installed skill.

This is a development/test harness.  It owns only temporary fixture copies,
temporary user scopes, newly-created Herdr panes, and ephemeral result files;
it is not an orchestration runtime, registry, journal, or lifecycle manager.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "tests/evals/orchestration-evals.json"
RESULT_SCHEMA_VERSION = 1
SUITES = {"install-materialization", "regression-orchestration", "contract-evidence", "capability-generalization"}
CASE_MODES = {"deterministic", "live", "dry-run"}
WORKFLOWS = {"single-turn", "correlate-follow-up"}
EVAL_MODEL = "gpt-5.6-luna"
EVAL_AGENT_ARGS = ("--model", EVAL_MODEL, "--sandbox", "workspace-write", "--config", "sandbox_workspace_write.network_access=true", "--ask-for-approval", "never")
CODEX_ROLE_ENVIRONMENT_ARGS = (
    "--config", 'shell_environment_policy.inherit="all"',
    "--config", "shell_environment_policy.ignore_default_excludes=false",
    "--config", "allow_login_shell=false",
    "--config", 'shell_environment_policy.filters.HOME="include"',
    "--config", 'shell_environment_policy.filters.CODEX_HOME="include"',
    "--config", 'shell_environment_policy.filters.PATH="include"',
    "--config", 'shell_environment_policy.filters.SHELL="include"',
    "--config", 'shell_environment_policy.filters.USER="include"',
    "--config", 'shell_environment_policy.filters.LOGNAME="include"',
    "--config", 'shell_environment_policy.filters.PWD="include"',
    "--config", 'shell_environment_policy.filters.TERM="include"',
    "--config", 'shell_environment_policy.filters.TMPDIR="include"',
    "--config", 'shell_environment_policy.filters.LANG="include"',
    "--config", 'shell_environment_policy.filters."LC_*"="include"',
    "--config", 'shell_environment_policy.filters.XDG_RUNTIME_DIR="include"',
    "--config", 'shell_environment_policy.filters."HERDR_*"="include"',
    "--config", 'shell_environment_policy.filters."HERDR_ORCHESTRATOR_*"="include"',
)
SLUG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")
SEMANTIC_OUTCOMES = {"COMPLETE", "REOPEN_REQUEST", "DEPENDENCY_REQUEST", "BLOCKED"}
PRIVATE_HOME_PREFIX = "home-"
PRIVATE_HOME_OWNER_FILE = ".herdr-eval-owner.json"
PRIVATE_HOME_LOCK_FILE = ".herdr-eval-home.lock"
RETAINED_EVIDENCE_SCHEMA_VERSION = 1
IGNORED_SKILL_TREE_NAMES = {"__pycache__", ".pytest_cache"}
SUPERVISOR_ROUTE_ARTIFACT = "evaluation-supervisor-routing.json"


class EvalError(Exception):
    """An invalid eval declaration or an environment failure."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvalError(f"cannot read {label}: {exc}") from exc


def _slug(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value[0] not in "abcdefghijklmnopqrstuvwxyz":
        raise EvalError(f"{label} must be lowercase kebab-case")
    if any(character not in SLUG_CHARS for character in value) or "--" in value or value.endswith("-"):
        raise EvalError(f"{label} must be lowercase kebab-case")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvalError(f"{label} must be a nonempty string")
    return value


def _relative(value: Any, label: str) -> str:
    text = _text(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise EvalError(f"{label} must be a normalized relative path")
    return text


def _scenario_invariants(root: Path) -> set[str]:
    source = _read_json(root / "tests/orchestration-scenarios.json", "scenario manifest")
    return {invariant["id"] for group in source["groups"] for invariant in group["invariants"]}


def _validate_grader(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"kind", "path", "requirements"}:
        raise EvalError(f"{label} must contain kind, path, and requirements")
    if value["kind"] != "evidence-contract":
        raise EvalError(f"{label}.kind must be evidence-contract")
    _relative(value["path"], f"{label}.path")
    requirements = value["requirements"]
    allowed = {
        "minimum_peer_agents", "exact_peer_agents", "minimum_supervisor_agents",
        "handbacks", "minimum_handbacks", "require_topology_rationale",
        "require_assignment_binding", "require_disjoint_assignment_scopes",
        "require_coupled_assignment_scopes", "require_correlation_sequence",
        "supervisor_routes", "controls", "review_controls", "handback_controls",
        "require_materialized_install", "required_handback_evidence_path",
    }
    if not isinstance(requirements, dict) or not requirements or set(requirements) - allowed:
        raise EvalError(f"{label}.requirements has unsupported or missing fields")
    for key in ("minimum_peer_agents", "minimum_supervisor_agents"):
        if key in requirements and (not isinstance(requirements[key], int) or requirements[key] < 0):
            raise EvalError(f"{label}.requirements.{key} must be a nonnegative integer")
    if "exact_peer_agents" in requirements and (not isinstance(requirements["exact_peer_agents"], int) or requirements["exact_peer_agents"] < 0):
        raise EvalError(f"{label}.requirements.exact_peer_agents must be a nonnegative integer")
    if "minimum_handbacks" in requirements and (not isinstance(requirements["minimum_handbacks"], int) or requirements["minimum_handbacks"] < 1):
        raise EvalError(f"{label}.requirements.minimum_handbacks must be a positive integer")
    if "require_topology_rationale" in requirements and requirements["require_topology_rationale"] is not True:
        raise EvalError(f"{label}.requirements.require_topology_rationale must be true when present")
    for key in ("require_assignment_binding", "require_correlation_sequence"):
        if key in requirements and requirements[key] is not True:
            raise EvalError(f"{label}.requirements.{key} must be true when present")
    if "require_disjoint_assignment_scopes" in requirements and (not isinstance(requirements["require_disjoint_assignment_scopes"], int) or requirements["require_disjoint_assignment_scopes"] < 2):
        raise EvalError(f"{label}.requirements.require_disjoint_assignment_scopes must be an integer of at least 2")
    if "require_coupled_assignment_scopes" in requirements:
        scopes = requirements["require_coupled_assignment_scopes"]
        if not isinstance(scopes, list) or len(scopes) < 2:
            raise EvalError(f"{label}.requirements.require_coupled_assignment_scopes must contain at least two scopes")
        for scope in scopes:
            _text(scope, f"{label}.requirements.require_coupled_assignment_scopes")
    if "supervisor_routes" in requirements:
        routes = requirements["supervisor_routes"]
        if not isinstance(routes, list) or not routes:
            raise EvalError(f"{label}.requirements.supervisor_routes must be a nonempty array")
        for route in routes:
            _relative(route, f"{label}.requirements.supervisor_routes")
    if "handbacks" in requirements:
        if not isinstance(requirements["handbacks"], list) or not requirements["handbacks"]:
            raise EvalError(f"{label}.requirements.handbacks must be a nonempty array")
        if any(item not in SEMANTIC_OUTCOMES for item in requirements["handbacks"]):
            raise EvalError(f"{label}.requirements.handbacks has unsupported outcome")
    if "controls" in requirements:
        controls = requirements["controls"]
        if not isinstance(controls, list) or not controls:
            raise EvalError(f"{label}.requirements.controls must be a nonempty array")
        for control in controls:
            if not isinstance(control, dict) or set(control) != {"command", "assignments", "expected_returncode"}:
                raise EvalError(f"{label}.requirements.controls entries are invalid")
            if control["command"] != "validate-delegation" or not isinstance(control["assignments"], list) or not control["assignments"]:
                raise EvalError(f"{label}.requirements.controls must declare bounded delegation checks")
            if control["expected_returncode"] not in {0, 2}:
                raise EvalError(f"{label}.requirements.controls expected_returncode must be 0 or 2")
            for path in control["assignments"]:
                _relative(path, f"{label}.requirements.controls.assignments")
    if "review_controls" in requirements:
        controls = requirements["review_controls"]
        if not isinstance(controls, list) or not controls:
            raise EvalError(f"{label}.requirements.review_controls must be a nonempty array")
        for control in controls:
            if not isinstance(control, dict) or set(control) != {"assignment", "current_candidate", "expected_returncode"}:
                raise EvalError(f"{label}.requirements.review_controls entries are invalid")
            _relative(control["assignment"], f"{label}.requirements.review_controls.assignment")
            _relative(control["current_candidate"], f"{label}.requirements.review_controls.current_candidate")
            if control["expected_returncode"] not in {0, 2}:
                raise EvalError(f"{label}.requirements.review_controls expected_returncode must be 0 or 2")
    if "handback_controls" in requirements:
        controls = requirements["handback_controls"]
        if not isinstance(controls, list) or not controls:
            raise EvalError(f"{label}.requirements.handback_controls must be a nonempty array")
        for control in controls:
            if not isinstance(control, dict) or set(control) != {"assignment", "handback", "outcome", "expected_returncode"}:
                raise EvalError(f"{label}.requirements.handback_controls entries are invalid")
            _relative(control["assignment"], f"{label}.requirements.handback_controls.assignment")
            _relative(control["handback"], f"{label}.requirements.handback_controls.handback")
            if control["outcome"] not in SEMANTIC_OUTCOMES or control["expected_returncode"] not in {0, 2}:
                raise EvalError(f"{label}.requirements.handback_controls has an invalid outcome or return code")
    if "require_materialized_install" in requirements and requirements["require_materialized_install"] is not True:
        raise EvalError(f"{label}.requirements.require_materialized_install must be true when present")
    if "required_handback_evidence_path" in requirements:
        _relative(requirements["required_handback_evidence_path"], f"{label}.requirements.required_handback_evidence_path")
    return value


def validate_suite(value: Any, root: Path = ROOT) -> dict[str, Any]:
    expected = {"schema_version", "fixture_root", "cases"}
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != 2:
        raise EvalError("eval suite must contain schema_version=2, fixture_root, and cases")
    fixture_root = _relative(value["fixture_root"], "fixture_root")
    fixtures = root / fixture_root
    if not fixtures.is_dir():
        raise EvalError("fixture_root must resolve to a directory")
    invariants = _scenario_invariants(root)
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise EvalError("cases must be a nonempty array")
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        required = {"id", "suite", "invariants", "fixture", "task", "mechanism", "workflow", "agent", "install", "topology", "repetitions", "graders", "threshold", "release_gate", "mode"}
        if not isinstance(case, dict) or set(case) != required:
            raise EvalError(f"cases[{index}] has invalid fields")
        identifier = _slug(case["id"], f"cases[{index}].id")
        if identifier in case_ids:
            raise EvalError("eval case IDs must be unique")
        case_ids.add(identifier)
        if case["suite"] not in SUITES:
            raise EvalError("eval suite class is invalid")
        if case["mode"] not in CASE_MODES:
            raise EvalError("eval mode is invalid")
        if not isinstance(case["invariants"], list) or not case["invariants"]:
            raise EvalError("eval invariants must be nonempty")
        for invariant in case["invariants"]:
            if _slug(invariant, "eval invariant") not in invariants:
                raise EvalError(f"eval invariant is not canonical: {invariant}")
        fixture = _slug(case["fixture"], f"cases[{index}].fixture")
        if not (fixtures / fixture).is_dir():
            raise EvalError(f"eval fixture does not exist: {fixture}")
        _text(case["task"], f"cases[{index}].task")
        _text(case["mechanism"], f"cases[{index}].mechanism")
        if case["workflow"] not in WORKFLOWS:
            raise EvalError("eval workflow is invalid")
        if not isinstance(case["agent"], dict) or set(case["agent"]) != {"kind", "args", "model"}:
            raise EvalError("eval agent must contain kind, args, and model")
        _slug(case["agent"]["kind"], "eval agent kind")
        if not isinstance(case["agent"]["args"], list) or not case["agent"]["args"] or any(not isinstance(arg, str) or not arg for arg in case["agent"]["args"]):
            raise EvalError("eval agent args must be a bounded nonempty native argument vector")
        if tuple(case["agent"]["args"]) != EVAL_AGENT_ARGS:
            raise EvalError("eval agent args must use the bounded Luna network-enabled recipe")
        if _text(case["agent"]["model"], "eval agent model") != EVAL_MODEL:
            raise EvalError(f"eval agent model must be {EVAL_MODEL}")
        if not isinstance(case["install"], dict) or set(case["install"]) != {"project_local", "official_skill"}:
            raise EvalError("eval install must declare project_local and official_skill")
        if case["install"] != {"project_local": True, "official_skill": "release-matched"}:
            raise EvalError("eval install must use a project-local current skill and release-matched official skill")
        if not isinstance(case["topology"], dict) or set(case["topology"]) != {"minimum_peer_agents", "minimum_supervisor_agents"}:
            raise EvalError("eval topology must declare minimum peer and supervisor agents")
        for key in case["topology"]:
            if not isinstance(case["topology"][key], int) or case["topology"][key] < 0:
                raise EvalError("eval topology counts must be nonnegative integers")
        if not isinstance(case["repetitions"], int) or case["repetitions"] < 1:
            raise EvalError("eval repetitions must be a positive integer")
        if case["release_gate"] and case["suite"] == "regression-orchestration" and case["repetitions"] != 5:
            raise EvalError("critical regression evals require exactly 5 repetitions by default")
        if not isinstance(case["graders"], dict) or set(case["graders"]) != {"functional", "hard", "quality"}:
            raise EvalError("eval graders must contain functional, hard, and quality")
        _validate_grader(case["graders"]["functional"], "functional grader")
        if not isinstance(case["graders"]["hard"], list) or not case["graders"]["hard"]:
            raise EvalError("hard graders must be a nonempty array")
        for grader in case["graders"]["hard"]:
            _validate_grader(grader, "hard grader")
        if case["graders"]["quality"] is not None:
            raise EvalError("quality grader is intentionally unsupported until an explicit bounded rubric is added")
        if not isinstance(case["threshold"], dict) or set(case["threshold"]) != {"required_passes", "rationale"}:
            raise EvalError("eval threshold must contain required_passes and rationale")
        if not isinstance(case["threshold"]["required_passes"], int) or not 1 <= case["threshold"]["required_passes"] <= case["repetitions"]:
            raise EvalError("eval threshold required_passes is invalid")
        _text(case["threshold"]["rationale"], "eval threshold rationale")
        if not isinstance(case["release_gate"], bool):
            raise EvalError("eval release_gate must be boolean")
    return value


def load_suite(path: Path, root: Path = ROOT) -> dict[str, Any]:
    return validate_suite(_read_json(path, "eval suite"), root)


def _command(arguments: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(arguments, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvalError(f"command failed to run: {' '.join(arguments[:3])}: {exc}") from exc


def _version(program: str, arguments: list[str]) -> str:
    completed = _command([program, *arguments], timeout=30)
    if completed.returncode:
        raise EvalError(f"{' '.join([program, *arguments])} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _git_revision(root: Path) -> str:
    completed = _command(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=30)
    return completed.stdout.strip() if completed.returncode == 0 else "uncommitted-checkout"


def _skill_tree_sha256(skill_root: Path) -> str:
    """Hash the complete materialized skill file tree in path/content order."""
    if not skill_root.is_dir():
        raise EvalError(f"skill tree is unavailable: {skill_root}")
    digest = hashlib.sha256()
    files = sorted(
        (path for path in skill_root.rglob("*") if path.is_file() and path.name not in IGNORED_SKILL_TREE_NAMES and not path.name.endswith(".pyc")),
        key=lambda path: path.relative_to(skill_root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(skill_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(b"file\0" + relative + b"\0" + len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def _source_provenance(source_skill: Path | None, fallback_root: Path) -> dict[str, Any]:
    if source_skill is None:
        return {"git_head": None, "git_dirty": None, "source_tree_sha256": None}
    candidate_root = source_skill.parent.parent if source_skill.name == "herdr-orchestrator" else fallback_root
    if (candidate_root / ".git").exists():
        head = _git_revision(candidate_root)
        status = _command(["git", "-C", str(candidate_root), "status", "--porcelain"], timeout=30)
        if status.returncode:
            raise EvalError(f"could not determine source checkout cleanliness: {status.stderr.strip()}")
        git_dirty: bool | None = bool(status.stdout.strip())
    else:
        head, git_dirty = None, None
    return {"git_head": head, "git_dirty": git_dirty, "source_tree_sha256": _skill_tree_sha256(source_skill)}


def _private_eval_home_root() -> Path:
    root = Path(tempfile.gettempdir()) / f"herdr-orchestrator-evals-{os.getuid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    details = root.stat()
    if details.st_uid != os.getuid() or root.is_symlink():
        raise EvalError("private eval HOME root is not owned safely by this user")
    root.chmod(0o700)
    return root


def _private_home_owner(path: Path) -> dict[str, Any] | None:
    marker = path / PRIVATE_HOME_OWNER_FILE
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return None
    if not isinstance(value.get("pid"), int) or value["pid"] <= 0:
        return None
    if not isinstance(value.get("run_id"), str) or not value["run_id"]:
        return None
    return value


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _cleanup_stale_private_eval_homes(home_root: Path) -> None:
    """Remove only dead, explicitly owned runner HOME directories.

    Callers create the owner marker while holding the root lock, so a concurrent
    runner can never mistake a newly-created but not-yet-owned HOME as stale.
    Unmanaged legacy directories are retained rather than guessed safe to delete.
    """
    for candidate in home_root.iterdir():
        if not candidate.name.startswith(PRIVATE_HOME_PREFIX) or candidate.is_symlink() or not candidate.is_dir():
            continue
        if candidate.stat().st_uid != os.getuid():
            continue
        owner = _private_home_owner(candidate)
        if owner is None or _process_is_alive(owner["pid"]):
            continue
        shutil.rmtree(candidate)


@contextmanager
def _owned_private_eval_home(home_root: Path):
    """Create one locked, live-marked private HOME and remove only that HOME."""
    lock_path = home_root / PRIVATE_HOME_LOCK_FILE
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            _cleanup_stale_private_eval_homes(home_root)
            home = Path(tempfile.mkdtemp(prefix=PRIVATE_HOME_PREFIX, dir=home_root))
            home.chmod(0o700)
            owner = {
                "schema_version": 1,
                "kind": "herdr-orchestrator-live-eval-home",
                "pid": os.getpid(),
                "run_id": uuid.uuid4().hex,
                "started_at": datetime.now(UTC).isoformat(),
            }
            marker = home / PRIVATE_HOME_OWNER_FILE
            marker.write_text(json.dumps(owner, sort_keys=True) + "\n", encoding="utf-8")
            marker.chmod(0o600)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    try:
        yield home
    finally:
        current_owner = _private_home_owner(home)
        if current_owner is not None and current_owner.get("run_id") == owner["run_id"]:
            shutil.rmtree(home, ignore_errors=True)


def _materialize_install(project: Path, home: Path, source_skill: Path | None, official_skill: str) -> dict[str, Any]:
    target = project / ".codex/skills/herdr-orchestrator"
    official_target = project / ".codex/skills/herdr"
    if source_skill is not None:
        shutil.copytree(source_skill, target, symlinks=False)
    official_target.mkdir(parents=True)
    (official_target / "SKILL.md").write_text(official_skill, encoding="utf-8")
    if source_skill is not None and (target.is_symlink() or any(path.is_symlink() for path in target.rglob("*"))):
        raise EvalError("project-local skill installation must be materialized, not symlinked")
    return {
        "mode": "materialized-project-local-copy" if source_skill is not None else "official-herdr-skill-only-control",
        "path": str(target.relative_to(project)) if source_skill is not None else None,
        "sha256": _sha256((target / "SKILL.md").read_bytes()) if source_skill is not None else None,
        "tree_sha256": _skill_tree_sha256(target) if source_skill is not None else None,
        "official_skill_path": str(official_target.relative_to(project)),
        "official_skill_sha256": _sha256(official_skill.encode()),
        "home": str(home),
    }


def _verify_materialized_install(project: Path, home: Path, installation: dict[str, Any], source_skill: Path | None, official_skill: str) -> dict[str, Any]:
    """Verify the install/isolation contract without starting an agent."""
    if home.resolve().is_relative_to(project.resolve()):
        raise EvalError("credential-bearing eval HOME must remain outside the consumer project")
    skill_path = installation.get("path")
    if source_skill is not None:
        if not isinstance(skill_path, str):
            raise EvalError("materialized current skill path is missing")
        target = project / skill_path
        if not target.is_dir() or target.is_symlink() or any(path.is_symlink() for path in target.rglob("*")):
            raise EvalError("project-local current skill must be a complete materialized non-symlink tree")
        if target.resolve() == source_skill.resolve() or installation.get("tree_sha256") != _skill_tree_sha256(target):
            raise EvalError("project-local current skill materialization/provenance is invalid")
    official_path = installation.get("official_skill_path")
    if not isinstance(official_path, str):
        raise EvalError("official Herdr skill materialization path is missing")
    official = project / official_path / "SKILL.md"
    if not official.is_file() or official.is_symlink() or _sha256(official.read_bytes()) != installation.get("official_skill_sha256") or official.read_text(encoding="utf-8") != official_skill:
        raise EvalError("official Herdr skill materialization/provenance is invalid")
    return {"materialized_installation": True, "project_local_skill": skill_path, "official_skill": official_path}


def _isolated_codex_config(agent: dict[str, str], project: Path) -> str:
    """Return the minimal, reproducible Codex config used by live eval agents."""
    return (
        f"model = {json.dumps(agent['model'])}\n"
        "model_reasoning_effort = \"low\"\n"
        "allow_login_shell = false\n\n"
        "[shell_environment_policy]\n"
        "inherit = \"all\"\n"
        "ignore_default_excludes = false\n\n"
        "[shell_environment_policy.filters]\n"
        "HOME = \"include\"\n"
        "CODEX_HOME = \"include\"\n"
        "PATH = \"include\"\n"
        "SHELL = \"include\"\n"
        "USER = \"include\"\n"
        "LOGNAME = \"include\"\n"
        "PWD = \"include\"\n"
        "TERM = \"include\"\n"
        "TMPDIR = \"include\"\n"
        "LANG = \"include\"\n"
        "\"LC_*\" = \"include\"\n"
        "XDG_RUNTIME_DIR = \"include\"\n"
        "\"HERDR_*\" = \"include\"\n"
        "\"HERDR_ORCHESTRATOR_*\" = \"include\"\n\n"
        f"[projects.{json.dumps(str(project))}]\ntrust_level = \"trusted\"\n"
    )


def _seed_provider_credential(home: Path, agent: dict[str, str], project: Path) -> str:
    """Copy only the provider login required to start an isolated eval agent.

    Credentials are not skill/config contamination.  The copy stays within the
    temporary HOME and is deleted with it; its contents are never reported.
    """
    if agent["kind"] != "codex":
        raise EvalError(f"isolated credential seeding is not implemented for agent kind: {agent['kind']}")
    source = Path.home() / ".codex/auth.json"
    target = home / ".codex/auth.json"
    if not source.is_file():
        raise EvalError("Codex authentication is unavailable for an isolated live eval")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o600)
    # A pristine zsh HOME otherwise opens its first-run interactive wizard and
    # consumes the beginning of the agent command instead of starting Codex.
    (home / ".zshrc").write_text("# isolated Herdr eval shell\n", encoding="utf-8")
    config = home / ".codex/config.toml"
    config.write_text(_isolated_codex_config(agent, project), encoding="utf-8")
    return "host provider credential plus a generated model/trust config copied into temporary HOME; no host skill or configuration copied"


def _prepare_fixture(seed: Path, project: Path) -> None:
    shutil.copytree(seed, project, symlinks=False)
    protocol = project / "WORKSPACE_PROTOCOL.md"
    if not protocol.is_file():
        raise EvalError("fixture must include WORKSPACE_PROTOCOL.md")
    orchestration = project / ".orchestration"
    orchestration.mkdir()
    role_args = [
        "--model", EVAL_MODEL, "--sandbox", "workspace-write",
        "--config", "sandbox_workspace_write.network_access=true",
        *CODEX_ROLE_ENVIRONMENT_ARGS, "--ask-for-approval", "never",
    ]
    (orchestration / "herdr-orchestrator.toml").write_text(
        "\n".join([
            "version = 3", 'fallback_peer_recipe = "eval-peer"',
            "", "[roles.lead]", 'kind = "codex"', f"args = {json.dumps(role_args)}",
            "", "[roles.supervisor]", 'kind = "codex"', f"args = {json.dumps(role_args)}",
            "", "[peer_recipes.eval-peer]",
            'description = "Bounded Luna Peer for isolated evaluation work."',
            'kind = "codex"', f"args = {json.dumps(role_args)}", "",
        ]),
        encoding="utf-8",
    )
    labels = (
        ("Owner", "Evaluation Human"), ("Version", "1"), ("Last reviewed", "2026-08-28"),
        ("Repository root", str(project)), ("Readers", "Project Lead and explicitly attached Supervisor"),
        ("Live orchestration language", "English"), ("Durable Markdown artifact language", "English"),
        ("Criticality", "bounded evaluation"), ("Dominant risks", "incorrect handoff correlation"),
        ("Expensive-to-reverse decisions", "none"), ("External side effects", "none"), ("Model/cost budget", "Luna only"),
        ("Lead may decide", "bounded evaluation evidence"), ("Human must decide", "scope expansion"),
        ("Edit/commit/push/deploy/publish authority", "evaluation artifacts only"), ("Scope-expansion boundary", "stop and report"),
        ("Architecture contracts reserved for Human review", "all durable architecture changes"), ("Prohibited without explicit Human authority", "external side effects"),
        ("Tiny", "one bounded Peer when evidence needs independent work"), ("Bounded implementation", "one Peer with exact scope"),
        ("Cross-module or lifecycle-sensitive", "record topology rationale"), ("Architecture lock-in", "Human review"), ("Subjective/product evidence", "Human decision"),
        ("Configured recipe capabilities and access constraints", "eval-peer uses isolated Codex Luna"), ("Selection by Assignment risk, independence, cost, and required access", "select eval-peer"),
        ("Recipe reuse or mixing across dynamically created Peers", "allowed for bounded independent work"), ("Specialized miss, configured fallback recipe, and out-of-envelope escalation", "use eval-peer or stop"),
        ("Fresh Architect required when", "architecture changes"), ("Fresh Reviewer required when", "candidate review"), ("Sealed council allowed when", "never"), ("Same-Engineer correction rule", "return bounded correction to same Engineer"),
        ("One writer per moving scope", "validate before writer dispatch"), ("Worktree rules for concurrent writers", "disjoint scopes only"), ("Exclusive resources", "none"), ("Handback and integration owner", "assigned Peer handback to Lead"),
        ("Allowed identity forms (Git commit or Git tree with exact base commit)", "exact commit or immutable Git tree"), ("Candidate freeze and replacement rules", "replacement needs fresh review"),
        ("Checks by task class", "validate exact Assignment and handback"), ("Independent falsification expectations", "fresh Reviewer when required"), ("Subjective/Human evidence", "escalate"), ("Minimum evidence required for Lead verdict", "validated handback"), ("Residual risk reporting", "record bounded risk"),
        ("`REOPEN_REQUEST` for failed foundations or premises", "route to Lead"), ("`DEPENDENCY_REQUEST` for another owner, API, scope, or prerequisite", "route to Lead"), ("`BLOCKED` for missing authority, external state, or Human decision", "route to Human"),
        ("Signal, evidence, suspected mechanism, open question, allowed response", "inspect before action"), ("Supervisor observation retention/export policy", "task-owned bounded artifact"), ("Supervisor project-read/notebook-write boundary", "read project, write only routing artifact"), ("Repeated-failure prerequisite check", "stop and report"),
        ("Review trigger and date", "after eval change on 2026-08-28"), ("Human approval required for material authority changes", "yes"), ("Version-history practice", "Git commits"), ("Repeated evidence required before promoting a protocol candidate", "five live repetitions"),
    )
    sections = [
        "# Evaluation workspace protocol",
        *(
            f"\n## {number}. Evaluation policy\n\n" + "\n".join(f"- {label}: {value}" for label, value in labels[start:end])
            for number, (start, end) in enumerate(((0, 7), (7, 12), (12, 18), (18, 23), (23, 27), (27, 31), (31, 35), (35, 37), (37, 42), (42, 45), (45, 49), (49, 53)), 1)
        ),
    ]
    (orchestration / "workspace-protocol.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
    (orchestration / "evaluation-evidence-template.json").write_text(
        json.dumps(
            {
                "peer_agents": [],
                "supervisor_agents": [],
                "handbacks": [],
                "dispatches": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (orchestration / "peer-assignment-template.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "assignment_id": "template-assignment",
                "role": "peer",
                "parent": {"role": "lead", "id": "template-lead"},
                "owner": "template-peer",
                "objective": "Record one bounded peer observation for the Lead.",
                "owned_scope": ["path:evidence/peer-output.json"],
                "exclusions": ["Do not create or coordinate another agent."],
                "authority": "write",
                "disposition": "Evidence collector",
                "recipe": "eval-peer",
                "verification": ["Validate the structured handback against this Assignment."],
                "dependencies": [],
                "languages": {"live": "English", "artifact": "English"},
                "topology_rationale": None,
                "candidate": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for command in (["git", "init", "-q"], ["git", "config", "user.email", "eval@example.invalid"], ["git", "config", "user.name", "Herdr Eval"], ["git", "add", "."], ["git", "commit", "-qm", "fixture seed"]):
        completed = _command(command, cwd=project, timeout=30)
        if completed.returncode:
            raise EvalError(f"could not prepare fixture Git history: {completed.stderr.strip()}")


def _relative_evidence_path(project: Path, raw: Any, label: str) -> Path:
    path = _relative(raw, label)
    candidate = project / path
    if not candidate.is_file():
        raise EvalError(f"{label} does not name a project-owned file")
    return candidate


def _run_delegation_control(project: Path, assignments: list[Any]) -> int:
    helper = project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
    if not helper.is_file():
        raise EvalError("materialized Assignment helper is unavailable for external grading")
    command = [sys.executable, str(helper), "validate-delegation"]
    for raw in assignments:
        command.extend(["--assignment", str(_relative_evidence_path(project, raw, "control assignment"))])
    return _command(command, cwd=project, timeout=30).returncode


def _run_review_control(project: Path, assignment: Any, current_candidate: Any) -> int:
    helper = project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
    if not helper.is_file():
        raise EvalError("materialized Assignment helper is unavailable for external grading")
    return _command([sys.executable, str(helper), "validate-review", "--assignment", str(_relative_evidence_path(project, assignment, "review control assignment")), "--current-candidate", str(_relative_evidence_path(project, current_candidate, "review control current candidate")), "--project-root", str(project)], cwd=project, timeout=30).returncode


def _run_handback_control(project: Path, assignment: Any, handback: Any) -> int:
    helper = project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
    if not helper.is_file():
        raise EvalError("materialized Assignment helper is unavailable for external grading")
    return _command([sys.executable, str(helper), "validate-handback", "--assignment", str(_relative_evidence_path(project, assignment, "handback control assignment")), "--handback", str(_relative_evidence_path(project, handback, "handback control handback"))], cwd=project, timeout=30).returncode


def _validate_materialized_project(project: Path) -> None:
    helper = project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
    completed = _command([sys.executable, str(helper), "validate-project", "--project-root", str(project)], cwd=project, timeout=30)
    if completed.returncode:
        raise EvalError(f"materialized eval project preflight failed: {completed.stderr.strip()}")


def _write_eval_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _deterministic_assignment(assignment_id: str, owner: str, scopes: list[str], *, authority: str = "write", disposition: str = "Engineer", candidate: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "assignment_id": assignment_id,
        "role": "peer",
        "parent": {"role": "lead", "id": "deterministic-lead"},
        "owner": owner,
        "objective": "Validate one bounded deterministic contract.",
        "owned_scope": scopes,
        "exclusions": ["Do not create or coordinate another agent."],
        "authority": authority,
        "disposition": disposition,
        "recipe": "eval-peer",
        "verification": ["Run the named contract validator."],
        "dependencies": [],
        "languages": {"live": "English", "artifact": "English"},
        "topology_rationale": None,
        "candidate": candidate,
    }


def _deterministic_handback(assignment_id: str, outcome: str) -> dict[str, str]:
    return {"assignment_id": assignment_id, "outcome": outcome, "evidence": "deterministic helper evidence", "impact": "bounded contract result", "need": "none"}


def _run_deterministic(case: dict[str, Any], project: Path, home: Path, installation: dict[str, Any], source_skill: Path | None, official_skill: str) -> dict[str, Any]:
    """Execute approved deterministic eval controls without Herdr agents."""
    evidence: dict[str, Any] = {"peer_agents": [], "supervisor_agents": [], "handbacks": [], "dispatches": []}
    case_id = case["id"]
    if case_id == "install-materialization-basic":
        evidence.update(_verify_materialized_install(project, home, installation, source_skill, official_skill))
    elif case_id in {"ownership-overlap-contract", "ownership-nested-overlap-contract"}:
        names = ("overlap-a", "overlap-b") if case_id == "ownership-overlap-contract" else ("retained-a", "retained-nested")
        scopes = (["path:src/shared"], ["path:src/shared/nested"]) if case_id == "ownership-overlap-contract" else (["path:src"], ["path:src/api"])
        for index, (name, owned_scope) in enumerate(zip(names, scopes, strict=True), 1):
            _write_eval_json(project / "evidence" / f"{name}.json", _deterministic_assignment(f"deterministic:{name}", f"peer-{index}", owned_scope))
    elif case_id == "ownership-independent-contract":
        _write_eval_json(project / "evidence/independent-a.json", _deterministic_assignment("deterministic:independent-a", "peer-a", ["path:src/alpha.txt"]))
        _write_eval_json(project / "evidence/independent-b.json", _deterministic_assignment("deterministic:independent-b", "peer-b", ["path:src/beta.txt"]))
    elif case_id == "candidate-binding-contract":
        helper = project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
        if not helper.is_file():
            raise EvalError("materialized candidate helper is unavailable for deterministic grading")
        first_freeze = _command([sys.executable, str(helper), "freeze-candidate", "--project-root", str(project)], cwd=project, timeout=30)
        if first_freeze.returncode:
            raise EvalError(f"could not freeze deterministic stale candidate: {first_freeze.stderr.strip()}")
        stale = json.loads(first_freeze.stdout)["candidate"]
        (project / "candidate-current.txt").write_text("new immutable candidate tree\n", encoding="utf-8")
        current_freeze = _command([sys.executable, str(helper), "freeze-candidate", "--project-root", str(project)], cwd=project, timeout=30)
        if current_freeze.returncode:
            raise EvalError(f"could not freeze deterministic current candidate: {current_freeze.stderr.strip()}")
        current = json.loads(current_freeze.stdout)["candidate"]
        _write_eval_json(project / "evidence/stale-review.json", _deterministic_assignment("deterministic:stale-review", "reviewer-a", [], authority="read-only", disposition="Reviewer", candidate=stale))
        _write_eval_json(project / "evidence/current-candidate.json", current)
        _write_eval_json(project / "evidence/matching-candidate.json", stale)
    elif case_id in {"reopen-handback-invalid-contract", "reopen-handback-valid-contract"}:
        outcome = "REOPEN_REQUEST" if case_id == "reopen-handback-invalid-contract" else "COMPLETE"
        stem = "reopen-invalid" if outcome == "REOPEN_REQUEST" else "reopen-valid"
        assignment = _deterministic_assignment(f"deterministic:{stem}", "deterministic-peer", [f"path:evidence/{stem}.json"])
        _write_eval_json(project / f"evidence/{stem}-assignment.json", assignment)
        _write_eval_json(project / f"evidence/{stem}-handback.json", _deterministic_handback(assignment["assignment_id"], outcome))
    else:
        raise EvalError(f"deterministic eval case has no approved executor: {case_id}")
    _write_eval_json(project / "evaluation-evidence.json", evidence)
    return evidence


def _path_scopes_overlap(left: str, right: str) -> bool:
    if not left.startswith("path:") or not right.startswith("path:"):
        return left == right
    left_path, right_path = left.removeprefix("path:"), right.removeprefix("path:")
    return left_path == right_path or left_path.startswith(right_path + "/") or right_path.startswith(left_path + "/")


def _validate_supervisor_route(project: Path, raw_path: str, topology: dict[str, Any]) -> None:
    """Validate a routing artifact, never a self-reported routing verdict."""
    route = _read_json(_relative_evidence_path(project, raw_path, "supervisor route"), "supervisor route")
    if not isinstance(route, dict) or set(route) != {"supervisor_agent", "target_lead", "open_question"}:
        raise EvalError("supervisor route must contain supervisor_agent, target_lead, and open_question")
    if route["supervisor_agent"] not in topology.get("supervisor_agents", []):
        raise EvalError("supervisor route is not authored by an observed Supervisor")
    if route["target_lead"] != topology.get("agent_name"):
        raise EvalError("supervisor route does not target this run's explicit Lead")
    _text(route["open_question"], "supervisor route open_question")


def _handback_evidence_path(project: Path, value: Any) -> Path:
    raw = _text(value, "handback.evidence_path")
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (project / _relative(raw, "handback.evidence_path")).resolve()


def grade(grader: dict[str, Any], project: Path, topology: dict[str, Any], *, helper: Path | None = None) -> dict[str, Any]:
    path = project / grader["path"]
    try:
        candidate = _read_json(path, "evaluation evidence")
    except EvalError as exc:
        return {"passed": False, "reason": str(exc)}
    if not isinstance(candidate, dict):
        return {"passed": False, "reason": "evaluation evidence must be an object", "path": grader["path"]}
    requirements = grader["requirements"]
    try:
        peer_agents = candidate.get("peer_agents", [])
        supervisor_agents = candidate.get("supervisor_agents", [])
        if not isinstance(peer_agents, list) or not all(isinstance(name, str) and name for name in peer_agents):
            raise EvalError("evaluation evidence peer_agents must be a string array")
        if not isinstance(supervisor_agents, list) or not all(isinstance(name, str) and name for name in supervisor_agents):
            raise EvalError("evaluation evidence supervisor_agents must be a string array")
        if len(set(peer_agents)) != len(peer_agents) or len(set(supervisor_agents)) != len(supervisor_agents):
            raise EvalError("evaluation evidence must not repeat participant agents")
        observed_peers = set(topology.get("peer_agents", []))
        observed_supervisors = set(topology.get("supervisor_agents", []))
        if not set(peer_agents) <= observed_peers or not set(supervisor_agents) <= observed_supervisors:
            raise EvalError("evaluation evidence names an agent that the runner did not observe through Herdr")
        if len(peer_agents) < requirements.get("minimum_peer_agents", 0):
            raise EvalError("evaluation evidence has too few observed Peer agents")
        if "exact_peer_agents" in requirements and len(peer_agents) != requirements["exact_peer_agents"]:
            raise EvalError("evaluation evidence has an invalid exact Peer topology")
        if len(supervisor_agents) < requirements.get("minimum_supervisor_agents", 0):
            raise EvalError("evaluation evidence has too few observed Supervisor agents")
        handbacks = candidate.get("handbacks", [])
        assignment_documents: list[tuple[dict[str, Any], dict[str, Any]]] = []
        if "handbacks" in requirements:
            if not isinstance(handbacks, list):
                raise EvalError("evaluation evidence handbacks must be an array")
            outcomes: list[str] = []
            rationales: list[Any] = []
            handback_helper = helper or project / ".codex/skills/herdr-orchestrator/scripts/herdr_orchestrator.py"
            for item in handbacks:
                if not isinstance(item, dict) or set(item) != {"assignment", "handback", "peer_agent"}:
                    raise EvalError("each evidence handback must name its assignment, handback, and actual Peer agent")
                if item["peer_agent"] not in peer_agents:
                    raise EvalError("each evidence handback must be attributed to an observed Peer agent")
                assignment = _relative_evidence_path(project, item["assignment"], "evidence assignment")
                handback = _relative_evidence_path(project, item["handback"], "evidence handback")
                completed = _command([sys.executable, str(handback_helper), "validate-handback", "--assignment", str(assignment), "--handback", str(handback)], cwd=project, timeout=30)
                if completed.returncode:
                    raise EvalError(f"external handback validation failed: {completed.stderr.strip()}")
                outcomes.append(_read_json(handback, "evidence handback").get("outcome"))
                assignment_document = _read_json(assignment, "evidence assignment")
                if not isinstance(assignment_document, dict):
                    raise EvalError("evidence assignment must be an object")
                assignment_documents.append((item, assignment_document))
                rationales.append(assignment_document.get("topology_rationale"))
            if len(handbacks) < requirements.get("minimum_handbacks", 0):
                raise EvalError("evaluation evidence has too few externally validated handbacks")
            for outcome in requirements["handbacks"]:
                if outcome not in outcomes:
                    raise EvalError(f"required semantic handback outcome was not externally validated: {outcome}")
            if "required_handback_evidence_path" in requirements:
                expected_path = (project / requirements["required_handback_evidence_path"]).resolve()
                evidence_paths = []
                for item in handbacks:
                    handback_document = _read_json(_relative_evidence_path(project, item["handback"], "evidence handback"), "evidence handback")
                    raw_path = handback_document.get("evidence_path") if isinstance(handback_document, dict) else None
                    if isinstance(raw_path, str):
                        try:
                            evidence_paths.append(_handback_evidence_path(project, raw_path))
                        except OSError:
                            continue
                if expected_path not in evidence_paths:
                    raise EvalError("required externally inspectable handback evidence path was not preserved")
            if requirements.get("require_topology_rationale") and not any(isinstance(value, str) and value.strip() for value in rationales):
                raise EvalError("no externally validated Assignment recorded a topology rationale")
        if requirements.get("require_assignment_binding"):
            dispatches = candidate.get("dispatches")
            if not isinstance(dispatches, list) or not dispatches:
                raise EvalError("evaluation evidence must index dispatches with exact Assignment hashes")
            dispatch_index: dict[tuple[str, str], str] = {}
            for dispatch in dispatches:
                if not isinstance(dispatch, dict) or set(dispatch) != {"assignment", "assignment_sha256", "peer_agent"}:
                    raise EvalError("each dispatch must contain assignment, assignment_sha256, and peer_agent")
                assignment = _relative_evidence_path(project, dispatch["assignment"], "evidence dispatch assignment")
                digest = _sha256(assignment.read_bytes())
                if dispatch["assignment_sha256"] != digest:
                    raise EvalError("dispatch Assignment hash does not match the inspected Assignment")
                if dispatch["peer_agent"] not in observed_peers:
                    raise EvalError("dispatch Peer was not observed through Herdr")
                dispatch_index[(dispatch["assignment"], dispatch["peer_agent"])] = digest
            for handback_item, assignment_document in assignment_documents:
                key = (handback_item["assignment"], handback_item["peer_agent"])
                if key not in dispatch_index:
                    raise EvalError("validated handback has no exact inspected dispatch binding")
                if assignment_document.get("owner") != handback_item["peer_agent"]:
                    raise EvalError("Assignment owner must be the Peer that owns this handback and write scope")
        if "require_disjoint_assignment_scopes" in requirements:
            assignments = [document for _, document in assignment_documents]
            count = requirements["require_disjoint_assignment_scopes"]
            if len(assignments) < count:
                raise EvalError("too few validated Assignments for independent topology")
            selected = assignments[:count]
            scopes = [scope for assignment in selected for scope in assignment.get("owned_scope", [])]
            if any(_path_scopes_overlap(left, right) for index, left in enumerate(scopes) for right in scopes[index + 1:]):
                raise EvalError("independent topology contains overlapping owned scopes")
        if "require_coupled_assignment_scopes" in requirements:
            required_scopes = set(requirements["require_coupled_assignment_scopes"])
            if not any(required_scopes <= set(document.get("owned_scope", [])) for _, document in assignment_documents):
                raise EvalError("coupled topology did not keep the required scopes in one Assignment")
        if requirements.get("require_correlation_sequence"):
            correlations = candidate.get("correlations")
            if not isinstance(correlations, list) or len(correlations) != 1:
                raise EvalError("evaluation evidence must index one old/new Assignment correlation")
            correlation = correlations[0]
            if not isinstance(correlation, dict) or set(correlation) != {"old_assignment", "new_assignment", "peer_agent"}:
                raise EvalError("correlation must contain old_assignment, new_assignment, and peer_agent")
            if correlation["peer_agent"] not in observed_peers:
                raise EvalError("correlation Peer was not observed through Herdr")
            matching = {item["assignment"]: item for item, _ in assignment_documents}
            if correlation["old_assignment"] == correlation["new_assignment"] or correlation["old_assignment"] not in matching or correlation["new_assignment"] not in matching:
                raise EvalError("correlation does not bind two validated distinct Assignments")
            if matching[correlation["old_assignment"]]["peer_agent"] != correlation["peer_agent"] or matching[correlation["new_assignment"]]["peer_agent"] != correlation["peer_agent"]:
                raise EvalError("correlation does not bind old and new Assignments to the same Peer")
            observed = topology.get("correlation_observation")
            if not isinstance(observed, dict) or observed.get("peer_agent") != correlation["peer_agent"] or observed.get("settled_before_follow_up") is not True:
                raise EvalError("runner did not observe the old Peer lifecycle settle before the newer Assignment")
        for route in requirements.get("supervisor_routes", []):
            _validate_supervisor_route(project, route, topology)
        for control in requirements.get("controls", []):
            result = _run_delegation_control(project, control["assignments"])
            if result != control["expected_returncode"]:
                raise EvalError(f"external {control['command']} control returned {result}, expected {control['expected_returncode']}")
        for control in requirements.get("review_controls", []):
            result = _run_review_control(project, control["assignment"], control["current_candidate"])
            if result != control["expected_returncode"]:
                raise EvalError(f"external validate-review control returned {result}, expected {control['expected_returncode']}")
        for control in requirements.get("handback_controls", []):
            result = _run_handback_control(project, control["assignment"], control["handback"])
            if result != control["expected_returncode"]:
                raise EvalError(f"external validate-handback control returned {result}, expected {control['expected_returncode']}")
            handback = _read_json(_relative_evidence_path(project, control["handback"], "handback control handback"), "handback control handback")
            if not isinstance(handback, dict) or handback.get("outcome") != control["outcome"]:
                raise EvalError("external handback control did not retain its expected semantic outcome")
        if requirements.get("require_materialized_install") and topology.get("materialized_installation") is not True:
            raise EvalError("runner did not verify project-local and official skill materialization")
    except EvalError as exc:
        return {"passed": False, "reason": str(exc), "path": grader["path"]}
    return {"passed": True, "reason": "externally observed provenance and inspected contract evidence validated", "path": grader["path"]}


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _scrub_retained_artifact(value: Any, project: Path, key: str | None = None) -> Any:
    """Keep JSON grader inputs while removing runner-private locations/fields."""
    protected = {"auth", "credential", "credentials", "token", "secret", "password", "home", "codex_home", "cwd", "pane_id", "workspace_id", "transcript"}
    if isinstance(value, dict):
        return {
            item_key: _scrub_retained_artifact(item_value, project, item_key)
            for item_key, item_value in value.items()
            if item_key.casefold() not in protected
        }
    if isinstance(value, list):
        return [_scrub_retained_artifact(item, project, key) for item in value]
    if key == "evidence_path" and isinstance(value, str):
        path = Path(value)
        resolved = path.resolve() if path.is_absolute() else (project / _relative(value, "handback.evidence_path")).resolve()
        try:
            return resolved.relative_to(project.resolve()).as_posix()
        except ValueError as exc:
            raise EvalError("cannot retain handback evidence outside the task project") from exc
    return value


def _retained_artifact_paths(case: dict[str, Any], project: Path) -> list[str]:
    paths = {"evaluation-evidence.json"}
    index = _read_json(project / "evaluation-evidence.json", "evaluation evidence")
    if not isinstance(index, dict):
        raise EvalError("cannot retain a non-object evaluation evidence index")
    for item in index.get("handbacks", []):
        if not isinstance(item, dict):
            raise EvalError("cannot retain malformed evidence handback")
        for field in ("assignment", "handback"):
            paths.add(_relative(item.get(field), f"retained evidence {field}"))
    graders = [case["graders"]["functional"], *case["graders"]["hard"]]
    for grader in graders:
        paths.add(_relative(grader["path"], "retained grader path"))
        for route in grader["requirements"].get("supervisor_routes", []):
            paths.add(_relative(route, "retained supervisor route"))
        required_evidence = grader["requirements"].get("required_handback_evidence_path")
        if required_evidence is not None:
            paths.add(_relative(required_evidence, "retained handback evidence path"))
    return sorted(paths)


def _retain_live_pass_evidence(case: dict[str, Any], result: dict[str, Any], project: Path, bundle_dir: Path) -> dict[str, str]:
    """Persist the minimal, scrubbed inputs needed to re-grade one live PASS."""
    if result.get("execution") != "live" or result.get("final") != "PASS":
        raise EvalError("only completed live PASS results may retain audit evidence")
    artifacts: dict[str, dict[str, Any]] = {}
    for relative in _retained_artifact_paths(case, project):
        source = project / relative
        if not source.is_file() or source.is_symlink():
            raise EvalError(f"required retained evidence artifact is unavailable: {relative}")
        raw = source.read_bytes()
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvalError(f"retained evidence artifact must be JSON: {relative}") from exc
        artifacts[relative] = {"source_sha256": _sha256(raw), "document": _scrub_retained_artifact(document, project)}

    index = artifacts["evaluation-evidence.json"]["document"]
    if not isinstance(index, dict):
        raise EvalError("cannot retain a non-object evaluation evidence index")
    for dispatch in index.get("dispatches", []):
        if not isinstance(dispatch, dict):
            raise EvalError("cannot retain malformed evidence dispatch")
        assignment = _relative(dispatch.get("assignment"), "retained dispatch assignment")
        if assignment not in artifacts:
            raise EvalError("retained dispatch does not name a retained Assignment")
        dispatch["assignment_sha256"] = _sha256(_canonical_json_bytes(artifacts[assignment]["document"]))

    artifact_rows = []
    for relative in sorted(artifacts):
        document = artifacts[relative]["document"]
        artifact_rows.append({
            "path": relative,
            "source_sha256": artifacts[relative]["source_sha256"],
            "sha256": _sha256(_canonical_json_bytes(document)),
            "document": document,
        })
    sut = result.get("sut", {})
    evidence = result.get("evidence", {})
    topology = {
        key: evidence[key]
        for key in ("agent_name", "peer_agents", "supervisor_agents", "correlation_observation")
        if key in evidence
    }
    bundle = {
        "schema_version": RETAINED_EVIDENCE_SCHEMA_VERSION,
        "kind": "herdr-orchestrator.live-pass-audit-bundle",
        "run": {
            "eval_id": result["eval_id"],
            "subject": result["subject"],
            "suite_class": result["suite_class"],
            "fixture": result["fixture"],
            "repetition": result["repetition"],
            "execution": "live",
            "final": "PASS",
        },
        "provenance": {
            key: sut[key]
            for key in ("git_head", "git_dirty", "source_tree_sha256", "installed_skill_tree_sha256", "official_herdr_skill_sha256", "herdr_version", "agent")
            if key in sut
        },
        "topology": topology,
        "graders": {
            "functional": {"definition": case["graders"]["functional"], "result": result["functional"]},
            "hard": [
                {"definition": grader, "result": outcome}
                for grader, outcome in zip(case["graders"]["hard"], result["hard_graders"], strict=True)
            ],
        },
        "artifacts": artifact_rows,
    }
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{result['eval_id']}-{result['subject']}-r{result['repetition']}-{uuid.uuid4().hex}.json"
    bundle_path.write_bytes(_canonical_json_bytes(bundle))
    return {"bundle_id": bundle_path.stem, "sha256": _sha256(bundle_path.read_bytes()), "path": str(bundle_path)}


def _regrade_retained_live_pass_bundle(path: Path, helper: Path) -> dict[str, Any]:
    """Re-grade a scrubbed live PASS bundle without its original HOME/worktree."""
    bundle = _read_json(path, "retained live PASS evidence bundle")
    if not isinstance(bundle, dict) or bundle.get("kind") != "herdr-orchestrator.live-pass-audit-bundle":
        raise EvalError("retained evidence bundle has an unsupported kind")
    if not helper.is_file():
        raise EvalError("retained evidence re-grade helper is unavailable")
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvalError("retained evidence bundle has no artifacts")
    topology = bundle.get("topology")
    graders = bundle.get("graders")
    if not isinstance(topology, dict) or not isinstance(graders, dict):
        raise EvalError("retained evidence bundle is missing topology or graders")
    with tempfile.TemporaryDirectory(prefix="herdr-retained-evidence-") as temporary:
        project = Path(temporary)
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != {"path", "source_sha256", "sha256", "document"}:
                raise EvalError("retained evidence artifact has an invalid shape")
            relative = _relative(artifact["path"], "retained artifact path")
            payload = _canonical_json_bytes(artifact["document"])
            if _sha256(payload) != artifact["sha256"]:
                raise EvalError(f"retained evidence artifact hash mismatch: {relative}")
            destination = project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        functional = graders.get("functional")
        hard = graders.get("hard")
        if not isinstance(functional, dict) or not isinstance(hard, list):
            raise EvalError("retained evidence grader records are invalid")
        functional_result = grade(functional["definition"], project, topology, helper=helper)
        hard_results = [grade(item["definition"], project, topology, helper=helper) for item in hard]
        passed = functional_result["passed"] and all(item["passed"] for item in hard_results)
        return {"passed": passed, "functional": functional_result, "hard_graders": hard_results}


def _pass_reason(mode: str) -> str:
    if mode == "deterministic":
        return "all deterministic graders passed"
    if mode == "live":
        return "live execution completed and all hard graders passed"
    raise EvalError(f"PASS wording is unsupported for mode: {mode}")


def _json_output(completed: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    if completed.returncode:
        raise EvalError(f"{label} failed: {completed.stderr.strip()}")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvalError(f"{label} did not return JSON") from exc
    if not isinstance(data, dict):
        raise EvalError(f"{label} did not return an object")
    return data


def _prompt_and_wait(target: str, prompt: str, timeout_seconds: int, label: str) -> bool:
    """Prompt once; a timeout is inspected and waited, never blindly resent."""
    command = ["herdr", "agent", "prompt", target, prompt, "--wait", "--timeout", str(timeout_seconds * 1000)]
    completed = _command(command, timeout=timeout_seconds + 30)
    try:
        response = json.loads(completed.stdout or completed.stderr) if (completed.stdout or completed.stderr) else None
    except json.JSONDecodeError:
        response = None
    error = response.get("error") if isinstance(response, dict) else None
    if completed.returncode == 0 and not isinstance(error, dict):
        _json_output(completed, label)
        return True
    if not isinstance(error, dict) or error.get("code") != "timeout":
        _json_output(completed, label)
        return True
    # Herdr documents that a waited prompt can time out while an agent remains
    # active. Inspect, then wait on that same turn. Do not send a duplicate.
    _command(["herdr", "agent", "read", target, "--source", "recent-unwrapped", "--lines", "80"], timeout=30)
    settled = _command(["herdr", "agent", "wait", target, "--timeout", str(min(timeout_seconds, 120) * 1000)], timeout=min(timeout_seconds, 120) + 30)
    _command(["herdr", "agent", "read", target, "--source", "recent-unwrapped", "--lines", "80"], timeout=30)
    return settled.returncode == 0


def _find_pane_id(value: Any) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get("pane_id"), str):
            return value["pane_id"]
        for child in value.values():
            found = _find_pane_id(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_pane_id(child)
            if found:
                return found
    return None


def _result(value: dict[str, Any], label: str) -> Any:
    if "result" not in value:
        raise EvalError(f"{label} did not return a result")
    return value["result"]


def _fresh_project_cwd(value: Any, project: Path) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return Path(value).resolve() == project.resolve()
    except OSError:
        return False


def _pane_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if isinstance(value.get("pane_id"), str):
            return value
        for child in value.values():
            found = _pane_record(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _pane_record(child)
            if found is not None:
                return found
    return None


def _listed_agents() -> list[dict[str, Any]]:
    response = _json_output(_command(["herdr", "agent", "list"], timeout=30), "Herdr agent list")
    payload = _result(response, "Herdr agent list")
    agents = payload.get("agents") if isinstance(payload, dict) else None
    if not isinstance(agents, list) or not all(isinstance(item, dict) for item in agents):
        raise EvalError("Herdr agent list returned invalid agents")
    return agents


def _resolve_agent_entry(agent: dict[str, Any], project: Path, expected_pane: str | None = None) -> dict[str, Any]:
    pane_id = agent.get("pane_id")
    if not isinstance(pane_id, str) or not pane_id:
        raise EvalError("declared participant has no Herdr pane identity")
    if expected_pane is not None and pane_id != expected_pane:
        raise EvalError("declared participant is not attached to its eval-owned pane")
    pane_response = _json_output(_command(["herdr", "pane", "get", pane_id], timeout=30), "Herdr pane get")
    pane = _pane_record(_result(pane_response, "Herdr pane get"))
    if pane is None or pane.get("pane_id") != pane_id:
        raise EvalError("Herdr did not resolve participant pane identity")
    if not _fresh_project_cwd(agent.get("cwd"), project) or not _fresh_project_cwd(pane.get("cwd"), project):
        raise EvalError("declared participant is not in this fresh eval project")
    return {"name": agent.get("name"), "pane_id": pane_id, "cwd": str(project), "workspace_id": pane.get("workspace_id")}


def _resolve_participant(name: str, project: Path, expected_pane: str | None = None) -> dict[str, Any]:
    """Prove agent → pane → fresh-project provenance before grading or cleanup.

    A participant name in agent-authored evidence is only an index.  The runner
    accepts it solely when installed Herdr independently resolves one named
    agent and its one pane to this repetition's freshly materialized project.
    """
    matches = [item for item in _listed_agents() if item.get("name") == name]
    if len(matches) != 1:
        raise EvalError(f"Herdr did not resolve exactly one declared participant: {name}")
    resolved = _resolve_agent_entry(matches[0], project, expected_pane)
    return {**resolved, "name": name}


def _discover_eval_owned_panes(project: Path) -> set[str]:
    """Recover only panes whose Herdr-observed cwd is this unique repetition."""
    panes: set[str] = set()
    try:
        for agent in _listed_agents():
            if isinstance(agent.get("pane_id"), str) and _fresh_project_cwd(agent.get("cwd"), project):
                try:
                    panes.add(_resolve_agent_entry(agent, project)["pane_id"])
                except EvalError:
                    # A changing/dead agent is not sufficiently proven safe to
                    # close. The explicitly provisioned panes remain covered by
                    # their own recorded identities below.
                    continue
    except EvalError:
        pass
    return panes


def _cleanup_eval_owned_panes(project: Path, provisioned_panes: Sequence[str]) -> None:
    """Close proven project-owned panes; never use participant names alone."""
    pane_ids = set(provisioned_panes) | _discover_eval_owned_panes(project)
    for pane_id in pane_ids:
        close = _command(["herdr", "pane", "close", pane_id], timeout=30)
        if close.returncode and sys.stderr:
            print(f"warning: could not close eval-owned pane {pane_id}: {close.stderr.strip()}", file=sys.stderr)


def _live_prompt(case: dict[str, Any], project: Path, source_skill: Path | None, supervisor_agents: Sequence[str] = ()) -> str:
    activation = "Activate and follow the installed $herdr-orchestrator skill; " if source_skill is not None else "Use the release-matched installed Herdr skill only; "
    return (
        "# Bounded live evaluation mandate\n\n"
        + "You are the already-spawned Project Lead for a bounded repeatable live evaluation in a fresh consumer project. The harness already materialized the skills and validated the project preflight. Do not take a Launcher/setup route, repeat setup, or create another Lead or Supervisor. "
        + activation + "do not read any source repository outside this project. "
        + f"Public task: {case['task']}\n"
        + (f"Human-attached Supervisor agent(s) for this public task: {', '.join(supervisor_agents)}.\n" if supervisor_agents else "")
        + "Any dynamically created Peer must use the installed orchestration contract's exact bound Lead pane as the native split target, then derive its binding from the exact pane ID returned by Herdr. Pass only the rendered project/helper/peer-role pane context; do not override a harness profile home, copy credentials, or prepare login. Do not set HERDR_ENV, HERDR_SOCKET_PATH, HERDR_PANE_ID, HERDR_TAB_ID, or HERDR_WORKSPACE_ID. "
        + "Use the installed skill and public workspace protocol to perform the public task. Runner preflight is already complete: do not reread setup documentation or perform unrelated work. "
        + "Use .orchestration/evaluation-evidence-template.json as the public schema for ./evaluation-evidence.json at the consumer-project root. Before your turn settles, index the actual task artifacts and every actual Peer and Supervisor used; do not invent participants or artifact records. "
        + "Do not write an answer key, eval ID, invariant list, grader rubric, or claimed pass/fail result. Then reply with one short sentence naming the evidence file."
    )


def _supervisor_prompt(case: dict[str, Any], project: Path, lead_name: str, source_skill: Path | None) -> str:
    activation = "Activate and follow the installed $herdr-orchestrator skill; " if source_skill is not None else "Use the release-matched installed Herdr skill only; "
    return (
        "You are a Human-attached evaluation Supervisor in a fresh consumer project. "
        + activation + "do not read any source repository outside this project. "
        + f"Your explicitly attached Lead is {lead_name}. Public mandate: {case['task']}\n"
        + "Observe only, do not create agents or modify project code. Do not act until the Lead workflow has produced task-owned evidence."
    )


def _supervisor_follow_up_prompt(project: Path, supervisor_name: str, lead_name: str) -> str:
    return (
        "The attached Lead workflow has now produced evaluation-evidence.json. Inspect that bounded project-owned evidence while remaining read-only. "
        f"Write {SUPERVISOR_ROUTE_ARTIFACT} with exactly supervisor_agent, target_lead, and open_question. supervisor_agent must be your exact name, target_lead must be the explicit attached Lead, and open_question must be one concrete evidence-backed governance question or Human-decision relay. "
        "Do not modify implementation, create agents, accept the project, emit a verdict, answer key, or pass/fail claim."
    )


def _require_supervisor_route_absent(project: Path) -> Path:
    path = project / SUPERVISOR_ROUTE_ARTIFACT
    if path.exists() or path.is_symlink():
        raise EvalError("Supervisor route artifact existed before the Supervisor follow-up")
    return path


def _observe_supervisor_route(path: Path, supervisor: str, lead: str, prompted_at: float) -> dict[str, Any]:
    if not path.is_file():
        raise EvalError("Supervisor did not produce the route artifact after its follow-up")
    try:
        route = _read_json(path, "Supervisor route artifact")
    except EvalError as exc:
        raise EvalError("Supervisor route artifact is not valid JSON") from exc
    if not isinstance(route, dict) or route.get("supervisor_agent") != supervisor or route.get("target_lead") != lead:
        raise EvalError("new Supervisor route artifact does not target its explicitly attached Lead")
    content = path.read_bytes()
    return {"path": str(path.relative_to(path.parent)), "sha256": _sha256(content), "bytes": len(content), "prompted_at_monotonic": prompted_at, "observed_after_supervisor_turn": True, "supervisor_agent": supervisor, "target_lead": lead}


def _supervisor_agent_name(case_id: str, index: int) -> str:
    """Create an Herdr-valid, bounded name for an eval-owned Supervisor."""
    return f"eval-sup-{case_id[:8]}-{index % 1000:03d}-{uuid.uuid4().hex[:6]}"


def _correlation_follow_up_prompt() -> str:
    return (
        "Now issue one newer bounded follow-up Assignment to the same Peer only after inspecting its existing structured handback. "
        "Do not treat lifecycle settle as completion of this new Assignment. Update evaluation-evidence.json with both validated handbacks, their dispatch bindings, and one correlations entry containing old_assignment, new_assignment, and peer_agent. Recalculate every dispatch assignment_sha256 with sha256sum from its final Assignment file bytes after this update. Do not retry blindly."
    )


def _validate_public_evidence_index_shape(evidence: Any) -> None:
    """Check only the public index shape before a bounded correction prompt."""
    if not isinstance(evidence, dict):
        raise EvalError("evaluation evidence must be an object")
    required = {"peer_agents", "supervisor_agents", "handbacks", "dispatches"}
    if not required <= set(evidence):
        raise EvalError("evaluation evidence omits public index fields")
    peer_agents = evidence["peer_agents"]
    supervisor_agents = evidence["supervisor_agents"]
    handbacks = evidence["handbacks"]
    dispatches = evidence["dispatches"]
    if not all(isinstance(value, list) for value in (peer_agents, supervisor_agents, handbacks, dispatches)):
        raise EvalError("evaluation evidence public index fields must be arrays")
    if not all(isinstance(name, str) and name for name in [*peer_agents, *supervisor_agents]):
        raise EvalError("evaluation evidence participant names must be nonempty strings")
    for record in handbacks:
        if not isinstance(record, dict) or set(record) != {"assignment", "handback", "peer_agent"}:
            raise EvalError("evaluation evidence handback records are incomplete")
    for record in dispatches:
        if not isinstance(record, dict) or set(record) != {"assignment", "assignment_sha256", "peer_agent"}:
            raise EvalError("evaluation evidence dispatch records are incomplete")


def _read_evidence_index(project: Path) -> dict[str, Any]:
    """Read a completed public index; evaluation never repairs agent output."""
    evidence = _read_json(project / "evaluation-evidence.json", "evaluation evidence")
    _validate_public_evidence_index_shape(evidence)
    return evidence


def _json_shape(path: Path) -> dict[str, Any]:
    """Return bounded structural diagnostics without retaining agent content."""
    item: dict[str, Any] = {"path": str(path), "sha256": _sha256(path.read_bytes()), "bytes": path.stat().st_size}
    try:
        value = _read_json(path, "eval diagnostic JSON")
    except EvalError:
        return {**item, "json": "invalid"}
    if isinstance(value, dict):
        shape: dict[str, Any] = {"json": "object", "keys": sorted(value)}
        for key in ("assignment_id", "authority", "owner", "owned_scope"):
            if key in value and isinstance(value[key], (str, list)):
                shape[key] = value[key]
        if "topology_rationale" in value:
            shape["topology_rationale_present"] = isinstance(value["topology_rationale"], str) and bool(value["topology_rationale"].strip())
        for key, child in value.items():
            if isinstance(child, list):
                shape[f"{key}_count"] = len(child)
                if child and isinstance(child[0], dict):
                    shape[f"{key}_record_keys"] = sorted(child[0])
        return {**item, **shape}
    return {**item, "json": type(value).__name__}


def _failure_diagnostics(project: Path, lead_name: str, transcript: str) -> dict[str, Any]:
    """Capture bounded failure structure before eval-owned cleanup."""
    paths = [project / "evaluation-evidence.json"]
    evidence_directory = project / "evidence"
    if evidence_directory.is_dir():
        paths.extend(sorted(evidence_directory.glob("*.json")))
    files = [_json_shape(path) for path in paths if path.is_file()]
    read = _command(["herdr", "agent", "read", lead_name, "--source", "recent-unwrapped", "--lines", "20"], timeout=30)
    observed = read.stdout if read.returncode == 0 else read.stderr
    return {
        "artifact_shapes": files,
        "lead_transcript_sha256": _sha256((transcript + observed).encode()),
        "lead_transcript_bytes": len((transcript + observed).encode()),
    }


def _run_live(case: dict[str, Any], project: Path, home: Path, timeout_seconds: int, source_skill: Path | None) -> dict[str, Any]:
    name = f"eval-{case['id'][:16]}-{uuid.uuid4().hex[:8]}"
    pane_ids: list[str] = []
    provisioned_supervisors: list[str] = []
    supervisor_panes: dict[str, str] = {}
    started = time.monotonic()
    transcript = ""
    try:
        split = _json_output(_command(["herdr", "pane", "split", "--current", "--direction", "right", "--cwd", str(project), "--env", f"HOME={home}", "--env", f"CODEX_HOME={home / '.codex'}", "--env", "HERDR_ORCHESTRATOR_ROLE=lead", "--no-focus"], timeout=30), "eval Lead pane split")
        lead_pane = _find_pane_id(split)
        if not lead_pane:
            raise EvalError("eval pane split returned no pane ID")
        pane_ids.append(lead_pane)
        _json_output(_command(["herdr", "agent", "start", name, "--kind", case["agent"]["kind"], "--pane", lead_pane, "--timeout", "30000", "--", *case["agent"]["args"]], timeout=45), "eval Lead agent start")
        for index in range(case["topology"]["minimum_supervisor_agents"]):
            split = _json_output(_command(["herdr", "pane", "split", "--current", "--direction", "right", "--cwd", str(project), "--env", f"HOME={home}", "--env", f"CODEX_HOME={home / '.codex'}", "--env", "HERDR_ORCHESTRATOR_ROLE=supervisor", "--no-focus"], timeout=30), "eval Supervisor pane split")
            supervisor_pane = _find_pane_id(split)
            if not supervisor_pane:
                raise EvalError("eval Supervisor pane split returned no pane ID")
            pane_ids.append(supervisor_pane)
            supervisor = _supervisor_agent_name(case["id"], index)
            _json_output(_command(["herdr", "agent", "start", supervisor, "--kind", case["agent"]["kind"], "--pane", supervisor_pane, "--timeout", "30000", "--", *case["agent"]["args"]], timeout=45), "eval Supervisor agent start")
            _prompt_and_wait(supervisor, _supervisor_prompt(case, project, name, source_skill), timeout_seconds, "eval Supervisor initial mandate")
            provisioned_supervisors.append(supervisor)
            supervisor_panes[supervisor] = supervisor_pane
        _prompt_and_wait(name, _live_prompt(case, project, source_skill, provisioned_supervisors), timeout_seconds, "eval agent prompt")
        # Read output is bounded supporting evidence only. Some installed
        # Herdr versions return plain text for this surface, so never make a
        # transcript-format variation override project-owned deterministic
        # grading.
        read = _command(["herdr", "agent", "read", name, "--source", "recent-unwrapped", "--lines", "80"], timeout=30)
        transcript = read.stdout if read.returncode == 0 else read.stderr
        evidence = _read_evidence_index(project)
        lead = _resolve_participant(name, project, lead_pane)
        observed: dict[str, list[str]] = {"peer_agents": [], "supervisor_agents": []}
        resolved_participants: dict[str, dict[str, Any]] = {}
        for key in observed:
            names = evidence.get(key, [])
            if not isinstance(names, list) or not all(isinstance(item, str) and item for item in names):
                raise EvalError(f"evaluation evidence {key} must be a string array")
            for participant in names:
                if participant == name:
                    raise EvalError("Lead cannot be counted as an independently observed Peer or Supervisor")
                expected_pane = None
                if key == "supervisor_agents":
                    if participant not in provisioned_supervisors:
                        raise EvalError("evaluation evidence names a Supervisor not provisioned by this run")
                    expected_pane = supervisor_panes[participant]
                resolved_participants[participant] = _resolve_participant(participant, project, expected_pane)
                pane_ids.append(resolved_participants[participant]["pane_id"])
                observed[key].append(participant)
        if set(provisioned_supervisors) != set(observed["supervisor_agents"]):
            raise EvalError("evaluation evidence must name exactly the Supervisor agents provisioned by this run")
        correlation_observation: dict[str, Any] | None = None
        if case["workflow"] == "correlate-follow-up":
            if len(observed["peer_agents"]) != 1:
                raise EvalError("correlation workflow requires exactly one declared first-stage Peer")
            old_peer = observed["peer_agents"][0]
            settled = _command(["herdr", "agent", "wait", old_peer, "--timeout", "30000"], timeout=45)
            if settled.returncode:
                raise EvalError(f"runner could not observe old Peer settle before follow-up: {settled.stderr.strip()}")
            _prompt_and_wait(name, _correlation_follow_up_prompt(), timeout_seconds, "eval correlation follow-up")
            correlation_observation = {"peer_agent": old_peer, "settled_before_follow_up": True}
            evidence = _read_evidence_index(project)
            for participant in evidence.get("peer_agents", []):
                if participant not in resolved_participants:
                    resolved_participants[participant] = _resolve_participant(participant, project)
                    pane_ids.append(resolved_participants[participant]["pane_id"])
            observed["peer_agents"] = list(evidence.get("peer_agents", []))
        supervisor_route_observations: list[dict[str, Any]] = []
        for supervisor in provisioned_supervisors:
            route_path = _require_supervisor_route_absent(project)
            prompted_at = time.monotonic()
            _prompt_and_wait(supervisor, _supervisor_follow_up_prompt(project, supervisor, name), timeout_seconds, "eval Supervisor governance follow-up")
            supervisor_route_observations.append(_observe_supervisor_route(route_path, supervisor, name, prompted_at))
        for key, required in case["topology"].items():
            observed_key = key.removeprefix("minimum_")
            if len(observed[observed_key]) < required:
                raise EvalError(f"case did not exercise required topology: {key}")
        return {
            "duration_seconds": round(time.monotonic() - started, 3),
            "agent_name": name, "pane_id": lead_pane, "lead": lead,
            "participants": resolved_participants,
            "transcript_sha256": _sha256(transcript.encode()), "transcript_bytes": len(transcript.encode()),
            **observed,
            **({"correlation_observation": correlation_observation} if correlation_observation else {}),
            **({"supervisor_route_observations": supervisor_route_observations} if supervisor_route_observations else {}),
        }
    except EvalError as exc:
        diagnostics = exc.diagnostics or _failure_diagnostics(project, name, transcript)
        raise EvalError(str(exc), diagnostics=diagnostics) from exc
    finally:
        _cleanup_eval_owned_panes(project, pane_ids)


def run_case(case: dict[str, Any], suite: dict[str, Any], root: Path, dry_run: bool, timeout_seconds: int, source_skill: Path | None = None, subject: str = "current", retained_evidence_dir: Path | None = None) -> list[dict[str, Any]]:
    if source_skill is None and subject == "current":
        source_skill = root / "skills/herdr-orchestrator"
    fixture_seed = root / suite["fixture_root"] / case["fixture"]
    herdr_version = _version("herdr", ["--version"])
    official_skill = _version("herdr", ["--skill"])
    source_provenance = _source_provenance(source_skill, root)
    home_root = _private_eval_home_root()
    if retained_evidence_dir is None:
        retained_evidence_dir = root / ".eval-results" / "audit-bundles"
    results: list[dict[str, Any]] = []
    for repetition in range(1, case["repetitions"] + 1):
        began = time.monotonic()
        scratch_root = root / ".eval-results"
        scratch_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".work-{case['id']}-", dir=scratch_root) as temporary:
            workspace = Path(temporary)
            project = workspace / "consumer-project"
            with _owned_private_eval_home(home_root) as home:
                _prepare_fixture(fixture_seed, project)
                installation = _materialize_install(project, home, source_skill, official_skill)
                _validate_materialized_project(project)
                credential_boundary = _seed_provider_credential(home, case["agent"], project) if case["mode"] == "live" and not dry_run else None
                result: dict[str, Any] = {
                    "schema_version": RESULT_SCHEMA_VERSION,
                    "eval_id": case["id"], "subject": subject, "suite_class": case["suite"], "repetition": repetition,
                    "fixture": case["fixture"], "execution": "dry-run" if dry_run else case["mode"],
                    "sut": {**source_provenance, "installed_skill_tree_sha256": installation["tree_sha256"], "official_herdr_skill_sha256": installation["official_skill_sha256"], "install": installation, "herdr_version": herdr_version, "agent": case["agent"], "hermetic": False, "external_state": ["Herdr server/config is host-managed; the credential-bearing agent HOME is private and external to the repository; the consumer project is fresh."] + ([credential_boundary] if credential_boundary else [])},
                    "evidence": {"fixture_commit": _git_revision(project)},
                }
                if dry_run:
                    result.update({"functional": {"passed": None, "reason": "not run in dry-run"}, "hard_graders": [], "final": "NOT_RUN", "reason": "dry-run validates isolated installation only"})
                else:
                    try:
                        if case["mode"] == "deterministic":
                            result["evidence"].update(_run_deterministic(case, project, home, installation, source_skill, official_skill))
                        else:
                            result["evidence"].update(_run_live(case, project, home, timeout_seconds, source_skill))
                        functional = grade(case["graders"]["functional"], project, result["evidence"])
                        hard = [grade(grader, project, result["evidence"]) for grader in case["graders"]["hard"]]
                        result.update({"functional": functional, "hard_graders": hard})
                        result["final"] = "PASS" if functional["passed"] and all(item["passed"] for item in hard) else "FAIL"
                        result["reason"] = _pass_reason(case["mode"]) if result["final"] == "PASS" else "functional or hard grader failed"
                        if result["final"] == "PASS" and case["mode"] == "live":
                            try:
                                result["retained_evidence"] = _retain_live_pass_evidence(case, result, project, retained_evidence_dir)
                            except EvalError as exc:
                                result["final"] = "FAIL"
                                result["reason"] = f"live PASS audit evidence retention failed: {exc}"
                        if result["final"] == "FAIL":
                            result["failure_diagnostics"] = _failure_diagnostics(project, result["evidence"]["agent_name"], "")
                    except EvalError as exc:
                        result.update({"functional": {"passed": False, "reason": str(exc)}, "hard_graders": [], "final": "FAIL", "reason": str(exc)})
                        if exc.diagnostics is not None:
                            result["failure_diagnostics"] = exc.diagnostics
                result["duration_seconds"] = round(time.monotonic() - began, 3)
                observed = result["evidence"]
                result["metrics"] = {
                    "prompt_count": None if dry_run or case["mode"] == "deterministic" else (2 if case["workflow"] == "correlate-follow-up" else 1) + len(observed.get("supervisor_agents", [])) * 2,
                    "follow_up_count": None if dry_run or case["mode"] == "deterministic" else (1 if case["workflow"] == "correlate-follow-up" else 0),
                    "peer_count": len(observed.get("peer_agents", [])),
                    "supervisor_count": len(observed.get("supervisor_agents", [])),
                    "review_cycles": None,
                    "candidate_count": None,
                    "max_concurrency": None,
                    "model_usage": None,
                }
                results.append(result)
    return results


def summarize(results: list[dict[str, Any]], cases: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    summary: dict[str, Any] = {"by_eval": {}, "by_invariant": {}}
    passed_all = True
    for case in cases:
        items = [item for item in results if item["eval_id"] == case["id"]]
        passed = sum(item["final"] == "PASS" for item in items)
        status = "NOT_RUN" if items and all(item["final"] == "NOT_RUN" for item in items) else ("PASS" if passed >= case["threshold"]["required_passes"] else "FAIL")
        summary["by_eval"][case["id"]] = {"passed": passed, "total": len(items), "required": case["threshold"]["required_passes"], "status": status}
        if case["release_gate"] and status != "PASS":
            passed_all = False
        for invariant in case["invariants"]:
            bucket = summary["by_invariant"].setdefault(invariant, {"evals": [], "passed": 0, "total": 0})
            bucket["evals"].append(case["id"]); bucket["passed"] += passed; bucket["total"] += len(items)
    return summary, passed_all


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--dry-run", action="store_true", help="validate isolated materialized installation without calling a real agent")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--repetitions", type=int, help="run a non-gating focused sample count instead of the manifest threshold")
    parser.add_argument("--result-dir", type=Path, default=ROOT / ".eval-results")
    parser.add_argument("--baseline-skill", type=Path, help="materialized previous release/checkout to compare under the same suite")
    parser.add_argument("--official-only-control", action="store_true", help="run selected non-gating control with only the release-matched official Herdr skill")
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.suite)
        selected = [case for case in suite["cases"] if not args.case_ids or case["id"] in args.case_ids]
        if not selected or (args.case_ids and {case["id"] for case in selected} != set(args.case_ids)):
            raise EvalError("requested eval case does not exist")
        if args.timeout_seconds < 10:
            raise EvalError("timeout-seconds must be at least 10")
        if args.repetitions is not None:
            if args.repetitions < 1:
                raise EvalError("focused repetitions must be positive")
            selected = [
                {
                    **copy.deepcopy(case),
                    "repetitions": args.repetitions,
                    "threshold": {"required_passes": args.repetitions, "rationale": "focused non-gating sample"},
                    "release_gate": False,
                }
                for case in selected
            ]
        args.result_dir.mkdir(parents=True, exist_ok=True)
        retained_evidence_dir = args.result_dir / "audit-bundles"
        results = [item for case in selected for item in run_case(case, suite, ROOT, args.dry_run, args.timeout_seconds, retained_evidence_dir=retained_evidence_dir)]
        summary, passed = summarize(results, selected)
        comparisons: dict[str, dict[str, Any]] = {}
        if args.baseline_skill is not None:
            baseline = args.baseline_skill.resolve()
            if not (baseline / "SKILL.md").is_file():
                raise EvalError("baseline-skill must be a skill directory containing SKILL.md")
            comparisons["baseline"] = {"equivalent_environment": True, "comparison_note": "Same runner invocation, suite, fixture, Herdr binary, agent recipe, model, and grader; baseline is not an absolute release threshold.", "results": [item for case in selected for item in run_case(case, suite, ROOT, args.dry_run, args.timeout_seconds, baseline, "baseline", retained_evidence_dir)]}
        if args.official_only_control:
            comparisons["official_herdr_only"] = {"equivalent_environment": True, "comparison_note": "Same runner invocation, suite, fixture, Herdr binary, agent recipe, model, and grader; this is an optional capability control, not a release threshold.", "results": [item for case in selected for item in run_case(case, suite, ROOT, args.dry_run, args.timeout_seconds, None, "official-herdr-only", retained_evidence_dir)]}
        document = {"schema_version": RESULT_SCHEMA_VERSION, "created_at": datetime.now(UTC).isoformat(), "suite": str(args.suite), "results": results, "summary": summary, "comparisons": comparisons}
        output = args.result_dir / f"live-eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}.json"
        output.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"result": str(output), "summary": summary}, sort_keys=True))
        return 0 if args.dry_run or passed else 1
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
