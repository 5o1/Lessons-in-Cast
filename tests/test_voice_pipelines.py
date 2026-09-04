from __future__ import annotations

import unittest
from pathlib import Path

from lessons_in_cast.characters import load_characters
from lessons_in_cast.config import load_pipeline_config
from lessons_in_cast.synthesis import (
    VoicePipeline,
    load_configured_voice_pipelines,
    load_voice_pipeline,
)
from lessons_in_cast.synthesis.index_tts_pipeline import IndexTtsPipeline
from voice_pipelines.ch_index_tts import ChinamiIndexTtsPipeline


class VoicePipelineTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_chinami_pipeline_has_required_inheritance_layers(self) -> None:
        self.assertTrue(issubclass(IndexTtsPipeline, VoicePipeline))
        self.assertTrue(
            issubclass(ChinamiIndexTtsPipeline, IndexTtsPipeline)
        )

    def test_configured_pipeline_loads_through_public_factory(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        character = load_characters(repository_root=self.root)["ch"]
        pipeline = load_voice_pipeline(
            self.root,
            Path(character.generation_script_path),
            character,
            config,
        )
        try:
            self.assertIsInstance(pipeline, VoicePipeline)
            self.assertEqual(pipeline.character_id, "ch")
            self.assertEqual(
                pipeline.configuration["backend"]["adapter"],
                "index-tts-2.5",
            )
            self.assertFalse(
                pipeline.configuration["backend"]["reference_processing"][
                    "prepare_references"
                ]
            )
        finally:
            pipeline.close()

    def test_main_synthesizer_routes_configured_character_pipelines(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        characters = load_characters(repository_root=self.root)
        synthesizer = load_configured_voice_pipelines(
            self.root,
            config,
            characters,
        )
        try:
            self.assertEqual(
                list(synthesizer.configuration["pipelines"]),
                ["ch"],
            )
        finally:
            synthesizer.close()


if __name__ == "__main__":
    unittest.main()
