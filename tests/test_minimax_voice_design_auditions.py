"""Offline checks for the audition runner; no credentials or paid calls."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

SPEC = importlib.util.spec_from_file_location(
    "minimax_auditions", Path(__file__).resolve().parents[1] / "scripts/run_minimax_voice_design_auditions.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class AuditionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan = self.root / "plan.json"
        self.data = {
            "endpoint": "https://api.minimaxi.com/v1/voice_design",
            "identity_brief": "An original voice.", "preview_direction": "Speak naturally.",
            "lines": [{"text": "Hello there."}],
            "candidates": [{"id": "01-test", "voice_description": "Light and clear."}],
        }
        self.addCleanup(patch.stopall)
        self.network = patch.object(runner.urllib.request, "urlopen").start()
        self.network.side_effect = AssertionError("Unexpected external call")
        patch.dict(runner.os.environ, {"MINIMAX_API_KEY": "test-not-a-real-credential"}).start()
        self.convert = patch.object(runner.subprocess, "run").start()

    def run_plan(self, *extra):
        runner.save_json(self.plan, self.data)
        with patch.object(sys, "argv", ["auditions", "--plan", str(self.plan), *extra]), contextlib.redirect_stdout(io.StringIO()):
            return runner.main()

    def test_dry_run_has_no_external_or_conversion_calls(self):
        self.assertEqual(self.run_plan("--dry-run"), 0)
        self.network.assert_not_called()
        self.convert.assert_not_called()

    def test_rejects_oversized_preview(self):
        self.data["lines"] = [{"text": "a" * 501}]
        with self.assertRaisesRegex(ValueError, "1..500"):
            self.run_plan("--dry-run")

    def test_rejects_oversized_prompt(self):
        self.data["identity_brief"] = "a" * 2001
        with self.assertRaisesRegex(ValueError, "2000"):
            self.run_plan("--dry-run")

    def test_rejects_untrusted_endpoint(self):
        self.data["endpoint"] = "https://example.invalid/voice_design"
        with self.assertRaisesRegex(ValueError, "official"):
            self.run_plan("--dry-run")

    def test_rejects_unsafe_candidate_path(self):
        self.data["candidates"][0]["id"] = "../escape"
        with self.assertRaisesRegex(ValueError, "safe"):
            self.run_plan("--dry-run")

    def test_rejects_changed_cached_request(self):
        directory = self.root / "01-test"
        directory.mkdir()
        runner.save_json(directory / "request.json", {"prompt": "old"})
        with self.assertRaisesRegex(ValueError, "Changed request"):
            self.run_plan()
        self.network.assert_not_called()

    def test_reuses_cached_response_without_regeneration(self):
        directory = self.root / "01-test"
        directory.mkdir()
        runner.save_json(directory / "request.json", {
            "prompt": "An original voice.\n\nLight and clear.\n\nSpeak naturally.",
            "preview_text": "Hello there.",
        })
        runner.save_json(directory / "response.json", {"voice_id": "fake-id", "trial_audio": "00"})
        with wave.open(str(directory / "preview.wav"), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\x01\x00" * 2400)
        self.assertEqual(self.run_plan(), 0)
        self.network.assert_not_called()
        metadata = json.loads((directory / "audio-metadata.json").read_text())
        self.assertEqual(metadata["duration_seconds"], 0.1)


if __name__ == "__main__":
    unittest.main()
