"""Clone a local reference once, then run the normal validated audition renderer.

New clones require --allow-clone and a separate pay-as-you-go credential.
Cached clones need only a TTS key, which may be a Token Plan subscription key.
Credentials are never saved. Uncertain POSTs are never automatically retried.
"""

import argparse
from dataclasses import replace
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
from urllib.parse import urlsplit
import uuid
import wave

from lessons_in_cast_core.audition.rendering import render_project, save
from lessons_in_cast_core.characters import load_characters
from lessons_in_cast_core.config import load_pipeline_config
from lessons_in_cast_core.hashing import file_hash
from lessons_in_cast_core.model_registry import load_model_registry
from lessons_in_cast_core.synthesis.backends.minimax.config import load_minimax_pipeline_config
from lessons_in_cast_core.synthesis.profiles.loader import load_voice_profile
from lessons_in_cast_core.synthesis.types import TtsJob


def successful(response):
    if response.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"MiniMax rejected request: {response.get('base_resp')}")
    return response


def cached_post(directory, name, metadata, request, key):
    request_path = directory / f"{name}.request.json"
    response_path = directory / f"{name}.response.json"
    if request_path.exists():
        if json.loads(request_path.read_text()) != metadata:
            raise ValueError(f"Changed {name} inputs; existing cache is preserved")
        if response_path.exists():
            return successful(json.loads(response_path.read_text()))
        raise RuntimeError(f"Uncertain previous {name} POST; inspect server state before retrying")
    if response_path.exists():
        raise ValueError(f"Orphan {name} response; no matching request record")
    save(request_path, metadata)
    print(f"MiniMax: {name}", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.load(response)
        save(response_path, data)
        return successful(data)
    except Exception as exc:
        save(directory / f"{name}.error.json", {
            "error": str(exc).replace(key, "[REDACTED]"), "automatic_retry": False,
        })
        raise


def reuse_clone(cache, base_url, voice_id, source, source_name):
    """Validate the complete local clone provenance without credentials/network."""
    if not (cache / "clone.response.json").exists():
        return False
    upload_request = json.loads((cache / "upload.request.json").read_text())
    expected_upload = {"endpoint": base_url + "/files/upload", "purpose": "voice_clone",
                       "source": source_name, "sha256": file_hash(source)}
    if upload_request != expected_upload or file_hash(cache / "reference.wav") != file_hash(source):
        raise ValueError("Cached clone reference or endpoint changed")
    upload = successful(json.loads((cache / "upload.response.json").read_text()))
    expected_clone = {"endpoint": base_url + "/voice_clone", "payload": {
        "file_id": int(upload["file"]["file_id"]), "voice_id": voice_id,
        "need_noise_reduction": False, "need_volume_normalization": False,
    }}
    if json.loads((cache / "clone.request.json").read_text()) != expected_clone:
        raise ValueError("Cached clone identity or settings changed")
    cloned = successful(json.loads((cache / "clone.response.json").read_text()))
    if cloned.get("input_sensitive"):
        raise RuntimeError("MiniMax rejected the cloning input; no synthesis attempted")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--allow-clone", action="store_true")
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument("--clone-key-env", default="MINIMAX_PAYG_API_KEY")
    parser.add_argument("--prompt-clone-key", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plan = json.loads(args.plan.read_text())
    def rooted(value):
        result = (root / value).resolve()
        if not result.is_relative_to(root):
            raise ValueError("Plan paths must stay inside the workspace")
        return result
    profile_path = rooted(plan["profile"])
    config = load_minimax_pipeline_config(profile_path.parent / "config.toml", repository_root=root)
    endpoint = urlsplit(config.endpoint)
    if endpoint.scheme != "https" or endpoint.netloc not in {
        "api.minimaxi.com", "api.minimax.cn", "api.minimax.io",
    } or endpoint.path != "/v1/t2a_v2" or endpoint.query or endpoint.fragment:
        raise ValueError("Use an official MiniMax T2A endpoint")
    base_url = f"https://{endpoint.netloc}/v1"
    source = rooted(plan["reference"])
    if file_hash(source) != plan["reference_sha256"]:
        raise ValueError("Reference changed; update the plan and clone identity explicitly")
    with wave.open(str(source)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    if not 10 <= duration <= 300 or source.stat().st_size >= 20 * 1024 * 1024:
        raise ValueError("Cloning requires a 10..300 second WAV under 20 MiB")
    project_config = load_pipeline_config(repository_root=root)
    project_config = replace(project_config, audio=replace(project_config.audio, format="wav"))
    # MiniMax serves at most 44.1 kHz; a 48 kHz project needs local conversion.
    subprocess.run([project_config.audio.ffmpeg_executable, "-version"],
                   check=True, capture_output=True)
    profile = load_voice_profile(root, profile_path, load_characters(repository_root=root)[plan["character"]],
                                 project_config, model_registry=load_model_registry(repository_root=root))
    # Compile every existing comparison job before any potentially billable call.
    originals = sorted(rooted(plan["comparison_run"]).glob("takes/*.job.json"))
    if len(originals) != plan["case_count"]:
        raise ValueError("The comparison run does not contain every expected case")
    for path in originals:
        profile.adapt(TtsJob.from_dict(json.loads(path.read_text())))
    profile.close()
    print(json.dumps({"voice_id": config.voice_id, "reference_seconds": duration,
                      "cases": len(originals), "model": config.model_id,
                      "unchanged_reference_sha256": file_hash(source)}), flush=True)
    if args.dry_run:
        return 0
    key = getpass.getpass("MiniMax TTS key (subscription or PAYG): ") if args.prompt_key else os.environ.get(config.api_key_environment, "")
    if not key:
        raise ValueError(f"Set {config.api_key_environment} or use --prompt-key for TTS")
    cache = profile_path.parent / "assets/clone"
    cache.mkdir(parents=True, exist_ok=True)
    lock = cache / ".clone.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        cached_clone = reuse_clone(cache, base_url, config.voice_id, source, plan["reference"])
        if cached_clone:
            print("MiniMax: reusing verified clone; no upload, clone call or PAYG key required", flush=True)
        else:
            if not args.allow_clone:
                raise ValueError("No completed clone cache; --allow-clone is required for a new upload/clone")
            clone_key = getpass.getpass("MiniMax PAYG key for cloning: ") if args.prompt_clone_key else os.environ.get(args.clone_key_env, "")
            if not clone_key or clone_key.startswith("sk-cp-"):
                raise ValueError("Voice cloning needs a separate PAYG key; Token Plan supports TTS, not new clones")
            create_clone(cache, source, plan["reference"], base_url, config.voice_id, clone_key)
    finally:
        lock.unlink()
    os.environ[config.api_key_environment] = key
    output = render_project(root, rooted(plan["project"]), plan["run"],
        cleaning=rooted(plan["cleaning"]), profile=profile_path, candidate="minimax-reference-clone")
    save(cache / "activation.json", {"voice_id": config.voice_id, "successful_audition": str(output),
                                    "tts_billing_route": "subscription" if key.startswith("sk-cp-") else "payg"})
    print(json.dumps({"output": str(output)}), flush=True)
    return 0


def create_clone(cache, source, source_name, base_url, voice_id, key):
    """Upload/clone only after separate explicit authorization and credentials."""
    reference_copy = cache / "reference.wav"
    if reference_copy.exists() and file_hash(reference_copy) != file_hash(source):
        raise ValueError("Cached reference differs; refusing to overwrite it")
    if not reference_copy.exists():
        shutil.copy2(source, reference_copy)
    boundary = "lic-" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nvoice_clone\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="reference.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n').encode() + reference_copy.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    uploaded = cached_post(cache, "upload", {
        "endpoint": base_url + "/files/upload", "purpose": "voice_clone",
        "source": source_name, "sha256": file_hash(reference_copy),
    }, urllib.request.Request(base_url + "/files/upload", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": f"multipart/form-data; boundary={boundary}",
    }), key)
    payload = {"file_id": int(uploaded["file"]["file_id"]), "voice_id": voice_id,
               "need_noise_reduction": False, "need_volume_normalization": False}
    cloned = cached_post(cache, "clone", {"endpoint": base_url + "/voice_clone", "payload": payload},
        urllib.request.Request(base_url + "/voice_clone", data=json.dumps(payload).encode(), headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
        }), key)
    if cloned.get("input_sensitive"):
        raise RuntimeError("MiniMax rejected the cloning input; no synthesis attempted")


if __name__ == "__main__":
    raise SystemExit(main())
