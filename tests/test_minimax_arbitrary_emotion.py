"""Auditable description fallbacks without changing core polish annotations."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from lessons_in_cast_core.config import AudioConfig
from lessons_in_cast_core.performance import SpeechPerformance
from lessons_in_cast_core.speech_markup import SpeechSegment
from lessons_in_cast_core.synthesis.backends.minimax import MiniMaxSpeechHttpSynthesizer
from lessons_in_cast_core.synthesis.backends.minimax.config import load_minimax_pipeline_config
from lessons_in_cast_core.synthesis.backends.minimax.emotion_lowering import validate_rules
from lessons_in_cast_core.synthesis.types import TtsJob
from .test_minimax_speech import _Opener, _Response, _wav_bytes


class MiniMaxArbitraryEmotionTests(unittest.TestCase):
    rules = {
        "Holding back fear.": {"emotion": "calm", "energy": -0.4},
        "An explosive outburst.": {"emotion": "angry", "energy": 0.9, "vocal_mode": "shout"},
    }

    def backend(self, **kwargs):
        return MiniMaxSpeechHttpSynthesizer(model="speech-2.8-hd", voice_id="test-voice",
            audio_config=AudioConfig(sample_rate=44100), arbitrary_emotions=self.rules, **kwargs)

    def job(self, **kwargs):
        job = TtsJob("test", "line", "a", "Stop!", None, {}, "test.wav", "cache",
                     arbitrary_emotion="An explosive outburst.")
        return replace(job, **kwargs)

    def test_description_stays_out_of_spoken_text_and_payload(self):
        backend = self.backend()
        job = self.job()
        result = backend.adapt(job)
        self.assertEqual(result.text, job.text)
        self.assertEqual(result.emotion, "angry")
        self.assertEqual(result.parameters["voice_modify"]["intensity"], -90)
        self.assertEqual(result.parameters["voice_setting"]["vol"], 1.25)
        self.assertEqual(result.features[0].fidelity, "approximated")
        self.assertIn(job.arbitrary_emotion, result.features[0].strategy)
        self.assertNotIn(job.arbitrary_emotion, json.dumps(backend.build_payload(job)))
        self.assertIsNone(job.emotion)
        self.assertEqual(job.performance, SpeechPerformance())

    def test_unknown_description_is_not_silently_neutral(self):
        with self.assertRaisesRegex(ValueError, "no explicit"):
            self.backend().adapt(self.job(arbitrary_emotion="An unseen direction."))

    def test_rules_are_fingerprinted_and_copied(self):
        backend = self.backend()
        config = backend.configuration
        config["arbitrary_emotions"]["An explosive outburst."]["energy"] = 0
        self.assertEqual(backend.configuration["arbitrary_emotions"], self.rules)

    def test_explicit_core_performance_takes_precedence(self):
        result = self.backend().adapt(self.job(arbitrary_emotion="Holding back fear.",
            performance=SpeechPerformance(energy=0.2)))
        self.assertEqual(result.parameters["voice_modify"]["intensity"], -20)

    def test_invalid_rules_fail_before_network(self):
        for invalid in [{"emotion": "unknown"}, {"emotion": "sad", "energy": float("nan")},
                        {"emotion": "sad", "energy": True}, {"emotion": "sad", "energy": 2},
                        {"emotion": "sad", "prompt": "Do not read this"}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_rules({"Description": invalid})

    def test_segment_render_keeps_both_controls_and_source_text(self):
        opener = _Opener({"data": {"audio": _wav_bytes().hex()},
                          "base_resp": {"status_code": 0}})
        backend = self.backend(opener=opener, api_key="test-secret")
        job = self.job(text="Please. Stop!", arbitrary_emotion=None,
            segments=(SpeechSegment("Please. ", None, arbitrary_emotion="Holding back fear."),
                      SpeechSegment("Stop!", None, arbitrary_emotion="An explosive outburst.")))
        with tempfile.TemporaryDirectory() as directory:
            result = backend.synthesize(job, Path(directory))
            self.assertTrue(result.is_file())
            self.assertEqual(len(opener.requests), 2)
            payloads = [json.loads(request.data) for request, _timeout in opener.requests]
            self.assertEqual([p["voice_setting"]["emotion"] for p in payloads], ["calm", "angry"])
            self.assertEqual("".join(p["text"] for p in payloads), job.text)

    def test_audition_profile_loads_all_six_explicit_descriptions(self):
        root = Path(__file__).resolve().parents[1]
        config = load_minimax_pipeline_config(root / "profiles/a_minimax_emotion_audition/config.toml", repository_root=root)
        self.assertEqual(len(config.arbitrary_emotions), 6)
        self.assertEqual(config.maximum_retries, 0)

    def test_conversion_retry_reuses_provider_audio_without_a_second_post(self):
        opener = _Opener({"data": {"audio": _wav_bytes().hex()},
                          "base_resp": {"status_code": 0}})
        backend = self.backend(opener=opener, api_key="test-secret")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(backend, "_normalize_wav", side_effect=FileNotFoundError("ffmpeg")):
                with self.assertRaises(FileNotFoundError):
                    backend.synthesize(self.job(), root)
            self.assertFalse((root / "test.wav").exists())
            self.assertEqual((root / "test.minimax/source.wav").read_bytes(), _wav_bytes())
            self.assertNotIn("test-secret", (root / "test.minimax/response.json").read_text())
            output = backend.synthesize(self.job(), root)
            self.assertEqual(output.read_bytes(), _wav_bytes())
            self.assertEqual(len(opener.requests), 1)

    def test_changed_payload_cannot_reuse_provider_audio(self):
        opener = _Opener({"data": {"audio": _wav_bytes().hex()},
                          "base_resp": {"status_code": 0}})
        backend = self.backend(opener=opener, api_key="test-secret")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(backend, "_normalize_wav", side_effect=FileNotFoundError("ffmpeg")):
                with self.assertRaises(FileNotFoundError):
                    backend.synthesize(self.job(), root)
            with self.assertRaisesRegex(ValueError, "cache inputs changed"):
                backend.synthesize(self.job(text="A different line."), root)
            self.assertEqual(len(opener.requests), 1)

    def test_provider_errors_are_saved_but_not_reused_as_successful_audio(self):
        opener = _Opener({"base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}})
        backend = self.backend(opener=opener, api_key="test-secret")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "1008"):
                backend.synthesize(self.job(), root)
            self.assertTrue((root / "test.minimax/error.json").is_file())
            self.assertFalse((root / "test.minimax/response.json").exists())
            opener.value = {"data": {"audio": _wav_bytes().hex()}, "base_resp": {"status_code": 0}}
            backend.synthesize(self.job(), root)
            self.assertEqual(len(opener.requests), 2)


class MiniMaxCloneCacheTests(unittest.TestCase):
    def runner(self):
        path = Path(__file__).resolve().parents[1] / "scripts/run_minimax_reference_audition.py"
        spec = importlib.util.spec_from_file_location("minimax_reference_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cached_posts_do_not_repeat_upload_or_clone(self):
        module = self.runner()
        request = urllib.request.Request("https://api.minimaxi.com/v1/voice_clone", data=b"{}")
        response = {"base_resp": {"status_code": 0}, "file": {"file_id": 123}}
        with tempfile.TemporaryDirectory() as directory, patch.object(module.urllib.request, "urlopen", return_value=_Response(response)) as opener:
            for _ in range(2):
                self.assertEqual(module.cached_post(Path(directory), "clone", {"voice_id": "test"}, request, "secret"), response)
            opener.assert_called_once()
            with self.assertRaisesRegex(ValueError, "Changed"):
                module.cached_post(Path(directory), "clone", {"voice_id": "different"}, request, "secret")

    def test_uncertain_post_is_not_automatically_repeated_and_key_is_redacted(self):
        module = self.runner()
        request = urllib.request.Request("https://api.minimaxi.com/v1/voice_clone", data=b"{}")
        with tempfile.TemporaryDirectory() as directory, patch.object(module.urllib.request, "urlopen", side_effect=OSError("secret")) as opener:
            with self.assertRaises(OSError):
                module.cached_post(Path(directory), "clone", {}, request, "secret")
            self.assertNotIn("secret", (Path(directory) / "clone.error.json").read_text())
            with self.assertRaisesRegex(RuntimeError, "Uncertain"):
                module.cached_post(Path(directory), "clone", {}, request, "secret")
            opener.assert_called_once()
