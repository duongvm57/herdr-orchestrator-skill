"""Mechanical inventory for harnesses without an authority adapter."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .candidate import HarnessObservation, HarnessStatus


KNOWN_HARNESSES = ("claude", "codex", "gemini", "opencode", "pi")


@lru_cache(maxsize=8)
def discover_unadapted_harnesses(
    *,
    excluded: Iterable[str] = (),
) -> tuple[HarnessObservation, ...]:
    """Report every known harness even when Herdr cannot yet enforce it.

    This inventory deliberately records no inferred models or capabilities.
    An installed harness without an authority adapter is visible but ineligible.
    """

    omitted = frozenset(excluded)
    observations: list[HarnessObservation] = []
    for kind in KNOWN_HARNESSES:
        if kind in omitted:
            continue
        located = shutil.which(kind)
        if located is None:
            observations.append(HarnessObservation(kind, HarnessStatus.NOT_INSTALLED))
            continue
        executable = str(Path(located).resolve())
        try:
            completed = subprocess.run(
                (executable, "--version"),
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        version = None
        issues = ["authority_adapter_unavailable"]
        if completed is not None and completed.returncode == 0:
            lines = (completed.stdout or completed.stderr).strip().splitlines()
            candidate = lines[0][:128] if lines else ""
            if candidate and not any(ord(character) < 32 for character in candidate):
                version = candidate
            else:
                issues.append("version_output_invalid")
        else:
            issues.append("version_probe_failed")
        observations.append(
            HarnessObservation(
                kind=kind,
                status=HarnessStatus.DETECTED_PARTIAL,
                executable=executable,
                version=version,
                issue_codes=tuple(issues),
            )
        )
    return tuple(observations)
