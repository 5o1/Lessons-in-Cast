"""PCM WAV rendering and technical quality checks."""

from __future__ import annotations

import shutil
import tempfile
import wave
from array import array
from pathlib import Path

from ..config import AudioConfig
from .api import AudioEffectProcessor
from .types import AudioQualityResult, RenderTask, TtsJob


class AudioRenderError(RuntimeError):
    """Raised when a render task requires unavailable audio behavior."""


class WaveRenderer:
    """Render single or unison PCM WAV components."""

    def __init__(
        self,
        effect_processor: AudioEffectProcessor | None = None,
    ) -> None:
        self._effect_processor = effect_processor

    def render(
        self,
        task: RenderTask,
        jobs_by_id: dict[str, TtsJob],
        artifact_root: Path,
    ) -> Path:
        if task.effects and self._effect_processor is None:
            raise AudioRenderError(
                f"{task.dialogue_id}: effects require a configured post-processor"
            )
        components = [
            artifact_root / jobs_by_id[job_id].output_path
            for job_id in task.component_job_ids
        ]
        if not components and not task.effects:
            raise AudioRenderError(
                f"{task.dialogue_id}: render task has no audio components"
            )
        destination = artifact_root / task.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if task.effects:
            assert self._effect_processor is not None
            with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
                intermediate = Path(directory) / "source.wav"
                source = self._render_components(task, components, intermediate)
                return self._effect_processor.process(
                    source,
                    destination,
                    task.effects,
                )
        self._render_components(task, components, destination)
        return destination

    def _render_components(
        self,
        task: RenderTask,
        components: list[Path],
        destination: Path,
    ) -> Path | None:
        if not components:
            return None
        if len(components) == 1:
            shutil.copy2(components[0], destination)
            return destination
        if task.render_mode != "unison":
            raise AudioRenderError(
                f"{task.dialogue_id}: unsupported render mode {task.render_mode!r}"
            )
        self._mix_unison(components, destination)
        return destination

    @staticmethod
    def _mix_unison(components: list[Path], destination: Path) -> None:
        parameters: tuple[int, int, int] | None = None
        streams: list[array[int]] = []
        for path in components:
            with wave.open(str(path), "rb") as source:
                current = (
                    source.getnchannels(),
                    source.getsampwidth(),
                    source.getframerate(),
                )
                if current[1] != 2:
                    raise AudioRenderError("Unison mixing currently requires 16-bit PCM WAV")
                if parameters is None:
                    parameters = current
                elif parameters != current:
                    raise AudioRenderError("Unison components have incompatible WAV parameters")
                samples = array("h")
                samples.frombytes(source.readframes(source.getnframes()))
                streams.append(samples)
        assert parameters is not None
        sample_count = max(len(stream) for stream in streams)
        mixed = array("h")
        for index in range(sample_count):
            total = sum(
                stream[index] if index < len(stream) else 0
                for stream in streams
            )
            mixed.append(round(total / len(streams)))
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(parameters[0])
            output.setsampwidth(parameters[1])
            output.setframerate(parameters[2])
            output.writeframes(mixed.tobytes())


class AudioQualityChecker:
    def __init__(self, config: AudioConfig) -> None:
        self._config = config

    def check(
        self,
        dialogue_id: str,
        path: Path,
    ) -> AudioQualityResult:
        issues: list[str] = []
        duration: float | None = None
        if not path.is_file():
            issues.append("missing_file")
        else:
            try:
                with wave.open(str(path), "rb") as source:
                    if source.getframerate() != self._config.sample_rate:
                        issues.append("sample_rate")
                    if source.getnchannels() != self._config.channels:
                        issues.append("channels")
                    if source.getsampwidth() != self._config.sample_width:
                        issues.append("sample_width")
                    frame_rate = source.getframerate()
                    duration = source.getnframes() / frame_rate if frame_rate else 0.0
            except (OSError, EOFError, wave.Error):
                issues.append("invalid_wav")
        if duration is not None and duration < self._config.minimum_duration_seconds:
            issues.append("duration_too_short")
        if duration is not None and duration > self._config.maximum_duration_seconds:
            issues.append("duration_too_long")
        return AudioQualityResult(
            dialogue_id=dialogue_id,
            path=str(path),
            valid=not issues,
            duration_seconds=duration,
            issues=tuple(issues),
        )
