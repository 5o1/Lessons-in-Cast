"""Dialogue records and streaming transformation contracts."""

from .api import DialogueProcessor, DialogueReader, DialogueWriter
from .types import DialogueRecord

__all__ = [
    "DialogueProcessor",
    "DialogueReader",
    "DialogueRecord",
    "DialogueWriter",
]
