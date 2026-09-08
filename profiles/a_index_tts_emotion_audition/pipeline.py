"""Ami audition candidate using cached QwenEmotion presets and the existing voice."""

from lessons_in_cast_core.synthesis.backends.index_tts import IndexTtsPipeline


class AmiEmotionAuditionPipeline(IndexTtsPipeline):
    pipeline_id = "ami-index-tts-qwen-emotion-audition"
    character_id = "a"


def create_pipeline(context):
    return AmiEmotionAuditionPipeline(context)
