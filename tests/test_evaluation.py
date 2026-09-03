from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast.evaluation import evaluate_annotations
from lessons_in_cast.jsonl import write_jsonl

from .helpers import accepted_annotation, record


class EvaluationTests(unittest.TestCase):
    def test_evaluates_a_gold_subset_by_stable_id(self) -> None:
        item = record(1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validated = root / "validated.jsonl"
            gold = root / "gold.jsonl"
            write_jsonl([accepted_annotation(item).to_dict()], validated)
            write_jsonl(
                [
                    {
                        "dialogue_id": item.id,
                        "expected": {
                            "action": "speak",
                            "spoken_text": item.dialogue,
                            "emotion": "neutral",
                        },
                    }
                ],
                gold,
            )
            result = evaluate_annotations(gold, validated)
            self.assertEqual(result.found, 1)
            self.assertEqual(result.to_dict()["action_accuracy"], 1.0)

    def test_rejects_duplicate_gold_ids(self) -> None:
        item = record(1)
        sample = {
            "dialogue_id": item.id,
            "expected": {
                "action": "speak",
                "spoken_text": item.dialogue,
                "emotion": "neutral",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validated = root / "validated.jsonl"
            gold = root / "gold.jsonl"
            write_jsonl([accepted_annotation(item).to_dict()], validated)
            write_jsonl([sample, sample], gold)
            with self.assertRaisesRegex(ValueError, "Duplicate gold"):
                evaluate_annotations(gold, validated)


if __name__ == "__main__":
    unittest.main()
