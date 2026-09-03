"""Command-line entry point for reproducible pipeline stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .annotation import MockDialogueAnnotator
from .characters import load_characters
from .config import (
    find_repository_root,
    load_dialogue_sources,
    load_pipeline_config,
    load_workspace_config,
)
from .evaluation import evaluate_annotations
from .pipeline import ArtifactLayout, DialoguePipeline, PipelineRequest
from .renpy import DialogueExtractionRequest, SubprocessDialogueExtractor
from .synthesis import SilenceSynthesizer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lessons-in-cast")
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root; discovered automatically by default.",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("artifacts"),
        help="Pipeline artifact directory relative to the repository root.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="Validate all project configuration.")
    extract = commands.add_parser("extract", help="Generate dialogue.tab with Ren'Py.")
    extract.add_argument("--launcher", type=Path)
    extract.add_argument("--language")
    prepare = commands.add_parser(
        "prepare",
        help="Convert dialogue.tab to raw JSONL and model requests.",
    )
    prepare.add_argument("--input", type=Path)
    annotate_mock = commands.add_parser(
        "annotate-mock",
        help="Write deterministic mock responses.",
    )
    annotate_mock.add_argument("--retry", action="store_true")
    validate = commands.add_parser(
        "validate",
        help="Validate model responses and apply overrides.",
    )
    validate.add_argument("--retry", action="store_true")
    commands.add_parser("plan-tts", help="Create cached TTS and render jobs.")
    commands.add_parser("synthesize-mock", help="Generate silent WAV test artifacts.")
    commands.add_parser("bundle", help="Build a game-relative voice release bundle.")
    evaluate = commands.add_parser(
        "evaluate",
        help="Compare validated annotations with a human gold set.",
    )
    evaluate.add_argument("--gold", type=Path, required=True)
    run = commands.add_parser("run-mock", help="Run all stages with deterministic mocks.")
    run.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = (args.root or find_repository_root()).resolve()
    artifact_root = args.artifacts
    if not artifact_root.is_absolute():
        artifact_root = root / artifact_root
    layout = ArtifactLayout(artifact_root.resolve())
    config = load_pipeline_config(repository_root=root)
    characters = load_characters(repository_root=root)
    sources = load_dialogue_sources(repository_root=root)

    if args.command == "check-config":
        workspace = load_workspace_config(repository_root=root)
        print(
            json.dumps(
                {
                    "release_path": str(workspace.release_path),
                    "dialogue_sources": len(sources),
                    "characters": len(characters),
                },
                indent=2,
            )
        )
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

    pipeline = DialoguePipeline(
        config=config,
        characters=characters,
        annotator=MockDialogueAnnotator(),
        synthesizer=SilenceSynthesizer(config.audio),
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
    elif args.command == "annotate-mock":
        count = pipeline.annotate(
            layout,
            requests_path=layout.retry_requests if args.retry else None,
            responses_path=layout.retry_responses if args.retry else None,
        )
        print(json.dumps({"response_count": count}))
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
    elif args.command == "synthesize-mock":
        jobs, rendered = pipeline.synthesize(layout)
        print(json.dumps({"tts_job_count": jobs, "rendered_count": rendered}))
    elif args.command == "bundle":
        print(json.dumps({"bundled_audio_count": pipeline.build_release_bundle(layout)}))
    elif args.command == "evaluate":
        gold_path = args.gold if args.gold.is_absolute() else root / args.gold
        print(
            json.dumps(
                evaluate_annotations(gold_path, layout.validated).to_dict(),
                indent=2,
            )
        )
    elif args.command == "run-mock":
        input_path = args.input if args.input.is_absolute() else root / args.input
        result = pipeline.run(
            PipelineRequest(
                artifact_root=layout.root,
                dialogue_tab_path=input_path,
                allowed_sources=sources,
                overrides_path=root / "configs" / "overrides.toml",
            )
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
                },
                indent=2,
            )
        )
    return 0
