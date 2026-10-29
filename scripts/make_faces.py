"""Make every interviewer's portrait and talking head, resuming where it stopped.

    python scripts/make_faces.py [--only ID ...] [--portraits-only] [--rebuild] [--stills]

For each persona in `scripts/faces/portraits.json`: a portrait — the team's
own (Avatar_Lab) where one is named, else FLUX.1-schnell through
stable-diffusion.cpp (the integrated GPU through Vulkan when it can, the CPU
when it cannot) — then its head and its still with `build_face.py`. One
person at a time, so faces arrive one by one, and at below-normal priority,
so the laptop stays usable while it runs (~4 minutes a portrait, ~3.5 a head).

A portrait that would make a poor head (mouth open, eyes shut, turned or
tilted: `build_face.portrait_check`) is made again with the next seed, up to
four times. `--rebuild` builds every head again into `faces/.staging` and
moves each into place only when it is whole, so the room never loses a face
while the batch runs. `--stills` makes the still for heads that have none,
from the portrait each head was made from.
Create `.face_builder/PAUSE` to hold the batch between steps (the voice's
latency is measured with the CPU to itself); delete it to go on. The batch
also holds by itself while an interview is on (M11's `/voice/activity`).

Portraits land in `.face_builder/portraits/` and heads in M11's `faces/`; both
are rebuilt only when missing (or with `--rebuild`). The prompt and seed
reproduce each portrait.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / ".face_builder"
FLUX = BUILDER / "flux"
PORTRAITS = BUILDER / "portraits"
FACES = ROOT / "Backend" / "backend_M11_Voice_Engine" / "faces"
STAGING = FACES / ".staging"
SPEC = Path(__file__).resolve().parent / "faces" / "portraits.json"
#: The persona files, beside this repo: the voice's kind and manner.
PERSONAS = ROOT.parent / "Mock_Interview_Engine" / "Backend" / "backend_M06_Mock_Interview_Engine" / "personas"
LOG = BUILDER / "make_faces.log"
PAUSE = BUILDER / "PAUSE"
ATTEMPTS = 4
#: M11, asked whether a student is waiting on the voice.
M11 = os.getenv("M11_URL", "http://127.0.0.1:8111")
#: Quiet this long (seconds) and the interview is over, or the student is
#: reading their notes: a question answered slowly is still under it.
QUIET_S = 300
REJECTED = 3  # build_face.py's exit code for a portrait that fails its check

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


def seed_for(persona: str, attempt: int = 0) -> int:
    """Stable per persona and attempt: the same prompt and seed make the same face."""
    base = int(hashlib.sha1(persona.encode()).hexdigest()[:8], 16)
    return (base + 7919 * attempt) % 2_000_000_000


def interview_on() -> bool:
    """A student waited on the voice in the last QUIET_S seconds (M11's
    `/voice/activity`). A mock recorded during a build heard 5 s and 14 s
    silences (2026-10-10): below-normal priority was not enough, the build
    still took the CPU the voice needed. M11 not running: nobody is waiting."""
    try:
        with urllib.request.urlopen(f"{M11}/v1/voice/activity", timeout=5) as response:
            ago = json.loads(response.read())["live_seconds_ago"]
    except (OSError, ValueError, KeyError):
        return False
    return ago is not None and ago < QUIET_S


def wait_while_paused() -> None:
    """Between steps: held while `.face_builder/PAUSE` exists, and while an
    interview is on."""
    if PAUSE.exists():
        log("paused (delete .face_builder/PAUSE to go on)")
        while PAUSE.exists():
            time.sleep(10)
        log("going on")
    if interview_on():
        log("an interview is on: waiting until the voice has been quiet for a while")
        while interview_on() or PAUSE.exists():
            time.sleep(15)
        log("going on")


def run(args: list[str], cwd: Path, log_to: Path) -> int:
    with log_to.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, creationflags=BELOW_NORMAL
        )
        return process.wait()


VOICE_ID = r"[a-z]{2}-[A-Z]{2}-([a-z]+)-([a-z]+)"


def voice_of(persona: str, entry: dict) -> tuple[str, str]:
    """(kind, manner) from the `voice_id` (`en-IN-female-warm`): the entry's own,
    for a face that is not an M06 interviewer (M16's counselors), else the
    persona file's."""
    if entry.get("voice_id"):
        match = re.fullmatch(VOICE_ID, entry["voice_id"])
        if not match:
            raise SystemExit(f"{persona}: voice_id {entry['voice_id']!r} is not like en-IN-female-warm")
        return match.group(1), match.group(2)
    text = (PERSONAS / f"{persona}.yaml").read_text(encoding="utf-8")
    match = re.search(rf"(?m)^voice_id:\s*{VOICE_ID}\s*$", text)
    if not match:
        raise SystemExit(f"{persona}: its persona file has no voice_id to read the face's kind from")
    return match.group(1), match.group(2)


def prompt_for(persona: str, entry: dict, spec: dict) -> str:
    kind, manner = voice_of(persona, entry)
    describe = entry["describe"]
    says = "woman" if re.search(r"\bwoman\b", describe) else "man" if re.search(r"\bman\b", describe) else None
    if says != {"female": "woman", "male": "man"}.get(kind):
        raise SystemExit(f"{persona}: the description says {says!r}, the voice is {kind!r}")
    return spec["template"].format(describe=describe, expression=spec["expressions"][manner])


def portrait(persona: str, entry: dict, spec: dict, attempt: int) -> Path | None:
    if "portrait" in entry:
        # The team's own: used as it is, whatever the attempt.
        source = (ROOT.parent / entry["portrait"]).resolve()
        if not source.exists():
            log(f"{persona}: the team's portrait {entry['portrait']} is not on disk (clone Avatar_Lab beside this repo)")
            return None
        target = PORTRAITS / f"{persona}{source.suffix.lower()}"
        if not target.exists():
            shutil.copyfile(source, target)
        return target
    target = PORTRAITS / f"{persona}.png"
    if target.exists():
        return target
    width, height = spec["size"]
    common = [
        *FLUX_ARGS,
        "-p", prompt_for(persona, entry, spec),
        "--steps", str(spec["steps"]),
        "-W", str(width),
        "-H", str(height),
        "--seed", str(seed_for(persona, attempt)),
        "-o", str(target),
    ]
    started = time.time()
    for backends, build in (("te=cpu", "sd-vulkan"), ("te=cpu,vae=cpu", "sd-vulkan"), ("", "sd-cpu")):
        args = [str(FLUX / build / "sd-cli.exe"), *common]
        if backends:
            args += ["--backend", backends]
        code = run(args, FLUX, BUILDER / "work" / f"{persona}.flux.log")
        if code == 0 and target.exists():
            log(f"{persona}: portrait in {time.time() - started:.0f} s ({build}, {backends or 'cpu'}, attempt {attempt + 1})")
            return target
        log(f"{persona}: portrait failed with {build} {backends or ''} (exit {code}); trying the next way")
    return None


def build(persona: str, picture: Path, *, still_only: bool = False, accept_any: bool = False) -> int:
    """build_face.py into the staging folder; each file moved into place whole."""
    started = time.time()
    python = BUILDER / "venv" / "Scripts" / "python.exe"
    STAGING.mkdir(parents=True, exist_ok=True)
    args = [str(python), "-X", "utf8", str(ROOT / "scripts" / "build_face.py"), str(picture), "--persona", persona]
    args += ["--out", str(STAGING)]
    if still_only:
        args.append("--still-only")
    if accept_any:
        args.append("--accept-any")
    code = run(args, ROOT, BUILDER / "work" / f"{persona}.build.log")
    moved = []
    for suffix in (".zip", ".webp"):
        staged = STAGING / f"{persona}{suffix}"
        if code == 0 and staged.exists():
            os.replace(staged, FACES / f"{persona}{suffix}")
            moved.append(suffix)
    what = "still" if still_only else "head"
    if code == 0:
        log(f"{persona}: {what} built in {time.time() - started:.0f} s ({', '.join(moved)})")
    elif code == REJECTED:
        log(f"{persona}: portrait rejected - {rejection(persona)}")
    else:
        log(f"{persona}: {what} FAILED (exit {code}) in {time.time() - started:.0f} s")
    return code


def rejection(persona: str) -> str:
    text = (BUILDER / "work" / f"{persona}.build.log").read_text(encoding="utf-8", errors="replace")
    found = re.findall(r"portrait check: (.+)", text)
    return found[-1] if found else "see the build log"


def built_from(persona: str) -> Path | None:
    """The portrait the head in place was made from, so its still is the same
    person: the name the head's meta.json records, the newest copy no newer
    than the head. A head from before a new spec was made from a portrait the
    rebuild has since set aside (`portraits_v1/`), not today's."""
    head = FACES / f"{persona}.zip"
    with zipfile.ZipFile(head) as packed:
        meta = next(n for n in packed.namelist() if n.endswith("meta.json"))
        name = json.loads(packed.read(meta))["portrait"]
    made = head.stat().st_mtime
    copies = [
        folder / name
        for folder in BUILDER.glob("portraits*")
        if (folder / name).is_file() and (folder / name).stat().st_mtime <= made
    ]
    return max(copies, key=lambda path: path.stat().st_mtime, default=None)


def make(persona: str, entry: dict, spec: dict, args: argparse.Namespace) -> bool:
    if args.stills:
        if (FACES / f"{persona}.zip").exists() and not (FACES / f"{persona}.webp").exists():
            picture = built_from(persona)
            if picture is None:
                log(f"{persona}: no portrait for a still")
                return False
            wait_while_paused()
            return build(persona, picture, still_only=True) == 0
        return True
    head = FACES / f"{persona}.zip"
    # A rebuild resumes: a head made after the spec last changed is current.
    if head.exists() and not args.force and (not args.rebuild or head.stat().st_mtime > SPEC.stat().st_mtime):
        return True
    for attempt in range(ATTEMPTS):
        # A seed makes the same portrait every time: one the check turned down
        # before is not made again (cn_divya cost six minutes a run for it).
        if attempt < ATTEMPTS - 1 and any((PORTRAITS / "rejected").glob(f"{persona}.{attempt}.*")):
            continue
        wait_while_paused()
        picture = portrait(persona, entry, spec, attempt)
        if picture is None:
            return False
        if args.portraits_only:
            return True
        wait_while_paused()
        last = attempt == ATTEMPTS - 1 or "portrait" in entry
        code = build(persona, picture, accept_any=last)
        if code == 0:
            return True
        if code != REJECTED:
            return False
        # Kept beside the rest, for a look at what the check turned down.
        rejected = PORTRAITS / "rejected"
        rejected.mkdir(exist_ok=True)
        os.replace(picture, rejected / f"{persona}.{attempt}{picture.suffix}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", nargs="*", help="these persona ids only")
    parser.add_argument("--portraits-only", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="build every head again, swapping each in when whole")
    parser.add_argument("--stills", action="store_true", help="make the still for heads that have none")
    parser.add_argument("--force", action="store_true", help="with --rebuild: build these heads again even if current")
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    PORTRAITS.mkdir(parents=True, exist_ok=True)
    (BUILDER / "work").mkdir(parents=True, exist_ok=True)
    wanted = [p for p in spec["personas"] if not args.only or p in args.only]
    # Every description against its persona file, before an hour is spent.
    for persona in wanted:
        if "describe" in spec["personas"][persona]:
            prompt_for(persona, spec["personas"][persona], spec)
    log(f"making {len(wanted)} interviewer(s){' (rebuild)' if args.rebuild else ''}{' (stills)' if args.stills else ''}")
    made = sum(make(persona, spec["personas"][persona], spec, args) for persona in wanted)
    log(f"finished: {made} of {len(wanted)}")


if __name__ == "__main__":
    main()
