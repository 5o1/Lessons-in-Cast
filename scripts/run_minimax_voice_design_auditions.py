"""Generate resumable text-only voice auditions without TTS voice activation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request
import wave


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--api-key-env", default="MINIMAX_API_KEY")
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    root = args.plan.resolve().parent
    endpoint = plan["endpoint"]
    if endpoint not in {
        "https://api.minimaxi.com/v1/voice_design",
        "https://api.minimax.cn/v1/voice_design",
        "https://api.minimax.io/v1/voice_design",
    }:
        raise ValueError("Use an official MiniMax voice-design endpoint")
    if args.limit < 1:
        raise ValueError("--limit must be positive")
    candidates = plan["candidates"][:args.limit]
    script = "\n".join(item["text"] for item in plan["lines"])
    if not 1 <= len(script) <= 500:
        raise ValueError("The voice-design preview must contain 1..500 characters")
    ids = [candidate["id"] for candidate in candidates]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z0-9-]+", item) for item in ids):
        raise ValueError("Candidate IDs must be unique safe directory names")
    requests = [(candidate, {
        "prompt": "\n\n".join([plan["identity_brief"], candidate["voice_description"], plan["preview_direction"]]),
        "preview_text": script,
    }) for candidate in candidates]
    # The service accepted 1990 characters but rejected 2001 in an actual request.
    if any(len(payload["prompt"]) > 2000 for _, payload in requests):
        raise ValueError("Keep combined voice-design prompts within 2000 characters")
    print(json.dumps({"candidates": ids, "characters_each": len(script),
                      "estimated_preview_cost_cny": round(len(script) * len(ids) * 2 / 10000, 4),
                      "activates_voice_ids": False}), flush=True)
    if args.dry_run:
        return 0
    # Check local conversion before making a potentially billable request.
    subprocess.run([args.ffmpeg, "-version"], check=True, stdout=subprocess.DEVNULL)
    key = getpass.getpass("MiniMax Speech API key (hidden): ") if args.prompt_key else os.environ.get(args.api_key_env, "")
    if not key or key.startswith("sk-cp-"):
        raise ValueError("A Speech API key is required, not a Coding Plan key")
    for candidate, payload in requests:
        directory = root / candidate["id"]
        directory.mkdir(exist_ok=True)
        request_path = directory / "request.json"
        response_path = directory / "response.json"
        if request_path.exists() and json.loads(request_path.read_text()) != payload:
            raise ValueError(f"Changed request for {candidate['id']}; choose a new output directory")
        if response_path.exists() and not request_path.exists():
            raise ValueError("Response cache has no matching request record")
        save_json(request_path, payload)
        if response_path.exists():
            response = json.loads(response_path.read_text())
            print(f"Reusing cached response: {candidate['id']}", flush=True)
        else:
            print(f"Generating: {candidate['id']}", flush=True)
            request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=180) as result:
                    response = json.load(result)
                if response.get("base_resp", {}).get("status_code") != 0:
                    raise RuntimeError(json.dumps(response.get("base_resp", {})))
                if not response.get("voice_id") or not response.get("trial_audio"):
                    raise RuntimeError("Missing voice_id or trial_audio in response")
            except (OSError, urllib.error.URLError, ValueError, RuntimeError) as exc:
                # No automatic POST retry: an uncertain response may already have been billed.
                error = {"candidate": candidate["id"], "message": str(exc).replace(key, "[REDACTED]"),
                         "automatic_retry": False, "time": datetime.now(timezone.utc).isoformat()}
                save_json(directory / "error.json", error)
                print(json.dumps(error), flush=True)
                return 1
            save_json(response_path, response)
            save_json(directory / "generation.json", {
                "created_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint,
                "voice_id": response["voice_id"], "activated_by_tts": False,
                "external_reference_uploaded": False,
            })
        original = directory / "preview-original.audio"
        if not original.exists():
            original.write_bytes(bytes.fromhex(response["trial_audio"]))
        output = directory / "preview.wav"
        if not output.exists():
            subprocess.run([args.ffmpeg, "-nostdin", "-v", "error", "-n", "-i", str(original),
                            "-c:a", "pcm_s16le", str(output)], check=True)
        with wave.open(str(output)) as wav:
            duration = wav.getnframes() / wav.getframerate()
            metadata = {"duration_seconds": duration, "sample_rate": wav.getframerate(),
                        "channels": wav.getnchannels(), "sample_width": wav.getsampwidth()}
        if duration <= 0:
            raise RuntimeError("Empty decoded preview")
        metadata.update({"voice_id": response["voice_id"], "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                         "human_listening_status": "pending", "source_audio": original.name,
                         "note": "Decoding to WAV does not improve the source audio quality."})
        save_json(directory / "audio-metadata.json", metadata)
        print(json.dumps({"candidate": candidate["id"], "audio": str(output),
                          "duration_seconds": round(duration, 3)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
