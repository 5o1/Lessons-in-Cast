"""Download and verify the four pinned components of the local H3 audio backend."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen


REPOSITORY = "Comfy-Org/MiniMax-H3"
REVISION = "a98869194787969724c7425d95d0ed73ce9202af"
FILES = {
    "diffusion_models/minimax_h3_ref2va_pruned_fp8_scaled.safetensors": "f86f2f79ebd2d76eb8eeb46091e83982e6ff51d255747e7b16e92834b392b8e9",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors": "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
    "vae/minimax_h3_audio_vae_fp32.safetensors": "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48",
    "vae/minimax_h3_video_vae_fp16.safetensors": "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522",
}
SIZES = (20958205608, 15687142551, 605254808, 5207808496)


def download_ranges(target, workers):
    """Bound each HTTP response so proxy resets do not discard a huge transfer."""
    chunk_size = 16 * 1024 * 1024
    pieces = target / ".range-download"
    tasks = []
    for (name, digest), size in zip(FILES.items(), SIZES):
        if (target / name).is_file() and (target / name).stat().st_size == size:
            continue
        directory = pieces / digest
        directory.mkdir(parents=True, exist_ok=True)
        for start in range(0, size, chunk_size):
            end = min(start + chunk_size, size) - 1
            path = directory / str(start)
            if not path.is_file() or path.stat().st_size != end - start + 1:
                tasks.append((name, start, end, size, path))

    def fetch(task):
        name, start, end, size, path = task
        url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
        for attempt in range(12):
            try:
                request = Request(url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"})
                with urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Server did not honor the exact requested range")
                    temporary = path.with_suffix(".partial")
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(response, output, 1024 * 1024)
                if temporary.stat().st_size != end - start + 1:
                    raise ValueError("Truncated range response")
                temporary.replace(path)
                return end - start + 1
            except Exception as exc:
                if attempt == 11:
                    raise RuntimeError(f"Range failed: {name} at {start}: {type(exc).__name__}") from exc
                time.sleep(min(2 ** attempt, 15))

    print(f"Downloading {len(tasks)} missing 16 MiB ranges with {workers} workers", flush=True)
    completed_bytes = 0
    report_time = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(fetch, task) for task in tasks]
        for number, future in enumerate(as_completed(pending), 1):
            completed_bytes += future.result()
            if time.monotonic() - report_time >= 20 or number == len(tasks):
                print(f"Ranges {number}/{len(tasks)}; received {completed_bytes / 1e9:.2f} GB this run", flush=True)
                report_time = time.monotonic()
    for (name, digest), size in zip(FILES.items(), SIZES):
        destination = target / name
        if destination.is_file() and destination.stat().st_size == size:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".assembling")
        with temporary.open("wb") as output:
            for start in range(0, size, chunk_size):
                with (pieces / digest / str(start)).open("rb") as source:
                    shutil.copyfileobj(source, output, 8 * 1024 * 1024)
        with temporary.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise ValueError(f"Assembled SHA-256 mismatch: {name}; retain range pieces for diagnosis")
        temporary.replace(destination)
        for start in range(0, size, chunk_size):
            (pieces / digest / str(start)).unlink()
        print(f"Assembled and verified {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy")
    parser.add_argument("--disable-xet", action="store_true", help="Use resumable HTTP when the proxy cannot reliably transfer Xet chunks")
    parser.add_argument("--range-workers", type=int, default=0, help="Use resumable bounded HTTP ranges with 1–16 workers instead of the Hub downloader")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ[name] = args.proxy
    os.environ.setdefault("HF_HOME", str(root / "build/cache/huggingface"))
    if args.disable_xet:
        os.environ["HF_HUB_DISABLE_XET"] = "1"
    target = root / "models/Comfy-Org/MiniMax-H3"
    if not 0 <= args.range_workers <= 16:
        parser.error("--range-workers must be between 0 and 16")
    if args.range_workers:
        download_ranges(target, args.range_workers)
    else:
        from huggingface_hub import snapshot_download
        snapshot_download(REPOSITORY, revision=REVISION, allow_patterns=list(FILES),
                          local_dir=target, max_workers=4)
    manifest = {"repository": REPOSITORY, "revision": REVISION, "files": {}}
    for name, expected in FILES.items():
        path = target / name
        print(f"Verifying {name}", flush=True)
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch: {name}")
        stat = path.stat()
        manifest["files"][name] = {"sha256": actual, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    target.mkdir(parents=True, exist_ok=True)
    temporary = target / "verified.partial.json"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(target / "verified.json")
    print("H3 component verification complete", flush=True)


if __name__ == "__main__":
    main()
