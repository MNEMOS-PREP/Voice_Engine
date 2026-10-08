"""Make every interviewer's portrait and talking head, resuming where it stopped.

    python scripts/make_faces.py [--only ID ...] [--portraits-only]

For each persona in `scripts/faces/portraits.json`: a portrait with FLUX.1-schnell
(stable-diffusion.cpp, the integrated GPU through Vulkan when it can, the CPU
when it cannot), then its head with `build_face.py`. One person at a time, so
faces arrive one by one, and at below-normal priority, so the laptop stays
usable while it runs (about 7 minutes a portrait and 2.5 a head here).

Portraits land in `.face_builder/portraits/` and heads in M11's `faces/`; both
are rebuilt only when missing. The prompt and seed reproduce each portrait.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / ".face_builder"
FLUX = BUILDER / "flux"
PORTRAITS = BUILDER / "portraits"
FACES = ROOT / "Backend" / "backend_M11_Voice_Engine" / "faces"
SPEC = Path(__file__).resolve().parent / "faces" / "portraits.json"
LOG = BUILDER / "make_faces.log"

#: Windows' BELOW_NORMAL_PRIORITY_CLASS: the student's own work comes first.
BELOW_NORMAL = 0x00004000 if sys.platform == "win32" else 0

#: What fits this laptop's 8 GB of shared GPU memory: the weights stream from
#: disk segment by segment, and the text encoder runs on the CPU. The VAE on
#: the GPU when it fits (a minute), the CPU when it does not (three).
FLUX_ARGS = [
    "--diffusion-model", "flux1-schnell-Q4_K_S.gguf",
    "--vae", "ae.safetensors",
    "--clip_l", "clip_l.safetensors",
    "--t5xxl", "t5xxl-Q4_K_M.gguf",
    "--cfg-scale", "1.0",
    "--sampling-method", "euler",
    "--mmap", "--params-backend", "disk", "--fa", "--vae-tiling",
]


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def seed_for(persona: str) -> int:
    """Stable per persona: the same prompt and seed make the same face."""
    return int(hashlib.sha1(persona.encode()).hexdigest()[:8], 16) % 2_000_000_000


def run(args: list[str], cwd: Path, log_to: Path) -> int:
    with log_to.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, creationflags=BELOW_NORMAL
        )
        return process.wait()


def portrait(persona: str, description: str, spec: dict) -> Path | None:
    target = PORTRAITS / f"{persona}.png"
    if target.exists():
        return target
    width, height = spec["size"]
    prompt = f"{description} {spec['suffix']}"
    common = [
        *FLUX_ARGS,
        "-p", prompt,
        "--steps", str(spec["steps"]),
        "-W", str(width),
        "-H", str(height),
        "--seed", str(seed_for(persona)),
        "-o", str(target),
    ]
    started = time.time()
    for backends, build in (("te=cpu", "sd-vulkan"), ("te=cpu,vae=cpu", "sd-vulkan"), ("", "sd-cpu")):
        args = [str(FLUX / build / "sd-cli.exe"), *common]
        if backends:
            args += ["--backend", backends]
        code = run(args, FLUX, BUILDER / "work" / f"{persona}.flux.log")
        if code == 0 and target.exists():
            log(f"{persona}: portrait in {time.time() - started:.0f} s ({build}, {backends or 'cpu'})")
            return target
        log(f"{persona}: portrait failed with {build} {backends or ''} (exit {code}); trying the next way")
    return None


def head(persona: str, picture: Path) -> bool:
    if (FACES / f"{persona}.zip").exists():
        return True
    started = time.time()
    python = BUILDER / "venv" / "Scripts" / "python.exe"
    code = run(
        [str(python), "-X", "utf8", str(ROOT / "scripts" / "build_face.py"), str(picture), "--persona", persona],
        ROOT,
        BUILDER / "work" / f"{persona}.build.log",
    )
    ok = code == 0 and (FACES / f"{persona}.zip").exists()
    log(f"{persona}: head {'built' if ok else f'FAILED (exit {code})'} in {time.time() - started:.0f} s")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", nargs="*", help="these persona ids only")
    parser.add_argument("--portraits-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    PORTRAITS.mkdir(parents=True, exist_ok=True)
    (BUILDER / "work").mkdir(parents=True, exist_ok=True)
    wanted = [p for p in spec["personas"] if not args.only or p in args.only]
    log(f"making {len(wanted)} interviewer(s)")
    for persona in wanted:
        picture = portrait(persona, spec["personas"][persona], spec)
        if picture is None or args.portraits_only:
            continue
        head(persona, picture)
    done = sum((FACES / f"{p}.zip").exists() for p in wanted)
    log(f"finished: {done} of {len(wanted)} heads")


if __name__ == "__main__":
    main()
