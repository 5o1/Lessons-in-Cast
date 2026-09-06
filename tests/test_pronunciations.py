from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast_core.config import ConfigurationError
from lessons_in_cast_core.pronunciations import (
    load_pronunciation_lexicon,
)


class PronunciationLexiconTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_project_lexicon_exposes_selected_arpabet_entries(self) -> None:
        lexicon = load_pronunciation_lexicon(repository_root=self.root)
        self.assertEqual(
            lexicon.for_system("arpabet"),
            {
                "Ami": "EY1 . M IY0",
                "Ayane": "AA0 . Y AA1 . N EH0",
                "Chinami": "CH IY1 . N AA0 . M IY0",
                "Maya": "M AY1 . Y AH0",
            },
        )

    def test_systems_remain_backend_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "pronunciations.toml"
            config.write_text(
                "schema_version = 1\n"
                "[proper_nouns.Chinami]\n"
                'arpabet = "CH IY1 . N AA0 . M IY0"\n'
                'kana = "ちなみ"\n',
                encoding="utf-8",
            )
            lexicon = load_pronunciation_lexicon(
                config,
                repository_root=root,
            )
            self.assertEqual(
                lexicon.for_system("kana"),
                {"Chinami": "ちなみ"},
            )

    def test_case_insensitive_duplicate_terms_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "pronunciations.toml"
            config.write_text(
                "schema_version = 1\n"
                "[proper_nouns.Chinami]\n"
                'arpabet = "one"\n'
                "[proper_nouns.chinami]\n"
                'arpabet = "two"\n',
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_pronunciation_lexicon(
                    config,
                    repository_root=root,
                )


if __name__ == "__main__":
    unittest.main()
