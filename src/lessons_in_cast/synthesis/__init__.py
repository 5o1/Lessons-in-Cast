"""Model-neutral speech synthesis planning and audio utilities."""

from .api import AudioEffectProcessor, SpeechSynthesizer
from .audio import AudioQualityChecker, WaveRenderer
from .gpt_sovits import GptSoVitsHttpSynthesizer, GptSoVitsReference
from .index_tts import (
    IndexTtsSubprocessSynthesizer,
    apply_index_pronunciations,
    index_emotion_vector,
    normalize_index_emotion_vector,
)
from .index_tts_pipeline import IndexTtsPipeline
from .planner import SynthesisPlanner
from .reference_builder import (
    ReferenceBuildError,
    ReferenceBuildResult,
    ReferenceBuildSettings,
    build_reference_from_directory,
    prepare_reference_sources,
)
from .voice_pipeline import (
    ReferenceBuildRequest,
    ReferenceVoicePipeline,
    VoicePipeline,
    VoicePipelineContext,
)
from .voice_pipeline_loader import (
    VoicePipelineSynthesizer,
    load_configured_voice_pipelines,
    load_voice_pipeline,
)
from .types import (
    AudioQualityResult,
    RenderTask,
    SynthesisIssue,
    SynthesisPlan,
    TtsJob,
)

__all__ = [
    "AudioQualityChecker",
    "AudioQualityResult",
    "AudioEffectProcessor",
    "GptSoVitsHttpSynthesizer",
    "GptSoVitsReference",
    "IndexTtsSubprocessSynthesizer",
    "IndexTtsPipeline",
    "apply_index_pronunciations",
    "index_emotion_vector",
    "normalize_index_emotion_vector",
    "prepare_reference_sources",
    "ReferenceBuildError",
    "ReferenceBuildRequest",
    "ReferenceVoicePipeline",
    "ReferenceBuildResult",
    "ReferenceBuildSettings",
    "build_reference_from_directory",
    "RenderTask",
    "SpeechSynthesizer",
    "SynthesisIssue",
    "SynthesisPlan",
    "SynthesisPlanner",
    "TtsJob",
    "VoicePipeline",
    "VoicePipelineContext",
    "VoicePipelineSynthesizer",
    "load_configured_voice_pipelines",
    "load_voice_pipeline",
    "WaveRenderer",
]
