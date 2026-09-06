"""JSON Schema construction for strict annotation responses."""

from __future__ import annotations

from typing import Any

from ..config import AnnotationConfig


def annotation_response_schema(
    config: AnnotationConfig | None = None,
) -> dict[str, Any]:
    emotion_schema: dict[str, Any] = {"type": ["string", "null"]}
    effect_schema: dict[str, Any] = {"type": "string"}
    if config is not None:
        emotion_schema = {
            "enum": [*sorted(config.allowed_emotions), None],
        }
        effect_schema = {
            "type": "string",
            "enum": sorted(config.allowed_effects),
        }
    annotation = {
        "type": "object",
        "additionalProperties": False,
        "required": [
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
        ],
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "action": {
                "type": "string",
                "enum": ["speak", "omit", "sfx_only", "speak_with_effect"],
            },
            "spoken_text": {"type": "string"},
            "emotion": emotion_schema,
            "intensity": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 1,
            },
            "delivery": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "effects": {
                "type": "array",
                "items": effect_schema,
                "uniqueItems": True,
            },
            "confidence": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 1,
            },
            "review_required": {"type": "boolean"},
            "reason": {"type": ["string", "null"]},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Lessons in Cast annotation response",
        "type": "object",
        "additionalProperties": False,
        "required": ["batch_id", "annotations"],
        "properties": {
            "batch_id": {"type": "string", "minLength": 1},
            "annotations": {
                "type": "array",
                "items": annotation,
            },
        },
    }
