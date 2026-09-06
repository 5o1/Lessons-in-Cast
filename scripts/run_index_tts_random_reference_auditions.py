#!/usr/bin/env python3
"""Build random reference bundles and render deterministic IndexTTS previews."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

from run_index_tts_reference_auditions import (
    REPOSITORY_ROOT,
    create_backend,
    resolve,
    write_index,
    write_json,
)

from lessons_in_cast_core.config import find_repository_root
from lessons_in_cast_core.synthesis.backends.index_tts.config import (
    load_index_tts_pipeline_config,
)
from lessons_in_cast_core.synthesis.references.builder import (
    ReferenceBuildError,
    prepare_reference_sources,
)
from lessons_in_cast_core.synthesis.types import TtsJob


DEFAULT_TEXT = "Just kidding. Please give Chinami a little sister."


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--profile-config",
        type=Path,
        default=Path("profiles/ch_index_tts/config.toml"),
    )
    result.add_argument(
        "--sample-dir",
        type=Path,
        default=Path("temp/KleeJPGPTSoVits/KleeSamples"),
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "build/auditions/index-tts-random-sample-bundles"
        ),
    )
    result.add_argument("--count", type=int, default=6)
    result.add_argument("--random-seed", type=int, default=20260906)
    result.add_argument("--text", default=DEFAULT_TEXT)
    result.add_argument("--character-id", default="ch")
    result.add_argument("--force", action="store_true")
    return result


def build_random_references(
    sample_directory: Path,
    output_directory: Path,
    profile_path: Path,
    root: Path,
    count: int,
    random_seed: int,
) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("Reference bundle count must be positive")
    candidates = sorted(sample_directory.glob("*.wav"))
    if not candidates:
        raise FileNotFoundError(
            f"No WAV samples found in {sample_directory}"
        )

    settings = load_index_tts_pipeline_config(
        profile_path,
        repository_root=root,
    ).reference_settings
    generator = random.Random(random_seed)
    generator.shuffle(candidates)
    cursor = 0
    auditions: list[dict[str, Any]] = []

    for number in range(1, count + 1):
        selected: list[Path] = []
        result = None
        while result is None:
            if cursor >= len(candidates):
                raise RuntimeError(
                    "Random sample pool was exhausted before all bundles "
                    "satisfied the reference constraints"
                )
            selected.append(candidates[cursor])
            cursor += 1
            destination = (
                output_directory / f"{number:02d}-random-bundle.wav"
            )
            try:
                result = prepare_reference_sources(
                    selected,
                    destination,
                    settings,
                )
            except ReferenceBuildError:
                continue

        auditions.append(
            {
                "id": f"{number:02d}-random-bundle",
                "description": (
                    f"{len(result.selected_paths)} randomly selected clips; "
                    f"{result.voiced_seconds:.3f}s detected speech and "
                    f"{result.prepared_duration_seconds:.3f}s prepared audio."
                ),
                "reference": str(result.output_path),
                "reference_sha256": hashlib.sha256(
                    result.output_path.read_bytes()
                ).hexdigest(),
                "selected_samples": [
                    str(path) for path in result.selected_paths
                ],
                "source_duration_seconds": round(
                    result.source_duration_seconds,
                    6,
                ),
                "voiced_seconds": round(result.voiced_seconds, 6),
                "duration_seconds": round(
                    result.prepared_duration_seconds,
                    6,
                ),
            }
        )
    return auditions


def main() -> int:
    args = parser().parse_args()
    root = find_repository_root(REPOSITORY_ROOT)
    profile_path = resolve(root, args.profile_config)
    sample_directory = resolve(root, args.sample_dir)
    output_directory = resolve(root, args.output_dir)
    output_directory.relative_to(root)
    output_directory.mkdir(parents=True, exist_ok=True)

    auditions = build_random_references(
        sample_directory,
        output_directory / "references",
        profile_path,
        root,
        args.count,
        args.random_seed,
    )
    backend, metadata = create_backend(
        root,
        profile_path,
        Path(auditions[0]["reference"]),
        args.character_id,
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "random-reference-sample-bundles",
        "sample_directory": str(sample_directory),
        "sample_count": len(tuple(sample_directory.glob("*.wav"))),
        "random_seed": args.random_seed,
        "selection_policy": (
            "Shuffle once with the recorded seed, consume samples without "
            "replacement, and stop each bundle when silence-gated prepared "
            "duration reaches the profile minimum."
        ),
        "text": args.text,
        "emotion": "neutral",
        "intensity": 0.0,
        **metadata,
        "auditions": auditions,
    }
    manifest_path = output_directory / "manifest.json"
    progress_path = output_directory / "progress.jsonl"
    write_json(manifest_path, manifest)
    write_index(output_directory, manifest)

    failures = 0
    try:
        for index, item in enumerate(auditions, start=1):
            preview = (
                output_directory / "previews" / f"{item['id']}.wav"
            )
            existed = preview.is_file() and not args.force
            if args.force:
                preview.unlink(missing_ok=True)
            job = TtsJob(
                id=f"audition-{item['id']}",
                dialogue_id=f"audition-{item['id']}",
                character_id=args.character_id,
                text=args.text,
                emotion="neutral",
                intensity=0.0,
                delivery={},
                output_path=str(preview.relative_to(root)),
                cache_key=hashlib.sha256(
                    (
                        f"{item['reference_sha256']}\0{args.text}"
                        f"\0neutral\0{args.character_id}"
                    ).encode()
                ).hexdigest(),
            )
            started = time.monotonic()
            action = "resume" if existed else "render"
            print(
                f"[{index}/{len(auditions)}] {item['id']}: {action}",
                flush=True,
            )
            try:
                backend.set_references(
                    args.character_id,
                    (Path(item["reference"]),),
                )
                backend.synthesize(job, root)
                item["state"] = "complete"
                item["reused_existing_preview"] = existed
                item["preview"] = str(preview)
                item["elapsed_seconds"] = round(
                    time.monotonic() - started,
                    3,
                )
            except Exception as exc:
                failures += 1
                item["state"] = "failed"
                item["error"] = f"{type(exc).__name__}: {exc}"
            with progress_path.open("a", encoding="utf-8") as progress:
                progress.write(json.dumps(item, ensure_ascii=False) + "\n")
            write_json(manifest_path, manifest)
            write_index(output_directory, manifest)
            print(
                f"[{index}/{len(auditions)}] "
                f"{item['id']}: {item['state']}",
                flush=True,
            )
    finally:
        backend.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
