"""Offline PCM checks for the two-generation reference audition script."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("synthetic_reference_auditions", SCRIPTS / "run_synthetic_reference_auditions.py")
runner = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPTS), *sys.path]):
    SPEC.loader.exec_module(runner)


class SyntheticReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def audio(self, name, rate=24000, frames=24000, channels=1):
        path = self.root / name
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(b"\x01\x00" * frames * channels)
        return path

    def test_duration_matching_uses_source_sample_rate(self):
        source = self.audio("source.wav", frames=48000)
        output = self.root / "cropped.wav"
        runner.crop_reference(source, output, 1.5)
        self.assertEqual(runner.audio_info(output)["frames"], 36000)
        self.assertEqual(runner.audio_info(source)["frames"], 48000)

    def test_crop_does_not_pad_short_source(self):
        source = self.audio("source.wav")
        output = self.root / "cropped.wav"
        runner.crop_reference(source, output, 15)
        self.assertEqual(runner.audio_info(output)["seconds"], 1)

    def test_montage_keeps_pcm_with_explicit_gap(self):
        first = self.audio("first.wav")
        second = self.audio("second.wav")
        output = self.root / "montage.wav"
        runner.montage([first, second], output)
        self.assertEqual(runner.audio_info(output)["frames"], 64800)

    def test_montage_rejects_mixed_sample_rates(self):
        first = self.audio("first.wav")
        second = self.audio("second.wav", rate=48000)
        with self.assertRaisesRegex(ValueError, "share"):
            runner.montage([first, second], self.root / "montage.wav")

    def test_audio_check_rejects_empty_or_stereo(self):
        for path in [self.audio("empty.wav", frames=0), self.audio("stereo.wav", channels=2)]:
            with self.assertRaisesRegex(ValueError, "nonempty mono"):
                runner.audio_info(path)


if __name__ == "__main__":
    unittest.main()
