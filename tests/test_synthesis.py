from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast_core.characters import CharacterDefinition
from lessons_in_cast_core.annotation import DialogueAction
from lessons_in_cast_core.config import AudioConfig
from lessons_in_cast_core.synthesis import (
    AudioQualityChecker,
    SynthesisPlanner,
    WaveRenderer,
    apply_index_pronunciations,
    index_emotion_vector,
)

from .fakes import SilenceSynthesizer
from .helpers import accepted_annotation, record


def character(
    character_id: str,
    *,
    members: tuple[str, ...] = (),
) -> CharacterDefinition:
    return CharacterDefinition(
        id=character_id,
        name=character_id,
        type="ensemble" if members else "individual",
        members=members,
        render_mode="unison" if members else None,
        definition_path="game/definitions.rpy",
        definition_line=1,
        built_in=False,
        default_voice_profile="",
    )


class SynthesisTests(unittest.TestCase):
    def test_planner_deduplicates_member_audio_and_renders_ensemble(self) -> None:
        first = record(1, character="a", dialogue="Same.")
        second = record(2, character="am", dialogue="Same.")
        characters = {
            "a": character("a"),
            "m": character("m"),
            "am": character("am", members=("a", "m")),
        }
        plan = SynthesisPlanner(characters).plan(
            {first.id: first, second.id: second},
            [accepted_annotation(first), accepted_annotation(second)],
        )
        self.assertEqual(len(plan.jobs), 2)
        self.assertEqual(len(plan.render_tasks), 2)
        self.assertEqual(len(plan.render_tasks[1].component_job_ids), 2)

    def test_planner_separates_wav_intermediate_from_opus_delivery(self) -> None:
        item = record(1, character="a")
        plan = SynthesisPlanner(
            {"a": character("a")},
            audio_config=AudioConfig(format="opus", intermediate_format="wav"),
        ).plan({item.id: item}, [accepted_annotation(item)])
        self.assertTrue(plan.jobs[0].output_path.endswith(".wav"))
        self.assertTrue(plan.render_tasks[0].output_path.endswith(".opus"))
        self.assertTrue(plan.render_tasks[0].virtual_path.endswith(".opus"))

    def test_planner_uses_synthesizer_configuration_in_cache_keys(self) -> None:
        item = record(1, character="a")
        regular = SynthesisPlanner(
            {"a": character("a")},
            synthesizer_configuration={"profiles": {"a": {"base_speed": 1.0}}},
        ).plan({item.id: item}, [accepted_annotation(item)])
        faster = SynthesisPlanner(
            {"a": character("a")},
            synthesizer_configuration={"profiles": {"a": {"base_speed": 1.25}}},
        ).plan({item.id: item}, [accepted_annotation(item)])
        self.assertFalse(hasattr(faster.jobs[0], "base_speed"))
        self.assertNotEqual(regular.jobs[0].cache_key, faster.jobs[0].cache_key)

    def test_silence_synthesis_render_and_quality_check(self) -> None:
        item = record(1, character="a")
        plan = SynthesisPlanner({"a": character("a")}).plan(
            {item.id: item},
            [accepted_annotation(item)],
        )
        config = AudioConfig()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            synthesizer = SilenceSynthesizer(config)
            for job in plan.jobs:
                synthesizer.synthesize(job, root)
            task = plan.render_tasks[0]
            path = WaveRenderer().render(
                task,
                {job.id: job for job in plan.jobs},
                root,
            )
            result = AudioQualityChecker(config).check(item.id, path)
            self.assertTrue(result.valid)
            self.assertGreater(result.duration_seconds or 0, 0)

    def test_unsafe_identifier_is_not_planned(self) -> None:
        item = record(1, character="a")
        item = type(item)(
            id=item.id,
            sequence=item.sequence,
            identifier="../unsafe",
            character=item.character,
            dialogue=item.dialogue,
            filename=item.filename,
            line_number=item.line_number,
            source_statement=item.source_statement,
        )
        plan = SynthesisPlanner({"a": character("a")}).plan(
            {item.id: item},
            [accepted_annotation(item)],
        )
        self.assertFalse(plan.jobs)
        self.assertEqual(plan.issues[0].code, "unsafe_identifier")

    def test_omit_does_not_create_audio_work(self) -> None:
        item = record(1, character="a")
        plan = SynthesisPlanner({"a": character("a")}).plan(
            {item.id: item},
            [accepted_annotation(item, action=DialogueAction.OMIT)],
        )
        self.assertFalse(plan.jobs)
        self.assertFalse(plan.render_tasks)
        self.assertFalse(plan.issues)

    def test_index_tts_pronunciation(self) -> None:
        self.assertEqual(
            apply_index_pronunciations(
                "chinami met Chinamiya.", {"Chinami": "CH IY1 . N AA0 . M IY0"}
            ),
            "<chinami|CH IY1 . N AA0 . M IY0> met Chinamiya.",
        )

    def test_index_tts_emotion_vector_uses_documented_axis_order(self) -> None:
        self.assertEqual(
            index_emotion_vector("excited", 1.0),
            [0.608696, 0.0, 0.0, 0.0, 0.0, 0.0, 0.191304, 0.0],
        )
        self.assertEqual(
            index_emotion_vector("neutral", 1.0),
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )

if __name__ == "__main__":
    unittest.main()
