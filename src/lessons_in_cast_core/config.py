"""Configuration loading and validation for pipeline workspaces."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when a project configuration is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    repository_root: Path
    release_path: Path


@dataclass(frozen=True, slots=True)
class BatchingConfig:
    target_size: int = 50
    context_before: int = 12
    context_after: int = 12
    max_characters: int = 40_000


@dataclass(frozen=True, slots=True)
class AnnotationConfig:
    allowed_emotions: frozenset[str]
    allowed_effects: frozenset[str]
    maximum_length_ratio: float = 4.0
    minimum_length_ratio: float = 0.15


@dataclass(frozen=True, slots=True)
class CodexConfig:
    batches_per_packet: int = 2
    source_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AudioConfig:
    format: str = "wav"
    intermediate_format: str = "wav"
    sample_rate: int = 44_100
    channels: int = 1
    sample_width: int = 2
    bitrate_kbps: int = 48
    ffmpeg_executable: str = "ffmpeg"
    ffprobe_executable: str = "ffprobe"
    minimum_duration_seconds: float = 0.05
    maximum_duration_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class GalgameConfig:
    backend: str = "renpy"


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    batching: BatchingConfig
    annotation: AnnotationConfig
    audio: AudioConfig
    codex: CodexConfig = CodexConfig()
    galgame: GalgameConfig = GalgameConfig()


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as source:
            return tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Unable to load {path}: {exc}") from exc


def find_repository_root(start: Path | None = None) -> Path:
    """Find the nearest directory containing the workspace configuration."""

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "configs" / "workspace.toml").is_file():
            return candidate
    raise ConfigurationError("Could not find configs/workspace.toml")


def load_workspace_config(
    path: Path = Path("configs/workspace.toml"),
    *,
    repository_root: Path | None = None,
) -> WorkspaceConfig:
    root = (repository_root or find_repository_root()).resolve()
    resolved_path = path if path.is_absolute() else root / path
    data = _load_toml(resolved_path)
    try:
        configured_release = Path(data["workspace"]["current_game_release"])
    except (KeyError, TypeError) as exc:
        raise ConfigurationError(
            f"{resolved_path}: workspace.current_game_release is required"
        ) from exc
    release_path = (
        configured_release
        if configured_release.is_absolute()
        else root / configured_release
    )
    return WorkspaceConfig(root, release_path.resolve())


def load_dialogue_sources(
    path: Path = Path("configs/dialogue_sources.toml"),
    *,
    repository_root: Path | None = None,
    include_excluded: bool = False,
) -> tuple[Path, ...]:
    root = (repository_root or find_repository_root()).resolve()
    resolved_path = path if path.is_absolute() else root / path
    data = _load_toml(resolved_path)
    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise ConfigurationError(f"{resolved_path}: [sources] table is required")
    result: list[Path] = []
    for group, values in sources.items():
        if group == "excluded_by_default" and not include_excluded:
            continue
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ConfigurationError(
                f"{resolved_path}: sources.{group} must be an array"
            )
        result.extend(Path(value) for value in values)
    if len(result) != len(set(result)):
        raise ConfigurationError(f"{resolved_path}: duplicate dialogue source paths")
    return tuple(result)


def load_pipeline_config(
    path: Path = Path("configs/pipeline.toml"),
    *,
    repository_root: Path | None = None,
) -> PipelineConfig:
    root = (repository_root or find_repository_root()).resolve()
    resolved_path = path if path.is_absolute() else root / path
    data = _load_toml(resolved_path)
    batching = data.get("batching", {})
    annotation = data.get("annotation", {})
    audio = data.get("audio", {})
    codex = data.get("codex", {})
    galgame = data.get("galgame", {})
    codex_source_files = codex.get("source_files", [])
    if not isinstance(codex_source_files, list) or not all(
        isinstance(value, str) and value for value in codex_source_files
    ):
        raise ConfigurationError("codex.source_files must be an array of paths")
    if len(codex_source_files) != len(set(codex_source_files)):
        raise ConfigurationError("codex.source_files contains duplicate paths")
    result = PipelineConfig(
        batching=BatchingConfig(**batching),
        annotation=AnnotationConfig(
            allowed_emotions=frozenset(annotation.get("allowed_emotions", ())),
            allowed_effects=frozenset(annotation.get("allowed_effects", ())),
            maximum_length_ratio=annotation.get("maximum_length_ratio", 4.0),
            minimum_length_ratio=annotation.get("minimum_length_ratio", 0.15),
        ),
        audio=AudioConfig(**audio),
        codex=CodexConfig(
            batches_per_packet=codex.get("batches_per_packet", 2),
            source_files=tuple(codex_source_files),
        ),
        galgame=GalgameConfig(backend=galgame.get("backend", "renpy")),
    )
    if result.batching.target_size < 1:
        raise ConfigurationError("batching.target_size must be positive")
    if result.batching.context_before < 0 or result.batching.context_after < 0:
        raise ConfigurationError("batching context sizes cannot be negative")
    if result.batching.max_characters < 1:
        raise ConfigurationError("batching.max_characters must be positive")
    if result.annotation.minimum_length_ratio < 0:
        raise ConfigurationError("annotation.minimum_length_ratio cannot be negative")
    if result.annotation.maximum_length_ratio < result.annotation.minimum_length_ratio:
        raise ConfigurationError("annotation length ratio range is invalid")
    if result.codex.batches_per_packet < 1:
        raise ConfigurationError("codex.batches_per_packet must be positive")
    if not result.galgame.backend.strip():
        raise ConfigurationError("galgame.backend cannot be empty")
    if not result.annotation.allowed_emotions:
        raise ConfigurationError("annotation.allowed_emotions cannot be empty")
    if result.audio.format.strip(".") == "":
        raise ConfigurationError("audio.format cannot be empty")
    if result.audio.format.lstrip(".").lower() not in {"wav", "opus"}:
        raise ConfigurationError("audio.format must be wav or opus")
    if result.audio.intermediate_format.lstrip(".").lower() != "wav":
        raise ConfigurationError("audio.intermediate_format must be wav")
    if result.audio.sample_rate < 1:
        raise ConfigurationError("audio.sample_rate must be positive")
    if result.audio.channels < 1:
        raise ConfigurationError("audio.channels must be positive")
    if result.audio.sample_width not in {1, 2, 3, 4}:
        raise ConfigurationError("audio.sample_width must be between 1 and 4")
    if result.audio.bitrate_kbps < 6:
        raise ConfigurationError("audio.bitrate_kbps must be at least 6")
    if not result.audio.ffmpeg_executable:
        raise ConfigurationError("audio.ffmpeg_executable cannot be empty")
    if not result.audio.ffprobe_executable:
        raise ConfigurationError("audio.ffprobe_executable cannot be empty")
    if result.audio.minimum_duration_seconds < 0:
        raise ConfigurationError("audio.minimum_duration_seconds cannot be negative")
    if (
        result.audio.maximum_duration_seconds
        < result.audio.minimum_duration_seconds
    ):
        raise ConfigurationError("audio duration range is invalid")
    return result
