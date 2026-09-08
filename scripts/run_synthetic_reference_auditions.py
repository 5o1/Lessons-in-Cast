"""Compare direct and second-generation references with local IndexTTS."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from run_all_profile_auditions import create_backend, profile_configuration, write_json
from lessons_in_cast_core.model_registry import load_model_registry
from lessons_in_cast_core.synthesis.types import TtsJob


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audio_info(path: Path) -> dict:
    with wave.open(str(path)) as reader:
        if reader.getsampwidth() != 2 or reader.getnchannels() != 1 or reader.getnframes() == 0:
            raise ValueError(f"Expected nonempty mono PCM16 audio: {path}")
        return {"sample_rate": reader.getframerate(), "frames": reader.getnframes(),
                "seconds": reader.getnframes() / reader.getframerate(), "sha256": digest(path)}


def crop_reference(source: Path, output: Path, seconds: float) -> None:
    with wave.open(str(source)) as reader:
        params = reader.getparams()
        count = min(reader.getnframes(), round(seconds * reader.getframerate()))
        frames = reader.readframes(count)
    temporary = output.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)
    temporary.replace(output)


def montage(paths: list[Path], output: Path) -> None:
    parts = []
    params = None
    for path in paths:
        with wave.open(str(path)) as reader:
            current = reader.getparams()
            if params and current[:3] != params[:3]:
                raise ValueError("Montage inputs must share their PCM format")
            if parts:
                parts.append(b"\0" * round(current.framerate * 0.7) * current.nchannels * current.sampwidth)
            parts.append(reader.readframes(reader.getnframes()))
            params = current
    if params is None:
        raise ValueError("No montage inputs")
    with wave.open(str(output), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(b"".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    output_root = plan_path.parent
    if not output_root.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Audition plans and outputs must live under build/")
    plan = json.loads(plan_path.read_text())
    config, config_path, original = profile_configuration(ROOT, plan["profile"])
    if any(not row.get("text", "").strip() for row in plan["reference_lines"] + plan["test_lines"]):
        raise ValueError("All audition texts must be nonempty")
    # Model loading and synthesis stay local; never silently download dependencies.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    backend = create_backend(ROOT, config, {plan["character"]: (original,)})
    original_info = audio_info(original)
    settings = {
        "plan": plan, "profile_configuration": asdict(config),
        "profile_sha256": digest(config_path),
        "pronunciations_sha256": digest(ROOT / "configs/pronunciations.toml"),
        "original_reference": {"path": str(original), **original_info},
        "model": load_model_registry(repository_root=ROOT).require(config.model_id).to_dict(),
        "backend": backend.configuration,
        "rights_status": "Derived from the existing reference; no rights clearance inferred from synthesis.",
        "source_assets": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
                          for path in sorted((config_path.parent / "assets/reference_sources").glob("*.wav"))],
    }
    total = len(plan["reference_lines"]) + 3 * len(plan["test_lines"])
    print(json.dumps({"jobs": total, "original_reference_seconds": original_info["seconds"],
                      "output": str(output_root), "external_api_calls": False}), flush=True)
    if args.dry_run:
        backend.close()
        return 0
    subprocess.run([str(ROOT / config.python_executable), "-c",
                    "import torch; assert torch.cuda.is_available(), 'CUDA unavailable; refusing CPU synthesis'"], check=True)
    settings_path = output_root / "experiment.json"
    if settings_path.exists() and json.loads(settings_path.read_text()) != settings:
        raise ValueError("Experiment inputs changed; choose a new output directory")
    write_json(settings_path, settings)
    records = []
    manifest = {"status": "running", "completed_jobs": 0, "total_jobs": total,
                "results": records, "human_listening_status": "pending"}
    manifest_path = output_root / "manifest.json"
    write_json(manifest_path, manifest)

    def render(group: str, row: dict, reference: Path) -> Path:
        output = output_root / group / f"{row['id']}.wav"
        specification = {"text": row["text"], "reference": str(reference), "reference_sha256": digest(reference),
                         "experiment_sha256": digest(settings_path), "emotion": "neutral"}
        request_path = output.with_suffix(".request.json")
        metadata_path = output.with_suffix(".json")
        if request_path.exists() and json.loads(request_path.read_text()) != specification:
            raise ValueError(f"Cached request mismatch: {output}")
        if output.exists() and not request_path.exists():
            raise ValueError(f"Unattributed existing output: {output}")
        if output.exists() and metadata_path.exists():
            previous = json.loads(metadata_path.read_text())
            if previous["audio"]["sha256"] != digest(output):
                raise ValueError(f"Cached audio changed: {output}")
        write_json(request_path, specification)
        reused = output.exists()
        print(f"[{len(records)+1}/{total}] {group}/{row['id']} {'cached' if reused else 'render'}", flush=True)
        key = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()
        job = TtsJob(id=f"{group}-{row['id']}", dialogue_id=row["id"], character_id=plan["character"],
                     text=row["text"], emotion="neutral", delivery={},
                     output_path=str(output), cache_key=key)
        started = time.monotonic()
        backend.set_references(plan["character"], (reference,))
        backend.synthesize(job, ROOT)
        record = {"group": group, "id": row["id"], "path": str(output), "text": row["text"],
                  "audio": audio_info(output), "reused": reused,
                  "elapsed_seconds": round(time.monotonic()-started, 3)}
        write_json(metadata_path, record)
        records.append(record)
        manifest["completed_jobs"] = len(records)
        write_json(manifest_path, manifest)
        print(f"Completed: {group}/{row['id']} ({record['audio']['seconds']:.2f}s)", flush=True)
        return output

    try:
        sources = [render("synthetic-sources", row, original) for row in plan["reference_lines"]]
        references = output_root / "references"
        references.mkdir(exist_ok=True)
        full = references / "synthetic-full.wav"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), environment.get("PYTHONPATH", "")])
        timing = config.reference_settings
        command = [str(ROOT / config.python_executable), "-m", "lessons_in_cast_core.synthesis.references.cli",
                   "--output", str(full), "--top-db", str(timing.top_db),
                   "--padding-ms", str(timing.padding_ms), "--gate-hold-ms", str(timing.gate_hold_ms),
                   "--minimum-speech-seconds", str(timing.minimum_speech_seconds),
                   "--minimum-duration-seconds", str(timing.minimum_duration_seconds)]
        for source in sources:
            command.extend(["--source", str(source)])
        if not timing.trim_silence:
            command.append("--no-trim-silence")
        result = subprocess.run(command, env=environment, text=True, stdout=subprocess.PIPE, check=True)
        write_json(references / "build.json", json.loads(result.stdout))
        matched = references / "synthetic-duration-matched.wav"
        crop_reference(full, matched, original_info["seconds"])
        if audio_info(matched)["seconds"] + 1/48000 < original_info["seconds"]:
            raise RuntimeError("Synthetic audio is too short for the duration-matched control")
        manifest["references"] = {
            "original": {"path": str(original), **original_info},
            "synthetic_matched": {"path": str(matched), **audio_info(matched)},
            "synthetic_full": {"path": str(full), **audio_info(full)},
            "note": "IndexTTS internally limits the speaker prompt; the full reference is not all consumed.",
        }
        write_json(manifest_path, manifest)
        for group, reference in [("01-direct", original), ("02-synthetic-matched", matched), ("03-synthetic-full", full)]:
            clips = [render(group, row, reference) for row in plan["test_lines"]]
            montage(clips, output_root / f"{group}.wav")
        manifest["status"] = "complete"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(manifest_path, manifest)
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
