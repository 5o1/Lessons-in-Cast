"""Install rendered voices into a Ren'Py-loadable directory tree."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..synthesis import AudioQualityResult, RenderTask


@dataclass(frozen=True, slots=True)
class RenPyInstallationResult:
    game_root: Path
    audio_count: int


class RenPyVoiceInstaller:
    """Create a fresh ``game/`` tree with mirrored virtual voice paths."""

    def install(
        self,
        destination_root: Path,
        *,
        artifact_root: Path,
        voice_script: Path,
        voice_manifest: Path,
        artifacts: Iterable[tuple[RenderTask, AudioQualityResult]],
    ) -> RenPyInstallationResult:
        destination_root = destination_root.resolve()
        destination_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(
                dir=destination_root.parent,
                prefix=f".{destination_root.name}.install.",
            )
        )
        staging_game = staging_root / "game"
        staging_game.mkdir()
        copied = 0
        try:
            for task, quality in artifacts:
                if not quality.valid:
                    continue
                source = artifact_root / task.output_path
                if not source.is_file():
                    raise FileNotFoundError(
                        f"Rendered audio is missing for {task.dialogue_id}: {source}"
                    )
                destination = self._virtual_destination(
                    staging_game,
                    task.virtual_path,
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied += 1

            shutil.copy2(voice_script, staging_game / voice_script.name)
            shutil.copy2(voice_manifest, staging_game / voice_manifest.name)

            destination_root.mkdir(parents=True, exist_ok=True)
            game_root = destination_root / "game"
            if game_root.exists():
                shutil.rmtree(game_root)
            staging_game.replace(game_root)
            return RenPyInstallationResult(game_root=game_root, audio_count=copied)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

    @staticmethod
    def _virtual_destination(game_root: Path, virtual_path: str) -> Path:
        path = PurePosixPath(virtual_path)
        if path.is_absolute() or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise ValueError(f"Unsafe Ren'Py virtual path: {virtual_path!r}")
        destination = game_root.joinpath(*path.parts).resolve()
        if not destination.is_relative_to(game_root.resolve()):
            raise ValueError(f"Ren'Py virtual path escapes game root: {virtual_path!r}")
        return destination
