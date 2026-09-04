"""Chinami voice rendering through the IndexTTS 2.5 backend."""

from __future__ import annotations

from lessons_in_cast.synthesis.index_tts_pipeline import IndexTtsPipeline
from lessons_in_cast.synthesis.voice_pipeline import (
    VoicePipeline,
    VoicePipelineContext,
)


class ChinamiIndexTtsPipeline(IndexTtsPipeline):
    """The active IndexTTS voice pipeline for Chinami."""


    @property
    def configuration_path(self) -> str:
        return "configs/voice_pipelines/ch_index_tts.toml"

    @property
    def pipeline_id(self) -> str:
        return "chinami-index-tts-2.5"

    @property
    def character_id(self) -> str:
        return "ch"


def create_pipeline(context: VoicePipelineContext) -> VoicePipeline:
    """Create the pipeline through the backend-neutral factory contract."""

    return ChinamiIndexTtsPipeline(context)
