"""Touka voice rendering through the IndexTTS 2.5 backend."""

from __future__ import annotations

from lessons_in_cast_core.synthesis.backends.index_tts import IndexTtsPipeline
from lessons_in_cast_core.synthesis.profiles import VoicePipeline, VoiceProfileContext


class ToukaIndexTtsPipeline(IndexTtsPipeline):
    """The initial IndexTTS voice pipeline for Touka."""

    @property
    def pipeline_id(self) -> str:
        return "touka-index-tts-2.5"

    @property
    def character_id(self) -> str:
        return "to"


def create_pipeline(context: VoiceProfileContext) -> VoicePipeline:
    """Create the pipeline through the backend-neutral factory contract."""

    return ToukaIndexTtsPipeline(context)
