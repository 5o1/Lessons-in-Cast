"""Speech jobs, line-level render tasks, and audio validation results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..annotation import DialogueAction


@dataclass(frozen=True, slots=True)
class TtsJob:
    id: str
    dialogue_id: str
    character_id: str
    text: str
    emotion: str
    intensity: float
    delivery: dict[str, str]
    base_speed: float
    model_path: str
    generation_script_path: str
    output_path: str
    cache_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dialogue_id": self.dialogue_id,
            "character_id": self.character_id,
            "text": self.text,
            "emotion": self.emotion,
            "intensity": self.intensity,
            "delivery": self.delivery,
            "base_speed": self.base_speed,
            "model_path": self.model_path,
            "generation_script_path": self.generation_script_path,
            "output_path": self.output_path,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TtsJob:
        return cls(**value)


@dataclass(frozen=True, slots=True)
class RenderTask:
    dialogue_id: str
    identifier: str
    action: DialogueAction
    component_job_ids: tuple[str, ...]
    render_mode: str
    effects: tuple[str, ...]
    output_path: str
    virtual_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id,
            "identifier": self.identifier,
            "action": self.action.value,
            "component_job_ids": list(self.component_job_ids),
            "render_mode": self.render_mode,
            "effects": list(self.effects),
            "output_path": self.output_path,
            "virtual_path": self.virtual_path,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RenderTask:
        return cls(
            dialogue_id=value["dialogue_id"],
            identifier=value["identifier"],
            action=DialogueAction(value["action"]),
            component_job_ids=tuple(value["component_job_ids"]),
            render_mode=value["render_mode"],
            effects=tuple(value["effects"]),
            output_path=value["output_path"],
            virtual_path=value["virtual_path"],
        )


@dataclass(frozen=True, slots=True)
class SynthesisIssue:
    dialogue_id: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "dialogue_id": self.dialogue_id,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class SynthesisPlan:
    jobs: tuple[TtsJob, ...]
    render_tasks: tuple[RenderTask, ...]
    issues: tuple[SynthesisIssue, ...]


@dataclass(frozen=True, slots=True)
class AudioQualityResult:
    dialogue_id: str
    path: str
    valid: bool
    duration_seconds: float | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id,
            "path": self.path,
            "valid": self.valid,
            "duration_seconds": self.duration_seconds,
            "issues": list(self.issues),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AudioQualityResult:
        return cls(
            dialogue_id=value["dialogue_id"],
            path=value["path"],
            valid=value["valid"],
            duration_seconds=value.get("duration_seconds"),
            issues=tuple(value.get("issues", ())),
        )
