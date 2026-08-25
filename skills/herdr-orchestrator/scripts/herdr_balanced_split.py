#!/usr/bin/env python3
"""Create one balanced, run-managed Herdr pane without changing focus."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 2
CELL_ASPECT = 2.0
MIN_COLUMNS = 36
MIN_ROWS = 12
COMMAND_TIMEOUT_SECONDS = 15


class LayoutError(RuntimeError):
    pass


def _rect(pane: dict[str, Any]) -> dict[str, int]:
    rect = pane.get("rect")
    if not isinstance(rect, dict):
        raise LayoutError(f"pane {pane.get('pane_id')!r} has no rectangle")
    try:
        return {key: int(rect[key]) for key in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError) as error:
        raise LayoutError(
            f"pane {pane.get('pane_id')!r} has an invalid rectangle"
        ) from error


def choose_split(
    layout: dict[str, Any],
    managed_panes: set[str],
    *,
    cell_aspect: float = CELL_ASPECT,
    min_columns: int = MIN_COLUMNS,
    min_rows: int = MIN_ROWS,
) -> dict[str, Any]:
    """Choose the largest usable managed leaf and its visually balanced axis."""
    candidates: list[tuple[tuple[int, int, int, str], dict[str, Any], bool, bool]] = []
    for pane in layout.get("panes", []):
        pane_id = pane.get("pane_id")
        if pane_id not in managed_panes:
            continue
        rect = _rect(pane)
        can_right = rect["width"] >= min_columns * 2
        can_down = rect["height"] >= min_rows * 2
        if not (can_right or can_down):
            continue
        rank = (
            rect["width"] * rect["height"],
            rect["x"],
            -rect["y"],
            str(pane_id),
        )
        candidates.append(
            (rank, {"pane_id": pane_id, "rect": rect}, can_right, can_down)
        )

    if not candidates:
        raise LayoutError(
            "no run-managed pane is large enough to split without creating an unreadable pane"
        )

    _, target, can_right, can_down = max(candidates, key=lambda item: item[0])
    rect = target["rect"]
    preferred = "right" if rect["width"] >= cell_aspect * rect["height"] else "down"
    if preferred == "right" and not can_right:
        preferred = "down"
    elif preferred == "down" and not can_down:
        preferred = "right"
    target["direction"] = preferred
    return target


def _run_json(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise LayoutError(
            f"{' '.join(command[:3])} timed out after {COMMAND_TIMEOUT_SECONDS}s"
        ) from error
    except OSError as error:
        raise LayoutError(f"cannot execute {command[0]}: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise LayoutError(f"{' '.join(command[:3])} failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise LayoutError(f"{' '.join(command[:3])} returned invalid JSON") from error


def _layout_from(response: dict[str, Any]) -> dict[str, Any]:
    try:
        layout = response["result"]["layout"]
    except (KeyError, TypeError) as error:
        raise LayoutError("Herdr layout response has no result.layout") from error
    if not isinstance(layout, dict) or not isinstance(layout.get("panes"), list):
        raise LayoutError("Herdr layout response is malformed")
    if layout.get("zoomed"):
        raise LayoutError("the target Herdr tab is zoomed; restore its full layout first")
    return layout


def _new_state(layout: dict[str, Any], anchor: str) -> dict[str, Any]:
    live = {pane.get("pane_id") for pane in layout["panes"]}
    if anchor not in live:
        raise LayoutError(f"anchor pane is not in the resolved layout: {anchor}")
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": layout.get("workspace_id"),
        "tab_id": layout.get("tab_id"),
        "managed_panes": [anchor],
        "splits": [],
        "retirements": [],
        "split_intent": None,
        "retirement_intent": None,
    }


def _upgrade_v1_state(state: dict[str, Any], path: Path) -> dict[str, Any]:
    """Upgrade only v1 states that never relied on implicit pane retirement."""
    required = {"schema_version", "workspace_id", "tab_id", "managed_panes", "splits"}
    if set(state) != required:
        raise LayoutError(f"layout state has an unsupported shape: {path}")
    managed = state.get("managed_panes")
    splits = state.get("splits")
    if not isinstance(managed, list) or not isinstance(splits, list):
        raise LayoutError(f"layout state has an unsupported shape: {path}")
    created = {
        split.get("new_pane_id")
        for split in splits
        if isinstance(split, dict)
        and isinstance(split.get("new_pane_id"), str)
        and split.get("new_pane_id")
    }
    absent_from_managed = created.difference(managed)
    if absent_from_managed:
        raise LayoutError(
            "schema v1 state contains implicitly retired panes and cannot be upgraded "
            "safely: "
            + ", ".join(sorted(absent_from_managed))
        )
    return {
        **state,
        "schema_version": SCHEMA_VERSION,
        "retirements": [],
        "split_intent": None,
        "retirement_intent": None,
    }


def _validate_rect(value: Any, description: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"}:
        raise LayoutError(f"layout state has an invalid {description}")
    try:
        rect = {key: int(value[key]) for key in ("x", "y", "width", "height")}
    except (TypeError, ValueError) as error:
        raise LayoutError(f"layout state has an invalid {description}") from error
    if rect["width"] <= 0 or rect["height"] <= 0:
        raise LayoutError(f"layout state has an invalid {description}")
    return rect


def _load_state(path: Path, layout: dict[str, Any], anchor: str) -> dict[str, Any]:
    if not path.exists():
        return _new_state(layout, anchor)
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise LayoutError(f"layout state is unreadable: {path}") from error
    if isinstance(state, dict) and state.get("schema_version") == 1:
        state = _upgrade_v1_state(state, path)
    required = {
        "schema_version",
        "workspace_id",
        "tab_id",
        "managed_panes",
        "splits",
        "retirements",
        "split_intent",
        "retirement_intent",
    }
    if (
        not isinstance(state, dict)
        or set(state) != required
        or state["schema_version"] != SCHEMA_VERSION
    ):
        raise LayoutError(f"layout state has an unsupported shape: {path}")
    managed = state["managed_panes"]
    splits = state["splits"]
    retirements = state["retirements"]
    if (
        not isinstance(managed, list)
        or not managed
        or any(not isinstance(pane_id, str) or not pane_id for pane_id in managed)
        or len(managed) != len(set(managed))
        or not isinstance(splits, list)
        or not isinstance(retirements, list)
    ):
        raise LayoutError(
            f"layout state has invalid managed panes, split history, or retirements: {path}"
        )
    split_keys = {"target_pane_id", "direction", "new_pane_id"}
    if any(
        not isinstance(split, dict)
        or set(split) != split_keys
        or not isinstance(split["target_pane_id"], str)
        or not split["target_pane_id"]
        or split["direction"] not in {"right", "down"}
        or not isinstance(split["new_pane_id"], str)
        or not split["new_pane_id"]
        for split in splits
    ):
        raise LayoutError(f"layout state has invalid split history: {path}")
    created = {split["new_pane_id"] for split in splits}
    if len(created) != len(splits) or managed[0] in created:
        raise LayoutError(f"layout state has inconsistent split history: {path}")
    retirement_keys = {"pane_id"}
    if any(
        not isinstance(retirement, dict)
        or set(retirement) != retirement_keys
        or not isinstance(retirement["pane_id"], str)
        or not retirement["pane_id"]
        for retirement in retirements
    ):
        raise LayoutError(f"layout state has invalid retirement history: {path}")
    retired = {retirement["pane_id"] for retirement in retirements}
    if (
        len(retired) != len(retirements)
        or not retired.issubset(created)
        or retired.intersection(managed)
        or created != retired.union(set(managed[1:]))
    ):
        raise LayoutError(f"layout state has inconsistent retirement history: {path}")
    split_intent = state["split_intent"]
    retirement_intent = state["retirement_intent"]
    if split_intent is not None and retirement_intent is not None:
        raise LayoutError("layout state contains two concurrent pending transactions")
    if split_intent is not None:
        intent_keys = {
            "target_pane_id",
            "direction",
            "cwd",
            "live_pane_ids",
            "target_rect",
        }
        if (
            not isinstance(split_intent, dict)
            or set(split_intent) != intent_keys
            or split_intent["target_pane_id"] not in managed
            or split_intent["direction"] not in {"right", "down"}
            or not isinstance(split_intent["cwd"], str)
            or not split_intent["cwd"]
            or not isinstance(split_intent["live_pane_ids"], list)
            or not split_intent["live_pane_ids"]
            or any(
                not isinstance(pane_id, str) or not pane_id
                for pane_id in split_intent["live_pane_ids"]
            )
            or len(split_intent["live_pane_ids"])
            != len(set(split_intent["live_pane_ids"]))
        ):
            raise LayoutError(f"layout state has an invalid split intent: {path}")
        split_intent["target_rect"] = _validate_rect(
            split_intent["target_rect"], "split-intent target rectangle"
        )
    if retirement_intent is not None:
        if (
            not isinstance(retirement_intent, dict)
            or set(retirement_intent) != {"pane_id"}
            or retirement_intent["pane_id"] not in managed
            or retirement_intent["pane_id"] not in created
        ):
            raise LayoutError(f"layout state has an invalid retirement intent: {path}")
    if (
        state["workspace_id"] != layout.get("workspace_id")
        or state["tab_id"] != layout.get("tab_id")
    ):
        raise LayoutError("layout state belongs to another Herdr workspace or tab")
    return state


def _live_pane_ids(layout: dict[str, Any]) -> set[str]:
    pane_ids = {pane.get("pane_id") for pane in layout["panes"]}
    if any(not isinstance(pane_id, str) or not pane_id for pane_id in pane_ids):
        raise LayoutError("Herdr layout contains an invalid pane ID")
    return pane_ids


def _pane_by_id(layout: dict[str, Any], pane_id: str) -> dict[str, Any]:
    matches = [pane for pane in layout["panes"] if pane.get("pane_id") == pane_id]
    if len(matches) != 1:
        raise LayoutError(f"pane {pane_id!r} is not uniquely present in the layout")
    return matches[0]


def _matches_intended_split(
    layout: dict[str, Any], candidate_id: str, intent: dict[str, Any]
) -> bool:
    before = intent["target_rect"]
    target = _rect(_pane_by_id(layout, intent["target_pane_id"]))
    candidate = _rect(_pane_by_id(layout, candidate_id))
    if min(
        target["width"],
        target["height"],
        candidate["width"],
        candidate["height"],
    ) <= 0:
        return False
    if intent["direction"] == "right":
        return (
            target["x"] == before["x"]
            and target["y"] == before["y"]
            and target["height"] == before["height"]
            and candidate["y"] == before["y"]
            and candidate["height"] == before["height"]
            and candidate["x"] == target["x"] + target["width"]
            and candidate["x"] + candidate["width"]
            == before["x"] + before["width"]
            and abs(target["width"] - candidate["width"]) <= 1
        )
    return (
        target["x"] == before["x"]
        and target["y"] == before["y"]
        and target["width"] == before["width"]
        and candidate["x"] == before["x"]
        and candidate["width"] == before["width"]
        and candidate["y"] == target["y"] + target["height"]
        and candidate["y"] + candidate["height"]
        == before["y"] + before["height"]
        and abs(target["height"] - candidate["height"]) <= 1
    )


def _validate_managed_presence(state: dict[str, Any], layout: dict[str, Any]) -> None:
    live = _live_pane_ids(layout)
    missing = [pane_id for pane_id in state["managed_panes"] if pane_id not in live]
    retirement_intent = state["retirement_intent"]
    permitted = (
        {retirement_intent["pane_id"]} if retirement_intent is not None else set()
    )
    unexpected = [pane_id for pane_id in missing if pane_id not in permitted]
    if unexpected:
        raise LayoutError(
            "run-managed panes disappeared without an explicit retirement intent: "
            + ", ".join(unexpected)
        )


def _finalize_retirement(
    path: Path, state: dict[str, Any], layout: dict[str, Any]
) -> dict[str, Any] | None:
    intent = state["retirement_intent"]
    if intent is None:
        return None
    pane_id = intent["pane_id"]
    if pane_id in _live_pane_ids(layout):
        return None
    state["managed_panes"].remove(pane_id)
    state["retirements"].append({"pane_id": pane_id})
    state["retirement_intent"] = None
    _write_state(path, state)
    return {"operation": "retire", "retired_pane_id": pane_id, "recovered": True}


def _recover_split(
    path: Path,
    state: dict[str, Any],
    layout: dict[str, Any],
    *,
    requested_cwd: str,
    expected_new_pane: str | None = None,
) -> dict[str, Any] | None:
    intent = state["split_intent"]
    if intent is None:
        return None
    if requested_cwd != intent["cwd"]:
        raise LayoutError(
            "pending split belongs to another requested cwd; recover it with "
            f"--cwd {intent['cwd']} before requesting a different pane"
        )
    before = set(intent["live_pane_ids"])
    live = _live_pane_ids(layout)
    removed = sorted(before.difference(live))
    if removed:
        raise LayoutError(
            "panes disappeared while a split transaction was pending: "
            + ", ".join(removed)
        )
    added = sorted(live.difference(before))
    if not added:
        if expected_new_pane is not None:
            raise LayoutError(
                "Herdr returned a new pane but the layout has not exposed it; "
                "the split intent was preserved for an explicit recovery call"
            )
        state["split_intent"] = None
        _write_state(path, state)
        return {
            "operation": "split_recovery",
            "requested_cwd": intent["cwd"],
            "mutation_observed": False,
            "retry_required": True,
            "recovered": True,
        }
    if len(added) != 1:
        raise LayoutError(
            "cannot deterministically recover pending split; unexpected panes appeared: "
            + ", ".join(added)
        )
    new_pane = added[0]
    if expected_new_pane is not None and new_pane != expected_new_pane:
        raise LayoutError(
            "Herdr split response does not match the pane added to the layout: "
            f"reported {expected_new_pane}, observed {new_pane}"
        )
    if not _matches_intended_split(layout, new_pane, intent):
        raise LayoutError(
            "cannot adopt the only new pane because it does not match the persisted split intent: "
            + new_pane
        )
    state["managed_panes"].append(new_pane)
    state["splits"].append(
        {
            "target_pane_id": intent["target_pane_id"],
            "direction": intent["direction"],
            "new_pane_id": new_pane,
        }
    )
    state["split_intent"] = None
    _write_state(path, state)
    return {
        "operation": "split",
        "choice": {
            "pane_id": intent["target_pane_id"],
            "rect": intent["target_rect"],
            "direction": intent["direction"],
        },
        "new_pane_id": new_pane,
        "recovered": True,
    }


def _write_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise LayoutError(f"cannot write layout state {path}: {error}") from error


@contextmanager
def _state_lock(path: Path):
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
    except OSError as error:
        raise LayoutError(f"cannot lock layout state {path}: {error}") from error


def _new_pane_id(response: dict[str, Any]) -> str:
    try:
        pane_id = response["result"]["pane"]["pane_id"]
    except (KeyError, TypeError) as error:
        raise LayoutError("Herdr split response has no result.pane.pane_id") from error
    if not isinstance(pane_id, str) or not pane_id:
        raise LayoutError("Herdr split returned an invalid pane ID")
    return pane_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split the best run-managed Herdr pane using balanced geometry, or "
            "transactionally retire a run-created pane."
        )
    )
    parser.add_argument(
        "--state", required=True, type=Path, help="run-local layout state path"
    )
    parser.add_argument(
        "--cwd", default=os.getcwd(), help="working directory for the new pane"
    )
    parser.add_argument(
        "--anchor",
        default=os.environ.get("HERDR_PANE_ID"),
        help="live pane used to resolve the tab",
    )
    parser.add_argument(
        "--herdr",
        default="herdr",
        help="Herdr executable or absolute path",
    )
    parser.add_argument(
        "--retire",
        metavar="PANE_ID",
        help="persist retirement intent, then close one run-created pane",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the choice without splitting or writing state",
    )
    return parser.parse_args()


def _validate_retirement_target(
    state: dict[str, Any], pane_id: str, anchor: str
) -> None:
    created = {split["new_pane_id"] for split in state["splits"]}
    if pane_id == anchor:
        raise LayoutError("cannot retire the pane currently used as the layout anchor")
    if pane_id not in state["managed_panes"]:
        raise LayoutError(f"pane is not currently run-managed: {pane_id}")
    if pane_id not in created:
        raise LayoutError(f"only a run-created pane may be retired: {pane_id}")


def _print_result(result: dict[str, Any], state_path: Path, dry_run: bool) -> None:
    output = {**result, "state": str(state_path), "dry_run": dry_run}
    print(json.dumps(output, sort_keys=True))


def main() -> int:
    args = parse_args()
    if os.environ.get("HERDR_ENV") != "1":
        raise LayoutError("HERDR_ENV=1 is required")
    if not args.anchor:
        raise LayoutError("--anchor or HERDR_PANE_ID is required")
    herdr = args.herdr
    if not herdr or any(character in herdr for character in "\r\n\0"):
        raise LayoutError("--herdr must be one safe nonempty argument")
    cwd = Path(args.cwd).resolve()
    if not args.retire and not cwd.is_dir():
        raise LayoutError(f"new-pane cwd is not a directory: {cwd}")
    if args.dry_run:
        layout = _layout_from(
            _run_json([herdr, "pane", "layout", "--pane", args.anchor])
        )
        state = _load_state(args.state, layout, args.anchor)
        _validate_managed_presence(state, layout)
        if state["split_intent"] is not None or state["retirement_intent"] is not None:
            raise LayoutError(
                "layout state has a pending transaction; run without --dry-run to recover it"
            )
        if args.retire:
            _validate_retirement_target(state, args.retire, args.anchor)
            _print_result(
                {"operation": "retire", "retired_pane_id": args.retire},
                args.state,
                True,
            )
            return 0
        choice = choose_split(layout, set(state["managed_panes"]))
        _print_result({"operation": "split", "choice": choice}, args.state, True)
        return 0

    with _state_lock(args.state):
        layout = _layout_from(
            _run_json([herdr, "pane", "layout", "--pane", args.anchor])
        )
        state = _load_state(args.state, layout, args.anchor)
        _validate_managed_presence(state, layout)

        recovered_retirement = _finalize_retirement(args.state, state, layout)
        if recovered_retirement is not None:
            _print_result(recovered_retirement, args.state, False)
            return 0

        if state["split_intent"] is not None:
            if args.retire:
                raise LayoutError(
                    "a split transaction is pending; recover it before retirement"
                )
            recovered_split = _recover_split(
                args.state, state, layout, requested_cwd=str(cwd)
            )
            if recovered_split is None:
                raise LayoutError("pending split recovery produced no result")
            _print_result(recovered_split, args.state, False)
            return 0

        retirement_intent = state["retirement_intent"]
        if retirement_intent is not None:
            pending_pane = retirement_intent["pane_id"]
            if args.retire != pending_pane:
                raise LayoutError(
                    "retirement is pending for "
                    f"{pending_pane}; rerun with --retire {pending_pane}"
                )

        if args.retire:
            _validate_retirement_target(state, args.retire, args.anchor)
            if retirement_intent is None:
                state["retirement_intent"] = {"pane_id": args.retire}
                _write_state(args.state, state)
            _run_json([herdr, "pane", "close", args.retire])
            layout_after_close = _layout_from(
                _run_json([herdr, "pane", "layout", "--pane", args.anchor])
            )
            _validate_managed_presence(state, layout_after_close)
            retired = _finalize_retirement(args.state, state, layout_after_close)
            if retired is None:
                raise LayoutError(
                    f"Herdr reported success but retired pane is still live: {args.retire}"
                )
            retired["recovered"] = False
            _print_result(retired, args.state, False)
            return 0

        choice = choose_split(layout, set(state["managed_panes"]))
        live_before = sorted(_live_pane_ids(layout))
        state["split_intent"] = {
            "target_pane_id": choice["pane_id"],
            "direction": choice["direction"],
            "cwd": str(cwd),
            "live_pane_ids": live_before,
            "target_rect": choice["rect"],
        }
        _write_state(args.state, state)
        split = _run_json(
            [
                herdr,
                "pane",
                "split",
                "--pane",
                choice["pane_id"],
                "--direction",
                choice["direction"],
                "--ratio",
                "0.5",
                "--cwd",
                str(cwd),
                "--no-focus",
            ]
        )
        new_pane = _new_pane_id(split)
        if new_pane in live_before:
            raise LayoutError(f"Herdr split returned an existing pane ID: {new_pane}")
        layout_after_split = _layout_from(
            _run_json([herdr, "pane", "layout", "--pane", args.anchor])
        )
        _validate_managed_presence(state, layout_after_split)
        completed_split = _recover_split(
            args.state,
            state,
            layout_after_split,
            requested_cwd=str(cwd),
            expected_new_pane=new_pane,
        )
        if completed_split is None:
            raise LayoutError("completed split recovery produced no result")
        completed_split["recovered"] = False
    _print_result(
        completed_split,
        args.state,
        False,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LayoutError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
