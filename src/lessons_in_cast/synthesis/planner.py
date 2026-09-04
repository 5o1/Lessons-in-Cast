"""Convert validated semantic annotations into cached speech jobs."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import PurePosixPath
from collections.abc import Iterable, Iterator
from typing import Any

from ..annotation import DialogueAction, ValidatedAnnotation, ValidationStatus
from ..characters import CharacterDefinition
from ..config import AudioConfig
from ..dialogue import DialogueRecord
from ..hashing import content_hash
from .types import RenderTask, SynthesisIssue, SynthesisPlan, TtsJob


_UNSAFE_PATH = re.compile(r"[^A-Za-z0-9_.-]+")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]+")


def _safe_component(value: str, fallback: str) -> str:
    cleaned = _UNSAFE_PATH.sub("_", value).strip("._")
    return cleaned or fallback


def _voice_virtual_path(
    source_filename: str,
    identifier: str,
    audio_format: str,
) -> str:
    source = PurePosixPath(source_filename.replace("\\", "/"))
    if source.is_absolute() or any(
        part in {"", ".", ".."} for part in source.parts
    ):
        raise ValueError(f"Unsafe Ren'Py source path: {source_filename!r}")
    parts = source.parts[1:] if source.parts[0] == "game" else source.parts
    if not parts:
        raise ValueError(f"Empty Ren'Py source path: {source_filename!r}")
    relative = PurePosixPath(*parts)
    if relative.suffix.lower() in {".rpy", ".rpym", ".rpyc"}:
        relative = relative.with_suffix("")
    return str(
        PurePosixPath("voice")
        / relative
        / f"{identifier}.{audio_format.lstrip('.')}"
    )


class SynthesisPlanner:
    """Create member-level TTS jobs and line-level render tasks."""

    def __init__(
        self,
        characters: dict[str, CharacterDefinition],
        *,
        audio_config: AudioConfig | None = None,
        synthesizer_configuration: dict[str, Any] | None = None,
    ) -> None:
        self._characters = characters
        self._audio_config = audio_config or AudioConfig()
        self._audio_format = self._audio_config.format.lstrip(".")
        self._synthesizer_configuration = synthesizer_configuration or {
            "adapter": "unconfigured"
        }

    def plan(
        self,
        records_by_id: dict[str, DialogueRecord],
        validated: list[ValidatedAnnotation],
    ) -> SynthesisPlan:
        jobs: list[TtsJob] = []
        renders: list[RenderTask] = []
        issues: list[SynthesisIssue] = []
        for item in self.iter_plan(
            (records_by_id[result.dialogue_id], result) for result in validated
        ):
            if isinstance(item, TtsJob):
                jobs.append(item)
            elif isinstance(item, RenderTask):
                renders.append(item)
            else:
                issues.append(item)
        return SynthesisPlan(tuple(jobs), tuple(renders), tuple(issues))

    def iter_plan(
        self,
        records_and_results: Iterable[tuple[DialogueRecord, ValidatedAnnotation]],
    ) -> Iterator[TtsJob | RenderTask | SynthesisIssue]:
        """Yield a plan incrementally while retaining only deduplication keys."""

        job_id_by_cache_key: dict[str, str] = {}
        identifiers: dict[str, str] = {}

        for record, result in records_and_results:
            if record.id != result.dialogue_id:
                raise ValueError(
                    f"Dialogue/result ID mismatch: {record.id!r} != "
                    f"{result.dialogue_id!r}"
                )
            if result.status is not ValidationStatus.ACCEPTED:
                continue
            annotation = result.annotation
            if annotation is None:
                continue
            if not _SAFE_IDENTIFIER.fullmatch(record.identifier):
                yield SynthesisIssue(
                    result.dialogue_id,
                    "unsafe_identifier",
                    f"Ren'Py identifier {record.identifier!r} is not path-safe.",
                )
                continue
            previous_dialogue = identifiers.get(record.identifier)
            if previous_dialogue is not None and previous_dialogue != record.id:
                yield SynthesisIssue(
                    result.dialogue_id,
                    "duplicate_identifier",
                    f"Ren'Py identifier {record.identifier!r} is not unique.",
                )
                continue
            identifiers[record.identifier] = record.id
            character_id = record.character or "narrator"
            character = self._characters.get(character_id)
            if character is None:
                yield SynthesisIssue(
                    result.dialogue_id,
                    "unknown_character",
                    f"Character {character_id!r} is not configured.",
                )
                continue

            if annotation.action is DialogueAction.OMIT:
                continue

            try:
                virtual_path = _voice_virtual_path(
                    record.filename,
                    record.identifier,
                    self._audio_format,
                )
            except ValueError as exc:
                yield SynthesisIssue(
                    result.dialogue_id,
                    "unsafe_source_path",
                    str(exc),
                )
                continue

            component_ids: list[str] = []
            if annotation.action in {
                DialogueAction.SPEAK,
                DialogueAction.SPEAK_WITH_EFFECT,
            }:
                assert annotation.emotion is not None
                assert annotation.intensity is not None
                for member_id in character.synthesis_members:
                    member = self._characters[member_id]
                    job = self._create_job(record, annotation, member)
                    existing_id = job_id_by_cache_key.get(job.cache_key)
                    if existing_id is None:
                        job_id_by_cache_key[job.cache_key] = job.id
                        yield job
                        component_ids.append(job.id)
                    else:
                        component_ids.append(existing_id)

            render_mode = character.render_mode or "single"
            output_name = f"{record.identifier}.{self._audio_format}"
            yield RenderTask(
                dialogue_id=record.id,
                identifier=record.identifier,
                action=annotation.action,
                component_job_ids=tuple(component_ids),
                render_mode=render_mode,
                effects=annotation.effects,
                output_path=str(PurePosixPath("voice") / output_name),
                virtual_path=virtual_path,
            )

    def _create_job(
        self,
        record: DialogueRecord,
        annotation: object,
        member: CharacterDefinition,
    ) -> TtsJob:
        from ..annotation import Annotation

        assert isinstance(annotation, Annotation)
        identity = {
            "character": member.id,
            "text": annotation.spoken_text,
            "emotion": annotation.emotion,
            "intensity": annotation.intensity,
            "delivery": annotation.delivery,
            "base_speed": member.base_speed,
            "model_path": member.model_path,
            "generation_script_path": member.generation_script_path,
            "audio": asdict(self._audio_config),
            "synthesizer": self._synthesizer_configuration,
        }
        cache_key = content_hash(identity)
        member_path = _safe_component(member.id, "character")
        output_path = str(
            PurePosixPath("audio/raw")
            / member_path
            / f"{cache_key}.{self._audio_format}"
        )
        return TtsJob(
            id=content_hash({"dialogue_id": record.id, **identity})[:24],
            dialogue_id=record.id,
            character_id=member.id,
            text=annotation.spoken_text,
            emotion=annotation.emotion or "neutral",
            intensity=annotation.intensity or 0.0,
            delivery=annotation.delivery,
            base_speed=member.base_speed,
            model_path=member.model_path,
            generation_script_path=member.generation_script_path,
            output_path=output_path,
            cache_key=cache_key,
        )
