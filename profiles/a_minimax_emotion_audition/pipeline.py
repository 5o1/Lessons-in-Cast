"""Ami's reference-cloned MiniMax comparison; not the production default."""

from lessons_in_cast_core.synthesis.backends.minimax import MiniMaxSpeechPipeline


class AmiMiniMaxEmotionAuditionPipeline(MiniMaxSpeechPipeline):
    pipeline_id = "ami-minimax-reference-emotion-audition-v1"
    character_id = "a"


def create_pipeline(context):
    return AmiMiniMaxEmotionAuditionPipeline(context)
