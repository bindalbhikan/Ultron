"""Runs a script the agent wrote, in a locked container, for a dynamic (ad-hoc) working.

The script gets only what the trusted caller copied in, and nothing else of the machine it runs on:

    /data   the input files, read-only
    /out    where it writes its results (xlsx, csv, png, txt), the only place it can write
    /tmp    scratch space in memory

No network, no secrets (the container starts with an empty environment), no other files of the host, an
unprivileged user, every Linux capability dropped, and limits on time, memory, CPU and processes. It runs the
host's own Python read-only (sys.base_prefix / sys.prefix mounted at the same paths), so it has exactly the
libraries of uv.lock: Polars, fastexcel / python-calamine, xlsxwriter, Pillow.

Needs Docker on Linux (GitHub's ubuntu runner has it). The container's base image is ULTRON_SANDBOX_IMAGE,
default ubuntu:24.04 (the runner's own system, so the mounted Python finds the same C library).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import env

log = logging.getLogger("ultron")

TIMEOUT = 240                 # seconds one script may run
OUTPUT_CHARS = 6000           # of its printed output, given back to the model
OUT_MAX_BYTES = 60 * 1024 * 1024
DEFAULT_IMAGE = "ubuntu:24.04"


@dataclass
class Result:
    code: int
    output: str
    files: list[Path] = field(default_factory=list)
    timed_out: bool = False


def image() -> str:
    return env("ULTRON_SANDBOX_IMAGE") or DEFAULT_IMAGE


def unavailable() -> str:
    """Why scripts cannot run on this machine; empty when they can."""
    if not sys.platform.startswith("linux"):
        return "dynamic workings run on GitHub's Linux runner only (this machine is not Linux)"
    if not shutil.which("docker"):
        return "Docker is not installed on this machine"
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Docker does not answer: {exc}"
    return "" if r.returncode == 0 else f"Docker does not answer: {r.stderr.strip()[:200]}"


def _mounts() -> list[str]:
    paths = {Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()}
    exe = Path(sys.executable).resolve()
    if not any(exe.is_relative_to(p) for p in paths):
        paths.add(exe.parent.parent)
    out = []
    for p in sorted(paths):
        out += ["-v", f"{p}:{p}:ro"]
    return out


def command(name: str, job: Path, data: Path, out: Path) -> list[str]:
    """The docker run line (kept separate so tests can check every limit is on it)."""
    return ["docker", "run", "--rm", "--name", name,
            "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=512m",
            "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "256", "--memory", "3g", "--cpus", "2",
            "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "TZ=Asia/Kolkata",
            "--env", "POLARS_MAX_THREADS=2",
            "-v", f"{job}:/job:ro", "-v", f"{data}:/data:ro", "-v", f"{out}:/out:rw",
            *_mounts(), "--workdir", "/out", image(),
            str(Path(sys.executable)), "-I", "/job/main.py"]


def run(script: str, data: Path, work: Path, timeout: int = TIMEOUT) -> Result:
    """Run `script` with `data` as /data; its results land in work/out. work must be new and empty."""
    reason = unavailable()
    if reason:
        raise RuntimeError(reason)
    job, out = work / "job", work / "out"
    job.mkdir(parents=True, exist_ok=False)
    out.mkdir()
    (job / "main.py").write_text(script, encoding="utf-8")
    for p in (job, job / "main.py", data, *data.rglob("*")):
        p.chmod(0o755 if p.is_dir() else 0o644)
    out.chmod(0o777)          # the container's user (nobody) writes here
    if subprocess.run(["docker", "image", "inspect", image()], capture_output=True, timeout=60).returncode:
        pulled = subprocess.run(["docker", "pull", "-q", image()], capture_output=True, text=True, timeout=300)
        if pulled.returncode:
            raise RuntimeError(f"the sandbox image {image()} could not be pulled: {pulled.stderr.strip()[:200]}")
    name = f"ultron-adhoc-{uuid.uuid4().hex[:12]}"
    try:
        r = subprocess.run(command(name, job, data, out), capture_output=True, timeout=timeout,
                           env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
        code, text, timed_out = r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        code, timed_out = 124, True
        text = ((exc.stdout or b"") + (exc.stderr or b"")).decode("utf-8", "replace")
        text += f"\nStopped: the script ran longer than {timeout} seconds."
    files = sorted(p for p in out.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    if total > OUT_MAX_BYTES:
        text += f"\nThe results were {total:,} bytes, over {OUT_MAX_BYTES:,}: none kept."
        for p in files:
            p.unlink()
        files = []
    if len(text) > OUTPUT_CHARS:
        text = f"({len(text) - OUTPUT_CHARS} earlier characters cut) ...\n" + text[-OUTPUT_CHARS:]
    log.info("Sandbox script ended with %s, %d result files", code, len(files))
    return Result(code, text, files, timed_out)
