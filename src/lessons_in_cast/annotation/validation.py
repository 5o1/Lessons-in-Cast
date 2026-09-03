"""Independent validation gate for untrusted model output."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ..config import AnnotationConfig
from ..dialogue import DialogueBatch, DialogueRecord
from ..hashing import content_hash
from .types import (
    Annotation,
    BatchValidationResult,
    DialogueAction,
    ValidatedAnnotation,
    ValidationIssue,
    ValidationStatus,
)


_PLACEHOLDER = re.compile(r"\[[^\[\]]+\]")
_TEXT_TAG = re.compile(r"\{[^{}]+\}")
_ALLOWED_FIELDS = {
    "id",
    "action",
    "spoken_text",
    "emotion",
    "intensity",
    "delivery",
    "effects",
    "confidence",
    "review_required",
    "reason",
}


class AnnotationValidator:
    """Validate structure, batch identity, cross-fields, and text risks."""

    def __init__(self, config: AnnotationConfig) -> None:
        self._config = config

    def validate_batch(
        self,
        batch: DialogueBatch,
        response: dict[str, Any],
        *,
        prompt_version: str,
        annotator_configuration: dict[str, Any],
        processed_at: str | None = None,
    ) -> BatchValidationResult:
        timestamp = processed_at or datetime.now(timezone.utc).isoformat()
        input_hash = content_hash(batch.to_dict())
        config_hash = content_hash(annotator_configuration)
        target_by_id = {item.id: item for item in batch.targets}
        context_ids = {
            item.id for item in (*batch.context_before, *batch.context_after)
        }
        batch_issues: list[ValidationIssue] = []

        if not isinstance(response, dict):
            return self._all_retryable(
                batch,
                "response_type",
                "Model response must be a JSON object.",
                input_hash,
                prompt_version,
                config_hash,
                timestamp,
            )
        unknown_response_fields = set(response) - {"batch_id", "annotations"}
        if unknown_response_fields:
            return self._all_retryable(
                batch,
                "unknown_response_fields",
                f"Unknown response fields: {sorted(unknown_response_fields)!r}",
                input_hash,
                prompt_version,
                config_hash,
                timestamp,
            )
        if response.get("batch_id") != batch.id:
            return self._all_retryable(
                batch,
                "batch_id_mismatch",
                "Model response batch_id does not match the request.",
                input_hash,
                prompt_version,
                config_hash,
                timestamp,
            )
        raw_annotations = response.get("annotations")
        if not isinstance(raw_annotations, list):
            return self._all_retryable(
                batch,
                "annotations_type",
                "Model response annotations must be an array.",
                input_hash,
                prompt_version,
                config_hash,
                timestamp,
            )

        raw_ids = [
            item.get("id")
            for item in raw_annotations
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        id_counts = Counter(raw_ids)
        for raw_id in raw_ids:
            if raw_id in context_ids:
                batch_issues.append(
                    ValidationIssue(
                        "context_output",
                        "The model returned an annotation for a context-only record.",
                        "error",
                        raw_id,
                    )
                )
            elif raw_id not in target_by_id:
                batch_issues.append(
                    ValidationIssue(
                        "unknown_id",
                        "The model returned an unknown dialogue ID.",
                        "error",
                        raw_id,
                    )
                )

        raw_by_id: dict[str, dict[str, Any]] = {}
        for item in raw_annotations:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                if item["id"] in target_by_id and item["id"] not in raw_by_id:
                    raw_by_id[item["id"]] = item

        validated: list[ValidatedAnnotation] = []
        for target in batch.targets:
            issues: list[ValidationIssue] = []
            if id_counts[target.id] == 0:
                issues.append(
                    ValidationIssue(
                        "missing_target",
                        "The model did not return this target.",
                        "error",
                        target.id,
                    )
                )
                annotation = None
            elif id_counts[target.id] > 1:
                issues.append(
                    ValidationIssue(
                        "duplicate_target",
                        "The model returned this target more than once.",
                        "error",
                        target.id,
                    )
                )
                annotation = None
            else:
                annotation, annotation_issues = self._validate_annotation(
                    target,
                    raw_by_id[target.id],
                )
                issues.extend(annotation_issues)

            if annotation is None or any(issue.severity == "error" for issue in issues):
                status = ValidationStatus.RETRYABLE
            elif annotation.review_required or issues:
                status = ValidationStatus.REVIEW_REQUIRED
            else:
                status = ValidationStatus.ACCEPTED
            validated.append(
                ValidatedAnnotation(
                    dialogue_id=target.id,
                    batch_id=batch.id,
                    status=status,
                    annotation=annotation,
                    issues=tuple(issues),
                    input_hash=input_hash,
                    prompt_version=prompt_version,
                    annotator_config_hash=config_hash,
                    processed_at=timestamp,
                )
            )

        return BatchValidationResult(batch.id, tuple(validated), tuple(batch_issues))

    def _validate_annotation(
        self,
        target: DialogueRecord,
        raw: dict[str, Any],
    ) -> tuple[Annotation | None, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []

        def error(code: str, message: str) -> None:
            issues.append(ValidationIssue(code, message, "error", target.id))

        unknown = set(raw) - _ALLOWED_FIELDS
        if unknown:
            error("unknown_fields", f"Unknown fields: {sorted(unknown)!r}")
        required = {
            "id",
            "action",
            "spoken_text",
            "emotion",
            "intensity",
            "delivery",
            "effects",
            "confidence",
            "review_required",
            "reason",
        }
        missing = required - set(raw)
        if missing:
            error("missing_fields", f"Missing fields: {sorted(missing)!r}")
            return None, issues
        if raw["id"] != target.id:
            error("id_mismatch", "Annotation ID does not match the target.")
        try:
            action = DialogueAction(raw["action"])
        except (TypeError, ValueError):
            error("invalid_action", "Action is not an allowed value.")
            return None, issues

        spoken_text = raw["spoken_text"]
        emotion = raw["emotion"]
        intensity = raw["intensity"]
        delivery = raw["delivery"]
        effects = raw["effects"]
        confidence = raw["confidence"]
        review_required = raw["review_required"]
        reason = raw["reason"]

        if not isinstance(spoken_text, str):
            error("spoken_text_type", "spoken_text must be a string.")
        if emotion is not None and not isinstance(emotion, str):
            error("emotion_type", "emotion must be a string or null.")
        elif emotion is not None and emotion not in self._config.allowed_emotions:
            error("invalid_emotion", f"Emotion {emotion!r} is not allowed.")
        if intensity is not None and (
            isinstance(intensity, bool)
            or not isinstance(intensity, (int, float))
            or not 0 <= intensity <= 1
        ):
            error("invalid_intensity", "intensity must be null or between 0 and 1.")
        if not isinstance(delivery, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in delivery.items()
        ):
            error("delivery_type", "delivery must be an object with string values.")
        if not isinstance(effects, list) or not all(
            isinstance(effect, str) for effect in effects
        ):
            error("effects_type", "effects must be an array of strings.")
        elif len(effects) != len(set(effects)):
            error("duplicate_effect", "effects cannot contain duplicates.")
        elif any(effect not in self._config.allowed_effects for effect in effects):
            error("invalid_effect", "effects contains an unsupported value.")
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            error("invalid_confidence", "confidence must be null or between 0 and 1.")
        if not isinstance(review_required, bool):
            error("review_required_type", "review_required must be a boolean.")
        if reason is not None and not isinstance(reason, str):
            error("reason_type", "reason must be a string or null.")
        if any(issue.severity == "error" for issue in issues):
            return None, issues

        assert isinstance(spoken_text, str)
        assert isinstance(delivery, dict)
        assert isinstance(effects, list)
        assert isinstance(review_required, bool)

        speaking = action in {DialogueAction.SPEAK, DialogueAction.SPEAK_WITH_EFFECT}
        if speaking and not spoken_text.strip():
            error("missing_spoken_text", "A speaking action requires spoken_text.")
        if not speaking and spoken_text:
            error("unexpected_spoken_text", "A non-speaking action requires empty spoken_text.")
        if speaking and (emotion is None or intensity is None):
            error("missing_emotion", "A speaking action requires emotion and intensity.")
        if action is DialogueAction.SPEAK and effects:
            error("unexpected_effects", "Use speak_with_effect when effects are present.")
        if action is DialogueAction.SPEAK_WITH_EFFECT and not effects:
            error("missing_effects", "speak_with_effect requires at least one effect.")
        if action is DialogueAction.SFX_ONLY and not effects:
            error("missing_effects", "sfx_only requires at least one effect.")
        if action is DialogueAction.OMIT and effects:
            error("unexpected_effects", "omit cannot contain effects.")
        if any(issue.severity == "error" for issue in issues):
            return None, issues

        self._add_text_risks(target, spoken_text, speaking, issues)
        if action in {DialogueAction.OMIT, DialogueAction.SFX_ONLY}:
            issues.append(
                ValidationIssue(
                    "high_impact_action",
                    "Omitting speech or replacing it with effects requires human review.",
                    "warning",
                    target.id,
                )
            )
        return (
            Annotation(
                id=target.id,
                action=action,
                spoken_text=spoken_text,
                emotion=emotion,
                intensity=float(intensity) if intensity is not None else None,
                delivery=delivery,
                effects=tuple(effects),
                confidence=float(confidence) if confidence is not None else None,
                review_required=review_required,
                reason=reason,
            ),
            issues,
        )

    def _add_text_risks(
        self,
        target: DialogueRecord,
        spoken_text: str,
        speaking: bool,
        issues: list[ValidationIssue],
    ) -> None:
        if not speaking:
            return
        if any(ord(character) < 32 and character not in "\t\n\r" for character in spoken_text):
            issues.append(
                ValidationIssue(
                    "control_character",
                    "spoken_text contains a control character.",
                    "warning",
                    target.id,
                )
            )
        if _TEXT_TAG.search(spoken_text):
            issues.append(
                ValidationIssue(
                    "text_tag",
                    "spoken_text may still contain a Ren'Py text tag.",
                    "warning",
                    target.id,
                )
            )
        original_placeholders = Counter(_PLACEHOLDER.findall(target.dialogue))
        spoken_placeholders = Counter(_PLACEHOLDER.findall(spoken_text))
        if original_placeholders != spoken_placeholders:
            issues.append(
                ValidationIssue(
                    "placeholder_change",
                    "Square-bracket placeholders changed during cleaning.",
                    "warning",
                    target.id,
                )
            )
        original_length = max(len(target.dialogue.strip()), 1)
        ratio = len(spoken_text.strip()) / original_length
        if (
            ratio < self._config.minimum_length_ratio
            or ratio > self._config.maximum_length_ratio
        ):
            issues.append(
                ValidationIssue(
                    "length_ratio",
                    f"Cleaned text length ratio {ratio:.2f} is outside the configured range.",
                    "warning",
                    target.id,
                )
            )

    def _all_retryable(
        self,
        batch: DialogueBatch,
        code: str,
        message: str,
        input_hash: str,
        prompt_version: str,
        config_hash: str,
        timestamp: str,
    ) -> BatchValidationResult:
        records = tuple(
            ValidatedAnnotation(
                dialogue_id=target.id,
                batch_id=batch.id,
                status=ValidationStatus.RETRYABLE,
                annotation=None,
                issues=(ValidationIssue(code, message, "error", target.id),),
                input_hash=input_hash,
                prompt_version=prompt_version,
                annotator_config_hash=config_hash,
                processed_at=timestamp,
            )
            for target in batch.targets
        )
        return BatchValidationResult(batch.id, records)
