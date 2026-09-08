#!/usr/bin/env python3
"""Run a resumable, fixed-reference delivery comparison in the VoxCPM2 environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lessons_in_cast_core.hashing import file_hash
from lessons_in_cast_core.model_registry import load_model_registry
from lessons_in_cast_core.voice_design import (
    VoiceDesignRequest, VoxCPM2Settings, VoxCPM2VoiceDesigner,
)


def save_json(path, data):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def montage(paths, destination):
    import numpy as np
    import soundfile as sf

    parts = []
    sample_rate = None
    for path in paths:
        audio, rate = sf.read(path, dtype="float32")
        if sample_rate is not None and sample_rate != rate:
            raise ValueError("Montage inputs must have the same sample rate")
        sample_rate = rate
        if parts:
            parts.append(np.zeros(round(rate * 0.7), dtype="float32"))
        parts.append(audio)
    sf.write(destination, np.concatenate(parts), sample_rate, subtype="PCM_16")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text("utf-8"))
    output_root = plan_path.parent
    reference = (ROOT / plan["reference_audio"]).resolve()
    source_manifest = (ROOT / plan["source_manifest"]).resolve()
    rows = json.loads(source_manifest.read_text("utf-8"))["results"]
    settings = VoxCPM2Settings(**plan["settings"])
    designer = VoxCPM2VoiceDesigner(
        load_model_registry(repository_root=ROOT), plan["model_id"], settings=settings,
    )
    reference_hash = file_hash(reference)
    report = {
        "plan": plan, "reference_sha256": reference_hash,
        "source_manifest_sha256": file_hash(source_manifest),
        "configuration": designer.configuration, "results": [],
    }
    completed = 0
    total = len(plan["variants"]) * len(rows)
    try:
        for variant in plan["variants"]:
            paths = []
            for row in rows:
                request = VoiceDesignRequest(
                    row["text"], variant["instruction"], reference, plan["seed"],
                )
                output = output_root / variant["id"] / f'{row["id"]}.wav'
                metadata_path = output.with_suffix(".json")
                expected = {
                    "text": request.text, "instruction": request.instruction,
                    "reference_audio": str(reference), "reference_sha256": reference_hash,
                    "seed": request.seed,
                }
                started = time.monotonic()
                if output.exists() and metadata_path.exists():
                    metadata = json.loads(metadata_path.read_text("utf-8"))
                    if (
                        metadata["request"] != expected
                        or metadata["configuration"] != designer.configuration
                        or metadata["audio"]["sha256"] != file_hash(output)
                    ):
                        raise ValueError(f"Existing audition does not match this run: {output}")
                else:
                    print(f"Generating {completed + 1}/{total}: {variant['id']}/{row['id']}", flush=True)
                    designer.generate(request, output)
                    metadata = json.loads(metadata_path.read_text("utf-8"))
                paths.append(output)
                completed += 1
                report["results"].append({
                    "variant": variant["id"], "line": row["id"], "text": row["text"],
                    "audio": str(output.relative_to(ROOT)),
                    "original_audio": row["path"],
                    "duration_seconds": metadata["audio"]["duration_seconds"],
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                save_json(output_root / "manifest.json", report)
                print(f"Completed {completed}/{total}: {output}", flush=True)
            montage(paths, output_root / f"{variant['id']}-all-five.wav")
        comparison_root = output_root / "by-line"
        comparison_root.mkdir(exist_ok=True)
        for row in rows:
            paths = [output_root / variant["id"] / f'{row["id"]}.wav' for variant in plan["variants"]]
            montage(paths, comparison_root / f'{row["id"]}-comparison.wav')
        report["complete"] = True
        save_json(output_root / "manifest.json", report)
    finally:
        designer.close()
    print(f"Finished: {output_root}", flush=True)


if __name__ == "__main__":
    main()
