from __future__ import annotations

import tempfile
import re
import tomllib
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
        entries = lexicon.for_system("arpabet")
        self.assertEqual(
            {name: entries[name] for name in ("Ami", "Ayane", "Chinami", "Maya")},
            {
                "Ami": "EY1 . M IY0",
                "Ayane": "AA0 . Y AA1 . N EH0",
                "Chinami": "CH IY1 . N AA0 . M IY0",
                "Maya": "M AY1 . Y AH0",
            },
        )

    def test_registered_personal_names_have_explicit_pronunciations(self):
        entries = load_pronunciation_lexicon(repository_root=self.root).for_system("arpabet")
        characters = tomllib.loads((self.root / "configs/characters.toml").read_text())["characters"]
        # Human-selected name-bearing speakers; descriptive labels are not names.
        ids = "a ai ale ales alexa amy arj barb ben c catherine ch chi chinko eve girl1 gregg h hi i ima iss jimmy john k ka kanon kas ken kenji ker ki kok m mak maki mal masa matt me mi mil miu mo mod moyo n na ni no o oli onu os pat r ri robbie s sa saki salvykun sar se shi t tb tbiso tk to tsurumi u w wil will yo yom yu yuu".split()
        for character_id in ids:
            name = characters[character_id]["name"].split(",")[0]
            for component in name.split():
                with self.subTest(character=character_id, component=component):
                    self.assertIn(component, entries)
        decorated = {
            "amb": "Amber", "beatrice": "Beatrice", "connor": "Connor",
            "fff": "Frank", "fff2": "Tony", "flo": "Laura", "gi": "Giuseppe",
            "ginro": "Ginro", "hailey": "Hailey", "hank": "Hank", "hid": "Hidari",
            "howard": "Howard", "lamar": "Lamar", "legitmom": "Mary", "mag": "Manny",
            "manny": "Manny", "mig": "Migi", "mrb": "Blake", "octavia": "Octavia",
            "paul": "Paul", "peggy": "Pegasus", "sato": "Sato", "seinfeld": "Seinfeld",
            "steve": "Steve", "taki": "Taki", "tenc": "Tenchou", "tod": "Todd", "tom": "Mato",
        }
        for character_id, term in decorated.items():
            with self.subTest(character=character_id):
                self.assertIn(term, characters[character_id]["name"])
                self.assertIn(term, entries)
        for character in characters.values():
            for member in character.get("members", []):
                self.assertIn(characters[member]["name"], entries)

    def test_all_configured_arpabet_tokens_and_fallbacks_are_explicit(self):
        lexicon = load_pronunciation_lexicon(repository_root=self.root)
        consonants = set("B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split())
        for entry in lexicon.entries:
            arpa = entry.for_system("arpabet")
            with self.subTest(name=entry.term):
                self.assertTrue(arpa)
                self.assertTrue(entry.for_system("respelling"))
                for token in arpa.split():
                    self.assertTrue(token == "." or token in consonants or re.fullmatch(r"(?:AA|AE|AH|AO|AW|AY|EH|ER|EY|IH|IY|OW|OY|UH|UW)[012]", token), token)

    def test_index_name_matching_respects_boundaries_case_and_existing_markup(self):
        from lessons_in_cast_core.synthesis.backends.index_tts.adapter import apply_index_pronunciations
        lexicon = load_pronunciation_lexicon(repository_root=self.root)
        def apply(text):
            return apply_index_pronunciations(text, lexicon.for_system("arpabet"), lexicon.select(("arpabet",), language="en"))
        text = "Sensei! sensei? Kumon-mi, Ami's Karins. hope HOPE. sensory."
        result = apply(text)
        self.assertIn("<Sensei|S EH1 N . S EY0>!", result)
        self.assertIn("<sensei|S EH1 N . S EY0>?", result)
        self.assertIn("<Kumon-mi|K UW0 . M OW1 N . M IY0>", result)
        self.assertIn("<Ami|EY1 . M IY0>'s", result)
        self.assertIn("hope <HOPE|HH OW1 P>", result)
        self.assertIn("sensory.", result)
        self.assertEqual(apply(result), result)

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
