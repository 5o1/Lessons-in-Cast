"""Persistent subprocess adapter for the official IndexTTS 2.5 environment."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from ....config import AudioConfig
from ...types import TtsJob


_EMOTION_AXES = {
    "happy": {"joy": 1.0},
    "excited": {"joy": 0.7, "surprise": 0.3},
    "affectionate": {"joy": 0.55, "calm": 0.45},
    "angry": {"anger": 1.0},
    "sad": {"sadness": 0.7, "depression": 0.3},
    "distressed": {"sadness": 0.4, "fear": 0.35, "depression": 0.25},
    "afraid": {"fear": 1.0},
    "disgusted": {"disgust": 1.0},
    "embarrassed": {"fear": 0.45, "sadness": 0.25, "calm": 0.3},
    "surprised": {"surprise": 1.0},
    "confused": {"surprise": 0.55, "calm": 0.45},
    "sarcastic": {"disgust": 0.5, "joy": 0.2, "calm": 0.3},
    "calm": {"calm": 1.0},
    "neutral": {"calm": 1.0},
}
_AXIS_ORDER = (
    "joy", "anger", "sadness", "fear", "disgust", "depression", "surprise", "calm"
)
_EMOTION_BIAS = (0.9375, 0.875, 1.0, 1.0, 0.9375, 0.9375, 0.6875, 0.5625)
_MAX_EMOTION_SUM = 0.8


def normalize_index_emotion_vector(vector: list[float]) -> list[float]:
    """Apply the bias and 0.8 total-strength cap used by the official WebUI."""

    if len(vector) != len(_AXIS_ORDER):
        raise ValueError("IndexTTS emotion vectors must contain eight values")
    biased = [
        max(float(value), 0.0) * bias for value, bias in zip(vector, _EMOTION_BIAS)
    ]
    total = sum(biased)
    if total > _MAX_EMOTION_SUM:
        scale = _MAX_EMOTION_SUM / total
        biased = [value * scale for value in biased]
    return [round(value, 6) for value in biased]


def index_emotion_vector(emotion: str, intensity: float) -> list[float]:
    """Map labels to a WebUI-normalized IndexTTS eight-axis emotion vector."""

    if emotion == "neutral":
        return [0.0] * len(_AXIS_ORDER)
    strength = min(max(float(intensity), 0.0), 1.0)
    if emotion == "calm":
        strength = max(strength, 0.2)
    weights = _EMOTION_AXES.get(emotion, {"calm": 1.0})
    raw = [weights.get(axis, 0.0) * strength for axis in _AXIS_ORDER]
    return normalize_index_emotion_vector(raw)


def apply_index_pronunciations(text: str, pronunciations: Mapping[str, str]) -> str:
    """Add official word-and-ARPABET pronunciation annotations."""

    result = text
    for word, phonemes in sorted(
        pronunciations.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if not word or not phonemes:
            raise ValueError("Pronunciation entries cannot be empty")
        result = re.sub(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            lambda match: f"<{match.group(0)}|{phonemes}>",
            result,
            flags=re.IGNORECASE,
        )
    return result


class IndexTtsSubprocessSynthesizer:
    """Keep one GPU-loaded IndexTTS worker alive across all TTS jobs."""

    def __init__(
        self,
        *,
        repository_root: Path,
        python_executable: Path,
        source_root: Path,
        model_path: Path,
        references: Mapping[str, Sequence[Path]],
        audio_config: AudioConfig,
        base_speed: float = 1.0,
        language: str = "EN",
        seed: int = 233333,
        use_bf16: bool = True,
        prepare_references: bool = True,
        trim_reference_silence: bool = True,
        reference_trim_top_db: float = 40.0,
        reference_trim_padding_ms: int = 150,
        reference_gate_hold_ms: int = 500,
        minimum_reference_speech_seconds: float = 3.0,
        minimum_reference_duration_seconds: float = 15.0,
        emotion_alpha: float = 0.65,
        use_random_emotion: bool = False,
        do_sample: bool = False,
        top_p: float = 0.8,
        top_k: int = 30,
        temperature: float = 0.8,
        num_beams: int = 3,
        repetition_penalty: float = 10.0,
        length_penalty: float = 0.0,
        max_mel_tokens: int = 1500,
        interval_silence_ms: int = 200,
        max_text_tokens_per_segment: int = 120,
        text_normalization: bool = True,
        pronunciations: Mapping[str, str] | None = None,
    ) -> None:
        if (
            audio_config.format.lstrip(".").lower() != "wav"
            or audio_config.sample_width != 2
        ):
            raise ValueError("IndexTTS adapter currently requires 16-bit WAV output")
        if base_speed <= 0:
            raise ValueError("IndexTTS base_speed must be positive")
        self._root = repository_root.resolve()
        # Resolving this symlink would bypass the virtual environment and use
        # uv's base interpreter without the environment's installed packages.
        self._python = python_executable.absolute()
        self._source = source_root.resolve()
        self._model = model_path.resolve()
        self._base_speed = float(base_speed)
        self._references = {
            key: tuple(value.resolve() for value in values)
            for key, values in references.items()
        }
        self._audio = audio_config
        self._language = language
        self._seed = seed
        self._use_bf16 = use_bf16
        self._reference_processing = {
            "prepare_references": prepare_references,
            "trim_reference_silence": trim_reference_silence,
            "reference_trim_top_db": reference_trim_top_db,
            "reference_trim_padding_ms": reference_trim_padding_ms,
            "reference_gate_hold_ms": reference_gate_hold_ms,
            "minimum_reference_speech_seconds": minimum_reference_speech_seconds,
            "minimum_reference_duration_seconds": minimum_reference_duration_seconds,
        }
        self._inference = {
            "emotion_alpha": emotion_alpha,
            "use_random_emotion": use_random_emotion,
            "do_sample": do_sample,
            "top_p": top_p,
            "top_k": top_k,
            "temperature": temperature,
            "num_beams": num_beams,
            "repetition_penalty": repetition_penalty,
            "length_penalty": length_penalty,
            "max_mel_tokens": max_mel_tokens,
            "interval_silence_ms": interval_silence_ms,
            "max_text_tokens_per_segment": max_text_tokens_per_segment,
            "text_normalization": text_normalization,
        }
        self._pronunciations = dict(pronunciations or {})
        self._process: subprocess.Popen[str] | None = None

    @property
    def name(self) -> str:
        return "index-tts-2.5"

    @property
    def configuration(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "model_path": str(self._model),
            "language": self._language,
            "base_speed": self._base_speed,
            "seed": self._seed,
            "use_bf16": self._use_bf16,
            "reference_processing": dict(self._reference_processing),
            "inference": dict(self._inference),
            "references": {
                key: [str(path) for path in paths]
                for key, paths in sorted(self._references.items())
            },
            "pronunciations": dict(sorted(self._pronunciations.items())),
        }

    def set_references(
        self, character_id: str, references: Sequence[Path]
    ) -> None:
        """Replace one character's references without restarting the worker."""

        resolved = tuple(reference.resolve() for reference in references)
        if not resolved:
            raise ValueError("IndexTTS requires at least one reference")
        self._references[character_id] = resolved

    def set_pronunciations(self, pronunciations: Mapping[str, str]) -> None:
        """Replace pronunciation annotations without restarting the worker."""
        self._pronunciations = dict(pronunciations)

    def synthesize(self, job: TtsJob, artifact_root: Path) -> Path:
        destination = (artifact_root / job.output_path).resolve()
        if destination.is_file():
            return destination
        references = self._references.get(job.character_id)
        if references is None:
            raise RuntimeError(
                f"No IndexTTS reference is configured for character "
                f"{job.character_id!r}"
            )
        for reference in references:
            if not reference.is_file():
                raise FileNotFoundError(
                    f"IndexTTS reference audio is missing: {reference}"
                )
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._exchange(
            {
                "id": job.id,
                "references": [str(reference) for reference in references],
                "text": apply_index_pronunciations(job.text, self._pronunciations),
                "output": str(destination),
                "emotion_vector": index_emotion_vector(job.emotion, job.intensity),
                "duration_factor": 1.0 / self._base_speed,
                "seed": self._seed,
                "sample_rate": self._audio.sample_rate,
                "channels": self._audio.channels,
                **self._reference_processing,
                **self._inference,
            }
        )
        if response.get("ok") is not True:
            raise RuntimeError(
                f"IndexTTS failed for {job.dialogue_id}: "
                f"{response.get('error', 'unknown worker error')}"
            )
        if not destination.is_file():
            raise RuntimeError(f"IndexTTS did not create {destination}")
        return destination

    def _exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        process = self._ensure_process()
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(
                f"IndexTTS worker stopped unexpectedly (exit {process.poll()})"
            )
        response = json.loads(line)
        if not isinstance(response, dict):
            raise RuntimeError("IndexTTS worker returned a non-object response")
        return response

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        for required in (self._python, self._source, self._model):
            if not required.exists():
                raise FileNotFoundError(f"IndexTTS dependency is missing: {required}")
        environment = os.environ.copy()
        package_root = str((self._root / "src").resolve())
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            package_root
            if not existing
            else os.pathsep.join((package_root, existing))
        )
        command = [
            str(self._python),
            "-m",
            "lessons_in_cast_core.synthesis.backends.index_tts.worker",
            "--source-root",
            str(self._source),
            "--model-path",
            str(self._model),
            "--language", self._language,
        ]
        if self._use_bf16:
            command.append("--use-bf16")
        self._process = subprocess.Popen(
            command,
            cwd=self._root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self._process

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)

    def __enter__(self) -> "IndexTtsSubprocessSynthesizer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
