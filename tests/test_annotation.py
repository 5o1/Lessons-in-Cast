from __future__ import annotations

import copy
import unittest

from lessons_in_cast.annotation import (
    AnnotationValidator,
    DialogueAction,
    ValidationStatus,
    apply_overrides,
    build_annotation_request,
)
from lessons_in_cast.config import AnnotationConfig
from lessons_in_cast.dialogue import DialogueBatch

from .fakes import MockDialogueAnnotator
from .helpers import record


class AnnotationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AnnotationConfig(
            allowed_emotions=frozenset({"neutral", "surprised"}),
            allowed_effects=frozenset({"glitch"}),
            maximum_length_ratio=4.0,
            minimum_length_ratio=0.15,
        )
        self.validator = AnnotationValidator(self.config)
        self.context = record(0)
        self.target = record(1, dialogue="Wait?!")
        self.batch = DialogueBatch("batch", (self.context,), (self.target,), ())

    def _response(self) -> dict[str, object]:
        request = build_annotation_request(self.batch)
        return MockDialogueAnnotator().annotate(request)

    def test_accepts_valid_response(self) -> None:
        result = self.validator.validate_batch(
            self.batch,
            self._response(),
            prompt_version="1",
            annotator_configuration={"adapter": "mock"},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.ACCEPTED)

    def test_request_contains_a_strict_response_schema(self) -> None:
        request = build_annotation_request(self.batch, annotation_config=self.config)
        schema = request["response_schema"]
        self.assertFalse(schema["additionalProperties"])
        annotation = schema["properties"]["annotations"]["items"]
        self.assertFalse(annotation["additionalProperties"])
        self.assertIn("neutral", annotation["properties"]["emotion"]["enum"])

    def test_missing_target_is_retryable(self) -> None:
        result = self.validator.validate_batch(
            self.batch,
            {"batch_id": "batch", "annotations": []},
            prompt_version="1",
            annotator_configuration={},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.RETRYABLE)
        self.assertEqual(result.records[0].issues[0].code, "missing_target")

    def test_context_output_is_reported_without_corrupting_target(self) -> None:
        response = self._response()
        response["annotations"].append(
            {
                **response["annotations"][0],
                "id": self.context.id,
            }
        )
        result = self.validator.validate_batch(
            self.batch,
            response,
            prompt_version="1",
            annotator_configuration={},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.ACCEPTED)
        self.assertEqual(result.issues[0].code, "context_output")

    def test_cross_field_violation_is_retryable(self) -> None:
        response = self._response()
        response["annotations"][0]["effects"] = ["glitch"]
        result = self.validator.validate_batch(
            self.batch,
            response,
            prompt_version="1",
            annotator_configuration={},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.RETRYABLE)
        self.assertIsNone(result.records[0].annotation)

    def test_text_risk_requires_review(self) -> None:
        response = self._response()
        response["annotations"][0]["spoken_text"] = "{i}Wait?!{/i}"
        result = self.validator.validate_batch(
            self.batch,
            response,
            prompt_version="1",
            annotator_configuration={},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.REVIEW_REQUIRED)

    def test_approved_override_accepts_risk_and_does_not_mutate_input(self) -> None:
        response = self._response()
        validated = list(
            self.validator.validate_batch(
                self.batch,
                response,
                prompt_version="1",
                annotator_configuration={},
            ).records
        )
        overrides = {
            self.target.id: {
                "spoken_text": "A much longer manually approved rendering.",
                "approved": True,
            }
        }
        original = copy.deepcopy(overrides)
        applied = apply_overrides(
            validated,
            {self.target.id: self.target},
            overrides,
            self.validator,
        )
        self.assertEqual(applied[0].status, ValidationStatus.ACCEPTED)
        self.assertEqual(applied[0].source, "manual")
        self.assertEqual(overrides, original)

    def test_manual_rejection(self) -> None:
        validated = list(
            self.validator.validate_batch(
                self.batch,
                self._response(),
                prompt_version="1",
                annotator_configuration={},
            ).records
        )
        applied = apply_overrides(
            validated,
            {self.target.id: self.target},
            {self.target.id: {"status": "rejected"}},
            self.validator,
        )
        self.assertEqual(applied[0].status, ValidationStatus.REJECTED)

    def test_omit_requires_human_review(self) -> None:
        response = self._response()
        response["annotations"][0].update(
            {
                "action": "omit",
                "spoken_text": "",
                "emotion": None,
                "intensity": None,
            }
        )
        result = self.validator.validate_batch(
            self.batch,
            response,
            prompt_version="1",
            annotator_configuration={},
        )
        self.assertEqual(result.records[0].status, ValidationStatus.REVIEW_REQUIRED)
        self.assertEqual(result.records[0].issues[0].code, "high_impact_action")


if __name__ == "__main__":
    unittest.main()
