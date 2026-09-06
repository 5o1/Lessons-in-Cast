"""Model-neutral speech synthesis planning and audio utilities."""

from .api import AudioEffectProcessor, SpeechSynthesizer
from .audio import AudioQualityChecker, WaveRenderer
from .backends.gpt_sovits import GptSoVitsHttpSynthesizer, GptSoVitsReference
from .backends.index_tts import (
    IndexTtsPipeline,
    IndexTtsSubprocessSynthesizer,
    apply_index_pronunciations,
    index_emotion_vector,
    normalize_index_emotion_vector,
)
from .planner import SynthesisPlanner
from .references import (
    ReferenceBuildError,
    ReferenceBuildResult,
    ReferenceBuildSettings,
    build_reference_from_directory,
    prepare_reference_sources,
)
from .profiles import (
    ReferenceBuildRequest,
    ReferenceVoicePipeline,
    VoicePipeline,
    VoiceProfileContext,
    VoiceProfileSynthesizer,
    load_configured_voice_profiles,
    load_voice_profile,
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
    "VoiceProfileContext",
    "VoiceProfileSynthesizer",
    "load_configured_voice_profiles",
    "load_voice_profile",
    "WaveRenderer",
]
