from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast.renpy import (
    DialogueExtractionRequest,
    RenPyVoiceManifestWriter,
    SubprocessDialogueExtractor,
)


class RenPyTests(unittest.TestCase):
    def test_subprocess_extractor_passes_release_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            release.mkdir()
            launcher = release / "game.sh"
            launcher.write_text(
                "#!/bin/sh\n"
                'test "$2" = "dialogue" || exit 7\n'
                'test "$3" = "None" || exit 8\n'
                'printf "Identifier\\tCharacter\\tDialogue\\tFilename\\tLine Number'
                '\\tRenPy Script\\n" > "$1/dialogue.tab"\n',
                encoding="utf-8",
            )
            launcher.chmod(launcher.stat().st_mode | 0o111)
            destination = root / "artifacts" / "dialogue.tab"
            result = SubprocessDialogueExtractor().extract(
                DialogueExtractionRequest(
                    release_path=release,
                    output_path=destination,
                    launcher_path=launcher,
                )
            )
            self.assertEqual(result.dialogue_path, destination)
            self.assertEqual(result.command[1], str(release.resolve()))
            self.assertTrue(destination.is_file())

    def test_auto_voice_script_uses_dialogue_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "voice.rpy"
            RenPyVoiceManifestWriter().write_auto_voice_script(
                destination,
                audio_format="wav",
            )
            self.assertIn(
                'config.auto_voice = "voice/{id}.wav"',
                destination.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
