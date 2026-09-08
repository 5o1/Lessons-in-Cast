"""Ami's experimental local H3 audition profile; not the production default."""

from lessons_in_cast_core.synthesis.backends.minimax_h3 import MiniMaxH3Pipeline


class AmiMiniMaxH3Pipeline(MiniMaxH3Pipeline):
    pipeline_id = "ami-minimax-h3-ref2va-v1"
    character_id = "a"


def create_pipeline(context):
    return AmiMiniMaxH3Pipeline(context)
