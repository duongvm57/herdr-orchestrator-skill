#!/usr/bin/env python3
"""Stable Supervisor-facing interface for governance observation records."""

from __future__ import annotations

import sys
from pathlib import Path

import herdr_orchestrator


OPERATIONS = {
    "record-observation": "supervisor-record",
    "request-human-attention": "supervisor-human-attention",
    "recommend-handoff": "supervisor-recommend-handoff",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in OPERATIONS:
        available = ", ".join(OPERATIONS)
        print(f"usage: herdr_supervisor_ops.py <{available}> [options]", file=sys.stderr)
        return 2
    run_dir = Path(__file__).resolve().parent.parent
    return herdr_orchestrator.main(
        [OPERATIONS[sys.argv[1]], "--run-dir", str(run_dir), *sys.argv[2:]]
    )


if __name__ == "__main__":
    raise SystemExit(main())
