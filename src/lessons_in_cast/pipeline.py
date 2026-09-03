"""Top-level orchestration for the dialogue-to-audio pipeline.

This module intentionally depends on interfaces instead of concrete parsers and
writers. Lower-level stages can therefore be implemented and tested without
changing the public pipeline entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .dialogue import DialogueProcessor, DialogueReader, DialogueRecord, DialogueWriter
from .dialogue.stream import apply_processors
from .renpy import DialogueExtractionRequest, DialogueExtractor


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    """Inputs and output locations for one pipeline run."""

    extraction: DialogueExtractionRequest
    processed_dialogue_path: Path


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Artifacts produced by a completed pipeline run."""

    extracted_dialogue_path: Path
    processed_dialogue_path: Path
    dialogue_count: int


class DialoguePipeline:
    """Coordinate extraction, streaming transforms, and serialization."""

    def __init__(
        self,
        *,
        extractor: DialogueExtractor,
        reader: DialogueReader,
        writer: DialogueWriter,
        processors: Sequence[DialogueProcessor] = (),
    ) -> None:
        self._extractor = extractor
        self._reader = reader
        self._writer = writer
        self._processors = tuple(processors)

    def run(self, request: PipelineRequest) -> PipelineResult:
        """Run all currently configured stages from top to bottom."""

        extraction = self._extractor.extract(request.extraction)
        records: Iterable[DialogueRecord] = self._reader.read(
            extraction.dialogue_path
        )
        processed_records = apply_processors(records, self._processors)
        dialogue_count = self._writer.write(
            processed_records,
            request.processed_dialogue_path,
        )

        return PipelineResult(
            extracted_dialogue_path=extraction.dialogue_path,
            processed_dialogue_path=request.processed_dialogue_path,
            dialogue_count=dialogue_count,
        )
