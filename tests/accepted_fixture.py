from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


PUBLICATION_SCHEMA = "herdr.setup-publication"
ACCEPTANCE_SCHEMA = "herdr.setup-acceptance"
ACTIVATION_SCHEMA = "herdr.setup-activation"
CANDIDATE_SCHEMA = "herdr.setup-candidate"


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def digest(label: str, value: object) -> str:
    return hashlib.sha256(label.encode() + b"\0" + canonical(value)).hexdigest()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _grants(name: str) -> tuple[tuple[str, str, str], ...]:
    return {
        "lead": (
            ("runtime:codex", "runtime", "read"),
            ("project:assigned", "workspace", "read"),
            ("git-common:assigned", "git_common", "read"),
            ("control:run", "evidence", "write"),
        ),
        "engineer": (
            ("runtime:codex", "runtime", "read"),
            ("project:assigned", "workspace", "write"),
            ("git-common:assigned", "git_common", "read"),
            ("evidence:assignment", "evidence", "write"),
        ),
        "reviewer": (
            ("runtime:codex", "runtime", "read"),
            ("project:assigned", "workspace", "read"),
            ("git-common:assigned", "git_common", "read"),
            ("evidence:assignment", "evidence", "write"),
        ),
        "supervisor": (
            ("runtime:codex", "runtime", "read"),
            ("project:assigned", "workspace", "read"),
            ("notebook:session", "notebook", "write"),
        ),
    }[name]


def _native_launch(name: str, project: Path, common: Path) -> dict[str, object]:
    paths = {
        "runtime:codex": "/usr/bin",
        "project:assigned": str(project),
        "git-common:assigned": str(common),
        "control:run": str(project),
        "evidence:assignment": str(project),
        "notebook:session": str(project),
    }
    rules = [
        {"resource": resource, "path": paths[resource], "access": access}
        for resource, _binding, access in _grants(name)
    ]
    rules.append({"resource": None, "path": ":minimal", "access": "read"})
    return {
        "adapter_kind": "codex",
        "executable": "/usr/bin/true",
        "cwd": str(project),
        "arguments": ["--strict-config"],
        "permission_profile": "herdr_fixture",
        "config_overrides": ["agents.enabled=false"],
        "filesystem_rules": rules,
        "model": "gpt-test",
        "reasoning_effort": "medium",
        "native_agents_enabled": False,
        "network_enabled": False,
        "selected_binding_id": f"codex-{name}",
        "effective_envelope": [
            {
                "name": "fs.write" if access == "write" else "fs.read",
                "resource": resource,
            }
            for resource, _binding, access in _grants(name)
        ],
    }


def _role(name: str, launch_digest: str) -> str:
    common_fields = f'''adapter_kind = "codex"
executable = "/usr/bin/true"
runtime_root = "/usr/bin"
model = "gpt-test"
reasoning_effort = "medium"
selected_binding_id = "codex-{name}"
native_agents_enabled = false
network_enabled = false
proof_launch_spec_digest = "{launch_digest}"
'''
    sections = [f"[roles.{name}]\n{common_fields}"]
    for resource, binding, access in _grants(name):
        sections.append(
            f'''[[roles.{name}.filesystem]]
resource = {json.dumps(resource)}
binding = {json.dumps(binding)}
access = {json.dumps(access)}
'''
        )
    return "\n".join(sections)


def publish_accepted_setup(
    project: Path,
    *,
    supervisor: bool = True,
    proof_status: str = "PROVEN",
    omit_plan_role: str | None = None,
) -> dict[str, object]:
    project = project.resolve()
    if not (project / ".git").exists():
        subprocess.run(
            ["git", "init", "-q", str(project)],
            check=True,
            capture_output=True,
            text=True,
        )
    common = Path(
        subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--git-common-dir"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if not common.is_absolute():
        common = (project / common).resolve()
    discovery = "2" * 64
    roles = ["engineer", "lead", "reviewer"]
    if supervisor:
        roles.append("supervisor")
    launches = {role: _native_launch(role, project, common) for role in roles}
    role_plans = [
        {
            "role": role,
            "requirement": {},
            "selector_receipt": {},
            "native_launch_spec": launches[role],
        }
        for role in roles
        if role != omit_plan_role
    ]
    plan_projection = {
        "schema_version": CANDIDATE_SCHEMA,
        "discovery": {},
        "discovery_digest": discovery,
        "human_decisions": {},
        "human_decisions_digest": "5" * 64,
        "compiled_policy": {},
        "model_bindings": [],
        "roles": role_plans,
        "provenance": [],
    }
    candidate = digest("herdr-setup-candidate", plan_projection)
    setup_plan = canonical({**plan_projection, "candidate_digest": candidate}) + b"\n"
    proof_roles = []
    for role in roles:
        check = {
            "identifier": f"{role}.native_spawn.config",
            "operation": "NATIVE_SPAWN",
            "resource": None,
            "target": "agents.enabled",
            "expected": "DENY",
            "observed": "DENY",
            "assurance": "STATIC_PROVEN",
            "error_code": None,
            "detail_digest": None,
        }
        role_projection = {
            "role": role,
            "candidate_digest": candidate,
            "launch_spec_digest": digest(
                "herdr-native-launch", launches[role]
            ),
            "status": "PROVEN",
            "checks": [check],
        }
        proof_roles.append(
            {
                **role_projection,
                "receipt_digest": digest("herdr-role-proof", role_projection),
            }
        )
    proof_projection = {
        "status": proof_status,
        "candidate_digest": candidate,
        "discovery_digest": discovery,
        "current_discovery_digest": discovery,
        "roles": proof_roles,
    }
    proof = digest("herdr-runtime-proof", proof_projection)
    runtime_proof = canonical({**proof_projection, "receipt_digest": proof}) + b"\n"
    config = (
        f'''schema = "{PUBLICATION_SCHEMA}"
candidate_digest = "{candidate}"
discovery_digest = "{discovery}"
project_root = {json.dumps(str(project))}
repository_root = {json.dumps(str(project))}
git_common_dir = {json.dumps(str(common))}
live_orchestration_language = "Vietnamese"
durable_artifact_language = "English"
native_agent_policy = "disabled"

'''
        + "\n".join(
            _role(role, digest("herdr-native-launch", launches[role]))
            for role in roles
        )
    ).encode()
    artifacts_data = {
        "herdr-orchestrator.toml": config,
        "runtime-proof.json": runtime_proof,
        "setup-plan.json": setup_plan,
        "workspace-protocol.md": b"# Workspace Protocol\n\nAccepted setup fixture.\n",
    }
    artifacts = [
        {"path": path, "sha256": sha256(data), "size": len(data)}
        for path, data in sorted(artifacts_data.items())
    ]
    publication_projection = {
        "schema": PUBLICATION_SCHEMA,
        "candidate_digest": candidate,
        "discovery_digest": discovery,
        "runtime_proof_digest": proof,
        "artifacts": artifacts,
    }
    publication = digest("herdr-setup-publication", publication_projection)
    generation_relative = f"generations/{publication}"
    receipt_projection = {
        "schema": ACCEPTANCE_SCHEMA,
        "status": "ACCEPTED",
        "candidate_digest": candidate,
        "discovery_digest": discovery,
        "runtime_proof_digest": proof,
        "publication_digest": publication,
        "prior_activation_digest": None,
        "generation": generation_relative,
        "artifacts": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in artifacts
        ],
    }
    receipt_digest = digest("herdr-setup-acceptance", receipt_projection)
    setup_root = project / ".orchestration/setup"
    generation = setup_root / generation_relative
    generation.mkdir(parents=True)
    for path, data in artifacts_data.items():
        (generation / path).write_bytes(data)
    publication_manifest = {
        **publication_projection,
        "publication_digest": publication,
    }
    receipt = {**receipt_projection, "receipt_digest": receipt_digest}
    (generation / "publication-manifest.json").write_bytes(
        canonical(publication_manifest) + b"\n"
    )
    (generation / "acceptance-receipt.json").write_bytes(canonical(receipt) + b"\n")
    activation = {
        "schema": ACTIVATION_SCHEMA,
        "status": "ACCEPTED",
        "candidate_digest": candidate,
        "discovery_digest": discovery,
        "runtime_proof_digest": proof,
        "publication_digest": publication,
        "acceptance_receipt_digest": receipt_digest,
        "generation": generation_relative,
        "artifacts": artifacts,
    }
    current = setup_root / "current.json"
    current.write_bytes(canonical(activation) + b"\n")
    return {
        "project": project,
        "common": common,
        "generation": generation,
        "activation": current,
        "config": generation / "herdr-orchestrator.toml",
        "protocol": generation / "workspace-protocol.md",
        "candidate_digest": candidate,
        "publication_digest": publication,
    }
