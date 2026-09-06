#!/usr/bin/env python3
"""Run resumable, deterministic IndexTTS reference-window auditions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from lessons_in_cast_core.config import (  # noqa: E402
    find_repository_root,
    load_pipeline_config,
)
from lessons_in_cast_core.model_registry import load_model_registry  # noqa: E402
from lessons_in_cast_core.pronunciations import (  # noqa: E402
    load_pronunciation_lexicon,
)
from lessons_in_cast_core.synthesis.backends.index_tts import (  # noqa: E402
    IndexTtsSubprocessSynthesizer,
)
from lessons_in_cast_core.synthesis.backends.index_tts.config import (  # noqa: E402
    load_index_tts_pipeline_config,
)
from lessons_in_cast_core.synthesis.types import TtsJob  # noqa: E402


DEFAULT_TEXT = "Just kidding. Please give Chinami a little sister."


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--profile-config",
        type=Path,
        default=Path("profiles/ch_index_tts/config.toml"),
    )
    result.add_argument(
        "--reference",
        type=Path,
        default=Path("build/references/ch.wav"),
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/auditions/index-tts-reference-windows"),
    )
    result.add_argument("--text", default=DEFAULT_TEXT)
    result.add_argument("--character-id", default="ch")
    result.add_argument("--force", action="store_true")
    return result


def resolve(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_wav(destination: Path, parameters: Any, frames: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as output:
        output.setparams(parameters)
        output.writeframes(frames)
    os.replace(temporary, destination)


def build_reference_windows(
    source: Path,
    output_directory: Path,
    seconds: float = 15.0,
) -> list[dict[str, Any]]:
    """Build four exact-length windows while preserving the PCM data."""

    with wave.open(str(source), "rb") as input_audio:
        parameters = input_audio.getparams()
        if parameters.nchannels != 1 or parameters.sampwidth != 2:
            raise ValueError("The prepared reference must be mono 16-bit PCM WAV")
        all_frames = input_audio.readframes(parameters.nframes)
    frame_width = parameters.nchannels * parameters.sampwidth
    limit = round(parameters.framerate * seconds)
    if parameters.nframes < limit:
        raise ValueError(
            f"Reference is {parameters.nframes / parameters.framerate:.2f}s; "
            f"at least {seconds:.2f}s is required"
        )

    def frames(start: int, end: int) -> bytes:
        return all_frames[start * frame_width : end * frame_width]

    midpoint = parameters.nframes // 2
    half_limit = limit // 2
    rotated = frames(midpoint, parameters.nframes) + frames(0, midpoint)
    variants = (
        (
            "01-first-15s",
            "First 15 seconds; equivalent to the current IndexTTS truncation.",
            frames(0, limit),
        ),
        (
            "02-last-15s",
            "Final 15 seconds of the prepared reference.",
            frames(parameters.nframes - limit, parameters.nframes),
        ),
        (
            "03-halves-swapped",
            "Reference rotated at its midpoint, then capped at 15 seconds.",
            rotated[: limit * frame_width],
        ),
        (
            "04-first-last-balanced",
            "First 7.5 seconds followed by the final 7.5 seconds.",
            frames(0, half_limit)
            + frames(
                parameters.nframes - (limit - half_limit),
                parameters.nframes,
            ),
        ),
    )
    result: list[dict[str, Any]] = []
    for identifier, description, audio_frames in variants:
        destination = output_directory / f"{identifier}.wav"
        write_wav(destination, parameters, audio_frames)
        result.append(
            {
                "id": identifier,
                "description": description,
                "reference": str(destination),
                "duration_seconds": round(
                    len(audio_frames) / frame_width / parameters.framerate,
                    6,
                ),
            }
        )
    return result


def create_backend(
    root: Path,
    profile_path: Path,
    source: Path,
    character_id: str,
) -> tuple[IndexTtsSubprocessSynthesizer, dict[str, Any]]:
    profile = load_index_tts_pipeline_config(
        profile_path,
        repository_root=root,
    )
    project = load_pipeline_config(repository_root=root)
    registry = load_model_registry(repository_root=root)
    pronunciations = load_pronunciation_lexicon(
        repository_root=root
    ).for_system("arpabet")
    model = registry.require(profile.model_id)
    model_path = registry.resolve_path(profile.model_id)
    repository_path = lambda value: (root / value).absolute()
    settings = profile.reference_settings
    backend = IndexTtsSubprocessSynthesizer(
        repository_root=root,
        python_executable=repository_path(profile.python_executable),
        source_root=repository_path(profile.source_root),
        model_path=model_path,
        references={character_id: (source,)},
        audio_config=project.audio,
        base_speed=profile.base_speed,
        language=profile.language,
        seed=profile.seed,
        use_bf16=profile.use_bf16,
        prepare_references=False,
        trim_reference_silence=settings.trim_silence,
        reference_trim_top_db=settings.top_db,
        reference_trim_padding_ms=settings.padding_ms,
        reference_gate_hold_ms=settings.gate_hold_ms,
        minimum_reference_speech_seconds=settings.minimum_speech_seconds,
        minimum_reference_duration_seconds=settings.minimum_duration_seconds,
        emotion_alpha=profile.emotion_alpha,
        use_random_emotion=profile.use_random_emotion,
        do_sample=profile.do_sample,
        top_p=profile.top_p,
        top_k=profile.top_k,
        temperature=profile.temperature,
        num_beams=profile.num_beams,
        repetition_penalty=profile.repetition_penalty,
        length_penalty=profile.length_penalty,
        max_mel_tokens=profile.max_mel_tokens,
        interval_silence_ms=profile.interval_silence_ms,
        max_text_tokens_per_segment=profile.max_text_tokens_per_segment,
        text_normalization=profile.text_normalization,
        pronunciations=pronunciations,
    )
    return backend, {
        "profile_config": str(profile_path),
        "model": model.to_dict(),
        "backend": backend.configuration,
    }


def write_index(output_directory: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# IndexTTS {manifest.get('experiment', 'reference-window')} auditions",
        "",
        f"Text: {manifest['text']}",
        "",
        (
            "All previews use neutral emotion, intensity 0, a fixed seed, "
            "deterministic decoding, and the profile base speed."
        ),
        "",
    ]
    for item in manifest["auditions"]:
        identifier = item["id"]
        lines.extend(
            (
                f"## {identifier} — {item.get('state', 'pending')}",
                "",
                item["description"],
                "",
                f"- Preview: [{identifier}.wav](previews/{identifier}.wav)",
                f"- Reference: [{identifier}.wav](references/{identifier}.wav)",
                "",
            )
        )
    (output_directory / "README.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> int:
    args = parser().parse_args()
    root = find_repository_root(REPOSITORY_ROOT)
    profile_path = resolve(root, args.profile_config)
    source = resolve(root, args.reference)
    output_directory = resolve(root, args.output_dir)
    output_directory.relative_to(root)
    if not source.is_file():
        raise FileNotFoundError(f"Prepared reference is missing: {source}")

    output_directory.mkdir(parents=True, exist_ok=True)
    variants = build_reference_windows(
        source,
        output_directory / "references",
    )
    backend, metadata = create_backend(
        root,
        profile_path,
        source,
        args.character_id,
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_reference": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_limitation": (
            "The original sample directory is unavailable; all variants are "
            "derived from the existing prepared reference."
        ),
        "text": args.text,
        "emotion": "neutral",
        "intensity": 0.0,
        **metadata,
        "auditions": variants,
    }
    manifest_path = output_directory / "manifest.json"
    progress_path = output_directory / "progress.jsonl"
    write_json(manifest_path, manifest)
    write_index(output_directory, manifest)

    failures = 0
    try:
        for index, item in enumerate(manifest["auditions"], start=1):
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
                    f"{item['id']}\0{args.text}\0neutral\0{source}".encode()
                ).hexdigest(),
            )
            started = time.monotonic()
            action = "resume" if existed else "render"
            print(
                f"[{index}/{len(variants)}] {item['id']}: {action}",
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
                f"[{index}/{len(variants)}] "
                f"{item['id']}: {item['state']}",
                flush=True,
            )
    finally:
        backend.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
