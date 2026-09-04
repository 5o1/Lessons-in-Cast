"""Load and route character voice pipelines through their public interface."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from ..characters import CharacterDefinition
from ..config import PipelineConfig
from .types import TtsJob
from .voice_pipeline import VoicePipeline, VoicePipelineContext


def load_voice_pipeline(
    repository_root: Path,
    script_path: Path,
    character: CharacterDefinition,
    project_config: PipelineConfig,
) -> VoicePipeline:
    """Load a configured pipeline factory and validate its public contract."""

    root = repository_root.resolve()
    resolved = script_path if script_path.is_absolute() else root / script_path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Voice pipeline must be inside the repository: {resolved}")
    if not resolved.is_file() or resolved.suffix != ".py":
        raise FileNotFoundError(f"Voice pipeline script is missing: {resolved}")

    try:
        relative = resolved.relative_to(root).with_suffix("")
    except ValueError as exc:
        raise ValueError(f"Voice pipeline is outside repository: {resolved}") from exc
    module_name = ".".join(relative.parts)
    root_text = str(root)
    added_to_path = root_text not in sys.path
    if added_to_path:
        sys.path.insert(0, root_text)
    try:
        importlib.invalidate_caches()
        module = importlib.import_module(module_name)
    finally:
        if added_to_path:
            sys.path.remove(root_text)

    factory = getattr(module, "create_pipeline", None)
    if not callable(factory):
        raise TypeError(f"{resolved} must export create_pipeline(context)")
    context = VoicePipelineContext(
        repository_root=root,
        character=character,
        project_config=project_config,
    )
    pipeline = factory(context)
    if not isinstance(pipeline, VoicePipeline):
        raise TypeError(
            f"{resolved} create_pipeline() must return a VoicePipeline"
        )
    if pipeline.character_id != character.id:
        raise ValueError(
            f"{resolved} handles {pipeline.character_id!r}, expected "
            f"{character.id!r}"
        )
    return pipeline


class VoicePipelineSynthesizer:
    """SpeechSynthesizer adapter routing jobs to configured voice pipelines."""

    def __init__(self, pipelines: dict[str, VoicePipeline]) -> None:
        if not pipelines:
            raise ValueError("At least one character voice pipeline is required")
        self._pipelines = dict(pipelines)

    @property
    def name(self) -> str:
        return "character-voice-pipelines"

    @property
    def configuration(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "pipelines": {
                character_id: pipeline.configuration
                for character_id, pipeline in sorted(self._pipelines.items())
            },
        }

    def prepare(self) -> dict[str, tuple[Path, ...]]:
        """Prepare generated dependencies for every configured pipeline."""

        return {
            character_id: pipeline.prepare()
            for character_id, pipeline in sorted(self._pipelines.items())
        }

    def synthesize(self, job: TtsJob, artifact_root: Path) -> Path:
        pipeline = self._pipelines.get(job.character_id)
        if pipeline is None:
            raise RuntimeError(
                f"No voice pipeline is configured for {job.character_id!r}"
            )
        return pipeline.render(job, artifact_root)

    def close(self) -> None:
        for pipeline in self._pipelines.values():
            pipeline.close()


def load_configured_voice_pipelines(
    repository_root: Path,
    project_config: PipelineConfig,
    characters: dict[str, CharacterDefinition],
) -> VoicePipelineSynthesizer:
    """Load every non-empty generation_script_path through VoicePipeline."""

    pipelines: dict[str, VoicePipeline] = {}
    for character_id, character in characters.items():
        if not character.generation_script_path:
            continue
        pipelines[character_id] = load_voice_pipeline(
            repository_root,
            Path(character.generation_script_path),
            character,
            project_config,
        )
    return VoicePipelineSynthesizer(pipelines)
