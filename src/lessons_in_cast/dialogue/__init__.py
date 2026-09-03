"""Dialogue records and streaming transformation contracts."""

from .api import DialogueProcessor, DialogueReader, DialogueWriter
from .audit import audit_dialogue
from .batching import DialogueBatch, DialogueBatchBuilder
from .jsonl import JsonlDialogueReader, JsonlDialogueWriter
from .tab import DialogueTabError, TabDialogueReader
from .types import DialogueRecord

__all__ = [
    "DialogueBatch",
    "DialogueBatchBuilder",
    "DialogueProcessor",
    "DialogueReader",
    "DialogueRecord",
    "DialogueTabError",
    "DialogueWriter",
    "JsonlDialogueReader",
    "JsonlDialogueWriter",
    "TabDialogueReader",
    "audit_dialogue",
]
