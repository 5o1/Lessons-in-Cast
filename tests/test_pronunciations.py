from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast_core.config import ConfigurationError
from lessons_in_cast_core.pronunciations import load_pronunciation_lexicon


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

    def test_v2_preserves_pronunciation_aligned_f0_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "pronunciations.toml"
            config.write_text(
                "schema_version = 2\n"
                "[proper_nouns.Chinami]\n"
                'language = "en"\n'
                "case_sensitive = false\n"
                "whole_word = true\n"
                "[proper_nouns.Chinami.forms]\n"
                'arpabet = "CH IY1 . N AA0 . M IY0"\n'
                'ipa = "tʃiː.nɑː.mi"\n'
                "[proper_nouns.Chinami.prosody]\n"
                'unit_kind = "syllable"\n'
                'pitch_reference = "local_baseline"\n'
                'interpolation = "smooth"\n'
                "duration_scale = 1.1\n"
                "units = [\n"
                "  { label = \"chi\", forms = { ipa = \"tʃiː\", "
                "arpabet = \"CH IY1\" }, "
                "pitch_contour = [\n"
                "    { position = 0.0, semitones = -3.0 },\n"
                "    { position = 0.5, semitones = 3.0 },\n"
                "    { position = 1.0, semitones = -1.0 },\n"
                "  ] },\n"
                "  { label = \"na\", forms = { ipa = \"nɑː\", "
                "arpabet = \"N AA0\" }, "
                "duration_scale = 1.2, pitch_contour = [\n"
                "    { position = 0.0, semitones = 1.0 },\n"
                "    { position = 1.0, semitones = -2.0 },\n"
                "  ] },\n"
                "  { label = \"mi\", forms = { ipa = \"mi\", "
                "arpabet = \"M IY0\" } },\n"
                "]\n",
                encoding="utf-8",
            )
            lexicon = load_pronunciation_lexicon(config, repository_root=root)
            selected = lexicon.select(("ipa", "respelling"), language="en")
            self.assertEqual(selected[0].system, "ipa")
            self.assertEqual(
                tuple(
                    point.semitones
                    for point in selected[0].prosody.units[0].pitch_contour
                ),
                (-3.0, 3.0, -1.0),
            )
            self.assertEqual(selected[0].prosody.unit_kind, "syllable")
            self.assertEqual(selected[0].prosody.interpolation, "smooth")
            self.assertEqual(
                selected[0].prosody.units[1].for_system("arpabet"),
                "N AA0",
            )
            self.assertEqual(selected[0].prosody.units[1].duration_scale, 1.2)
            self.assertEqual(selected[0].prosody.duration_scale, 1.1)

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

    def test_unit_f0_contour_requires_explicit_onset_and_offset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "pronunciations.toml"
            config.write_text(
                "schema_version = 2\n"
                "[proper_nouns.Ami.forms]\n"
                'ipa = "ˈeɪ.mi"\n'
                "[proper_nouns.Ami.prosody]\n"
                "units = [{ label = \"ay\", forms = { ipa = \"eɪ\" }, "
                "pitch_contour = ["
                "{ position = 0.5, semitones = 2.0 }, "
                "{ position = 1.0, semitones = 0.0 }] }]\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_pronunciation_lexicon(config, repository_root=root)


if __name__ == "__main__":
    unittest.main()
