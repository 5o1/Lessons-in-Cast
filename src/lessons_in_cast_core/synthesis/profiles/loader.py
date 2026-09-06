"""Load user-defined voice profiles and route jobs through their pipelines."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

from ...characters import CharacterDefinition
from ...config import PipelineConfig
from ...model_registry import ModelRegistry, load_model_registry
from ..types import TtsJob
from .api import VoicePipeline
from .context import VoiceProfileContext


def load_voice_profile(
    repository_root: Path,
    entrypoint_path: Path,
    character: CharacterDefinition,
    project_config: PipelineConfig,
    *,
    model_registry: ModelRegistry,
) -> VoicePipeline:
    """Load one profile entrypoint and validate its public contract."""

    root = repository_root.resolve()
    resolved = (
        entrypoint_path
        if entrypoint_path.is_absolute()
        else root / entrypoint_path
    )
    resolved = resolved.resolve()
    profiles_root = (root / "profiles").resolve()
    if not resolved.is_relative_to(profiles_root):
        raise ValueError(f"Voice profile must be inside {profiles_root}: {resolved}")
    if not resolved.is_file() or resolved.suffix != ".py":
        raise FileNotFoundError(f"Voice profile entrypoint is missing: {resolved}")

    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    module_name = f"lessons_in_cast_core_voice_profile_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load voice profile: {resolved}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ImportError(
            f"Unable to execute voice profile {resolved}: {exc}"
        ) from exc

    factory = getattr(module, "create_pipeline", None)
    if not callable(factory):
        raise TypeError(f"{resolved} must export create_pipeline(context)")
    context = VoiceProfileContext(
        repository_root=root,
        entrypoint=resolved,
        profile_root=resolved.parent,
        character=character,
        project_config=project_config,
        model_registry=model_registry,
    )
    pipeline = factory(context)
    if not isinstance(pipeline, VoicePipeline):
        raise TypeError(
            f"{resolved} create_pipeline() must return VoicePipeline"
        )
    if pipeline.character_id != character.id:
        raise ValueError(
            f"{resolved} handles {pipeline.character_id!r}, expected "
            f"{character.id!r}"
        )
    return pipeline


class VoiceProfileSynthesizer:
    """SpeechSynthesizer adapter routing jobs to configured voice profiles."""

    def __init__(self, pipelines: dict[str, VoicePipeline]) -> None:
        if not pipelines:
            raise ValueError("At least one character voice profile is required")
        self._pipelines = dict(pipelines)

    @property
    def name(self) -> str:
        return "character-voice-profiles"

    @property
    def configuration(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "profiles": {
                character_id: pipeline.configuration
                for character_id, pipeline in sorted(self._pipelines.items())
            },
        }

    def prepare(self) -> dict[str, tuple[Path, ...]]:
        """Prepare generated dependencies for every configured profile."""

        return {
            character_id: pipeline.prepare()
            for character_id, pipeline in sorted(self._pipelines.items())
        }

    def synthesize(self, job: TtsJob, artifact_root: Path) -> Path:
        pipeline = self._pipelines.get(job.character_id)
        if pipeline is None:
            raise RuntimeError(
                f"No voice profile is configured for {job.character_id!r}"
            )
        return pipeline.render(job, artifact_root)

    def close(self) -> None:
        for pipeline in self._pipelines.values():
            pipeline.close()


def load_configured_voice_profiles(
    repository_root: Path,
    project_config: PipelineConfig,
    characters: dict[str, CharacterDefinition],
    *,
    model_registry: ModelRegistry | None = None,
) -> VoiceProfileSynthesizer:
    """Load each character's non-empty default voice profile."""

    models = model_registry
    if models is None:
        models = load_model_registry(repository_root=repository_root)
    pipelines: dict[str, VoicePipeline] = {}
    for character_id, character in characters.items():
        if not character.default_voice_profile:
            continue
        pipelines[character_id] = load_voice_profile(
            repository_root,
            Path(character.default_voice_profile),
            character,
            project_config,
            model_registry=models,
        )
    return VoiceProfileSynthesizer(pipelines)
