"""Shared interface and validation primitives for Herdr harness adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


MODEL_ID_RE = re.compile(
    r"(?=.{1,192}\Z)~?[A-Za-z0-9][A-Za-z0-9._:+-]*"
    r"(?:/~?[A-Za-z0-9][A-Za-z0-9._:+-]*)*\Z"
)
IDENTIFIER_RE = re.compile(r"(?=.{1,128}\Z)[A-Za-z0-9][A-Za-z0-9._:+-]*\Z")
TOOL_NAME_RE = re.compile(r"(?=.{1,128}\Z)[A-Za-z][A-Za-z0-9._:+-]*\Z")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class HarnessError(Exception):
    """A safe, user-actionable adapter failure."""


ValueValidator = Callable[[str, str], None]
CatalogProjector = Callable[[bytes, str], list[dict[str, Any]]]
CatalogSelector = Callable[[list[dict[str, Any]], Path], list[dict[str, Any]]]
ArgumentSetValidator = Callable[[list[str], str], None]


@dataclass(frozen=True)
class ArgumentRule:
    validator: Optional[ValueValidator] = None
    repeatable: bool = False
    unique_value_key: bool = False

    @property
    def is_flag(self) -> bool:
        return self.validator is None


@dataclass(frozen=True)
class CatalogSpec:
    command: tuple[str, ...]
    modes: dict[str, tuple[str, ...]]
    projector: CatalogProjector
    selector: Optional[CatalogSelector] = None


@dataclass(frozen=True)
class EvidenceRootRule:
    option: str
    mode_option: Optional[str] = None
    restricted_modes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class HarnessAdapter:
    kind: str
    arguments: dict[str, ArgumentRule]
    argument_set_validator: Optional[ArgumentSetValidator] = None
    catalog: Optional[CatalogSpec] = None
    evidence_root: Optional[EvidenceRootRule] = None

    def validate_arguments(self, args: list[str], location: str) -> None:
        seen: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()
        seen_value_keys: dict[str, set[str]] = {}
        index = 0
        while index < len(args):
            option = args[index]
            rule = self.arguments.get(option)
            if rule is None:
                raise HarnessError(
                    f"{location}.args has an unsupported option at index {index}"
                )
            if option in seen and not rule.repeatable:
                raise HarnessError(f"{location}.args repeats a non-repeatable option")
            seen.add(option)
            index += 1
            if rule.is_flag:
                continue
            if index >= len(args):
                raise HarnessError(
                    f"{location}.args option at index {index - 1} requires a value"
                )
            assert rule.validator is not None
            rule.validator(args[index], f"{location}.args value at index {index}")
            pair = (option, args[index])
            if pair in seen_pairs:
                raise HarnessError(f"{location}.args repeats an option value")
            seen_pairs.add(pair)
            if rule.unique_value_key:
                value_key = args[index].split("=", 1)[0]
                option_keys = seen_value_keys.setdefault(option, set())
                if value_key in option_keys:
                    raise HarnessError(
                        f"{location}.args repeats an {option} configuration key"
                    )
                option_keys.add(value_key)
            index += 1
        if self.argument_set_validator is not None:
            self.argument_set_validator(args, location)

    def option_values(self, args: list[str], option: str) -> list[str]:
        values: list[str] = []
        index = 0
        while index < len(args):
            current = args[index]
            rule = self.arguments.get(current)
            index += 1
            if rule is not None and rule.is_flag:
                continue
            if index >= len(args):  # validate_arguments rejects this first
                break
            if current == option:
                values.append(args[index])
            index += 1
        return values

    def validate_lead_evidence_root(
        self,
        args: list[str],
        common: Path,
        location: str,
    ) -> None:
        rule = self.evidence_root
        if rule is None:
            return
        if rule.mode_option is not None:
            modes = self.option_values(args, rule.mode_option)
            if len(modes) != 1 or modes[0] not in rule.restricted_modes:
                return
        if str(common) not in self.option_values(args, rule.option):
            raise HarnessError(
                f"{location} {self.kind} args must add the exact Git common directory "
                f"with {rule.option}"
            )

    def project_catalog(
        self,
        raw: bytes,
        label: str,
        schema_version: int,
        project_root: Path,
    ) -> dict[str, Any]:
        if self.catalog is None:
            raise HarnessError(f"{self.kind} has no bounded model catalog adapter")
        models = self.catalog.projector(raw, label)
        if self.catalog.selector is not None:
            models = self.catalog.selector(models, project_root)
        return {
            "schema_version": schema_version,
            "harness": self.kind,
            "models": models,
        }

    def catalog_command(self, mode: str) -> tuple[str, ...]:
        if self.catalog is None:
            raise HarnessError(f"{self.kind} has no bounded model catalog adapter")
        mode_arguments = self.catalog.modes.get(mode)
        if mode_arguments is None:
            raise HarnessError(
                f"{self.kind} model catalog does not support the requested mode"
            )
        return (*self.catalog.command, *mode_arguments)


def validate_model(value: str, location: str) -> None:
    if MODEL_ID_RE.fullmatch(value) is None:
        raise HarnessError(f"{location} has an unsupported value")


def validate_identifier(value: str, location: str) -> None:
    if IDENTIFIER_RE.fullmatch(value) is None:
        raise HarnessError(f"{location} has an unsupported value")


def validate_tool_list(value: str, location: str) -> None:
    tools = [item for item in re.split(r"[\s,]+", value) if item]
    if not tools or not all(TOOL_NAME_RE.fullmatch(item) for item in tools):
        raise HarnessError(f"{location} has an unsupported value")


def choices(*allowed: str) -> ValueValidator:
    allowed_values = frozenset(allowed)

    def validate(value: str, location: str) -> None:
        if value not in allowed_values:
            raise HarnessError(f"{location} has an unsupported value")

    return validate


def validate_absolute_directory(value: str, location: str) -> None:
    path = Path(value)
    if not path.is_absolute():
        raise HarnessError(
            f"{location} has an unsupported directory; canonical absolute path required"
        )
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HarnessError(
            f"{location} has an unsupported directory; canonical absolute path required"
        ) from exc
    if not resolved.is_dir() or resolved == Path(resolved.anchor) or value != str(resolved):
        raise HarnessError(
            f"{location} has an unsupported directory; canonical absolute path required"
        )


def decode_catalog(raw: bytes, label: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError(f"{label} must be UTF-8: byte {exc.start}") from exc
    return ANSI_ESCAPE_RE.sub("", text)


def catalog_model_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or MODEL_ID_RE.fullmatch(value) is None:
        raise HarnessError(f"{label} has an invalid model identifier")
    return value
