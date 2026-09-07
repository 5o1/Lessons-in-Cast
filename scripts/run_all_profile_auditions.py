#!/usr/bin/env python3
"""Render five resumable, neutral audition lines for every voice profile."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable
import wave


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from lessons_in_cast_core.characters import load_characters  # noqa: E402
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
    IndexTtsPipelineConfig,
    load_index_tts_pipeline_config,
)
from lessons_in_cast_core.synthesis.types import TtsJob  # noqa: E402


DEFAULT_INPUT = Path("build/current/raw.jsonl")
DEFAULT_OUTPUT = Path("build/auditions/all-character-profiles-5-lines")
TARGET_LINE_COUNT = 5
SAFE_TEXT = re.compile(r"^[\x20-\x7e]+$")
SPECIAL_TEXT = re.compile(r"[\[\]{}<>]|https?://|www\.", re.IGNORECASE)
EXPLICIT_TEXT = re.compile(
    r"\b(?:"
    r"bastard|bitch|boob|breast|cock|cum|cunt|dick|douchenozzle|fuck|"
    r"masturbat|moan|naked|nude|orgasm|penis|perv|prick|pussy|sex|shit|"
    r"underwear|vagina"
    r")\w*\b|\bbare skin\b|\brub mine\b|\btouchy-feely\b",
    re.IGNORECASE,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    result.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--character", action="append", dest="characters")
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


def acceptable_text(text: str) -> bool:
    words = text.split()
    return (
        16 <= len(text) <= 180
        and 4 <= len(words) <= 28
        and SAFE_TEXT.fullmatch(text) is not None
        and SPECIAL_TEXT.search(text) is None
        and EXPLICIT_TEXT.search(text) is None
        and "..." not in text
        and not text.isupper()
        and any(character.isalpha() for character in text)
    )


def choose_lines(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose one readable line from each fifth of a character's timeline."""

    candidates = [row for row in rows if acceptable_text(row["dialogue"].strip())]
    if len(candidates) < TARGET_LINE_COUNT:
        raise ValueError(f"only {len(candidates)} clean audition lines are available")
    selected: list[dict[str, Any]] = []
    for bucket in range(TARGET_LINE_COUNT):
        start = len(candidates) * bucket // TARGET_LINE_COUNT
        end = len(candidates) * (bucket + 1) // TARGET_LINE_COUNT
        choices = candidates[start:end]
        choice = min(
            choices,
            key=lambda row: (
                abs(len(row["dialogue"].strip()) - 72),
                row["sequence"],
            ),
        )
        selected.append(choice)
    return selected


def read_selections(
    path: Path,
    character_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            character_id = row.get("character")
            if character_id in character_ids:
                rows[character_id].append(row)
    missing = sorted(character_ids - rows.keys())
    if missing:
        raise ValueError(f"No dialogue rows found for: {', '.join(missing)}")
    return {character_id: choose_lines(rows[character_id]) for character_id in sorted(rows)}


def profile_configuration(
    root: Path,
    entrypoint: str,
) -> tuple[IndexTtsPipelineConfig, Path, Path]:
    profile_root = resolve(root, Path(entrypoint)).parent
    config_path = profile_root / "config.toml"
    config = load_index_tts_pipeline_config(config_path, repository_root=root)
    resolver = profile_root if config.reference_scope == "profile" else root
    reference = (resolver / config.reference_path).resolve()
    return config, config_path, reference


def backend_signature(config: IndexTtsPipelineConfig) -> str:
    value = asdict(config)
    for name in (
        "reference_source_directory",
        "reference_scope",
        "reference_sources",
        "reference_path",
        "reference_settings",
    ):
        value.pop(name)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def create_backend(
    root: Path,
    config: IndexTtsPipelineConfig,
    references: dict[str, tuple[Path, ...]],
) -> IndexTtsSubprocessSynthesizer:
    project = load_pipeline_config(repository_root=root)
    registry = load_model_registry(repository_root=root)
    pronunciations = load_pronunciation_lexicon(
        repository_root=root
    ).for_system("arpabet")
    settings = config.reference_settings
    return IndexTtsSubprocessSynthesizer(
        repository_root=root,
        python_executable=(root / config.python_executable).absolute(),
        source_root=(root / config.source_root).absolute(),
        model_path=registry.resolve_path(config.model_id),
        references=references,
        audio_config=replace(
            project.audio,
            format=project.audio.intermediate_format,
        ),
        base_speed=config.base_speed,
        language=config.language,
        seed=config.seed,
        use_bf16=config.use_bf16,
        prepare_references=False,
        trim_reference_silence=settings.trim_silence,
        reference_trim_top_db=settings.top_db,
        reference_trim_padding_ms=settings.padding_ms,
        reference_gate_hold_ms=settings.gate_hold_ms,
        minimum_reference_speech_seconds=settings.minimum_speech_seconds,
        minimum_reference_duration_seconds=settings.minimum_duration_seconds,
        emotion_alpha=config.emotion_alpha,
        use_random_emotion=config.use_random_emotion,
        do_sample=config.do_sample,
        top_p=config.top_p,
        top_k=config.top_k,
        temperature=config.temperature,
        num_beams=config.num_beams,
        repetition_penalty=config.repetition_penalty,
        length_penalty=config.length_penalty,
        max_mel_tokens=config.max_mel_tokens,
        interval_silence_ms=config.interval_silence_ms,
        max_text_tokens_per_segment=config.max_text_tokens_per_segment,
        text_normalization=config.text_normalization,
        pronunciations=pronunciations,
    )


def join_wavs(paths: Iterable[Path], destination: Path, silence_ms: int = 500) -> None:
    paths = tuple(paths)
    with wave.open(str(paths[0]), "rb") as first:
        parameters = first.getparams()
    silence = b"\0" * (
        round(parameters.framerate * silence_ms / 1000)
        * parameters.nchannels
        * parameters.sampwidth
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as output:
        output.setparams(parameters)
        for index, path in enumerate(paths):
            with wave.open(str(path), "rb") as source:
                current = source.getparams()
                if (
                    current.nchannels,
                    current.sampwidth,
                    current.framerate,
                    current.comptype,
                ) != (
                    parameters.nchannels,
                    parameters.sampwidth,
                    parameters.framerate,
                    parameters.comptype,
                ):
                    raise ValueError(f"Incompatible WAV parameters: {path}")
                if index:
                    output.writeframes(silence)
                output.writeframes(source.readframes(current.nframes))
    os.replace(temporary, destination)


def write_index(output: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# All-character voice-profile auditions",
        "",
        "Five real game lines per character, rendered with neutral emotion and each character's configured profile.",
        "",
    ]
    for item in manifest["characters"]:
        directory = item["directory"]
        lines.extend((
            f'## {item["name"]} (`{item["id"]}`) — {item["state"]}',
            "",
            f'- Combined preview: [all-five.wav]({directory}/all-five.wav)',
            "",
        ))
        for line in item["lines"]:
            lines.append(
                f'{line["index"]}. [{line["text"]}]({line["audio"]}) '
                f'— `{line["filename"]}:{line["line_number"]}`'
            )
        lines.append("")
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parser().parse_args()
    root = find_repository_root(REPOSITORY_ROOT)
    input_path = resolve(root, args.input)
    output = resolve(root, args.output_dir)
    output.relative_to(root)
    characters = load_characters(repository_root=root)
    configured = {
        character_id: character
        for character_id, character in characters.items()
        if character.default_voice_profile
    }
    if args.characters:
        requested = set(args.characters)
        unknown = sorted(requested - configured.keys())
        if unknown:
            raise ValueError(f"Characters lack configured profiles: {', '.join(unknown)}")
        configured = {key: value for key, value in configured.items() if key in requested}

    selections = read_selections(input_path, set(configured))
    groups: dict[str, list[tuple[str, Any, IndexTtsPipelineConfig, Path, Path]]] = defaultdict(list)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "input": str(input_path),
        "line_selection": "One clean, approximately 72-character line from each fifth of the character timeline.",
        "emotion": "neutral",
        "intensity": 0.0,
        "line_count_per_character": TARGET_LINE_COUNT,
        "characters": [],
    }
    records: dict[str, dict[str, Any]] = {}
    for character_id, character in sorted(configured.items()):
        config, config_path, reference = profile_configuration(
            root, character.default_voice_profile
        )
        if not reference.is_file():
            raise FileNotFoundError(f"Prepared reference is missing: {reference}")
        group_key = backend_signature(config)
        groups[group_key].append((character_id, character, config, config_path, reference))
        directory_name = f"{character_id}-{character.name.lower().replace(' ', '-')}"
        lines = []
        for index, row in enumerate(selections[character_id], 1):
            relative_audio = f"{directory_name}/{index:02d}.wav"
            lines.append({
                "index": index,
                "dialogue_id": row["id"],
                "identifier": row["identifier"],
                "text": row["dialogue"].strip(),
                "filename": row["filename"],
                "line_number": row["line_number"],
                "audio": relative_audio,
                "state": "pending",
            })
        record = {
            "id": character_id,
            "name": character.name,
            "profile": character.default_voice_profile,
            "profile_config": str(config_path),
            "reference": str(reference),
            "directory": directory_name,
            "state": "pending",
            "lines": lines,
        }
        manifest["characters"].append(record)
        records[character_id] = record

    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    progress_path = output / "progress.jsonl"
    write_json(manifest_path, manifest)
    write_index(output, manifest)
    total = len(configured) * TARGET_LINE_COUNT
    completed = 0
    failures = 0
    for group_number, members in enumerate(groups.values(), 1):
        references = {item[0]: (item[4],) for item in members}
        backend = create_backend(root, members[0][2], references)
        print(
            f"backend group {group_number}/{len(groups)}: {len(members)} characters",
            flush=True,
        )
        try:
            for character_id, character, _config, _config_path, reference in members:
                record = records[character_id]
                character_paths = []
                for line in record["lines"]:
                    completed += 1
                    destination = output / line["audio"]
                    if args.force:
                        destination.unlink(missing_ok=True)
                    existed = destination.is_file()
                    job = TtsJob(
                        id=f'audition-{character_id}-{line["dialogue_id"]}',
                        dialogue_id=line["dialogue_id"],
                        character_id=character_id,
                        text=line["text"],
                        emotion="neutral",
                        intensity=0.0,
                        delivery={},
                        output_path=str(destination.relative_to(root)),
                        cache_key=hashlib.sha256(
                            f'{character_id}\0{line["dialogue_id"]}\0{line["text"]}\0{reference}'.encode()
                        ).hexdigest(),
                        voice_profile=character.default_voice_profile,
                    )
                    started = time.monotonic()
                    action = "resume" if existed else "render"
                    print(
                        f'[{completed}/{total}] {character_id} line {line["index"]}: {action}',
                        flush=True,
                    )
                    try:
                        backend.synthesize(job, root)
                        line["state"] = "complete"
                        line["reused"] = existed
                        line["elapsed_seconds"] = round(time.monotonic() - started, 3)
                        character_paths.append(destination)
                    except Exception as exc:  # Continue so the batch is resumable.
                        failures += 1
                        line["state"] = "failed"
                        line["error"] = f"{type(exc).__name__}: {exc}"
                    with progress_path.open("a", encoding="utf-8") as progress:
                        progress.write(json.dumps({
                            "character": character_id,
                            **line,
                        }, ensure_ascii=False) + "\n")
                    write_json(manifest_path, manifest)
                if len(character_paths) == TARGET_LINE_COUNT:
                    join_wavs(
                        character_paths,
                        output / record["directory"] / "all-five.wav",
                    )
                    record["state"] = "complete"
                else:
                    record["state"] = "failed"
                write_json(manifest_path, manifest)
                write_index(output, manifest)
                print(f'{character_id}: {record["state"]}', flush=True)
        finally:
            backend.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
