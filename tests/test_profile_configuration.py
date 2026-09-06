from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.synthesis.backends.index_tts.config import (
    load_index_tts_pipeline_config,
)
from lessons_in_cast_core.synthesis.backends.index_tts.worker import _prepare_reference
from lessons_in_cast_core.synthesis.references.builder import (
    ReferenceBuildResult,
    ReferenceBuildSettings,
    _validate_result,
)
from lessons_in_cast_core.synthesis.references.cache import (
    ensure_reference_from_directory,
)


class VoiceProfileConfigurationTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_core_pipeline_config_has_no_backend_fields(self) -> None:
        config = load_pipeline_config(repository_root=self.root)
        self.assertFalse(hasattr(config, "synthesis"))

    def test_index_tts_settings_are_owned_by_profile_bundle(self) -> None:
        config = load_index_tts_pipeline_config(
            Path("profiles/ch_index_tts/config.toml"),
            repository_root=self.root,
        )
        self.assertEqual(config.language, "EN")
        self.assertEqual(config.emotion_alpha, 0.65)
        self.assertEqual(config.base_speed, 1.0)
        self.assertEqual(config.model_id, "index_tts_2_5")
        self.assertEqual(config.reference_scope, "profile")
        self.assertEqual(
            config.reference_sources,
            ("source-01.wav", "source-02.wav", "source-03.wav"),
        )
        self.assertEqual(
            config.reference_path,
            "assets/references/default.wav",
        )
        self.assertFalse(hasattr(config, "pronunciations"))

    def test_reference_cache_reuses_and_invalidates_generated_audio(self) -> None:
        settings = ReferenceBuildSettings(
            minimum_speech_seconds=1.0,
            minimum_duration_seconds=15.0,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "samples"
            sources.mkdir()
            sample = sources / "one.wav"
            sample.write_bytes(b"source-v1")
            output = root / "build" / "reference.wav"
            calls: list[bytes] = []

            def builder(
                input_directory: Path,
                output_path: Path,
                _settings: ReferenceBuildSettings,
            ) -> ReferenceBuildResult:
                calls.append(sample.read_bytes())
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"generated-" + calls[-1])
                return ReferenceBuildResult(
                    output_path=output_path.resolve(),
                    selected_paths=(sample.resolve(),),
                    source_duration_seconds=15.0,
                    voiced_seconds=10.0,
                    prepared_duration_seconds=15.0,
                    sample_rate=32_000,
                )

            first, first_reused = ensure_reference_from_directory(
                pipeline_id="test",
                input_directory=sources,
                output_path=output,
                settings=settings,
                builder=builder,
            )
            second, second_reused = ensure_reference_from_directory(
                pipeline_id="test",
                input_directory=sources,
                output_path=output,
                settings=settings,
                builder=builder,
            )
            self.assertFalse(first_reused)
            self.assertTrue(second_reused)
            self.assertEqual(first.output_path, second.output_path)
            self.assertEqual(len(calls), 1)

            sample.write_bytes(b"source-v2")
            _, changed_reused = ensure_reference_from_directory(
                pipeline_id="test",
                input_directory=sources,
                output_path=output,
                settings=settings,
                builder=builder,
            )
            self.assertFalse(changed_reused)
            self.assertEqual(len(calls), 2)
            self.assertTrue(
                output.with_suffix(".wav.manifest.json").is_file()
            )

    def test_prepared_reference_is_passed_through_without_reprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "prepared.wav"
            reference.write_bytes(b"prepared-audio")
            result = _prepare_reference(
                {
                    "references": [str(reference)],
                    "prepare_references": False,
                },
                root / "worker-cache",
                {},
            )
            self.assertEqual(result, reference.resolve())
            self.assertEqual(reference.read_bytes(), b"prepared-audio")


    def test_short_reference_warns_without_failing(self) -> None:
        settings = ReferenceBuildSettings(
            minimum_speech_seconds=3.0,
            minimum_duration_seconds=15.0,
        )
        with self.assertWarnsRegex(RuntimeWarning, "at least 15.00s is recommended"):
            _validate_result(
                (Path("short-reference.wav"),),
                voiced_seconds=8.0,
                prepared_duration=12.0,
                settings=settings,
            )


if __name__ == "__main__":
    unittest.main()
