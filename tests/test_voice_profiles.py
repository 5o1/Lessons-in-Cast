from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast_core.characters import load_characters
from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.model_registry import ModelDefinition, ModelRegistry
from lessons_in_cast_core.synthesis import (
    VoicePipeline,
    VoiceProfileContext,
    load_configured_voice_profiles,
    load_voice_profile,
)
from lessons_in_cast_core.synthesis.backends.index_tts import IndexTtsPipeline


class VoiceProfileTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def model_registry(self) -> ModelRegistry:
        return ModelRegistry(
            self.root,
            {
                "index_tts_2_5": ModelDefinition(
                    id="index_tts_2_5",
                    path="models/IndexTeam/IndexTTS-2.5",
                    provider="huggingface",
                    repository="IndexTeam/IndexTTS-2.5",
                    revision="test-revision",
                    license="test-license",
                )
            },
        )

    def test_profile_context_resolves_only_bundle_resources(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        character = load_characters(repository_root=self.root)["ch"]
        entrypoint = self.root / character.default_voice_profile
        context = VoiceProfileContext(
            repository_root=self.root,
            entrypoint=entrypoint,
            profile_root=entrypoint.parent,
            character=character,
            project_config=config,
            model_registry=self.model_registry,
        )
        self.assertEqual(
            context.resolve_resource("config.toml"),
            self.root / "profiles/ch_index_tts/config.toml",
        )
        with self.assertRaises(ValueError):
            context.resolve_resource("../outside.toml")

    def test_single_file_profile_loads_without_being_a_python_package(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        character = load_characters(repository_root=self.root)["ch"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "profiles"
            profiles.mkdir()
            entrypoint = profiles / "simple.py"
            entrypoint.write_text(
                "from pathlib import Path\n"
                "from lessons_in_cast_core.synthesis import VoicePipeline\n"
                "class SimplePipeline(VoicePipeline):\n"
                "    pipeline_id = 'simple'\n"
                "    character_id = 'ch'\n"
                "    @property\n"
                "    def configuration(self):\n"
                "        return {'kind': 'single-file'}\n"
                "    def render(self, job, artifact_root: Path):\n"
                "        return artifact_root / job.output_path\n"
                "def create_pipeline(context):\n"
                "    assert context.entrypoint.name == 'simple.py'\n"
                "    return SimplePipeline()\n",
                encoding="utf-8",
            )
            pipeline = load_voice_profile(
                root,
                Path("profiles/simple.py"),
                character,
                config,
                model_registry=ModelRegistry(root, {}),
            )
            try:
                self.assertEqual(pipeline.configuration["kind"], "single-file")
            finally:
                pipeline.close()

    def test_chinami_profile_has_required_inheritance_layers(self) -> None:
        self.assertTrue(issubclass(IndexTtsPipeline, VoicePipeline))

    def test_configured_pipeline_loads_through_public_factory(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        character = load_characters(repository_root=self.root)["ch"]
        pipeline = load_voice_profile(
            self.root,
            Path(character.default_voice_profile),
            character,
            config,
            model_registry=self.model_registry,
        )
        try:
            self.assertIsInstance(pipeline, VoicePipeline)
            self.assertIsInstance(pipeline, IndexTtsPipeline)
            self.assertEqual(pipeline.character_id, "ch")
            self.assertEqual(
                pipeline.configuration["backend"]["adapter"],
                "index-tts-2.5",
            )
            self.assertEqual(
                pipeline.configuration["model"]["revision"],
                "test-revision",
            )
            self.assertFalse(
                pipeline.configuration["backend"]["reference_processing"][
                    "prepare_references"
                ]
            )
            self.assertEqual(
                Path(pipeline.configuration["configuration_path"]),
                self.root / "profiles/ch_index_tts/config.toml",
            )
            self.assertEqual(
                pipeline.configuration["backend"]["base_speed"],
                1.0,
            )
            self.assertEqual(
                pipeline.configuration["backend"]["pronunciations"]["Chinami"],
                "CH IY1 . N AA0 . M IY0",
            )
            self.assertEqual(
                Path(pipeline.configuration["pronunciation_config_path"]),
                self.root / "configs/pronunciations.toml",
            )
            self.assertEqual(
                Path(pipeline.configuration["reference_path"]),
                self.root
                / "profiles/ch_index_tts/assets/references/default.wav",
            )
        finally:
            pipeline.close()

    def test_main_synthesizer_routes_configured_character_pipelines(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        characters = load_characters(repository_root=self.root)
        synthesizer = load_configured_voice_profiles(
            self.root,
            config,
            characters,
            model_registry=self.model_registry,
        )
        try:
            self.assertEqual(
                list(synthesizer.configuration["profiles"]),
                ["a", "ch", "m"],
            )
        finally:
            synthesizer.close()


if __name__ == "__main__":
    unittest.main()
