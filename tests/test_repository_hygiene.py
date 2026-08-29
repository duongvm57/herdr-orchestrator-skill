from __future__ import annotations

import ast
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/herdr-orchestrator"
EXCLUDED_PATHS = {
    "maintenance/herdr-orchestrator-target-architecture-plan.md",
}
SOURCE_SUFFIXES = {".py", ".md", ".toml", ".json", ".yaml", ".yml"}
BAD_ARTIFACT_NAME = re.compile(
    r"(?:^|[_-])(?:phase\d*|step\d*|v\d+|new|old|final|refactored)(?:[_-]|$)",
    re.IGNORECASE,
)
BAD_IDENTIFIER = re.compile(
    r"(?:phase\d*|step\d*|v\d+|new|old|final|refactored)$", re.IGNORECASE
)


def changed_source_paths() -> list[Path]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        raw = record[3:].decode("utf-8")
        path = Path(raw)
        if (
            path.as_posix() not in EXCLUDED_PATHS
            and path.suffix in SOURCE_SUFFIXES
            and path.is_file()
        ):
            paths.append(path)
    return paths


def identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


class RepositoryHygieneTests(unittest.TestCase):
    def test_rejects_milestone_and_migration_names(self) -> None:
        for name in ("phase1_test", "runtime_v2", "new_runtime", "build_assignment_v2"):
            self.assertRegex(name, BAD_ARTIFACT_NAME)
        self.assertRegex("SupervisorV2", BAD_IDENTIFIER)
        self.assertNotRegex("schema_version", BAD_ARTIFACT_NAME)

    def test_changed_source_artifacts_and_python_symbols_use_final_names(self) -> None:
        for path in changed_source_paths():
            self.assertIsNone(BAD_ARTIFACT_NAME.search(path.stem), path)
            if path.suffix == ".py":
                for name in identifiers((ROOT / path).read_text(encoding="utf-8")):
                    self.assertIsNone(BAD_IDENTIFIER.search(name), f"{path}: {name}")

    def test_generic_runtime_seam_is_not_multiplied(self) -> None:
        seams = sorted(SKILL_ROOT.glob("scripts/*runtime*.py"))
        self.assertLessEqual(len(seams), 1, seams)


if __name__ == "__main__":
    unittest.main()
