"""Public API for extracting dialogue from a Ren'Py release.

The concrete adapter for Ren'Py's dialogue extraction command will be added in
a lower-level implementation pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class DialogueExtractionRequest:
    """Parameters required to invoke Ren'Py dialogue extraction."""

    release_path: Path
    output_path: Path
    source_paths: Sequence[Path] = ()
    language: str | None = None


@dataclass(frozen=True, slots=True)
class DialogueExtractionResult:
    """Metadata returned by a Ren'Py dialogue extractor."""

    dialogue_path: Path
    source_count: int


class DialogueExtractor(Protocol):
    """Extract a dialogue artifact, normally ``dialogue.tab``."""

    def extract(
        self,
        request: DialogueExtractionRequest,
    ) -> DialogueExtractionResult: ...
