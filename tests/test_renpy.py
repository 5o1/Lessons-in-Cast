from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast.annotation import DialogueAction
from lessons_in_cast.renpy import (
    DialogueExtractionRequest,
    RenPyVoiceInstaller,
    RenPyVoiceManifestWriter,
    SubprocessDialogueExtractor,
)
from lessons_in_cast.synthesis import AudioQualityResult, RenderTask


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
            destination = root / "build" / "dialogue.tab"
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
                entries=[("line_123", "voice/chapter1/main/line_123.wav")],
            )
            self.assertIn(
                '"line_123": "voice/chapter1/main/line_123.wav"',
                destination.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "config.auto_voice = _lessons_in_cast_auto_voice",
                destination.read_text(encoding="utf-8"),
            )

    def test_installer_mirrors_source_path_and_removes_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            source = artifacts / "voice" / "line_123.wav"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"audio")
            script = artifacts / "lessons_in_cast_voice.rpy"
            manifest = artifacts / "voice_manifest.json"
            script.write_text("init python:\n    pass\n", encoding="utf-8")
            manifest.write_text("{}\n", encoding="utf-8")
            task = RenderTask(
                dialogue_id="dialogue-1",
                identifier="line_123",
                action=DialogueAction.SPEAK,
                component_job_ids=("job-1",),
                render_mode="single",
                effects=(),
                output_path="voice/line_123.wav",
                virtual_path="voice/chapter1/main/line_123.wav",
            )
            quality = AudioQualityResult(
                dialogue_id="dialogue-1",
                path=str(source),
                valid=True,
                duration_seconds=1.0,
                issues=(),
            )
            stale = root / "release" / "game" / "voice" / "stale.wav"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"stale")

            result = RenPyVoiceInstaller().install(
                root / "release",
                artifact_root=artifacts,
                voice_script=script,
                voice_manifest=manifest,
                artifacts=[(task, quality)],
            )

            self.assertEqual(result.audio_count, 1)
            self.assertEqual(
                (result.game_root / task.virtual_path).read_bytes(),
                b"audio",
            )
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
