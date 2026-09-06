#!/usr/bin/env python3
"""Render controlled IndexTTS ARPABET pronunciation auditions."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from run_index_tts_reference_auditions import (
    REPOSITORY_ROOT,
    create_backend,
    resolve,
    write_json,
)

from lessons_in_cast_core.config import find_repository_root
from lessons_in_cast_core.synthesis.types import TtsJob


DEFAULT_TEXT = "Just kidding. Please give Chinami a little sister."
DEFAULT_REFERENCE = Path(
    "build/auditions/index-tts-bundle-06-reordered/"
    "references/06-stable-first.wav"
)
VARIANTS = (
    (
        "01-middle-primary",
        "CH IY0 . N AA1 . M IY0",
        "Primary stress on the middle syllable; current profile baseline.",
    ),
    (
        "02-initial-primary",
        "CH IY1 . N AA0 . M IY0",
        "Primary stress on the first syllable.",
    ),
    (
        "03-middle-secondary",
        "CH IY0 . N AA2 . M IY0",
        "Weaker secondary stress on the middle syllable.",
    ),
    (
        "04-no-primary-stress",
        "CH IY0 . N AA0 . M IY0",
        "No lexical primary stress; experimental flatter reading.",
    ),
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--profile-config",
        type=Path,
        default=Path("profiles/ch_index_tts/config.toml"),
    )
    result.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/auditions/index-tts-chinami-arpabet"),
    )
    result.add_argument("--text", default=DEFAULT_TEXT)
    result.add_argument("--word", default="Chinami")
    result.add_argument("--character-id", default="ch")
    result.add_argument("--force", action="store_true")
    return result


def write_index(output_directory: Path, manifest: dict[str, Any]) -> None:
    reference = Path(manifest["reference"])
    try:
        reference_link = reference.relative_to(output_directory)
    except ValueError:
        reference_link = Path("..") / reference.relative_to(
            output_directory.parent
        )
    lines = [
        "# IndexTTS Chinami ARPABET auditions",
        "",
        f"Text: {manifest['text']}",
        "",
        f"Fixed reference SHA-256: {manifest['reference_sha256']}",
        "",
        f"- Fixed reference: [06-stable-first.wav]({reference_link})",
        "",
    ]
    for item in manifest["auditions"]:
        identifier = item["id"]
        lines.extend(
            (
                f"## {identifier} — {item.get('state', 'pending')}",
                "",
                f"ARPABET: {item['arpabet']}",
                "",
                item["description"],
                "",
                f"- Preview: [{identifier}.wav](previews/{identifier}.wav)",
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
    reference = resolve(root, args.reference)
    output_directory = resolve(root, args.output_dir)
    output_directory.relative_to(root)
    if not reference.is_file():
        raise FileNotFoundError(f"Baseline reference is missing: {reference}")
    output_directory.mkdir(parents=True, exist_ok=True)

    backend, metadata = create_backend(
        root,
        profile_path,
        reference,
        args.character_id,
    )
    reference_sha256 = hashlib.sha256(reference.read_bytes()).hexdigest()
    auditions: list[dict[str, Any]] = [
        {
            "id": identifier,
            "arpabet": arpabet,
            "description": description,
            "state": "pending",
        }
        for identifier, arpabet, description in VARIANTS
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "chinami-arpabet-only",
        "only_variable": "pronunciations.Chinami",
        "reference": str(reference),
        "reference_sha256": reference_sha256,
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
                        f"{reference_sha256}\0{item['arpabet']}"
                        f"\0{args.text}\0neutral"
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
                backend.set_pronunciations(
                    {args.word: item["arpabet"]}
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
