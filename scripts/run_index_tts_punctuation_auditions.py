"""Compare only IndexTTS punctuation modes with fixed references and acting.

These are backend regression probes, not new cleaning/polish annotations.
Existing accepted audition jobs retain their labels. The mixed-mark probe uses
an explicitly neutral test condition on a cited game line.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import time
import wave

from lessons_in_cast_core.characters import load_characters
from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.hashing import content_hash, file_hash
from lessons_in_cast_core.model_registry import load_model_registry
from lessons_in_cast_core.synthesis.profiles import load_voice_profile
from lessons_in_cast_core.synthesis.types import TtsJob


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_listening_sheet(output, manifest):
    rows = ["# IndexTTS punctuation comparison", "",
            "Same reference, seed and emotion for each row. Only the IndexTTS punctuation mode changes.", "",
            "| Probe | Original (`native`) | Comma | Period |", "| --- | --- | --- | --- |"]
    names = manifest.get("probes", ("02-happy", "03-angry", "mixed-question"))
    for name in names:
        takes = {item["mode"]: item for item in manifest["cases"] if item["id"].startswith(name + "-")}
        cells = [f"[{takes[mode]['seconds']:.2f}s]({takes[mode]['audio']})" if mode in takes else "Pending"
                 for mode in ("native", "comma", "period")]
        rows.append("| " + " | ".join([name, *cells]) + " |")
    rows.extend(["", "Compare phrase boundaries after exclamation and question marks in the selected probes.", "",
                 "Longer total duration is not proof of better timing. Native silence is retained; no endpoint trimming was applied.", "",
                 "See each adaptation and component frontend JSON for the supplied text, emotion and actual model token segments.", ""])
    (output / "README.md").write_text("\n".join(rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="index-tts-punctuation-v1")
    parser.add_argument("--case", action="append", choices=("02-happy", "03-angry", "mixed-question", "ami-sensei"),
                        help="Select individual probes; defaults to the original three-case comparison")
    args = parser.parse_args()
    from lessons_in_cast_core.audition.types import slug
    slug(args.run)
    root = Path(__file__).resolve().parents[1]
    output = root / "build/auditions" / args.run
    output.mkdir(parents=True, exist_ok=False)
    entry = root / "profiles/a_index_tts_emotion_audition/pipeline.py"
    pipeline = load_voice_profile(root, entry, character=load_characters(repository_root=root)["a"],
        project_config=load_pipeline_config(repository_root=root), model_registry=load_model_registry(repository_root=root))
    cases = []
    selected = args.case or ["02-happy", "03-angry", "mixed-question"]
    for name in ("02-happy", "03-angry"):
        if name not in selected:
            continue
        source = root / "build/auditions/ami-emotion-range-v1/takes" / f"{name}.job.json"
        cases.append((name, TtsJob.from_dict(json.loads(source.read_text())), str(source.relative_to(root))))
    # Keep the probe's text auditable against the exact game source.
    from lessons_in_cast_core.config import load_workspace_config
    if "mixed-question" in selected:
        script = load_workspace_config(repository_root=root).release_path / "game/AmiEvents.rpy"
        text = "Really?! You'll go on a date with me?!"
        line = next(i for i, value in enumerate(script.read_text().splitlines(), 1) if f'a "{text}"' in value)
        cases.append(("mixed-question", TtsJob("mixed-question", "punctuation-probe", "a", text, "neutral", {}, "unused.wav", "probe"),
                      f"game/AmiEvents.rpy:{line}; neutral regression test condition, not a polish prediction"))
    if "ami-sensei" in selected:
        source = root / "build/runs/amnesia-ami-maya-demo/tts_jobs.jsonl"
        with source.open() as stream:
            original = next(item for row in stream if (item := json.loads(row))["dialogue_id"] == "57d4f42ee22e46a94ed3c285")
        # Reuse the historical spoken text and semantic label under the current
        # profile's vector mapping. The retired scalar intensity is not a vector.
        job = TtsJob("ami-sensei", original["dialogue_id"], original["character_id"], original["text"],
                     original["emotion"], original["delivery"], "unused.wav", original["cache_key"])
        cases.append(("ami-sensei", job, f"{source.relative_to(root)}; game/script.rpy:572; "
                      "historical text/label with current profile settings, not a bit-identical demo1 reproduction"))
    manifest = {"profile": str(entry.relative_to(root)), "probes": [name for name, _, _ in cases],
                "cases": [], "status": "running"}
    try:
        dependencies = pipeline.prepare()
        manifest["references"] = {str(p): file_hash(p) for p in dependencies}
        backend = pipeline._backend  # Deliberately backend-specific diagnostic harness.
        for mode in ("native", "comma", "period"):
            backend.set_expressive_pause(mode)
            for name, original, source in cases:
                identifier = f"{name}-{mode}"
                key = content_hash({"job": original.to_dict(), "backend": pipeline.configuration})
                job = replace(original, id=identifier, output_path=str(output / f"{identifier}.wav"), cache_key=key)
                save(output / f"{identifier}.job.json", job.to_dict())
                save(output / f"{identifier}.adaptation.json", pipeline.adapt(job).to_dict())
                print(f"Rendering {identifier}", flush=True)
                started = time.monotonic()
                path = pipeline.render(job, output)
                with wave.open(str(path)) as audio:
                    duration = audio.getnframes() / audio.getframerate()
                manifest["cases"].append({"id": identifier, "source": source, "text": original.text, "mode": mode,
                    "audio": path.name, "seconds": duration, "wall_seconds": time.monotonic()-started, "sha256": file_hash(path)})
                save(output / "manifest.json", manifest)
        manifest["status"] = "complete"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        save(output / "manifest.json", manifest)
        write_listening_sheet(output, manifest)
        pipeline.close()


if __name__ == "__main__":
    main()
