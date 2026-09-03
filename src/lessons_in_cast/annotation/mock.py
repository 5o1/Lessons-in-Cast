"""Deterministic annotator used to test the pipeline without a model."""

from __future__ import annotations

from typing import Any


class MockDialogueAnnotator:
    @property
    def configuration(self) -> dict[str, Any]:
        return {"adapter": "mock", "version": 1}

    def annotate(self, request: dict[str, Any]) -> dict[str, Any]:
        batch = request["batch"]
        return {
            "batch_id": batch["batch_id"],
            "annotations": [
                {
                    "id": item["id"],
                    "action": "speak",
                    "spoken_text": item["dialogue"],
                    "emotion": "neutral",
                    "intensity": 0.5,
                    "delivery": {},
                    "effects": [],
                    "confidence": 1.0,
                    "review_required": False,
                    "reason": "Deterministic mock annotation.",
                }
                for item in batch["targets"]
            ],
        }
