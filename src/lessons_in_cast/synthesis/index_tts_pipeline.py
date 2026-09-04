"""Reusable IndexTTS implementation of the voice-pipeline interface."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .index_tts import IndexTtsSubprocessSynthesizer
from .index_tts_config import (
    load_index_tts_pipeline_config,
)
from .reference_builder import ReferenceBuildResult
from .reference_cache import ensure_reference_from_directory
from .types import TtsJob
from .voice_pipeline import (
    ReferenceBuildRequest,
    ReferenceVoicePipeline,
    VoicePipelineContext,
)


class IndexTtsPipeline(ReferenceVoicePipeline, ABC):
    """Base class for one character rendered through IndexTTS 2.5."""

    @property
    @abstractmethod
    def configuration_path(self) -> str:
        """Return the project-relative IndexTTS pipeline configuration path."""

    def __init__(self, context: VoicePipelineContext) -> None:
        if context.character.id != self.character_id:
            raise ValueError(
                f"{self.pipeline_id} handles {self.character_id!r}, not "
                f"{context.character.id!r}"
            )
        if not context.character.model_path:
            raise ValueError(
                f"{self.pipeline_id} requires a character model_path"
            )
        self._context = context
        root = context.repository_root.resolve()
        self._config_path = (root / self.configuration_path).resolve()
        self._config = load_index_tts_pipeline_config(
            self._config_path,
            repository_root=root,
        )
        config = self._config
        resolve = lambda value: (root / value).resolve()
        self._reference_source = resolve(config.reference_source_directory)
        self._reference_path = resolve(config.reference_output_path)
        settings = config.reference_settings
        self._backend = IndexTtsSubprocessSynthesizer(
            repository_root=root,
            python_executable=(root / config.python_executable).absolute(),
            source_root=resolve(config.source_root),
            model_path=resolve(context.character.model_path),
            references={self.character_id: (self._reference_path,)},
            audio_config=context.project_config.audio,
            language=config.language,
            seed=config.seed,
            use_bf16=config.use_bf16,
            prepare_references=False,
            trim_reference_silence=settings.trim_silence,
            reference_trim_top_db=settings.top_db,
            reference_trim_padding_ms=settings.padding_ms,
            reference_gate_hold_ms=settings.gate_hold_ms,
            minimum_reference_speech_seconds=settings.minimum_speech_seconds,
            minimum_reference_duration_seconds=settings.minimum_duration_seconds,
            emotion_alpha=config.emotion_alpha,
            use_random_emotion=config.use_random_emotion,
            do_sample=config.do_sample,
            top_p=config.top_p,
            top_k=config.top_k,
            temperature=config.temperature,
            num_beams=config.num_beams,
            repetition_penalty=config.repetition_penalty,
            length_penalty=config.length_penalty,
            max_mel_tokens=config.max_mel_tokens,
            interval_silence_ms=config.interval_silence_ms,
            max_text_tokens_per_segment=config.max_text_tokens_per_segment,
            text_normalization=config.text_normalization,
            pronunciations=dict(config.pronunciations),
        )

    @property
    def configuration(self) -> dict[str, Any]:
        config = self._config
        return {
            "pipeline_id": self.pipeline_id,
            "character_id": self.character_id,
            "configuration_path": str(self._config_path),
            "backend": self._backend.configuration,
            "reference_source_directory": str(self._reference_source),
            "reference_output_path": str(self._reference_path),
            "reference_settings": asdict(config.reference_settings),
        }


    @property
    def default_reference_request(self) -> ReferenceBuildRequest:
        return ReferenceBuildRequest(
            input_directory=self._reference_source,
            output_path=self._reference_path,
        )

    def prepare(self) -> tuple[Path, ...]:
        ensure_reference_from_directory(
            pipeline_id=self.pipeline_id,
            input_directory=self._reference_source,
            output_path=self._reference_path,
            settings=self._config.reference_settings,
            builder=lambda source, output, _settings: self.build_reference(
                ReferenceBuildRequest(source, output)
            ),
        )
        return (self._reference_path,)

    def build_reference(
        self,
        request: ReferenceBuildRequest,
    ) -> ReferenceBuildResult:
        root = self._context.repository_root.resolve()
        config = self._config
        settings = config.reference_settings
        python_executable = (root / config.python_executable).absolute()
        if not python_executable.exists():
            raise FileNotFoundError(
                f"Voice-pipeline Python executable is missing: "
                f"{python_executable}"
            )
        environment = os.environ.copy()
        python_paths = (str(root), str(root / "src"))
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            (*python_paths, *((existing,) if existing else ()))
        )
        command = [
            str(python_executable),
            "-m",
            "lessons_in_cast.synthesis.reference_builder",
            "--input-dir",
            str(request.input_directory.resolve()),
            "--output",
            str(request.output_path.resolve()),
            "--top-db",
            str(settings.top_db),
            "--padding-ms",
            str(settings.padding_ms),
            "--gate-hold-ms",
            str(settings.gate_hold_ms),
            "--minimum-speech-seconds",
            str(settings.minimum_speech_seconds),
            "--minimum-duration-seconds",
            str(settings.minimum_duration_seconds),
        ]
        if not settings.trim_silence:
            command.append("--no-trim-silence")
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"{self.pipeline_id} reference builder failed: {detail}"
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{self.pipeline_id} reference builder returned invalid JSON"
            ) from exc
        return ReferenceBuildResult.from_dict(result)

    def render(self, job: TtsJob, artifact_root: Path) -> Path:
        if job.character_id != self.character_id:
            raise ValueError(
                f"{self.pipeline_id} cannot render {job.character_id!r}"
            )
        self.prepare()
        return self._backend.synthesize(job, artifact_root)

    def close(self) -> None:
        self._backend.close()
