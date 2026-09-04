"""Command-line entry point for reproducible pipeline stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .characters import CharacterDefinition, load_characters
from .config import (
    PipelineConfig,
    find_repository_root,
    load_dialogue_sources,
    load_pipeline_config,
    load_workspace_config,
)
from .pipeline import ArtifactLayout, DialoguePipeline, PipelineRequest
from .renpy import DialogueExtractionRequest, SubprocessDialogueExtractor
from .synthesis import (
    ReferenceBuildRequest,
    ReferenceVoicePipeline,
    VoicePipelineSynthesizer,
    load_configured_voice_pipelines,
    load_voice_pipeline,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lessons-in-cast")
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root; discovered automatically by default.",
    )
    parser.add_argument(
        "--build-dir",
        dest="build_dir",
        type=Path,
        default=Path("build/current"),
        help="Active run directory relative to the repository root.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="Validate all project configuration.")
    extract = commands.add_parser("extract", help="Generate dialogue.tab with Ren'Py.")
    extract.add_argument("--launcher", type=Path)
    extract.add_argument("--language")
    prepare = commands.add_parser(
        "prepare",
        help="Convert dialogue.tab to raw JSONL and annotation requests.",
    )
    prepare.add_argument("--input", type=Path)
    codex_next = commands.add_parser(
        "codex-next",
        help="Export the next continuous transcript packet for Codex.",
    )
    codex_next.add_argument("--retry", action="store_true")
    codex_next.add_argument("--batches-per-packet", type=int)
    codex_import = commands.add_parser(
        "codex-import",
        help="Import and split the active Codex packet response.",
    )
    codex_import.add_argument("--retry", action="store_true")
    codex_import.add_argument("--replace", action="store_true")
    codex_status = commands.add_parser(
        "codex-status",
        help="Report progress for the Codex annotation pass.",
    )
    codex_status.add_argument("--retry", action="store_true")
    validate = commands.add_parser(
        "validate",
        help="Validate annotation responses and apply overrides.",
    )
    validate.add_argument("--retry", action="store_true")
    commands.add_parser("plan-tts", help="Create cached TTS and render jobs.")
    commands.add_parser(
        "prepare-voices",
        help="Prepare generated dependencies for configured voice pipelines.",
    )
    commands.add_parser(
        "synthesize", help="Generate audio with configured voice pipelines."
    )
    build_reference = commands.add_parser(
        "build-reference",
        help="Build a character reference WAV from a sample-audio directory.",
    )
    build_reference.add_argument("--character", required=True)
    build_reference.add_argument("--input-dir", type=Path, required=True)
    build_reference.add_argument("--output", type=Path)
    commands.add_parser("bundle", help="Build a game-relative voice release bundle.")
    production = commands.add_parser(
        "run-production",
        help="Validate external annotations, synthesize, and build the Ren'Py bundle.",
    )
    production.add_argument("--input", type=Path, required=True)
    production.add_argument("--responses", type=Path, required=True)
    production.add_argument(
        "--cache-intermediates",
        action="store_true",
        help="Retain intermediate JSONL and audio after a successful run.",
    )
    return parser


def _voice_synthesizer(
    root: Path,
    config: PipelineConfig,
    characters: dict[str, CharacterDefinition],
) -> VoicePipelineSynthesizer:
    return load_configured_voice_pipelines(root, config, characters)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = (args.root or find_repository_root()).resolve()
    artifact_root = args.build_dir
    if not artifact_root.is_absolute():
        artifact_root = root / artifact_root
    layout = ArtifactLayout(artifact_root.resolve())
    config = load_pipeline_config(repository_root=root)
    characters = load_characters(repository_root=root)
    sources = load_dialogue_sources(repository_root=root)

    if args.command == "check-config":
        workspace = load_workspace_config(repository_root=root)
        voice_synthesizer = load_configured_voice_pipelines(
            root, config, characters
        )
        try:
            voice_pipeline_ids = sorted(
                voice_synthesizer.configuration["pipelines"]
            )
        finally:
            voice_synthesizer.close()
        print(
            json.dumps(
                {
                    "release_path": str(workspace.release_path),
                    "dialogue_sources": len(sources),
                    "characters": len(characters),
                    "voice_pipelines": voice_pipeline_ids,
                    "codex_batches_per_packet": config.codex.batches_per_packet,
                    "codex_source_files": list(config.codex.source_files),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "prepare-voices":
        voice_synthesizer = _voice_synthesizer(root, config, characters)
        try:
            prepared = voice_synthesizer.prepare()
        finally:
            voice_synthesizer.close()
        print(
            json.dumps(
                {key: [str(path) for path in paths] for key, paths in prepared.items()},
                indent=2,
            )
        )
        return 0

    if args.command == "build-reference":
        character = characters.get(args.character)
        if character is None:
            raise ValueError(f"Unknown character ID: {args.character!r}")
        if not character.generation_script_path:
            raise ValueError(
                f"Character {args.character!r} has no generation_script_path"
            )
        voice_pipeline = load_voice_pipeline(
            root,
            Path(character.generation_script_path),
            character,
            config,
        )
        if not isinstance(voice_pipeline, ReferenceVoicePipeline):
            voice_pipeline.close()
            raise TypeError(
                f"Voice pipeline for {character.id!r} does not build references"
            )
        default_request = voice_pipeline.default_reference_request
        input_directory = (
            args.input_dir
            if args.input_dir.is_absolute()
            else root / args.input_dir
        )
        output_path = args.output or default_request.output_path
        if not output_path.is_absolute():
            output_path = root / output_path
        try:
            result = voice_pipeline.build_reference(
                ReferenceBuildRequest(input_directory, output_path)
            )
        finally:
            voice_pipeline.close()
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.command == "extract":
        workspace = load_workspace_config(repository_root=root)
        launcher = args.launcher
        if launcher is not None and not launcher.is_absolute():
            launcher = root / launcher
        request = DialogueExtractionRequest(
            release_path=workspace.release_path,
            output_path=layout.dialogue_tab,
            source_paths=sources,
            language=args.language,
            launcher_path=launcher,
        )
        pipeline = DialoguePipeline(config=config, characters=characters)
        path = pipeline.extract(SubprocessDialogueExtractor(), request)
        print(path)
        return 0

    if args.command in {"codex-next", "codex-import", "codex-status"}:
        from .annotation import CodexAnnotationWorkflow, CodexWorkspace

        retry = args.retry
        requests_path = (
            layout.retry_requests if retry else layout.annotation_requests
        )
        responses_path = (
            layout.retry_responses if retry else layout.annotation_responses
        )
        workspace = CodexWorkspace(
            layout.root / "codex" / ("retry" if retry else "initial")
        )
        workflow = CodexAnnotationWorkflow(
            root / "prompts" / "codex_dialogue_cleanup.md",
            {
                character_id: character.name
                for character_id, character in characters.items()
            },
            config.codex.source_files,
        )
        if args.command == "codex-next":
            packet = workflow.export_next(
                requests_path,
                responses_path,
                workspace,
                batches_per_packet=(
                    args.batches_per_packet
                    if args.batches_per_packet is not None
                    else config.codex.batches_per_packet
                ),
            )
            print(json.dumps(packet.to_dict()))
        elif args.command == "codex-import":
            imported = workflow.import_outbox(
                requests_path,
                responses_path,
                workspace,
                replace=args.replace,
            )
            print(json.dumps({"imported_batches": imported}))
        else:
            print(json.dumps(workflow.status(requests_path, responses_path).to_dict()))
        return 0

    synthesizer = None
    if args.command in {"synthesize", "run-production"}:
        synthesizer = _voice_synthesizer(root, config, characters)
    pipeline = DialoguePipeline(
        config=config,
        characters=characters,
        synthesizer=synthesizer,
    )
    if args.command == "prepare":
        source = args.input or layout.dialogue_tab
        counts = pipeline.prepare(
            PipelineRequest(
                artifact_root=layout.root,
                dialogue_tab_path=source,
                allowed_sources=sources,
            )
        )
        print(json.dumps({"dialogue_count": counts[0], "batch_count": counts[1]}))
    elif args.command == "validate":
        summary = pipeline.validate(
            layout,
            overrides_path=root / "configs" / "overrides.toml",
            retry=args.retry,
        )
        print(json.dumps(summary.to_dict()))
    elif args.command == "plan-tts":
        jobs, renders = pipeline.plan_synthesis(layout)
        print(json.dumps({"tts_job_count": jobs, "render_task_count": renders}))
    elif args.command == "synthesize":
        jobs, rendered = pipeline.synthesize(layout)
        print(json.dumps({"tts_job_count": jobs, "rendered_count": rendered}))
    elif args.command == "bundle":
        print(
            json.dumps(
                {"bundled_audio_count": pipeline.build_release_bundle(layout)}
            )
        )
    elif args.command == "run-production":
        input_path = args.input if args.input.is_absolute() else root / args.input
        responses_path = (
            args.responses if args.responses.is_absolute() else root / args.responses
        )
        result = pipeline.run_from_responses(
            PipelineRequest(
                artifact_root=layout.root,
                dialogue_tab_path=input_path,
                allowed_sources=sources,
                overrides_path=root / "configs" / "overrides.toml",
            ),
            responses_path,
            cache_intermediates=args.cache_intermediates,
        )
        print(
            json.dumps(
                {
                    "dialogue_count": result.dialogue_count,
                    "batch_count": result.batch_count,
                    "accepted_count": result.accepted_count,
                    "review_count": result.review_count,
                    "retryable_count": result.retryable_count,
                    "rejected_count": result.rejected_count,
                    "tts_job_count": result.tts_job_count,
                    "rendered_count": result.rendered_count,
                    "release_bundle": str(result.artifacts.release_bundle),
                    "intermediates_cached": args.cache_intermediates,
                },
                indent=2,
            )
        )
    return 0
