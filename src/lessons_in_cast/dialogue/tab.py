"""Strict reader for Ren'Py's tab-delimited dialogue export."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath

from ..hashing import content_hash
from .types import DialogueRecord


RENPY_DIALOGUE_HEADER = (
    "Identifier",
    "Character",
    "Dialogue",
    "Filename",
    "Line Number",
    "Ren'Py Script",
)


class DialogueTabError(ValueError):
    """Raised when a dialogue table violates Ren'Py's six-column format."""


def normalize_source_path(value: str) -> str:
    """Normalize separators without resolving or touching the source path."""

    return str(PurePosixPath(value.replace("\\", "/")))


class TabDialogueReader:
    """Read dialogue rows exactly as emitted by Ren'Py."""

    def __init__(self, allowed_sources: Iterable[Path | str] | None = None) -> None:
        self._allowed_sources = (
            {
                normalize_source_path(str(source))
                for source in allowed_sources
            }
            if allowed_sources is not None
            else None
        )

    def read(self, source: Path) -> Iterator[DialogueRecord]:
        occurrences: defaultdict[tuple[str, str, int], int] = defaultdict(int)
        with source.open("r", encoding="utf-8-sig", newline="") as dialogue_file:
            rows = csv.reader(
                dialogue_file,
                delimiter="\t",
                quoting=csv.QUOTE_NONE,
                strict=True,
            )
            try:
                header = tuple(next(rows))
            except StopIteration as exc:
                raise DialogueTabError(f"{source}: empty dialogue table") from exc
            if header != RENPY_DIALOGUE_HEADER:
                raise DialogueTabError(
                    f"{source}: expected header {RENPY_DIALOGUE_HEADER!r}, got {header!r}"
                )

            sequence = 0
            for table_line, row in enumerate(rows, start=2):
                if len(row) != len(RENPY_DIALOGUE_HEADER):
                    raise DialogueTabError(
                        f"{source}:{table_line}: expected 6 columns, got {len(row)}"
                    )
                identifier, character, dialogue, filename, raw_line, renpy_script = row
                filename = normalize_source_path(filename)
                if self._allowed_sources is not None and filename not in self._allowed_sources:
                    continue
                try:
                    line_number = int(raw_line)
                except ValueError as exc:
                    raise DialogueTabError(
                        f"{source}:{table_line}: invalid source line number {raw_line!r}"
                    ) from exc
                if line_number < 1:
                    raise DialogueTabError(
                        f"{source}:{table_line}: source line number must be positive"
                    )
                occurrence_key = (identifier, filename, line_number)
                occurrence = occurrences[occurrence_key]
                occurrences[occurrence_key] += 1
                stable_id = content_hash(
                    {
                        "identifier": identifier,
                        "filename": filename,
                        "line_number": line_number,
                        "occurrence": occurrence,
                    }
                )[:24]
                yield DialogueRecord(
                    id=stable_id,
                    sequence=sequence,
                    identifier=identifier,
                    character=character,
                    dialogue=dialogue,
                    filename=filename,
                    line_number=line_number,
                    renpy_script=renpy_script,
                )
                sequence += 1
