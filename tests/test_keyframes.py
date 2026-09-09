"""Executable checks for symbolic anchors, measured alignment and PCM rendering."""

from array import array
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import wave

from lessons_in_cast_core.config import AudioConfig
from lessons_in_cast_core.keyframes import KeyframeProcessor, compile_keyframes, extract_anchors
from lessons_in_cast_core.keyframes.mfa import boundary_times, read_intervals
from lessons_in_cast_core.pronunciations import load_pronunciation_lexicon
from lessons_in_cast_core.synthesis import SynthesisPlanner, WaveRenderer
from .helpers import accepted_annotation, record
from .test_synthesis import character


def curve(*points, interpolation="linear"):
    return [{"type": "gain_envelope", "interpolation": interpolation,
             "keyframes": [{"anchor": identity, "gain": gain} for identity, gain in points]}]


class KeyframeTests(unittest.TestCase):
    def test_compile_and_reject_invalid_references(self):
        effects = curve(("1", 0), ("2", 0), ("3", 1))
        program = compile_keyframes("{1}Sen{2}sei?{3}", effects)
        self.assertEqual(program["text"], "Sensei?")
        self.assertEqual(program["anchors"], {"1": 0, "2": 3, "3": 7})
        self.assertEqual(extract_anchors("é{1}{{2}}"), ("é{2}", {"1": 1}))
        for text, curves in [
            ("{1}a{1}", curve(("1", 0), ("2", 1))),
            ("{01}a{2}", curve(("01", 0), ("2", 1))),
            ("{1}{2}a", curve(("1", 0), ("2", 1))),
            ("{1}a{2}", curve(("2", 0), ("1", 1))),
            ("{1}a{2}", curve(("1", True), ("2", 1))),
            ("{1}a{2}", curve(("1", float("nan")), ("2", 1))),
            ("{1}a{2}", []),
            ("{1}a", curve(("1", 0), ("2", 1))),
        ]:
            with self.subTest(text=text, curves=curves), self.assertRaises(ValueError):
                compile_keyframes(text, curves)

    def test_dry_jobs_exclude_markers_and_curves(self):
        item = record(1, character="a", dialogue="Sensei?")
        validated = accepted_annotation(item)
        annotation = replace(validated.annotation, emotion=None,
            spoken_text='<emotion name="calm">{1}Sen{2}sei?{3}</emotion>',
            keyframe_effects=curve(("1", 0), ("2", 0), ("3", 1)))
        planner = SynthesisPlanner({"a": character("a")})
        first = planner.plan({item.id: item}, [replace(validated, annotation=annotation)])
        changed = replace(annotation, keyframe_effects=curve(("1", .1), ("2", .2), ("3", 1)))
        second = planner.plan({item.id: item}, [replace(validated, annotation=changed)])
        self.assertEqual(first.jobs[0].text, "Sensei?")
        self.assertEqual(first.jobs[0].segments[0].text, "Sensei?")
        self.assertEqual(first.jobs[0].cache_key, second.jobs[0].cache_key)
        self.assertNotEqual(first.render_tasks[0].keyframe_program, second.render_tasks[0].keyframe_program)

    def test_render_resolves_and_caches_alignment_and_preserves_dry_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dry.wav"
            with wave.open(str(source), "wb") as stream:
                stream.setparams((1, 2, 1000, 1000, "NONE", "not compressed"))
                stream.writeframes(array("h", [10000] * 1000).tobytes())
            dry = source.read_bytes()
            processor = KeyframeProcessor(command=["test-aligner"], revision="fixture-1")
            program = compile_keyframes("{1}Sen{2}sei?{3}", curve(("1", 0), ("2", 0), ("3", 1)))
            def aligned(*args, **kwargs):
                request = json.loads(kwargs["input"])
                return SimpleNamespace(returncode=0, stdout=json.dumps({
                    "version": 1, "audio_sha256": request["audio_sha256"], "text": request["text"],
                    "boundaries": [{"offset": 3, "time": .5, "confidence": .95, "source": "phone_alignment"}],
                }))
            with patch("lessons_in_cast_core.keyframes.renderer.subprocess.run", side_effect=aligned) as process:
                for name in ("one", "two"):
                    processor.process(source, root / f"{name}.wav", program, cache_root=root / "cache", trace_path=root / f"{name}.json")
                self.assertEqual(process.call_count, 1)
            self.assertEqual(source.read_bytes(), dry)
            with wave.open(str(root / "one.wav"), "rb") as stream:
                samples = array("h", stream.readframes(1000))
            self.assertEqual(samples[499], 0)
            self.assertEqual(samples[750], 5000)
            self.assertGreater(samples[-1], 9900)
            with self.assertRaisesRegex(ValueError, "configured"):
                KeyframeProcessor().process(source, root / "no.wav", program, cache_root=root / "none", trace_path=root / "no.json")
            cached = next((root / "cache").glob("*.json"))
            data = json.loads(cached.read_text())
            data["response"]["boundaries"][0]["confidence"] = .1
            cached.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "confidence"):
                processor.process(source, root / "bad.wav", program, cache_root=root / "cache", trace_path=root / "bad.json")
            endpoint_program = compile_keyframes("{1}Sensei?{2}", curve(("1", 0), ("2", 1), interpolation="smooth"))
            KeyframeProcessor().process(source, root / "endpoints.wav", endpoint_program, cache_root=root / "unused", trace_path=root / "endpoints.json")
            self.assertFalse((root / "unused").exists())
            item = record(1, character="a", dialogue="Sensei?")
            accepted = accepted_annotation(item)
            annotation = replace(accepted.annotation, emotion=None,
                spoken_text='<emotion name="calm">{1}Sensei?{2}</emotion>',
                keyframe_effects=curve(("1", 0), ("2", 1)))
            plan = SynthesisPlanner({"a": character("a")}, audio_config=AudioConfig(format="wav")).plan(
                {item.id: item}, [replace(accepted, annotation=annotation)])
            job = replace(plan.jobs[0], output_path="dry.wav")
            output = WaveRenderer(keyframe_processor=KeyframeProcessor()).render(plan.render_tasks[0], {job.id: job}, root)
            self.assertNotEqual(output.read_bytes(), dry)
            self.assertEqual(source.read_bytes(), dry)

    def test_mfa_maps_explicit_phone_units_not_character_proportions(self):
        lexicon = load_pronunciation_lexicon(repository_root=Path(__file__).resolve().parents[1])
        words = [(.1, .9, "sensei")]
        phones = [(.1, .2, "S"), (.2, .3, "EH"), (.3, .4, "N"), (.4, .5, "S"), (.5, .9, "EY")]
        result = boundary_times("Sensei?", [3, 4, 6], words, phones, lexicon)
        self.assertEqual([x["time"] for x in result], [.4, .5, .9])
        self.assertTrue(all(x["confidence"] is None for x in result))
        with self.assertRaisesRegex(ValueError, "No measured"):
            boundary_times("Sensei?", [5], words, phones, lexicon)
        with self.assertRaisesRegex(ValueError, "phones differ"):
            boundary_times("Sensei?", [3], words, phones[:-1], lexicon)
        textgrid = 'item [1]:\n name = "words"\n intervals [1]:\n xmin = 0.1\n xmax = 0.9\n text = "sensei"\n'
        self.assertEqual(read_intervals(textgrid, "words"), words)


if __name__ == "__main__":
    unittest.main()
