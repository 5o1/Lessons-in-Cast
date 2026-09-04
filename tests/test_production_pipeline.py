from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast.annotation import MockDialogueAnnotator
from lessons_in_cast.characters import CharacterDefinition
from lessons_in_cast.config import AnnotationConfig, AudioConfig, BatchingConfig, PipelineConfig
from lessons_in_cast.pipeline import ArtifactLayout, DialoguePipeline, PipelineRequest
from lessons_in_cast.synthesis import SilenceSynthesizer


HEADER = "Identifier\tCharacter\tDialogue\tFilename\tLine Number\tRen'Py Script\n"


class ProductionPipelineTests(unittest.TestCase):
    def test_external_responses_run_retains_only_release_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dialogue_tab = root / "dialogue.tab"
            dialogue_tab.write_text(
                HEADER + 'one\ta\tHello.\tgame/chapter/main.rpy\t1\ta "[what]"\n',
                encoding="utf-8",
            )
            config = PipelineConfig(
                batching=BatchingConfig(target_size=1),
                annotation=AnnotationConfig(
                    allowed_emotions=frozenset({"neutral"}),
                    allowed_effects=frozenset(),
                ),
                audio=AudioConfig(),
            )
            character = CharacterDefinition(
                id="a",
                name="Ami",
                type="individual",
                members=(),
                render_mode=None,
                definition_path="game/definitions.rpy",
                definition_line=1,
                built_in=False,
                model_path="",
                generation_script_path="",
                base_speed=1.0,
            )
            annotation_root = root / "annotation"
            request = PipelineRequest(
                artifact_root=annotation_root,
                dialogue_tab_path=dialogue_tab,
                allowed_sources=(Path("game/chapter/main.rpy"),),
            )
            annotation_pipeline = DialoguePipeline(
                config=config,
                characters={"a": character},
                annotator=MockDialogueAnnotator(),
            )
            annotation_pipeline.prepare(request)
            annotation_layout = ArtifactLayout(annotation_root)
            annotation_pipeline.annotate(annotation_layout)

            production_root = root / "production"
            production_root.mkdir()
            (production_root / "unrelated.txt").write_text("keep", encoding="utf-8")
            production_pipeline = DialoguePipeline(
                config=config,
                characters={"a": character},
                synthesizer=SilenceSynthesizer(config.audio),
            )
            result = production_pipeline.run_from_responses(
                PipelineRequest(
                    artifact_root=production_root,
                    dialogue_tab_path=dialogue_tab,
                    allowed_sources=(Path("game/chapter/main.rpy"),),
                ),
                annotation_layout.annotation_responses,
            )

            self.assertEqual(
                {path.name for path in production_root.iterdir()},
                {"release_bundle", "run_manifest.json", "unrelated.txt"},
            )
            self.assertTrue(
                (
                    result.artifacts.release_bundle
                    / "game"
                    / "voice"
                    / "chapter"
                    / "main"
                    / "one.wav"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
