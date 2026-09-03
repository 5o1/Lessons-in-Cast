"""Public API and subprocess adapter for Ren'Py dialogue extraction."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class DialogueExtractionError(RuntimeError):
    """Raised when Ren'Py cannot produce a dialogue table."""


@dataclass(frozen=True, slots=True)
class DialogueExtractionRequest:
    """Parameters required to invoke Ren'Py dialogue extraction."""

    release_path: Path
    output_path: Path
    source_paths: Sequence[Path] = ()
    language: str | None = None
    launcher_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DialogueExtractionResult:
    """Metadata returned by a Ren'Py dialogue extractor."""

    dialogue_path: Path
    source_count: int
    command: tuple[str, ...]


class DialogueExtractor(Protocol):
    """Extract a dialogue artifact, normally dialogue.tab."""

    def extract(
        self,
        request: DialogueExtractionRequest,
    ) -> DialogueExtractionResult: ...


class SubprocessDialogueExtractor:
    """Invoke the game release's native Ren'Py launcher."""

    def __init__(self, *, timeout_seconds: float = 600.0) -> None:
        self._timeout_seconds = timeout_seconds

    def extract(
        self,
        request: DialogueExtractionRequest,
    ) -> DialogueExtractionResult:
        release_path = request.release_path.resolve()
        if not release_path.is_dir():
            raise DialogueExtractionError(
                f"Ren'Py release directory does not exist: {release_path}"
            )
        launcher = (
            request.launcher_path.resolve()
            if request.launcher_path is not None
            else self._find_launcher(release_path)
        )
        language = request.language if request.language is not None else "None"
        command = (str(launcher), str(release_path), "dialogue", language)
        try:
            completed = subprocess.run(
                command,
                cwd=release_path,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DialogueExtractionError(
                f"Unable to run Ren'Py dialogue extraction: {exc}"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise DialogueExtractionError(
                f"Ren'Py dialogue extraction failed with exit code "
                f"{completed.returncode}: {detail}"
            )

        generated = release_path / "dialogue.tab"
        if not generated.is_file():
            raise DialogueExtractionError(
                f"Ren'Py completed without producing {generated}"
            )
        output_path = request.output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if generated != output_path:
            shutil.copy2(generated, output_path)
        return DialogueExtractionResult(
            dialogue_path=output_path,
            source_count=len(request.source_paths),
            command=command,
        )

    @staticmethod
    def _find_launcher(release_path: Path) -> Path:
        launchers = sorted(release_path.glob("*.sh"))
        if not launchers:
            raise DialogueExtractionError(
                f"No Linux Ren'Py launcher was found in {release_path}"
            )
        if len(launchers) > 1:
            names = ", ".join(path.name for path in launchers)
            raise DialogueExtractionError(
                f"Multiple Ren'Py launchers found; specify one explicitly: {names}"
            )
        return launchers[0].resolve()
