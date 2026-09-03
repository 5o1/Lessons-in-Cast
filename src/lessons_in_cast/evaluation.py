"""Repeatable evaluation of validated annotations against human gold data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .annotation import ValidatedAnnotation
from .jsonl import JsonlIndex, read_jsonl


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    total: int
    found: int
    action_correct: int
    emotion_correct: int
    spoken_text_correct: int
    review_required: int
    missing_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        denominator = self.found or 1
        return {
            "total": self.total,
            "found": self.found,
            "missing": len(self.missing_ids),
            "action_accuracy": self.action_correct / denominator,
            "emotion_accuracy": self.emotion_correct / denominator,
            "spoken_text_exact_accuracy": self.spoken_text_correct / denominator,
            "review_rate": self.review_required / denominator,
            "missing_ids": list(self.missing_ids),
        }


def evaluate_annotations(
    gold_path: Path,
    validated_path: Path,
) -> EvaluationResult:
    total = 0
    found = 0
    action_correct = 0
    emotion_correct = 0
    spoken_text_correct = 0
    review_required = 0
    missing: list[str] = []
    with JsonlIndex(validated_path, "dialogue_id") as validated:
        if validated.duplicates:
            raise ValueError(
                "Validated annotations contain duplicate dialogue IDs: "
                f"{sorted(validated.duplicates)!r}"
            )
        seen_gold_ids: set[str] = set()
        for sample in read_jsonl(gold_path):
            total += 1
            dialogue_id = sample.get("dialogue_id")
            expected = sample.get("expected")
            if not isinstance(dialogue_id, str) or not isinstance(expected, dict):
                raise ValueError("Gold samples require dialogue_id and expected")
            if dialogue_id in seen_gold_ids:
                raise ValueError(f"Duplicate gold dialogue ID: {dialogue_id!r}")
            seen_gold_ids.add(dialogue_id)
            raw_actual = validated.get(dialogue_id)
            actual = (
                ValidatedAnnotation.from_dict(raw_actual)
                if raw_actual is not None
                else None
            )
            if actual is None or actual.annotation is None:
                missing.append(dialogue_id)
                continue
            found += 1
            annotation = actual.annotation
            action_correct += annotation.action.value == expected.get("action")
            emotion_correct += annotation.emotion == expected.get("emotion")
            spoken_text_correct += (
                annotation.spoken_text == expected.get("spoken_text")
            )
            review_required += actual.status.value == "review_required"
    return EvaluationResult(
        total=total,
        found=found,
        action_correct=action_correct,
        emotion_correct=emotion_correct,
        spoken_text_correct=spoken_text_correct,
        review_required=review_required,
        missing_ids=tuple(missing),
    )
