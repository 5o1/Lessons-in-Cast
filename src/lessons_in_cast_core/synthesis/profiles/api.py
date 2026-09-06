"""Backend-neutral interface for character voice pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..references.builder import ReferenceBuildResult
from ..types import TtsJob

@dataclass(frozen=True, slots=True)
class ReferenceBuildRequest:
    """Explicit source and destination for a generated voice reference."""

    input_directory: Path
    output_path: Path


class VoicePipeline(ABC):
    """Backend-neutral contract used by the main dialogue pipeline."""

    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Return a stable identifier for cache fingerprints and diagnostics."""

    @property
    @abstractmethod
    def character_id(self) -> str:
        """Return the character handled by this pipeline."""

    @property
    @abstractmethod
    def configuration(self) -> dict[str, Any]:
        """Return all settings that can affect rendered output."""

    def prepare(self) -> tuple[Path, ...]:
        """Prepare generated dependencies and return their paths."""

        return ()

    @abstractmethod
    def render(self, job: TtsJob, artifact_root: Path) -> Path:
        """Render one immutable speech job."""

    def close(self) -> None:
        """Release any loaded models or subprocesses."""


class ReferenceVoicePipeline(VoicePipeline, ABC):
    """Optional capability implemented by pipelines that build references."""

    @property
    @abstractmethod
    def default_reference_request(self) -> ReferenceBuildRequest:
        """Return the configured source and generated-reference destination."""

    @abstractmethod
    def build_reference(
        self,
        request: ReferenceBuildRequest,
    ) -> ReferenceBuildResult:
        """Build a persistent reference from a directory of source samples."""
