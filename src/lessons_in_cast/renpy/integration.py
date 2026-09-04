"""Write a traceable dialogue-to-audio manifest for Ren'Py integration."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..dialogue import DialogueRecord
from ..synthesis import AudioQualityResult, RenderTask


class RenPyVoiceManifestWriter:
    def write(
        self,
        destination: Path,
        records_by_id: dict[str, DialogueRecord],
        render_tasks: list[RenderTask],
        quality_by_id: dict[str, AudioQualityResult],
    ) -> Path:
        return self.write_entries(
            destination,
            (
                self.create_entry(
                    records_by_id[task.dialogue_id],
                    task,
                    quality_by_id.get(task.dialogue_id),
                )
                for task in render_tasks
            ),
        )

    @staticmethod
    def create_entry(
        record: DialogueRecord,
        task: RenderTask,
        quality: AudioQualityResult | None,
    ) -> dict[str, Any]:
        return {
            "dialogue_id": record.id,
            "identifier": record.identifier,
            "character": record.character,
            "source": {
                "filename": record.filename,
                "line_number": record.line_number,
            },
            "action": task.action.value,
            "effects": list(task.effects),
            "audio_path": task.virtual_path if quality and quality.valid else None,
            "quality": quality.to_dict() if quality else None,
        }

    def write_entries(
        self,
        destination: Path,
        entries: Iterable[Mapping[str, Any]],
    ) -> Path:
        """Write a JSON-array manifest without retaining all entries."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write('{"entries":[')
                first = True
                for entry in entries:
                    if not first:
                        output.write(",")
                    json.dump(entry, output, ensure_ascii=False, sort_keys=True)
                    first = False
                output.write('],"schema_version":1}\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return destination

    def write_auto_voice_script(
        self,
        destination: Path,
        *,
        entries: Iterable[tuple[str, str]],
    ) -> Path:
        """Write a callable auto-voice resolver for mirrored virtual paths."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write("init -100 python:\n")
                output.write("    _lessons_in_cast_voice_paths = {\n")
                for identifier, virtual_path in entries:
                    output.write(
                        f"        {json.dumps(identifier)}: "
                        f"{json.dumps(virtual_path)},\n"
                    )
                output.write("    }\n\n")
                output.write("    def _lessons_in_cast_auto_voice(identifier):\n")
                output.write(
                    "        return _lessons_in_cast_voice_paths.get(identifier)\n\n"
                )
                output.write("    config.auto_voice = _lessons_in_cast_auto_voice\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return destination
