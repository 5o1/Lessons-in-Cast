from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast.annotation import MockDialogueAnnotator
from lessons_in_cast.characters import CharacterDefinition
from lessons_in_cast.config import (
    AnnotationConfig,
    AudioConfig,
    BatchingConfig,
    PipelineConfig,
)
from lessons_in_cast.pipeline import DialoguePipeline, PipelineRequest
from lessons_in_cast.jsonl import read_jsonl, write_jsonl
from lessons_in_cast.synthesis import SilenceSynthesizer


HEADER = (
    "Identifier\tCharacter\tDialogue\tFilename\tLine Number\tRen'Py Script\n"
)


class PipelineTests(unittest.TestCase):
    def test_mock_pipeline_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dialogue_tab = root / "dialogue.tab"
            dialogue_tab.write_text(
                HEADER
                + 'one\ta\tHello.\tgame/AmiEvents.rpy\t1\ta "[what]"\n'
                + 'two\ta\tAgain.\tgame/AmiEvents.rpy\t2\ta "[what]"\n',
                encoding="utf-8",
            )
            config = PipelineConfig(
                batching=BatchingConfig(target_size=1, context_before=1, context_after=1),
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
            )
            pipeline = DialoguePipeline(
                config=config,
                characters={"a": character},
                annotator=MockDialogueAnnotator(),
                synthesizer=SilenceSynthesizer(config.audio),
            )
            artifacts = root / "artifacts"
            result = pipeline.run(
                PipelineRequest(
                    artifact_root=artifacts,
                    dialogue_tab_path=dialogue_tab,
                    allowed_sources=(Path("game/AmiEvents.rpy"),),
                )
            )
            self.assertEqual(result.dialogue_count, 2)
            self.assertEqual(result.batch_count, 2)
            self.assertEqual(result.accepted_count, 2)
            self.assertEqual(result.rendered_count, 2)
            self.assertTrue(result.artifacts.voice_manifest.is_file())
            self.assertTrue(result.artifacts.run_manifest.is_file())
            self.assertTrue(result.artifacts.renpy_script.is_file())
            self.assertTrue(
                (
                    result.artifacts.release_bundle
                    / "game"
                    / "lessons_in_cast_voice.rpy"
                ).is_file()
            )

    def test_validation_exports_only_failed_targets_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dialogue_tab = root / "dialogue.tab"
            dialogue_tab.write_text(
                HEADER
                + 'one\ta\tHello.\tgame/AmiEvents.rpy\t1\ta "[what]"\n'
                + 'two\ta\tAgain.\tgame/AmiEvents.rpy\t2\ta "[what]"\n',
                encoding="utf-8",
            )
            config = PipelineConfig(
                batching=BatchingConfig(target_size=2, context_before=1, context_after=1),
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
            )
            pipeline = DialoguePipeline(
                config=config,
                characters={"a": character},
                annotator=MockDialogueAnnotator(),
            )
            artifacts = root / "artifacts"
            request = PipelineRequest(
                artifact_root=artifacts,
                dialogue_tab_path=dialogue_tab,
                allowed_sources=(Path("game/AmiEvents.rpy"),),
            )
            pipeline.prepare(request)
            layout = request.artifact_root
            from lessons_in_cast.pipeline import ArtifactLayout

            artifact_layout = ArtifactLayout(layout)
            pipeline.annotate(artifact_layout)
            envelopes = list(read_jsonl(artifact_layout.model_responses))
            envelopes[0]["response"]["annotations"].pop()
            write_jsonl(envelopes, artifact_layout.model_responses)
            summary = pipeline.validate(artifact_layout)
            self.assertEqual(summary.retryable_count, 1)
            retry_requests = list(read_jsonl(artifact_layout.retry_requests))
            self.assertEqual(len(retry_requests), 1)
            self.assertEqual(len(retry_requests[0]["batch"]["targets"]), 1)
            pipeline.annotate(
                artifact_layout,
                requests_path=artifact_layout.retry_requests,
                responses_path=artifact_layout.retry_responses,
            )
            retried = pipeline.validate(artifact_layout, retry=True)
            self.assertEqual(retried.accepted_count, 2)
            self.assertEqual(retried.retryable_count, 0)
            self.assertFalse(list(read_jsonl(artifact_layout.retry_requests)))


if __name__ == "__main__":
    unittest.main()
