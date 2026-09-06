"""Backend-neutral proper-noun pronunciation configuration."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigurationError, find_repository_root


_SYSTEM_ID = re.compile(r"[a-z][a-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class ProperNounPronunciation:
    """Pronunciations available for one exact proper noun."""

    term: str
    systems: tuple[tuple[str, str], ...]

    def for_system(self, system: str) -> str | None:
        return dict(self.systems).get(system)

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "systems": dict(self.systems),
        }


@dataclass(frozen=True, slots=True)
class PronunciationLexicon:
    """Validated proper nouns keyed by backend pronunciation system."""

    entries: tuple[ProperNounPronunciation, ...]

    def for_system(self, system: str) -> dict[str, str]:
        if not _SYSTEM_ID.fullmatch(system):
            raise ValueError(f"Invalid pronunciation system: {system!r}")
        result: dict[str, str] = {}
        for entry in self.entries:
            pronunciation = entry.for_system(system)
            if pronunciation is not None:
                result[entry.term] = pronunciation
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            entry.term: dict(entry.systems)
            for entry in self.entries
        }


def load_pronunciation_lexicon(
    path: Path = Path("configs/pronunciations.toml"),
    *,
    repository_root: Path | None = None,
) -> PronunciationLexicon:
    """Load the shared proper-noun pronunciation lexicon."""

    root = (repository_root or find_repository_root()).resolve()
    resolved = path if path.is_absolute() else root / path
    try:
        with resolved.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Unable to load {resolved}: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ConfigurationError(
            f"{resolved}: schema_version must be 1"
        )
    raw_entries = data.get("proper_nouns")
    if not isinstance(raw_entries, dict):
        raise ConfigurationError(
            f"{resolved}: [proper_nouns] table is required"
        )

    entries: list[ProperNounPronunciation] = []
    normalized_terms: set[str] = set()
    for term, raw_systems in raw_entries.items():
        if not isinstance(term, str) or not term.strip():
            raise ConfigurationError(
                f"{resolved}: proper-noun terms must be non-empty strings"
            )
        normalized = term.casefold()
        if normalized in normalized_terms:
            raise ConfigurationError(
                f"{resolved}: duplicate case-insensitive term {term!r}"
            )
        normalized_terms.add(normalized)
        if not isinstance(raw_systems, dict) or not raw_systems:
            raise ConfigurationError(
                f"{resolved}: proper_nouns.{term} must define a pronunciation"
            )

        systems: list[tuple[str, str]] = []
        for system, pronunciation in raw_systems.items():
            if (
                not isinstance(system, str)
                or not _SYSTEM_ID.fullmatch(system)
                or not isinstance(pronunciation, str)
                or not pronunciation.strip()
            ):
                raise ConfigurationError(
                    f"{resolved}: proper_nouns.{term} contains an invalid "
                    "pronunciation system or value"
                )
            systems.append((system, pronunciation.strip()))
        entries.append(
            ProperNounPronunciation(
                term=term,
                systems=tuple(sorted(systems)),
            )
        )

    entries.sort(key=lambda entry: entry.term.casefold())
    return PronunciationLexicon(tuple(entries))
