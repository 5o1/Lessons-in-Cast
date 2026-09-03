"""Canonical types passed between dialogue pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DialogueRecord:
    """One source-ordered unit of dialogue and its provenance."""

    id: str
    sequence: int
    speaker: str | None
    text: str
    source_file: Path
    line_number: int
    label: str | None = None
    event_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
