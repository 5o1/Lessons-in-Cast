"""Run a local H3 audition in the background after external setup finishes.

This does not install packages, download weights, rewrite polish, or use a cloud
API. Start those explicit setup steps first. All lifecycle records live in build.
"""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from lessons_in_cast_core.audition.types import slug
from lessons_in_cast_core.model_registry import load_model_registry
from lessons_in_cast_core.synthesis.backends.minimax_h3.client import ComfyClient, save_json
from lessons_in_cast_core.synthesis.backends.minimax_h3.config import load_config


def environment_ready(source):
    python = source / ".venv/bin/python"
    if not python.is_file():
        return False
    packages = [re.split(r"[<=>!~\[;\s]", line.strip())[0]
                for line in (source / "requirements.txt").read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    code = "from importlib.metadata import distribution; import sys; [distribution(p) for p in sys.argv[1:]]"
    return subprocess.run([str(python), "-c", code, *packages], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=30).returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("auditions/ami/emotion-range/project.json"))
    parser.add_argument("--cleaning", type=Path, default=Path("build/auditions/ami-emotion-range-v1-cleaning"))
    parser.add_argument("--profile", type=Path, default=Path("profiles/a_minimax_h3/pipeline.py"))
    parser.add_argument("--reference-audio", type=Path)
    parser.add_argument("--run", default="ami-emotion-range-minimax-h3-v1")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--wait-for-setup", action="store_true")
    parser.add_argument("--setup-timeout", type=float, default=43200)
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args()
    slug(args.run)
    if not 0 < args.setup_timeout <= 86400:
        parser.error("--setup-timeout must be between 0 and 86400 seconds")
    root = Path(__file__).resolve().parents[1]
    lifecycle = root / "build/backends/minimax-h3/runs" / args.run
    lifecycle.mkdir(parents=True, exist_ok=True)
    if args.detach:
        command = [sys.executable, str(Path(__file__).resolve()), *(v for v in sys.argv[1:] if v != "--detach")]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        environment["PYTHONUNBUFFERED"] = "1"
        with (lifecycle / "runner.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({"pid": process.pid, "log": str(lifecycle / "runner.log"),
                          "state": str(lifecycle / "state.json")}, indent=2))
        return 0
    lock = lifecycle / "runner.lock"
    try:
        with lock.open("x") as output:
            output.write(str(os.getpid()))
    except FileExistsError:
        raise RuntimeError(f"Runner already owns {lock}; inspect it before starting another process")
    state = {"pid": os.getpid(), "run": args.run}
    worker = None
    def update(status, **extra):
        state.update(status=status, **extra)
        save_json(lifecycle / "state.json", state)
        print(json.dumps(state), flush=True)
    try:
        config_path = (root / args.profile).parent / "config.toml"
        config = load_config(config_path)
        source = root / config.source_directory
        registry = load_model_registry(repository_root=root)
        models = registry.resolve_path(config.model_id)
        deadline = time.monotonic() + args.setup_timeout
        while True:
            model_ready = (models / "verified.json").is_file()
            env_ready = environment_ready(source)
            if model_ready and env_ready:
                break
            update("waiting_for_setup", models_verified=model_ready, environment_ready=env_ready)
            if not args.wait_for_setup or time.monotonic() >= deadline:
                raise RuntimeError("Complete the documented H3 weight/environment setup first")
            time.sleep(30)
        client = ComfyClient(config.endpoint)
        try:
            client.request("/system_stats")
        except OSError:
            pass
        else:
            raise RuntimeError("H3 endpoint already has a worker; use the normal audition CLI to reuse it")
        # Own a new process group, so only this runner's dedicated worker is stopped.
        command = [sys.executable, "-m", "lessons_in_cast_core.synthesis.backends.minimax_h3", "serve",
                   "--profile-config", str(config_path)]
        with (lifecycle / "worker.log").open("ab") as log:
            worker = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, start_new_session=True)
        update("starting_worker", worker_pid=worker.pid, endpoint=config.endpoint)
        ready_deadline = time.monotonic() + 180
        while time.monotonic() < ready_deadline:
            if worker.poll() is not None:
                raise RuntimeError(f"H3 worker exited; inspect {lifecycle / 'worker.log'}")
            try:
                client.request("/system_stats")
                break
            except OSError:
                time.sleep(2)
        else:
            raise TimeoutError("H3 worker did not become ready")
        update("rendering")
        # Import the rendering core in a fresh process after potentially hours of
        # setup, so code fingerprints describe the code that actually executes.
        render_command = [sys.executable, "-m", "lessons_in_cast_core.audition", "render", str(root / args.project),
                          "--cleaning", str(root / args.cleaning), "--run", args.run, "--profile", str(args.profile),
                          "--candidate", "minimax-h3-ref2va-fp8"]
        if args.reference_audio:
            render_command.extend(["--reference-audio", str(root / args.reference_audio)])
        for case in args.case:
            render_command.extend(["--case", case])
        subprocess.run(render_command, cwd=root, check=True)
        output = root / "build/auditions" / args.run
        update("complete", output=str(output))
        return 0
    except Exception as exc:
        # A timed-out request may still be running; do not destroy its queue/history.
        update("failed", error=f"{type(exc).__name__}: {exc}", worker_left_running=worker is not None and worker.poll() is None)
        raise
    finally:
        if state.get("status") == "complete" and worker is not None and worker.poll() is None:
            os.killpg(worker.pid, signal.SIGTERM)
            try:
                worker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                print(f"Worker group {worker.pid} has not exited; inspect before stopping manually", flush=True)
        lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
