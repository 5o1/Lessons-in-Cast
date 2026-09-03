"""Character mapping loader and consistency checks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigurationError, find_repository_root


@dataclass(frozen=True, slots=True)
class CharacterDefinition:
    id: str
    name: str
    type: str
    members: tuple[str, ...]
    render_mode: str | None
    definition_path: str
    definition_line: int
    built_in: bool
    model_path: str
    generation_script_path: str

    @property
    def synthesis_members(self) -> tuple[str, ...]:
        return self.members if self.type == "ensemble" else (self.id,)


def load_characters(
    path: Path = Path("configs/characters.toml"),
    *,
    repository_root: Path | None = None,
) -> dict[str, CharacterDefinition]:
    root = (repository_root or find_repository_root()).resolve()
    resolved_path = path if path.is_absolute() else root / path
    try:
        with resolved_path.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Unable to load {resolved_path}: {exc}") from exc
    raw_characters = data.get("characters")
    if not isinstance(raw_characters, dict):
        raise ConfigurationError(f"{resolved_path}: [characters] table is required")

    result: dict[str, CharacterDefinition] = {}
    for character_id, raw in raw_characters.items():
        if not isinstance(raw, dict):
            raise ConfigurationError(
                f"{resolved_path}: characters.{character_id} must be a table"
            )
        result[character_id] = _parse_character(resolved_path, character_id, raw)

    for character in result.values():
        if character.type != "ensemble":
            continue
        if not character.members:
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} has no members"
            )
        if len(character.members) != len(set(character.members)):
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} has duplicate members"
            )
        if character.id in character.members:
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} contains itself"
            )
        missing = [member for member in character.members if member not in result]
        if missing:
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} has unknown members {missing!r}"
            )
        if character.render_mode is None:
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} requires render_mode"
            )
        if character.render_mode != "unison":
            raise ConfigurationError(
                f"{resolved_path}: ensemble {character.id!r} has unsupported "
                f"render_mode {character.render_mode!r}"
            )
    return result


def _parse_character(
    source: Path,
    character_id: str,
    raw: dict[str, Any],
) -> CharacterDefinition:
    character_type = raw.get("type", "individual")
    if character_type not in {"individual", "ensemble"}:
        raise ConfigurationError(
            f"{source}: characters.{character_id}.type is invalid"
        )
    members = raw.get("members", ())
    if not isinstance(members, list | tuple) or not all(
        isinstance(member, str) for member in members
    ):
        raise ConfigurationError(
            f"{source}: characters.{character_id}.members must be an array of strings"
        )
    if character_type == "individual" and members:
        raise ConfigurationError(
            f"{source}: individual character {character_id!r} cannot have members"
        )
    required_types: dict[str, type] = {
        "name": str,
        "definition_path": str,
        "definition_line": int,
        "built_in": bool,
        "model_path": str,
        "generation_script_path": str,
    }
    for field, expected in required_types.items():
        if (
            field not in raw
            or not isinstance(raw[field], expected)
            or (expected is int and isinstance(raw[field], bool))
        ):
            raise ConfigurationError(
                f"{source}: characters.{character_id}.{field} has an invalid type"
            )
    render_mode = raw.get("render_mode")
    if render_mode is not None and not isinstance(render_mode, str):
        raise ConfigurationError(
            f"{source}: characters.{character_id}.render_mode must be a string"
        )
    return CharacterDefinition(
        id=character_id,
        name=raw["name"],
        type=character_type,
        members=tuple(members),
        render_mode=render_mode,
        definition_path=raw["definition_path"],
        definition_line=raw["definition_line"],
        built_in=raw["built_in"],
        model_path=raw["model_path"],
        generation_script_path=raw["generation_script_path"],
    )
