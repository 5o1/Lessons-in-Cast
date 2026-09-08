"""CPU-only contracts for local H3 prompt compilation and queued audio jobs."""

from dataclasses import replace
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from lessons_in_cast_core.emotions import EMOTION_LABELS
from lessons_in_cast_core.performance import PerformanceCue, PerformanceCueKind, SpeechPerformance, VocalMode
from lessons_in_cast_core.speech_markup import SpeechSegment
from lessons_in_cast_core.synthesis.backends.minimax_h3.client import ComfyClient
from lessons_in_cast_core.synthesis.backends.minimax_h3.config import COMPONENTS, MODEL_REPOSITORY, MODEL_REVISION, MiniMaxH3Config, validate_endpoint
from lessons_in_cast_core.synthesis.backends.minimax_h3.prompt import compile_prompt
from lessons_in_cast_core.synthesis.backends.minimax_h3.workflow import build_workflow
from lessons_in_cast_core.synthesis.types import TtsJob


class H3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "default.wav"
        self.reference.write_bytes(b"reference")
        self.config = MiniMaxH3Config("h3")
        self.job = TtsJob("test", "line", "a", "Are you okay?", "neutral", {}, "take.wav", "key")

    def compile(self, job=None):
        return compile_prompt(job or self.job, self.config, self.reference, EMOTION_LABELS)

    def test_plain_dialogue_is_not_changed(self):
        result = self.compile()
        self.assertEqual(result.text, self.job.text)
        prompt = result.parameters["prompt"]
        self.assertIn("<d>[English]Are you okay?</d>", prompt)
        self.assertEqual(prompt.count("<d>"), 1)
        self.assertIn("<Audio 1>: reference", prompt)
        self.assertNotIn("fully_copy", prompt)
        self.assertIn("non_diegetic_music:\nNone.", prompt)
        self.assertTrue(all(f.fidelity.value == "approximated" for f in result.features))

    def test_downloader_and_runtime_share_exact_pins(self):
        downloader = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/download_minimax_h3.py"))
        self.assertEqual(downloader["FILES"], COMPONENTS)
        self.assertEqual(downloader["REPOSITORY"], MODEL_REPOSITORY)
        self.assertEqual(downloader["REVISION"], MODEL_REVISION)

    def test_empty_dialogue_rejected_and_unmarked_defaults_to_neutral(self):
        with self.assertRaises(ValueError):
            self.compile(replace(self.job, text=" \t"))
        self.assertIn(EMOTION_LABELS["neutral"][0], self.compile(replace(self.job, emotion=None)).parameters["prompt"])

    def test_inline_transition_remains_one_take(self):
        job = replace(self.job, text="Wait. No!", emotion=None, segments=(
            SpeechSegment("Wait. ", emotion="restrained_grief"),
            SpeechSegment("No!", None, arbitrary_emotion="A terrified scream breaking into sobs.")))
        prompt = self.compile(job).parameters["prompt"]
        self.assertIn(EMOTION_LABELS["restrained_grief"][0], prompt)
        self.assertIn("A terrified scream breaking into sobs.", prompt)
        self.assertEqual(prompt.count("<d>"), 2)
        self.assertLess(prompt.index("Wait."), prompt.index("No!"))

    def test_unknown_emotion_and_malformed_dialogue_rejected(self):
        for job in (replace(self.job, emotion="not_known"), replace(self.job, text="<d>bad</d>"),
                    replace(self.job, segments=(SpeechSegment("Missing text", "neutral"),))):
            with self.subTest(job=job), self.assertRaises(ValueError):
                self.compile(job)

    def test_voice_tags_select_reference_files(self):
        variant = self.root / "crying.flac"
        variant.write_bytes(b"cry")
        job = replace(self.job, text="One. Two.", emotion=None, segments=(
            SpeechSegment("One. ", "neutral"), SpeechSegment("Two.", "neutral", voice="crying")))
        result = self.compile(job)
        self.assertEqual(result.parameters["references"], [str(self.reference), str(variant)])
        self.assertIn("<Audio 2>", result.parameters["prompt"])
        with self.assertRaises(ValueError):
            self.compile(replace(self.job, voice="missing"))

    def test_reference_count_limit(self):
        for i in range(4):
            (self.root / f"voice{i}.wav").write_bytes(b"ref")
        job = replace(self.job, text="0123", emotion=None,
                      segments=tuple(SpeechSegment(str(i), "neutral", voice=f"voice{i}") for i in range(4)))
        with self.assertRaisesRegex(ValueError, "at most three"):
            self.compile(job)

    def test_native_workflow_only_decodes_audio(self):
        graph = build_workflow(self.compile(), ["ref.wav"], output_prefix="lic/test")
        inputs = graph["136"]["inputs"]
        self.assertEqual((inputs["width"], inputs["height"]), (32, 32))
        self.assertEqual(inputs["ref_audios.ref_audio_0"], ["200", 0])
        self.assertEqual(graph["121"]["class_type"], "VAEDecodeAudio")
        self.assertEqual(graph["92"]["class_type"], "SaveAudio")
        self.assertFalse(any(n["class_type"] in {"VAEDecode", "CreateVideo", "SaveVideo"} for n in graph.values()))

    def test_native_frame_alignment_and_numeric_validation(self):
        for seconds in (4, 5, 10, 14.9, 15):
            config = replace(self.config, duration_seconds=seconds)
            self.assertEqual(config.frame_count % 17, 5)
            self.assertLessEqual(config.frame_count / 24, 15)
        for settings in ({"steps": True}, {"seed": -1}, {"duration_seconds": float("nan")},
                         {"base_speed": 0}, {"timeout_seconds": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                replace(self.config, **settings)

    def test_loopback_only_and_proxy_bypass(self):
        for url in ("https://api.minimax.io", "http://0.0.0.0:8196", "http://localhost", "http://u:p@localhost:8196"):
            with self.assertRaises(ValueError):
                validate_endpoint(url)
        client = ComfyClient("http://127.0.0.1:8196")
        self.assertFalse(any(type(handler).__name__ == "ProxyHandler" for handler in client.opener.handlers))

    def test_performance_compiles_without_spoken_instructions(self):
        performance = SpeechPerformance(vocal_mode=VocalMode.WHISPER, speed=.9, pitch_semitones=1,
            cues=(PerformanceCue(PerformanceCueKind.PAUSE, 3, duration_seconds=.4),))
        result = self.compile(replace(self.job, performance=performance))
        self.assertIn("Vocal mode: whisper", result.parameters["prompt"])
        self.assertIn("for 0.4 seconds", result.parameters["prompt"])
        self.assertEqual(result.text, self.job.text)

    def test_success_caches_native_and_does_not_resubmit(self):
        client = ComfyClient(self.config.endpoint)
        cache = self.root / "cache"
        calls = []
        def request(path, data=None, **kwargs):
            calls.append(path)
            state = json.loads((cache / "request.json").read_text())
            prompt_id = state["prompt_id"]
            if path == "/prompt":
                self.assertEqual(data["prompt_id"], prompt_id)
                return {"prompt_id": prompt_id}
            if path.startswith("/history/"):
                return {prompt_id: {"status": {"completed": True}, "outputs": {
                    "92": {"audio": [{"filename": "take.flac", "subfolder": "lic", "type": "output"}]}}}}
            if path.startswith("/view?"):
                return b"fLaCtest"
            self.fail(path)
        with patch.object(client, "request", side_effect=request):
            result = client.execute({"graph": 1}, cache, identity="test", timeout_seconds=10)
            self.assertEqual(result.read_bytes(), b"fLaCtest")
            client.execute({"graph": 1}, cache, identity="test", timeout_seconds=10)
            self.assertEqual(calls.count("/prompt"), 1)
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                client.execute({"graph": 2}, cache, identity="test", timeout_seconds=10)
            result.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "modified"):
                client.execute({"graph": 1}, cache, identity="test", timeout_seconds=10)

    def test_lost_submission_is_not_automatically_retried(self):
        client = ComfyClient(self.config.endpoint)
        cache = self.root / "lost"
        with patch.object(client, "request", side_effect=TimeoutError), patch(
                "lessons_in_cast_core.synthesis.backends.minimax_h3.client.time.sleep"):
            with self.assertRaises(TimeoutError):
                client.execute({}, cache, identity="test", timeout_seconds=0)
        with patch.object(client, "request") as request:
            with self.assertRaises(TimeoutError):
                client.execute({}, cache, identity="test", timeout_seconds=0)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
