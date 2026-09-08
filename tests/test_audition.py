"""Casting project, immutable take cache, and profile capability tests."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from lessons_in_cast_core.audition.types import load_project
from lessons_in_cast_core.audition.rendering import render_project
from lessons_in_cast_core.audition.collection import collect_contexts
from lessons_in_cast_core.audition.cli import main
from lessons_in_cast_core.audition.cleaning import prepare_cleaning, validate_cleaning, workflow
from lessons_in_cast_core.annotation import Annotation, ValidatedAnnotation, ValidationStatus, DialogueAction
from lessons_in_cast_core.performance import SpeechPerformance
from lessons_in_cast_core.annotation.codex import CodexWorkspace
from lessons_in_cast_core.workflow.artifacts import ArtifactLayout
from lessons_in_cast_core.characters import CharacterDefinition
from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.dialogue.types import DialogueRecord
from lessons_in_cast_core.synthesis.profiles import VoicePipeline

ROOT = Path(__file__).resolve().parents[1]


def write_wave(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\1\0" * 2400)


class FakeProfile(VoicePipeline):
    pipeline_id = "test"
    character_id = "a"

    def __init__(self, reference):
        self.reference = reference
        self.jobs = []
        self.closed = False

    @property
    def configuration(self):
        return {"reference": str(self.reference)}

    def override_reference_audio(self, path):
        if not path.is_file():
            raise FileNotFoundError(path)
        self.reference = path

    def prepare(self):
        return (self.reference,)

    def render(self, job, artifact_root):
        self.jobs.append(job)
        path = Path(job.output_path)
        write_wave(path)
        return path

    def close(self):
        self.closed = True


class AuditionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "project.json"
        self.source = DialogueRecord("source", 1, "label_1", "a", "Hello.", "game/test.rpy", 2, 'a "[what]"', "label", "room")
        self.data = {"version": 2, "id": "ami", "character": "a", "brief": "One consistent youthful voice.",
            "coverage": {"status": "partial", "notes": "A selected test side, not all story states."},
            "cases": [{"id": "hello", "title": "Hello", "state": "everyday", "background": "They meet.",
                "addressee": "Friend", "intention": "Greet them.",
                "direction": "Light and natural.", "listen_for": ["Ease"], "avoid": ["Shouting"], "source": self.source.to_dict()}]}
        self.write_project()

    def write_project(self):
        self.path.write_text(json.dumps(self.data))

    def setup_renderer(self):
        entrypoint = self.root / "profiles/test/pipeline.py"
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_text("# Test fixture\n")
        config = self.root / "configs/pronunciations.toml"
        config.parent.mkdir()
        config.write_text("# Test fixture\n")
        reference = self.root / "reference.wav"
        write_wave(reference)
        character = CharacterDefinition("a", "Ami", "individual", (), None, "", 1, False, "profiles/test/pipeline.py")
        self.profile = FakeProfile(reference)
        self.addCleanup(patch.stopall)
        module = "lessons_in_cast_core.audition.rendering."
        patch(module + "load_pipeline_config", return_value=load_pipeline_config(repository_root=ROOT)).start()
        patch(module + "load_characters", return_value={"a": character}).start()
        patch(module + "load_model_registry", return_value=Mock()).start()
        self.factory = patch(module + "load_voice_profile", return_value=self.profile).start()
        self.cleaning = self.root / "cleaning"
        self.cleaning.mkdir()
        (self.cleaning / "annotation_responses.jsonl").write_text('{"fixture": true}\n')
        def validated_fixture(root, project, directory):
            records, validated, targets = {}, {}, {}
            for case in project.cases:
                record = replace(case.source, id=case.id)
                records[case.id] = record
                targets[case.id] = case.id
                annotation = Annotation(case.id, DialogueAction.SPEAK, "Hello.", "happy", {}, (), 1.0, False,
                                        performance=SpeechPerformance(direction="Cleaning-stage direction."))
                validated[case.id] = ValidatedAnnotation(case.id, "batch", ValidationStatus.ACCEPTED, annotation, (), "input", "v2", "config", "2026-01-01")
            return {"case_targets": targets, "requests_sha256": "fixture"}, records, validated
        self.validation = patch(module + "validate_cleaning", side_effect=validated_fixture).start()

    def render(self, run="test", **kwargs):
        return render_project(self.root, self.path, run, cleaning=self.cleaning, **kwargs)

    def test_load_preserves_source_and_separates_spoken_text(self):
        case = load_project(self.path).cases[0]
        self.assertEqual(case.source, self.source)
        self.assertFalse(hasattr(case, "emotion"))
        self.assertFalse(hasattr(case, "intensity"))
        self.assertEqual(case.source.dialogue, "Hello.")

    def test_cases_are_not_limited_to_five_or_unique_emotions(self):
        self.data["cases"] = [{**self.data["cases"][0], "id": f"case-{i}"} for i in range(30)]
        self.write_project()
        self.assertEqual(len(load_project(self.path).cases), 30)

    def test_rejects_bad_cases(self):
        original = deepcopy(self.data)
        for field, value in [("id", "../escape"), ("text", " "), ("intensity", float("nan")),
                             ("intensity", True), ("listen_for", []), ("performance", {"speed": 0}),
                             ("performance", {"extra": 1}), ("performance", {"cues": [{"kind": "pause", "offset": 99}]})]:
            with self.subTest(field=field, value=value):
                self.data = deepcopy(original)
                self.data["cases"][0][field] = value
                self.write_project()
                with self.assertRaises((ValueError, TypeError)):
                    load_project(self.path)

    def test_rejects_duplicate_case_ids(self):
        self.data["cases"].append(deepcopy(self.data["cases"][0]))
        self.write_project()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_project(self.path)

    def test_render_uses_profile_and_resumes_without_repeating(self):
        self.setup_renderer()
        output = self.render()
        self.render()
        self.assertEqual(len(self.profile.jobs), 1)
        self.assertEqual(self.profile.jobs[0].text, "Hello.")
        self.assertEqual(self.profile.jobs[0].performance.direction, "Cleaning-stage direction.")
        self.assertEqual(self.profile.jobs[0].emotion, "happy")
        self.assertNotIn("intensity", self.profile.jobs[0].to_dict())
        self.assertTrue(self.profile.closed)
        self.assertFalse((output / ".render.lock").exists())
        self.assertTrue((output / "takes/hello.adaptation.json").exists())
        self.assertEqual(json.loads((output / "casting_notes.json").read_text())["hello"]["decision"], "undecided")

    def test_reference_override_changes_only_loaded_instance(self):
        self.setup_renderer()
        original = self.profile.reference.read_bytes()
        override = self.root / "alternate.wav"
        write_wave(override)
        output = self.render("override", reference_audio=override)
        self.assertEqual(self.profile.reference, override)
        self.assertEqual((self.root / "reference.wav").read_bytes(), original)
        self.assertEqual(json.loads((output / "inputs.json").read_text())["reference_override"], str(override))

    def test_effects_are_applied_after_profile_and_preserve_raw_take(self):
        self.setup_renderer()
        original = self.validation.side_effect

        def effected(*args):
            metadata, records, validated = original(*args)
            for key, result in validated.items():
                annotation = replace(result.annotation, action=DialogueAction.SPEAK_WITH_EFFECT, effects=("fade_out",))
                validated[key] = replace(result, annotation=annotation)
            return metadata, records, validated

        self.validation.side_effect = effected
        output = self.render()
        self.assertTrue((output / "raw/hello.wav").is_file())
        self.assertNotEqual((output / "raw/hello.wav").read_bytes(), (output / "takes/hello.wav").read_bytes())
        audit = json.loads((output / "takes/hello.effects.json").read_text())
        self.assertEqual(audit["steps"][0]["type"], "fade_out")
        self.assertEqual(self.profile.jobs[0].text, "Hello.")
        self.render()
        self.assertEqual(len(self.profile.jobs), 1)

    def test_effect_only_case_does_not_call_profile_render(self):
        self.setup_renderer()
        original = self.validation.side_effect

        def effected(*args):
            metadata, records, validated = original(*args)
            for key, result in validated.items():
                annotation = replace(result.annotation, action=DialogueAction.SFX_ONLY, spoken_text="", emotion=None, effects=("censor_beep",))
                validated[key] = replace(result, annotation=annotation)
            return metadata, records, validated

        self.validation.side_effect = effected
        output = self.render()
        self.assertEqual(len(self.profile.jobs), 0)
        self.assertTrue((output / "takes/hello.effects.json").is_file())

    def test_changed_inputs_preserve_previous_takes(self):
        self.setup_renderer()
        output = self.render()
        before = (output / "takes/hello.wav").read_bytes()
        self.data["cases"][0]["direction"] = "Speak more urgently."
        self.write_project()
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.render()
        self.assertEqual((output / "takes/hello.wav").read_bytes(), before)

    def test_modified_take_is_not_silently_reused(self):
        self.setup_renderer()
        output = self.render()
        (output / "takes/hello.wav").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "modified take"):
            self.render()

    def test_callback_filters_cases(self):
        self.setup_renderer()
        self.data["cases"].append({**self.data["cases"][0], "id": "second"})
        self.write_project()
        self.render("callback", case_ids=("second",))
        self.assertEqual([job.id for job in self.profile.jobs], ["second"])

    def test_distinct_cases_with_same_source_keep_individual_takes(self):
        self.setup_renderer()
        self.data["cases"].append({**self.data["cases"][0], "id": "second"})
        self.write_project()
        self.render()
        self.assertEqual([job.id for job in self.profile.jobs], ["hello", "second"])

    def test_unaccepted_annotation_does_not_load_model(self):
        self.setup_renderer()
        metadata, records, validated = self.validation.side_effect(self.root, load_project(self.path), self.cleaning)
        validated["hello"] = replace(validated["hello"], status=ValidationStatus.RETRYABLE)
        self.validation.side_effect = None
        self.validation.return_value = metadata, records, validated
        with self.assertRaisesRegex(ValueError, "Polish not accepted"):
            self.render()
        self.factory.assert_not_called()

    def test_cleaner_can_omit_a_side_without_creating_audio(self):
        self.setup_renderer()
        metadata, records, validated = self.validation.side_effect(self.root, load_project(self.path), self.cleaning)
        annotation = replace(validated["hello"].annotation, action=DialogueAction.OMIT, spoken_text=None,
                             emotion=None, reason="Non-spoken text")
        validated["hello"] = replace(validated["hello"], annotation=annotation)
        self.validation.side_effect = None
        self.validation.return_value = metadata, records, validated
        output = self.render()
        self.assertEqual(self.profile.jobs, [])
        self.assertFalse((output / "takes/hello.wav").exists())
        self.assertNotIn("takes/hello.wav", (output / "README.md").read_text())

    def test_unknown_case_does_not_load_model(self):
        self.setup_renderer()
        with self.assertRaisesRegex(ValueError, "Unknown cases"):
            render_project(self.root, self.path, "test", case_ids=("missing",))
        self.factory.assert_not_called()

    def test_unsupported_reference_override_is_explicit(self):
        with self.assertRaisesRegex(NotImplementedError, "does not support"):
            VoicePipeline.override_reference_audio(FakeProfile(self.root / "a.wav"), self.root / "b.wav")

    def test_collection_reads_later_chapters_and_keeps_other_speakers(self):
        rows = [self.source, replace(self.source, id="reply", character="s", dialogue="Hi.", line_number=3),
                replace(self.source, id="later", filename="game/chapter4.rpy", dialogue="Later.")]
        backend = Mock()
        backend.read_dialogue.return_value = iter(rows)
        export = self.root / "dialogue.tab"
        export.write_text("fixture")
        module = "lessons_in_cast_core.audition.collection."
        with patch(module+"load_characters", return_value={"a": SimpleNamespace(name="Ami")}), \
             patch(module+"load_pipeline_config", return_value=SimpleNamespace(galgame=SimpleNamespace(backend="test"))), \
             patch(module+"load_workspace_config", return_value=SimpleNamespace(release_path=self.root)), \
             patch(module+"load_galgame_backend", return_value=backend):
            report = collect_contexts(self.root, export, "a", self.root / "collection")
        self.assertEqual(report["candidate_contexts"], 2)
        packets = [json.loads(line) for line in (self.root / "collection/contexts.jsonl").read_text().splitlines()]
        self.assertTrue(any(any(row["character"] == "s" for row in packet["dialogue"]) for packet in packets))
        backend.read_dialogue.assert_called_once_with(export, source_root=self.root)

    def test_ami_sides_include_main_story_beyond_chapter_one(self):
        project = load_project(ROOT / "auditions/ami/project.json")
        files = {case.source.filename for case in project.cases}
        self.assertTrue({"game/script.rpy", "game/ch2script.rpy", "game/chap3.rpy", "game/chap4.rpy", "game/chap4part2.rpy"} <= files)
        self.assertEqual(project.coverage["status"], "partial")

    def test_listening_decision_is_separate_from_render_completion(self):
        self.setup_renderer()
        output = self.render()
        before = (output / "manifest.json").read_bytes()
        status = main(["--root", str(self.root), "review", "--run", "test", "--case", "hello",
                       "--decision", "callback", "--notes", "Try less emphasis."])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads((output / "casting_notes.json").read_text())["hello"]["decision"], "callback")
        self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_no_annotation_means_no_model_loading(self):
        self.setup_renderer()
        with self.assertRaisesRegex(ValueError, "cleaning run is required"):
            render_project(self.root, self.path, "missing")
        self.factory.assert_not_called()

    def test_formal_cleaning_roundtrip_and_request_binding(self):
        config = load_pipeline_config(repository_root=ROOT)
        prompt = self.root / config.codex.prompt_path
        prompt.parent.mkdir(parents=True)
        prompt.write_text("Clean and annotate all targets.")
        character = CharacterDefinition("a", "Ami", "individual", (), None, "", 1, False, "profiles/test/pipeline.py")
        backend = Mock()
        backend.read_dialogue.return_value = iter([self.source])
        export = self.root / "dialogue.tab"
        export.write_text("fixture")
        directory = self.root / "cleaning"
        module = "lessons_in_cast_core.audition.cleaning."
        with patch(module+"load_pipeline_config", return_value=config), \
             patch(module+"load_characters", return_value={"a": character}), \
             patch(module+"load_workspace_config", return_value=SimpleNamespace(release_path=self.root)), \
             patch(module+"load_galgame_backend", return_value=backend):
            prepare_cleaning(self.root, self.path, export, directory)
            packet = json.loads((directory / "codex/inbox.json").read_text())
            target = packet["batches"][0]["target_ids"][0]
            self.assertEqual(packet["director_notes"], {})
            self.assertIn("cleaning-import", (directory / "codex/task.md").read_text())
            with self.assertRaisesRegex(ValueError, "No cleaning annotations"):
                validate_cleaning(self.root, load_project(self.path), directory)
            response = {"packet_id": packet["packet_id"], "annotations": [{
                "id": target, "action": "speak", "spoken_text": 'Hello.', "performance": {"cues": []},
                "effects": [], "confidence": 1, "review_required": False, "reason": ""}]}
            (directory / "codex/outbox.json").write_text(json.dumps(response))
            layout = ArtifactLayout(directory)
            workflow(self.root, directory).import_outbox(layout.annotation_requests, layout.annotation_responses, CodexWorkspace(directory / "codex"))
            _, _, results = validate_cleaning(self.root, load_project(self.path), directory, require_polish=False)
            self.assertEqual(results[target].status, ValidationStatus.ACCEPTED, results[target].issues)
            self.assertEqual(results[target].annotation.spoken_text, "Hello.")
            with self.assertRaisesRegex(ValueError, "No polish"):
                validate_cleaning(self.root, load_project(self.path), directory)
            from lessons_in_cast_core.polish import PolishStage
            from .fakes import write_mock_responses
            polish = PolishStage(config)
            polish.prepare(layout, prompt_path=prompt)
            write_mock_responses(layout.polish.annotation_requests, layout.polish.annotation_responses)
            _, _, results = validate_cleaning(self.root, load_project(self.path), directory)
            self.assertEqual(results[target].status, ValidationStatus.ACCEPTED, results[target].issues)
            self.assertIn('<emotion name="neutral">', results[target].annotation.spoken_text)
            layout.annotation_requests.write_text(layout.annotation_requests.read_text()+"\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                validate_cleaning(self.root, load_project(self.path), directory)


if __name__ == "__main__":
    unittest.main()
