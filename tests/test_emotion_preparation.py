"""Offline preset registration, cache validity and incremental compilation."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from lessons_in_cast_core.emotion_presets import add_emotion_preset, load_emotion_catalog
from lessons_in_cast_core.emotions import emotion_definitions
from lessons_in_cast_core.synthesis.backends.index_tts.emotion_preparation import (
    AXES, compile_cache, load_vector_cache, validate_prediction,
)


class EmotionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / "vectors.json"
        self.catalog = {"test_emotion": ("Tears with resolve.", "I can do it.")}
        self.definitions = emotion_definitions(self.catalog, self.catalog)
        self.context = {"backend": "index-tts", "input_kind": "description", "model": {"id": "test"}}
        self.engine = Mock()
        self.engine.raw_output = '{"悲伤": 0.5, "自然": 0.3}'
        self.engine.inference.return_value = dict(zip(AXES, [0, 0, .5, 0, 0, 0, 0, .3]))
        self.factory = Mock(return_value=self.engine)

    def prepare(self, force=False):
        return compile_cache(self.definitions, self.context, self.output, self.factory, force=force)

    def test_register_persists_without_mutating_builtin_catalog(self):
        path = self.root / "emotions.toml"
        add_emotion_preset(path, "new_emotion", 'A "bright" voice.', "Hello!")
        self.assertEqual(load_emotion_catalog(path)["new_emotion"], ('A "bright" voice.', "Hello!"))
        self.assertNotIn("new_emotion", load_emotion_catalog(self.root / "missing.toml"))
        with self.assertRaises(ValueError):
            add_emotion_preset(path, "happy", "No overwrite", "Hi")
        with self.assertRaises(ValueError):
            add_emotion_preset(path, "sad,calm", "No combinations", "Hi")

    def test_custom_preset_reaches_polish_through_pipeline_config(self):
        from lessons_in_cast_core.config import load_pipeline_config
        from lessons_in_cast_core.annotation import build_annotation_request
        from lessons_in_cast_core.dialogue import DialogueBatch
        from .helpers import record
        path = self.root / "configs/emotions.toml"
        add_emotion_preset(path, "new_emotion", "Nervous reassurance", "It is fine.")
        original = (Path(__file__).resolve().parents[1] / "configs/pipeline.toml").read_text()
        (path.parent / "pipeline.toml").write_text(original.replace('"neutral",', '"neutral", "new_emotion",'))
        config = load_pipeline_config(repository_root=self.root)
        request = build_annotation_request(DialogueBatch("batch", (), (record(1),), ()),
                                           annotation_config=config.annotation, stage="polish")
        self.assertEqual(request["emotion_labels"]["new_emotion"]["description"], "Nervous reassurance")
        clean = build_annotation_request(DialogueBatch("batch", (), (record(1),), ()),
                                         annotation_config=config.annotation, stage="cleaning")
        self.assertEqual(clean["emotion_labels"], {})

    def test_cache_hit_needs_no_model_and_raw_vector_normalized_only_once(self):
        self.prepare()
        self.engine.inference.assert_called_once_with("Tears with resolve.")
        self.factory.reset_mock()
        self.prepare()
        self.factory.assert_not_called()
        vectors, identity = load_vector_cache(self.output, self.catalog, model_id="test")
        self.assertEqual(vectors["test_emotion"], [0, 0, .5, 0, 0, 0, 0, .3])
        self.assertTrue(identity)
        self.assertEqual(json.loads(self.output.read_text())["entries"]["test_emotion"]["vector"][-1], .16875)

    def test_changed_description_invalidates_and_regenerates_only_changed_label(self):
        self.prepare()
        self.catalog["test_emotion"] = ("New direction", "I can do it.")
        with self.assertRaises(ValueError):
            load_vector_cache(self.output, self.catalog)
        self.definitions = emotion_definitions(self.catalog, self.catalog)
        self.prepare()
        self.assertEqual(self.engine.inference.call_count, 2)
        load_vector_cache(self.output, self.catalog)

    def test_resume_after_failure_never_publishes_incomplete_cache(self):
        self.definitions["z_other"] = {"description": "Other", "example": "Hi"}
        prediction = self.engine.inference.return_value
        self.engine.inference.side_effect = [prediction, ValueError("failed model output")]
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.assertTrue(self.output.with_suffix(".json.partial").exists())
        self.assertTrue(self.output.with_suffix(".json.failure.json").exists())
        self.engine.inference.side_effect = None
        self.engine.inference.reset_mock()
        self.prepare()
        self.engine.inference.assert_called_once_with("Other")

    def test_invalid_predictions_and_tampered_cache_are_rejected(self):
        for bad in ({}, {**self.engine.inference.return_value, "sad": float("nan")},
                    {**self.engine.inference.return_value, "sad": True},
                    {**self.engine.inference.return_value, "sad": 2}):
            with self.assertRaises(ValueError):
                validate_prediction(bad)
        self.prepare()
        document = json.loads(self.output.read_text())
        document["entries"]["test_emotion"]["vector"][0] = .4
        self.output.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            load_vector_cache(self.output, self.catalog)

    def test_force_and_model_or_input_changes_require_new_predictions(self):
        self.prepare()
        self.prepare(force=True)
        self.context = {**self.context, "input_kind": "example"}
        self.prepare()
        self.engine.inference.assert_called_with("I can do it.")
        self.assertEqual(self.engine.inference.call_count, 3)
        with self.assertRaises(ValueError):
            load_vector_cache(self.output, self.catalog, model_id="wrong-model")


if __name__ == "__main__":
    unittest.main()
