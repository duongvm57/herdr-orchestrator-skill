#!/usr/bin/env python3
"""Stable Lead-facing interface for run-local Peer lifecycle operations."""

from __future__ import annotations

import sys
from pathlib import Path

import herdr_orchestrator


OPERATIONS = {
    "launch-peer": "lead-launch-peer",
    "launch-reviewer": "lead-launch-reviewer",
    "wait": "lead-wait",
    "collect": "lead-collect",
    "followup": "lead-followup",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in OPERATIONS:
        available = ", ".join(OPERATIONS)
        print(f"usage: herdr_lead_ops.py <{available}> [options]", file=sys.stderr)
        return 2
    run_dir = Path(__file__).resolve().parent.parent
    return herdr_orchestrator.main(
        [OPERATIONS[sys.argv[1]], "--run-dir", str(run_dir), *sys.argv[2:]]
    )


if __name__ == "__main__":
    raise SystemExit(main())
