"""A deterministic silence generator for end-to-end pipeline tests."""

from __future__ import annotations

import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config import AudioConfig
from .types import TtsJob


class SilenceSynthesizer:
    def __init__(self, config: AudioConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "silence"

    @property
    def configuration(self) -> dict[str, Any]:
        return {"adapter": self.name, "audio": asdict(self._config)}

    def synthesize(self, job: TtsJob, artifact_root: Path) -> Path:
        destination = artifact_root / job.output_path
        if destination.is_file():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        duration = min(max(len(job.text) / 12.0, 0.1), 10.0)
        frame_count = round(duration * self._config.sample_rate)
        frame = b"\x00" * self._config.sample_width * self._config.channels
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(self._config.channels)
            output.setsampwidth(self._config.sample_width)
            output.setframerate(self._config.sample_rate)
            output.writeframes(frame * frame_count)
        return destination
