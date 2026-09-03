from __future__ import annotations

from lessons_in_cast.annotation import (
    Annotation,
    DialogueAction,
    ValidatedAnnotation,
    ValidationStatus,
)
from lessons_in_cast.dialogue import DialogueRecord


def record(
    sequence: int,
    *,
    character: str = "a",
    dialogue: str = "Hello.",
    filename: str = "game/AmiEvents.rpy",
) -> DialogueRecord:
    return DialogueRecord(
        id=f"id-{sequence}",
        sequence=sequence,
        identifier=f"line_{sequence}",
        character=character,
        dialogue=dialogue,
        filename=filename,
        line_number=sequence + 1,
        renpy_script=f'{character} "[what]"',
    )


def accepted_annotation(
    item: DialogueRecord,
    *,
    action: DialogueAction = DialogueAction.SPEAK,
    effects: tuple[str, ...] = (),
) -> ValidatedAnnotation:
    annotation = Annotation(
        id=item.id,
        action=action,
        spoken_text=item.dialogue if "speak" in action.value else "",
        emotion="neutral" if "speak" in action.value else None,
        intensity=0.5 if "speak" in action.value else None,
        delivery={},
        effects=effects,
        confidence=1.0,
        review_required=False,
    )
    return ValidatedAnnotation(
        dialogue_id=item.id,
        batch_id="batch",
        status=ValidationStatus.ACCEPTED,
        annotation=annotation,
        issues=(),
        input_hash="input",
        prompt_version="1",
        annotator_config_hash="config",
        processed_at="2026-09-04T00:00:00+00:00",
    )
