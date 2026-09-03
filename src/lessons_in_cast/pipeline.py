"""Top-level orchestration for the dialogue-to-audio pipeline."""

from __future__ import annotations

import json
import shutil
from contextlib import ExitStack, nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .annotation import (
    AnnotationValidator,
    DialogueAnnotator,
    ValidatedAnnotation,
    ValidationStatus,
    apply_override,
    build_annotation_request,
    load_overrides,
)
from .characters import CharacterDefinition
from .config import PipelineConfig
from .dialogue import (
    DialogueBatch,
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


@dataclass(frozen=True, slots=True)
class ArtifactLayout:
    root: Path

    @property
    def dialogue_tab(self) -> Path:
        return self.root / "dialogue.tab"

    @property
    def raw_dialogue(self) -> Path:
        return self.root / "raw.jsonl"

    @property
    def model_requests(self) -> Path:
        return self.root / "model_requests.jsonl"

    @property
    def source_audit(self) -> Path:
        return self.root / "source_audit.json"

    @property
    def model_responses(self) -> Path:
        return self.root / "model_responses.jsonl"

    @property
    def validated(self) -> Path:
        return self.root / "validated.jsonl"

    @property
    def review_required(self) -> Path:
        return self.root / "review_required.jsonl"

    @property
    def retryable(self) -> Path:
        return self.root / "retryable.jsonl"

    @property
    def retry_requests(self) -> Path:
        return self.root / "retry_requests.jsonl"

    @property
    def retry_responses(self) -> Path:
        return self.root / "retry_responses.jsonl"

    @property
    def retry_validated(self) -> Path:
        return self.root / "retry_validated.jsonl"

    @property
    def rejected(self) -> Path:
        return self.root / "rejected.jsonl"

    @property
    def validation_issues(self) -> Path:
        return self.root / "validation_issues.jsonl"

    @property
    def retry_validation_issues(self) -> Path:
        return self.root / "retry_validation_issues.jsonl"

    @property
    def tts_jobs(self) -> Path:
        return self.root / "tts_jobs.jsonl"

    @property
    def render_tasks(self) -> Path:
        return self.root / "render_tasks.jsonl"

    @property
    def synthesis_issues(self) -> Path:
        return self.root / "synthesis_issues.jsonl"

    @property
    def audio_quality(self) -> Path:
        return self.root / "audio_quality.jsonl"

    @property
    def voice_manifest(self) -> Path:
        return self.root / "voice_manifest.json"

    @property
    def renpy_script(self) -> Path:
        return self.root / "lessons_in_cast_voice.rpy"

    @property
    def run_manifest(self) -> Path:
        return self.root / "run_manifest.json"

    @property
    def release_bundle(self) -> Path:
        return self.root / "release_bundle"


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    artifact_root: Path
    dialogue_tab_path: Path
    allowed_sources: tuple[Path, ...] = ()
    prompt_version: str = "1"
    overrides_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    artifacts: ArtifactLayout
    dialogue_count: int
    batch_count: int
    accepted_count: int
    review_count: int
    retryable_count: int
    rejected_count: int
    tts_job_count: int
    rendered_count: int


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    accepted_count: int
    review_required_count: int
    retryable_count: int
    rejected_count: int
    retry_request_count: int
    batch_issue_count: int

    @property
    def total(self) -> int:
        return (
            self.accepted_count
            + self.review_required_count
            + self.retryable_count
            + self.rejected_count
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "accepted": self.accepted_count,
            "review_required": self.review_required_count,
            "retryable": self.retryable_count,
            "rejected": self.rejected_count,
            "retry_requests": self.retry_request_count,
            "batch_issues": self.batch_issue_count,
        }


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
        self._validator = AnnotationValidator(config.annotation)

    def extract(
        self,
        extractor: DialogueExtractor,
        request: DialogueExtractionRequest,
    ) -> Path:
        result = extractor.extract(request)
        layout = ArtifactLayout(request.output_path.resolve().parent)
        self._update_manifest(
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
        """Import dialogue losslessly and export fixed-window model requests."""

        layout = ArtifactLayout(request.artifact_root.resolve())
        layout.root.mkdir(parents=True, exist_ok=True)
        dialogue_tab_hash = file_hash(request.dialogue_tab_path)
        self._start_manifest(
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
            layout.model_requests,
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
            }
        )
        character_fingerprint = content_hash(
            {
                character_id: asdict(character)
                for character_id, character in sorted(self._characters.items())
            }
        )
        self._update_manifest(
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
        requests_path = requests_path or layout.model_requests
        responses_path = responses_path or layout.model_responses
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
        self._update_manifest(
            layout,
            {
                "model_response_count": output.count,
                "model_response_reused": reused,
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
        """Validate untrusted model responses and apply trusted human overrides."""

        requests_path = layout.retry_requests if retry else layout.model_requests
        responses_path = layout.retry_responses if retry else layout.model_responses
        overrides = load_overrides(overrides_path) if overrides_path is not None else {}
        override_records: dict[str, DialogueRecord] = {}
        missing_override_ids = set(overrides)
        if missing_override_ids:
            for record in JsonlDialogueReader().read(layout.raw_dialogue):
                if record.id in missing_override_ids:
                    override_records[record.id] = record
                    missing_override_ids.remove(record.id)
                    if not missing_override_ids:
                        break
        if missing_override_ids:
            raise ValueError(
                f"Overrides reference unknown IDs: {sorted(missing_override_ids)!r}"
            )

        requested_batch_ids: set[str] = set()
        requested_dialogue_ids: set[str] = set()
        current_output = layout.retry_validated if retry else layout.validated
        issue_path = (
            layout.retry_validation_issues
            if retry
            else layout.validation_issues
        )
        with JsonlIndex(responses_path, "batch_id") as response_index:
            with ExitStack() as stack:
                current_writer = stack.enter_context(
                    AtomicJsonlWriter(current_output)
                )
                issue_writer = stack.enter_context(
                    AtomicJsonlWriter(issue_path)
                )
                retry_writer = stack.enter_context(
                    AtomicJsonlWriter(layout.retry_requests)
                )
                for request in read_jsonl(requests_path):
                    batch = DialogueBatch.from_dict(request["batch"])
                    if batch.id in requested_batch_ids:
                        raise ValueError(f"Duplicate request batch ID: {batch.id!r}")
                    requested_batch_ids.add(batch.id)
                    target_ids = {target.id for target in batch.targets}
                    duplicate_targets = target_ids & requested_dialogue_ids
                    if duplicate_targets:
                        raise ValueError(
                            "Dialogue targets occur in more than one request: "
                            f"{sorted(duplicate_targets)!r}"
                        )
                    if len(target_ids) != len(batch.targets):
                        raise ValueError(
                            f"Request batch {batch.id!r} contains duplicate targets"
                        )
                    requested_dialogue_ids.update(target_ids)
                    envelope = response_index.get(batch.id)
                    if batch.id in response_index.duplicates:
                        issue_writer.write(
                            self._batch_issue(
                                batch.id,
                                "duplicate_batch_response",
                                "More than one response exists for this batch.",
                            )
                        )
                        envelope = None
                    expected_request_hash = content_hash(request)
                    if (
                        envelope is not None
                        and envelope.get("request_hash") != expected_request_hash
                    ):
                        issue_writer.write(
                            self._batch_issue(
                                batch.id,
                                "request_hash_mismatch",
                                "Response does not match the current model request.",
                            )
                        )
                        envelope = None
                    if (
                        envelope is not None
                        and envelope.get("prompt_version")
                        != request["prompt_version"]
                    ):
                        issue_writer.write(
                            self._batch_issue(
                                batch.id,
                                "prompt_version_mismatch",
                                "Response prompt version does not match its request.",
                            )
                        )
                        envelope = None
                    response = envelope.get("response", {}) if envelope else {}
                    configuration = (
                        envelope.get("annotator_configuration", {})
                        if envelope
                        else {}
                    )
                    result = self._validator.validate_batch(
                        batch,
                        response,
                        prompt_version=request["prompt_version"],
                        annotator_configuration=configuration,
                        processed_at=(
                            envelope.get("generated_at")
                            if envelope
                            and isinstance(envelope.get("generated_at"), str)
                            else None
                        ),
                    )
                    for issue in result.issues:
                        issue_writer.write(
                            {**issue.to_dict(), "batch_id": batch.id}
                        )
                    for item in result.records:
                        configured_override = overrides.get(item.dialogue_id)
                        if configured_override is not None:
                            item = apply_override(
                                item,
                                override_records[item.dialogue_id],
                                configured_override,
                                self._validator,
                            )
                        current_writer.write(item.to_dict())
                        if item.status is ValidationStatus.RETRYABLE:
                            retry_writer.write(
                                self._build_retry_request(batch, item, request)
                            )
                for unknown_batch_id in (
                    set(response_index.offsets) - requested_batch_ids
                ):
                    issue_writer.write(
                        self._batch_issue(
                            unknown_batch_id,
                            "unknown_batch_response",
                            "Response does not correspond to a current request.",
                        )
                    )
            batch_issue_count = issue_writer.count
            retry_request_count = retry_writer.count

        if retry:
            self._merge_retry_results(layout)
        summary = self._split_validated_outputs(layout)
        manifest_key = "retry_validation" if retry else "validation"
        self._update_manifest(
            layout,
            {
                manifest_key: {
                    "counts": {
                    "accepted": summary.accepted_count,
                    "review_required": summary.review_required_count,
                    "retryable": summary.retryable_count,
                    "rejected": summary.rejected_count,
                    },
                    "retry_request_count": retry_request_count,
                    "batch_issue_count": batch_issue_count,
                },
            },
        )
        return ValidationSummary(
            accepted_count=summary.accepted_count,
            review_required_count=summary.review_required_count,
            retryable_count=summary.retryable_count,
            rejected_count=summary.rejected_count,
            retry_request_count=retry_request_count,
            batch_issue_count=batch_issue_count,
        )

    def _merge_retry_results(self, layout: ArtifactLayout) -> None:
        with JsonlIndex(layout.retry_validated, "dialogue_id") as replacements:
            with AtomicJsonlWriter(layout.validated) as output:
                seen: set[str] = set()
                for value in read_jsonl(layout.validated):
                    dialogue_id = value["dialogue_id"]
                    replacement = replacements.get(dialogue_id)
                    output.write(replacement or value)
                    if replacement is not None:
                        seen.add(dialogue_id)
                unknown = set(replacements.offsets) - seen
                if unknown:
                    raise ValueError(
                        f"Retry results reference unknown dialogue IDs: {sorted(unknown)!r}"
                    )

    def _split_validated_outputs(
        self,
        layout: ArtifactLayout,
    ) -> ValidationSummary:
        counts = {status: 0 for status in ValidationStatus}
        with (
            AtomicJsonlWriter(layout.review_required) as review_writer,
            AtomicJsonlWriter(layout.retryable) as retryable_writer,
            AtomicJsonlWriter(layout.rejected) as rejected_writer,
        ):
            for value in read_jsonl(layout.validated):
                status = ValidationStatus(value["status"])
                counts[status] += 1
                if status is ValidationStatus.REVIEW_REQUIRED:
                    review_writer.write(value)
                elif status is ValidationStatus.RETRYABLE:
                    retryable_writer.write(value)
                elif status is ValidationStatus.REJECTED:
                    rejected_writer.write(value)
        return ValidationSummary(
            accepted_count=counts[ValidationStatus.ACCEPTED],
            review_required_count=counts[ValidationStatus.REVIEW_REQUIRED],
            retryable_count=counts[ValidationStatus.RETRYABLE],
            rejected_count=counts[ValidationStatus.REJECTED],
            retry_request_count=0,
            batch_issue_count=0,
        )

    def _build_retry_request(
        self,
        batch: DialogueBatch,
        item: ValidatedAnnotation,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        target = next(
            target for target in batch.targets if target.id == item.dialogue_id
        )
        ordered = [*batch.context_before, *batch.targets, *batch.context_after]
        position = ordered.index(target)
        before = tuple(
            ordered[
                max(0, position - self._config.batching.context_before):
                position
            ]
        )
        after = tuple(
            ordered[
                position + 1:
                position + 1 + self._config.batching.context_after
            ]
        )
        attempt = request.get("attempt", 0) + 1
        retry_batch = DialogueBatch(
            id=content_hash(
                {
                    "retry_of": batch.id,
                    "dialogue_id": target.id,
                    "attempt": attempt,
                }
            )[:24],
            context_before=before,
            targets=(target,),
            context_after=after,
        )
        retry_request = build_annotation_request(
            retry_batch,
            prompt_version=request["prompt_version"],
            annotation_config=self._config.annotation,
        )
        retry_request["retry_of"] = request.get("retry_of", batch.id)
        retry_request["attempt"] = attempt
        return retry_request

    @staticmethod
    def _batch_issue(
        batch_id: str,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "severity": "error",
            "dialogue_id": None,
            "batch_id": batch_id,
        }

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
        self._update_manifest(
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
        integration_writer.write_auto_voice_script(
            layout.renpy_script,
            audio_format=self._config.audio.format,
        )
        self._update_manifest(
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

        game_root = layout.release_bundle / "game"
        voice_root = game_root / "voice"
        voice_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        with JsonlIndex(layout.audio_quality, "dialogue_id") as quality_index:
            for value in read_jsonl(layout.render_tasks):
                task = RenderTask.from_dict(value)
                result = quality_index.get(task.dialogue_id)
                if result is None or result.get("valid") is not True:
                    continue
                source = layout.root / task.output_path
                destination = game_root / task.output_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied += 1
        shutil.copy2(layout.renpy_script, game_root / layout.renpy_script.name)
        shutil.copy2(layout.voice_manifest, game_root / layout.voice_manifest.name)
        self._update_manifest(layout, {"release_bundle_audio_count": copied})
        return copied

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

    @staticmethod
    def _start_manifest(
        layout: ArtifactLayout,
        *,
        dialogue_path: Path,
        dialogue_hash: str,
    ) -> None:
        extraction: dict[str, Any] | None = None
        if layout.run_manifest.exists():
            with layout.run_manifest.open("r", encoding="utf-8") as source:
                previous = json.load(source)
            candidate = previous.get("extraction")
            if (
                isinstance(candidate, dict)
                and candidate.get("dialogue_path")
                == str(dialogue_path.resolve())
                and candidate.get("dialogue_sha256") == dialogue_hash
            ):
                extraction = candidate
        started_at = datetime.now(timezone.utc).isoformat()
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "started_at": started_at,
            "updated_at": started_at,
        }
        if extraction is not None:
            manifest["extraction"] = extraction
        DialoguePipeline._write_manifest(layout, manifest)

    @staticmethod
    def _update_manifest(layout: ArtifactLayout, updates: dict[str, Any]) -> None:
        current: dict[str, Any] = {}
        if layout.run_manifest.exists():
            with layout.run_manifest.open("r", encoding="utf-8") as source:
                current = json.load(source)
        current.setdefault("schema_version", 1)
        current.update(updates)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        DialoguePipeline._write_manifest(layout, current)

    @staticmethod
    def _write_manifest(layout: ArtifactLayout, manifest: dict[str, Any]) -> None:
        layout.run_manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = layout.run_manifest.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.write("\n")
        temporary.replace(layout.run_manifest)
