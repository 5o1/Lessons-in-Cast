"""Top-level orchestration for the dialogue-to-audio pipeline."""

from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .annotation import (
    DialogueAnnotator,
    ValidatedAnnotation,
    build_annotation_request,
)
from .characters import CharacterDefinition
from .config import PipelineConfig
from .dialogue import (
    DialogueBatchBuilder,
    DialogueRecord,
    JsonlDialogueReader,
    JsonlDialogueWriter,
    TabDialogueReader,
    audit_dialogue,
)
from .hashing import content_hash, file_hash
from .jsonl import AtomicJsonlWriter, JsonlIndex, read_jsonl, write_jsonl
from .renpy import (
    DialogueExtractionRequest,
    DialogueExtractor,
    RenPyVoiceInstaller,
    RenPyVoiceManifestWriter,
)
from .synthesis import (
    AudioQualityChecker,
    AudioQualityResult,
    RenderTask,
    SpeechSynthesizer,
    SynthesisPlanner,
    SynthesisIssue,
    TtsJob,
    WaveRenderer,
)
from .synthesis.audio import AudioRenderError
from .workflow import (
    ArtifactLayout,
    PipelineRequest,
    PipelineResult,
    ValidationSummary,
)
from .workflow.manifest import start_run_manifest, update_run_manifest
from .workflow.validation import AnnotationValidationStage


class DialoguePipeline:
    """Coordinate every model-neutral stage and replaceable backend."""

    def __init__(
        self,
        *,
        config: PipelineConfig,
        characters: dict[str, CharacterDefinition],
        annotator: DialogueAnnotator | None = None,
        synthesizer: SpeechSynthesizer | None = None,
        renderer: WaveRenderer | None = None,
    ) -> None:
        self._config = config
        self._characters = characters
        self._annotator = annotator
        self._synthesizer = synthesizer
        self._renderer = renderer or WaveRenderer()
        self._validation = AnnotationValidationStage(config)

    def extract(
        self,
        extractor: DialogueExtractor,
        request: DialogueExtractionRequest,
    ) -> Path:
        result = extractor.extract(request)
        layout = ArtifactLayout(request.output_path.resolve().parent)
        update_run_manifest(
            layout,
            {
                "extraction": {
                    "release_path": str(request.release_path.resolve()),
                    "dialogue_path": str(result.dialogue_path.resolve()),
                    "dialogue_sha256": file_hash(result.dialogue_path),
                    "source_count": result.source_count,
                    "command": list(result.command),
                }
            },
        )
        return result.dialogue_path

    def prepare(self, request: PipelineRequest) -> tuple[int, int]:
        """Import dialogue losslessly and export fixed-window requests."""

        layout = ArtifactLayout(request.artifact_root.resolve())
        layout.root.mkdir(parents=True, exist_ok=True)
        dialogue_tab_hash = file_hash(request.dialogue_tab_path)
        start_run_manifest(
            layout,
            dialogue_path=request.dialogue_tab_path,
            dialogue_hash=dialogue_tab_hash,
        )
        source_filter = request.allowed_sources or None
        reader = TabDialogueReader(source_filter)
        dialogue_count = JsonlDialogueWriter().write(
            reader.read(request.dialogue_tab_path),
            layout.raw_dialogue,
        )
        batches = DialogueBatchBuilder(self._config.batching).build(
            JsonlDialogueReader().read(layout.raw_dialogue)
        )
        batch_count = write_jsonl(
            (
                build_annotation_request(
                    batch,
                    prompt_version=request.prompt_version,
                    annotation_config=self._config.annotation,
                )
                for batch in batches
            ),
            layout.annotation_requests,
        )
        source_audit = audit_dialogue(
            JsonlDialogueReader().read(layout.raw_dialogue),
            known_characters=set(self._characters),
        )
        layout.source_audit.write_text(
            json.dumps(source_audit, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        configuration_fingerprint = content_hash(
            {
                "batching": asdict(self._config.batching),
                "annotation": {
                    "allowed_emotions": sorted(
                        self._config.annotation.allowed_emotions
                    ),
                    "allowed_effects": sorted(
                        self._config.annotation.allowed_effects
                    ),
                    "maximum_length_ratio": (
                        self._config.annotation.maximum_length_ratio
                    ),
                    "minimum_length_ratio": (
                        self._config.annotation.minimum_length_ratio
                    ),
                },
                "audio": asdict(self._config.audio),
                "codex": asdict(self._config.codex),
            }
        )
        character_fingerprint = content_hash(
            {
                character_id: asdict(character)
                for character_id, character in sorted(self._characters.items())
            }
        )
        update_run_manifest(
            layout,
            {
                "dialogue_tab": {
                    "path": str(request.dialogue_tab_path.resolve()),
                    "sha256": dialogue_tab_hash,
                },
                "dialogue_count": dialogue_count,
                "batch_count": batch_count,
                "prompt_version": request.prompt_version,
                "source_audit_valid": source_audit["valid"],
                "pipeline_configuration_hash": configuration_fingerprint,
                "character_configuration_hash": character_fingerprint,
            },
        )
        return dialogue_count, batch_count

    def annotate(
        self,
        layout: ArtifactLayout,
        *,
        requests_path: Path | None = None,
        responses_path: Path | None = None,
    ) -> int:
        """Run the configured annotator with content-addressed response reuse."""

        if self._annotator is None:
            raise RuntimeError("No dialogue annotator is configured")
        requests_path = requests_path or layout.annotation_requests
        responses_path = responses_path or layout.annotation_responses
        index_context = (
            JsonlIndex(responses_path, "request_hash")
            if responses_path.exists()
            else nullcontext(None)
        )
        reused = 0
        with index_context as existing, AtomicJsonlWriter(responses_path) as output:
            for request in read_jsonl(requests_path):
                request_hash = content_hash(request)
                cached = existing.get(request_hash) if existing is not None else None
                if (
                    cached is not None
                    and cached.get("annotator_configuration")
                    == self._annotator.configuration
                ):
                    output.write(cached)
                    reused += 1
                    continue
                response = self._annotator.annotate(request)
                output.write(
                    {
                        "request_hash": request_hash,
                        "batch_id": request["batch"]["batch_id"],
                        "prompt_version": request["prompt_version"],
                        "annotator_configuration": self._annotator.configuration,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "response": response,
                    }
                )
        update_run_manifest(
            layout,
            {
                "annotation_response_count": output.count,
                "annotation_response_reused": reused,
                "annotator_configuration": self._annotator.configuration,
            },
        )
        return output.count

    def validate(
        self,
        layout: ArtifactLayout,
        *,
        overrides_path: Path | None = None,
        retry: bool = False,
    ) -> ValidationSummary:
        """Validate untrusted annotations and apply trusted overrides."""

        return self._validation.run(
            layout,
            overrides_path=overrides_path,
            retry=retry,
        )

    def plan_synthesis(self, layout: ArtifactLayout) -> tuple[int, int]:
        planner = SynthesisPlanner(
            self._characters,
            audio_config=self._config.audio,
            synthesizer_configuration=(
                self._synthesizer.configuration
                if self._synthesizer is not None
                else None
            ),
        )
        with JsonlIndex(layout.raw_dialogue, "id") as record_index:
            def records_and_results() -> Any:
                for value in read_jsonl(layout.validated):
                    result = ValidatedAnnotation.from_dict(value)
                    raw_record = record_index.get(result.dialogue_id)
                    if raw_record is None:
                        raise ValueError(
                            "Validated result references unknown dialogue ID "
                            f"{result.dialogue_id!r}"
                        )
                    yield DialogueRecord.from_dict(raw_record), result

            with (
                AtomicJsonlWriter(layout.tts_jobs) as job_writer,
                AtomicJsonlWriter(layout.render_tasks) as render_writer,
                AtomicJsonlWriter(layout.synthesis_issues) as issue_writer,
            ):
                for item in planner.iter_plan(records_and_results()):
                    if isinstance(item, TtsJob):
                        job_writer.write(item.to_dict())
                    elif isinstance(item, RenderTask):
                        render_writer.write(item.to_dict())
                    elif isinstance(item, SynthesisIssue):
                        issue_writer.write(item.to_dict())
                    else:
                        raise TypeError(f"Unexpected synthesis plan item: {item!r}")
        job_count = job_writer.count
        render_count = render_writer.count
        issue_count = issue_writer.count
        update_run_manifest(
            layout,
            {
                "tts_job_count": job_count,
                "render_task_count": render_count,
                "synthesis_issue_count": issue_count,
            },
        )
        return job_count, render_count

    def synthesize(self, layout: ArtifactLayout) -> tuple[int, int]:
        if self._synthesizer is None:
            raise RuntimeError("No speech synthesizer is configured")
        job_count = 0
        reused_job_count = 0
        for value in read_jsonl(layout.tts_jobs):
            job = TtsJob.from_dict(value)
            job_count += 1
            if (layout.root / job.output_path).is_file():
                reused_job_count += 1
            else:
                self._synthesizer.synthesize(job, layout.root)

        checker = AudioQualityChecker(self._config.audio)
        rendered = 0
        quality_failures = 0
        with (
            JsonlIndex(layout.tts_jobs, "id") as job_index,
            AtomicJsonlWriter(layout.audio_quality) as quality_writer,
        ):
            for value in read_jsonl(layout.render_tasks):
                task = RenderTask.from_dict(value)
                component_jobs: dict[str, TtsJob] = {}
                try:
                    for job_id in task.component_job_ids:
                        raw_job = job_index.get(job_id)
                        if raw_job is None:
                            raise KeyError(job_id)
                        component_jobs[job_id] = TtsJob.from_dict(raw_job)
                    path = self._renderer.render(task, component_jobs, layout.root)
                except (AudioRenderError, KeyError) as exc:
                    result = AudioQualityResult(
                        dialogue_id=task.dialogue_id,
                        path=str(layout.root / task.output_path),
                        valid=False,
                        duration_seconds=None,
                        issues=(str(exc),),
                    )
                else:
                    result = checker.check(task.dialogue_id, path)
                quality_writer.write(result.to_dict())
                if result.valid:
                    rendered += 1
                else:
                    quality_failures += 1

        integration_writer = RenPyVoiceManifestWriter()
        with (
            JsonlIndex(layout.raw_dialogue, "id") as record_index,
            JsonlIndex(layout.audio_quality, "dialogue_id") as quality_index,
        ):
            def manifest_entries() -> Any:
                for value in read_jsonl(layout.render_tasks):
                    task = RenderTask.from_dict(value)
                    raw_record = record_index.get(task.dialogue_id)
                    raw_quality = quality_index.get(task.dialogue_id)
                    if raw_record is None or raw_quality is None:
                        raise ValueError(
                            "Cannot build manifest for dialogue "
                            f"{task.dialogue_id!r}"
                        )
                    yield integration_writer.create_entry(
                        DialogueRecord.from_dict(raw_record),
                        task,
                        AudioQualityResult.from_dict(raw_quality),
                    )

            integration_writer.write_entries(
                layout.voice_manifest,
                manifest_entries(),
            )
        with JsonlIndex(layout.audio_quality, "dialogue_id") as quality_index:
            integration_writer.write_auto_voice_script(
                layout.renpy_script,
                entries=(
                    (task.identifier, task.virtual_path)
                    for value in read_jsonl(layout.render_tasks)
                    for task in (RenderTask.from_dict(value),)
                    if (
                        (quality := quality_index.get(task.dialogue_id)) is not None
                        and quality.get("valid") is True
                    )
                ),
            )
        update_run_manifest(
            layout,
            {
                "synthesizer": self._synthesizer.name,
                "tts_job_count": job_count,
                "tts_job_reused": reused_job_count,
                "rendered_count": rendered,
                "audio_quality_failure_count": quality_failures,
            },
        )
        return job_count, rendered

    def build_release_bundle(self, layout: ArtifactLayout) -> int:
        """Create a game-relative directory without mutating the source release."""

        with JsonlIndex(layout.audio_quality, "dialogue_id") as quality_index:
            def install_artifacts() -> Any:
                for value in read_jsonl(layout.render_tasks):
                    task = RenderTask.from_dict(value)
                    raw_quality = quality_index.get(task.dialogue_id)
                    if raw_quality is None:
                        raise ValueError(
                            "Cannot install dialogue without quality result: "
                            f"{task.dialogue_id!r}"
                        )
                    yield task, AudioQualityResult.from_dict(raw_quality)

            result = RenPyVoiceInstaller().install(
                layout.release_bundle,
                artifact_root=layout.root,
                voice_script=layout.renpy_script,
                voice_manifest=layout.voice_manifest,
                artifacts=install_artifacts(),
            )
        update_run_manifest(
            layout,
            {"release_bundle_audio_count": result.audio_count},
        )
        return result.audio_count

    def run(self, request: PipelineRequest) -> PipelineResult:
        dialogue_count, batch_count = self.prepare(request)
        self.annotate(ArtifactLayout(request.artifact_root.resolve()))
        layout = ArtifactLayout(request.artifact_root.resolve())
        validated = self.validate(layout, overrides_path=request.overrides_path)
        tts_job_count, _ = self.plan_synthesis(layout)
        _, rendered_count = self.synthesize(layout)
        self.build_release_bundle(layout)
        return PipelineResult(
            artifacts=layout,
            dialogue_count=dialogue_count,
            batch_count=batch_count,
            accepted_count=validated.accepted_count,
            review_count=validated.review_required_count,
            retryable_count=validated.retryable_count,
            rejected_count=validated.rejected_count,
            tts_job_count=tts_job_count,
            rendered_count=rendered_count,
        )

    def run_from_responses(
        self,
        request: PipelineRequest,
        responses_path: Path,
        *,
        cache_intermediates: bool = False,
    ) -> PipelineResult:
        """Run model-neutral stages from externally produced model responses."""

        layout = ArtifactLayout(request.artifact_root.resolve())
        source_dialogue = request.dialogue_tab_path.resolve()
        source_responses = responses_path.resolve()
        if not cache_intermediates and (
            source_dialogue.is_relative_to(layout.root)
            or source_responses.is_relative_to(layout.root)
        ):
            raise ValueError(
                "Production inputs must be outside the artifact directory when "
                "intermediate caching is disabled"
            )
        layout.root.mkdir(parents=True, exist_ok=True)
        layout.reset_generated()
        dialogue_count, batch_count = self.prepare(request)
        shutil.copy2(source_responses, layout.annotation_responses)
        try:
            validated = self.validate(
                layout,
                overrides_path=request.overrides_path,
            )
            tts_job_count, _ = self.plan_synthesis(layout)
            _, rendered_count = self.synthesize(layout)
            self.build_release_bundle(layout)
            result = PipelineResult(
                artifacts=layout,
                dialogue_count=dialogue_count,
                batch_count=batch_count,
                accepted_count=validated.accepted_count,
                review_count=validated.review_required_count,
                retryable_count=validated.retryable_count,
                rejected_count=validated.rejected_count,
                tts_job_count=tts_job_count,
                rendered_count=rendered_count,
            )
            update_run_manifest(
                layout,
                {
                    "production": {
                        "annotation_responses": str(source_responses),
                        "cache_intermediates": cache_intermediates,
                        "retained_paths": (
                            ["release_bundle", "run_manifest.json"]
                            if not cache_intermediates
                            else ["all"]
                        ),
                    }
                },
            )
            if not cache_intermediates:
                layout.discard_intermediates()
            return result
        finally:
            close = getattr(self._synthesizer, "close", None)
            if close is not None:
                close()
