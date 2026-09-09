"""Separate cleaning/polish contracts and semantic-label backend compilation."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from lessons_in_cast_core.annotation import AnnotationValidator, ValidationStatus, build_annotation_request
from lessons_in_cast_core.annotation.codex import CodexAnnotationWorkflow, CodexWorkspace
from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.dialogue import DialogueBatch
from lessons_in_cast_core.emotions import EMOTION_LABELS
from lessons_in_cast_core.jsonl import read_jsonl, write_jsonl
from lessons_in_cast_core.polish import PolishStage
from lessons_in_cast_core.speech_markup import parse_emotion_markup
from lessons_in_cast_core.synthesis.backends.index_tts.adapter import index_emotion_vector
from lessons_in_cast_core.synthesis.backends.index_tts.emotions import EMOTION_VECTORS
from lessons_in_cast_core.workflow.artifacts import ArtifactLayout
from lessons_in_cast_core.workflow.validation import AnnotationValidationStage
from .fakes import write_mock_responses
from .helpers import record

ROOT = Path(__file__).resolve().parents[1]


class PolishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.layout = ArtifactLayout(self.root / "run")
        self.layout.root.mkdir()
        self.config = load_pipeline_config(repository_root=ROOT)
        self.source = record(1, dialogue="I will try. Stay here.")
        self.batch = DialogueBatch("batch", (record(0, character="s", dialogue="You can do it."),), (self.source,), ())
        request = build_annotation_request(self.batch, annotation_config=self.config.annotation, stage="cleaning")
        request["director_notes"] = {self.source.id: {"direction": "Tears, then renewed purpose."}}
        write_jsonl([self.source.to_dict()], self.layout.raw_dialogue)
        write_jsonl([request], self.layout.annotation_requests)
        write_mock_responses(self.layout.annotation_requests, self.layout.annotation_responses)
        self.pause = {"kind": "pause", "offset": 12, "duration_seconds": .3, "intensity": None}
        self.modify(self.layout.annotation_responses, lambda row: row.update(performance={"cues": [self.pause]}))
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 1)
        self.stage = PolishStage(self.config)

    def modify(self, path, callback):
        rows = list(read_jsonl(path))
        callback(rows[0]["response"]["annotations"][0])
        write_jsonl(rows, path)

    def prepare(self):
        self.stage.prepare(self.layout)
        write_mock_responses(self.layout.polish.annotation_requests, self.layout.polish.annotation_responses)

    def test_cleaning_has_no_emotion_catalog_or_acting_controls(self):
        request = next(read_jsonl(self.layout.annotation_requests))
        self.assertEqual(request["stage"], "cleaning")
        self.assertEqual(request["emotion_labels"], {})
        schema = request["response_schema"]["properties"]["annotations"]["items"]["properties"]
        self.assertNotIn("delivery", schema)
        self.assertEqual(set(schema["performance"]["properties"]), {"cues"})

    def test_cleaning_rejects_emotion_and_voice_semantics(self):
        base = next(read_jsonl(self.layout.annotation_responses))["response"]
        for field, value in [("spoken_text", '<emotion name="calm">I will try.</emotion>'),
                             ("emotion", "sad"), ("delivery", {"style": "sad"}),
                             ("performance", {"direction": "Playful", "cues": []})]:
            response = {**base, "annotations": [{**base["annotations"][0], field: value}]}
            result = AnnotationValidator(self.config.annotation).validate_batch(self.batch, response,
                stage="cleaning", schema_version=4, prompt_version="v4", annotator_configuration={})
            self.assertEqual(result.records[0].status, ValidationStatus.RETRYABLE)

    def test_polish_preserves_context_director_notes_cleaned_text_and_pauses(self):
        self.prepare()
        request = next(read_jsonl(self.layout.polish.annotation_requests))
        self.assertEqual(request["stage"], "polish")
        self.assertIn("tearful_resolve", request["emotion_labels"])
        self.assertEqual(request["batch"]["context_before"][0]["dialogue"], "You can do it.")
        self.assertEqual(request["director_notes"][self.source.id]["direction"], "Tears, then renewed purpose.")
        self.modify(self.layout.polish.annotation_responses, lambda row: row.update(
            spoken_text='<emotion name="tearful_resolve">I will try. Stay here.</emotion>'))
        self.assertEqual(self.stage.validate(self.layout).accepted_count, 1)
        result = next(read_jsonl(self.layout.polish.validated))
        self.assertEqual(result["annotation"]["performance"]["cues"], [self.pause])
        self.assertNotIn("intensity", result["annotation"])

    def test_polish_keyframes_preserve_cleaning_and_original_text(self):
        from .test_keyframes import curve
        self.prepare()
        request = next(read_jsonl(self.layout.polish.annotation_requests))
        self.assertEqual(request["original_texts"][self.source.id], self.source.dialogue)
        self.assertIn("keyframe_effects", request["response_schema"]["properties"]["annotations"]["items"]["properties"])
        self.modify(self.layout.polish.annotation_responses, lambda row: row.update(
            spoken_text='<emotion name="calm">{1}I will try. {2}Stay here.{3}</emotion>',
            keyframe_effects=curve(("1", 0), ("2", .5), ("3", 1))))
        self.assertEqual(self.stage.validate(self.layout).accepted_count, 1)
        result = next(read_jsonl(self.layout.polish.validated))
        self.assertEqual(result["annotation"]["performance"]["cues"], [self.pause])
        self.modify(self.layout.polish.annotation_responses, lambda row: row.update(
            spoken_text='<emotion name="calm">{1}I will not try. {2}Stay here.{3}</emotion>'))
        self.assertEqual(self.stage.validate(self.layout).retryable_count, 1)

    def test_partial_original_requires_polish_gain_envelope(self):
        from .test_keyframes import curve
        self.source = replace(self.source, dialogue="...Stay here.")
        write_jsonl([self.source.to_dict()], self.layout.raw_dialogue)
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 1)
        self.stage.prepare(self.layout)
        request = next(read_jsonl(self.layout.polish.annotation_requests))
        self.assertEqual(request["keyframe_required"], [self.source.id])
        write_mock_responses(self.layout.polish.annotation_requests, self.layout.polish.annotation_responses)
        self.assertEqual(self.stage.validate(self.layout).retryable_count, 1)
        self.modify(self.layout.polish.annotation_responses, lambda row: row.update(
            spoken_text='<emotion name="calm">{1}I will try. Stay here.{2}</emotion>',
            keyframe_effects=curve(("1", 0), ("2", 1), interpolation="smooth")))
        self.assertEqual(self.stage.validate(self.layout).accepted_count, 1)

    def test_polish_cannot_rewrite_words_or_change_pauses_actions_effects(self):
        self.prepare()
        original = list(read_jsonl(self.layout.polish.annotation_responses))
        changes = [{"spoken_text": '<emotion name="calm">I will try again.</emotion>'},
                   {"performance": {"cues": []}},
                   {"action": "speak_with_effect", "effects": ["echo"]}]
        for change in changes:
            write_jsonl(original, self.layout.polish.annotation_responses)
            self.modify(self.layout.polish.annotation_responses, lambda row: row.update(change))
            self.assertEqual(self.stage.validate(self.layout).retryable_count, 1)
            retry = next(read_jsonl(self.layout.polish.retry_requests))
            self.assertEqual(retry["stage"], "polish")
            self.assertIn(self.source.id, retry["cleaned_annotations"])
            self.assertIn(self.source.id, retry["director_notes"])

    def test_missing_polish_is_not_default_neutral(self):
        self.stage.prepare(self.layout)
        with self.assertRaisesRegex(ValueError, "No polish responses"):
            self.stage.validate(self.layout)

    def test_accepted_retry_survives_revalidation_before_synthesis(self):
        self.prepare()
        self.modify(self.layout.polish.annotation_responses, lambda row: row.update(
            spoken_text="Missing labels."))
        self.assertEqual(self.stage.validate(self.layout).retryable_count, 1)
        write_mock_responses(self.layout.polish.retry_requests, self.layout.polish.retry_responses)
        self.assertEqual(self.stage.validate(self.layout, retry=True).accepted_count, 1)
        self.assertEqual(self.stage.validate(self.layout).accepted_count, 1)

    def test_unaccepted_cleaning_cannot_be_polished(self):
        self.modify(self.layout.annotation_responses, lambda row: row.update(review_required=True))
        AnnotationValidationStage(self.config).run(self.layout)
        with self.assertRaisesRegex(ValueError, "requires accepted"):
            self.stage.prepare(self.layout)

    def test_changed_cleaning_invalidates_polish(self):
        self.prepare()
        self.modify(self.layout.annotation_responses, lambda row: row.update(spoken_text="Changed."))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.stage.validate(self.layout)

    def test_polish_packets_include_semantic_definitions_not_vectors(self):
        self.prepare()
        workflow = CodexAnnotationWorkflow(ROOT / self.config.codex.polish_prompt_path)
        packet = workflow._build_packet(list(read_jsonl(self.layout.polish.annotation_requests)))
        self.assertEqual(packet["stage"], "polish")
        self.assertEqual(set(packet["emotion_labels"]["tearful_resolve"]), {"description", "example"})
        self.assertIn(self.source.id, packet["cleaned_annotations"])
        self.assertNotIn("emotion_vectors", packet)

    def test_single_complex_tag_has_a_multiaxis_vector(self):
        spans = parse_emotion_markup('<emotion name="tearful_resolve">I will try.</emotion>', EMOTION_LABELS)
        self.assertEqual(spans[0].to_dict(), {"text": "I will try.", "emotion": "tearful_resolve", "voice": None})
        vector = index_emotion_vector(spans[0].emotion)
        self.assertEqual(len(vector), 8)
        self.assertGreater(sum(value > 0 for value in vector), 1)
        self.assertLessEqual(sum(vector), .800001)
        self.assertEqual(set(EMOTION_LABELS), set(EMOTION_VECTORS))

    def test_combination_labels_and_numeric_intensity_are_rejected(self):
        for markup in ['<emotion name="sad,calm">Hi.</emotion>',
                       '<emotion name="sad calm">Hi.</emotion>',
                       '<emotion name="tearful_resolve" intensity="0.5">Hi.</emotion>']:
            with self.assertRaises(ValueError):
                parse_emotion_markup(markup, EMOTION_LABELS)


if __name__ == "__main__":
    unittest.main()
