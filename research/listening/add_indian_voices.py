"""More Indian voices, so a foreign accent is the rare one (2026-10-08).

The user, on the 39-interviewer cast: "add more Indians, foreigners can be
lesser and a bit rare". The cast had five Indian voices — only two of them
higher — so ten interviewers spoke with a foreign accent. `pick_voices.py`
had already found 21 distinct speakers in IndicTTS English; this takes seven
more of them, spread by pitch so the voices at one table sound different:
four higher and three lower. Voice 2 (027797), heard in the team's blind
test and left out of the cast, stays out.

Each reference becomes a 15-second, 24 kHz mono clip in M11's `voices/`,
cut at a pause, at the cast's loudness, and is written into `cast.json`
with its source, licence and credit. Who speaks in which voice is
`recast()`'s, and M06's persona files carry the same key (`voice:`).

    Backend\\.venv\\Scripts\\python research\\listening\\add_indian_voices.py
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
REF = HERE / "reference"
ROOT = HERE.parents[1]
VOICES = ROOT / "Backend" / "backend_M11_Voice_Engine" / "voices"
CAST = VOICES / "cast.json"
M06_PERSONAS = ROOT.parent / "Mock_Interview_Engine" / "Backend" / "backend_M06_Mock_Interview_Engine" / "personas"
RATE = 24_000
SECONDS = 15.0

#: offset → (label number, register). Numbers continue the cast's own (1-6).
NEW = {
    "133931": (7, "higher"),
    "083391": (8, "higher"),
    "048013": (9, "higher"),
    "002527": (10, "higher"),
    "012635": (11, "lower"),
    "128877": (12, "lower"),
    "144039": (13, "lower"),
}

#: The two foreign voices stay with the two the team cast them for in its
#: blind listening test (2026-10-06): Priya and Kabir. Nobody else.
FOREIGN_KEEP = {"methodical_engineer": "chatterbox-default", "startup_founder": "dailytalk-0"}


def load_mono(path: pathlib.Path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    data = data.mean(axis=1)
    if rate != RATE:
        positions = np.arange(0, len(data), rate / RATE)
        data = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
    return data


def cut_at_pause(audio: np.ndarray, seconds: float = SECONDS) -> np.ndarray:
    """The first `seconds`, ended in the quietest 50 ms of the last second,
    so the clip does not stop mid-word."""
    end = int(seconds * RATE)
    if len(audio) <= end:
        return audio
    window = int(0.05 * RATE)
    start = end - RATE
    energies = [
        float(np.sqrt(np.mean(audio[i : i + window] ** 2)))
        for i in range(start, end - window, window // 2)
    ]
    quietest = start + int(np.argmin(energies)) * (window // 2) + window // 2
    return audio[:quietest]


def loudness(audio: np.ndarray) -> float:
    voiced = audio[np.abs(audio) > 0.01]
    return float(np.sqrt(np.mean(voiced**2))) if len(voiced) else 0.0


def measured_pitch() -> dict[str, int]:
    """Median pitch per reference, as `pick_voices.py` measured it."""
    rows = json.loads((REF / "voices.json").read_text(encoding="utf-8"))
    return {row["file"].removeprefix("indictts_").removesuffix(".wav"): int(row["pitch_hz"]) for row in rows}


def make_clips(cast: dict) -> None:
    pitches = measured_pitch()
    target = np.median([loudness(load_mono(VOICES / f"{k}.flac")) for k in cast["voices"] if k.startswith("indictts")])
    for offset, (number, register) in NEW.items():
        key = f"indictts-{offset}"
        audio = cut_at_pause(load_mono(REF / f"indictts_{offset}.wav"))
        audio = np.clip(audio * (target / max(loudness(audio), 1e-6)), -0.98, 0.98).astype(np.float32)
        sf.write(VOICES / f"{key}.flac", audio, RATE)
        cast["voices"][key] = {
            "label": f"Indian voice {number}",
            "accent": "indian",
            "register": register,
            "pitch_hz": pitches[offset],
            "source": f"IndicTTS English (SPRINGLab/IndicTTS-English, offset {int(offset)})",
            "licence": "CC BY 4.0",
            "credit": "IndicTTS, SMT Lab, IIT Madras",
        }
        print(f"{key}: {len(audio) / RATE:.1f} s, {cast['voices'][key]['pitch_hz']} Hz", flush=True)


def gender(persona: dict) -> str:
    return "female" if "-female-" in persona["voice_id"] else "male"


def recast(cast: dict) -> dict[str, str]:
    """Everyone not kept foreign gets an Indian voice of their register,
    shared out evenly, people of one track spread across voices (they are
    the likeliest to share a table). The team's first seven keep theirs."""
    import yaml

    personas = {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(M06_PERSONAS.glob("*.yaml"))
    }
    first_seven = {
        "friendly_recruiter", "hr_generalist", "bar_raiser", "professor",
        "impatient_senior", "methodical_engineer", "startup_founder",
    }
    pools = {
        register: sorted(
            k for k, v in cast["voices"].items() if v["accent"] == "indian" and v["register"] == register
        )
        for register in ("higher", "lower")
    }
    uses = {k: 0 for pool in pools.values() for k in pool}
    for kept in first_seven:
        uses[cast["cast"][kept]] = uses.get(cast["cast"][kept], 0) + 1
    out = {pid: cast["cast"][pid] for pid in first_seven}
    # By track (the id's prefix), so one track's three or four people are
    # handed out one after another and land on different voices.
    for pid in sorted(personas, key=lambda p: (p.split("_")[0], p)):
        if pid in first_seven:
            continue
        pool = pools["higher" if gender(personas[pid]) == "female" else "lower"]
        same_track = {out[o] for o in out if o.split("_")[0] == pid.split("_")[0]}
        choice = min(pool, key=lambda k: (k in same_track, uses[k], k))
        out[pid] = choice
        uses[choice] += 1
    for pid, voice in FOREIGN_KEEP.items():
        out[pid] = voice
    return out


def write_personas(assignment: dict[str, str]) -> None:
    import re

    for pid, voice in assignment.items():
        path = M06_PERSONAS / f"{pid}.yaml"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^voice: .*$", f"voice: {voice}", text, count=1)
        path.write_text(text, encoding="utf-8")


def main() -> None:
    cast = json.loads(CAST.read_text(encoding="utf-8"))
    make_clips(cast)
    assignment = recast(cast)
    cast["cast"] = {pid: assignment[pid] for pid in sorted(assignment)}
    note = (
        "2026-10-08: seven more IndicTTS voices (Indian voices 7-13); a foreign accent is now the "
        "rare one - Priya and Kabir, as the team cast them - and everyone else speaks in an Indian voice."
    )
    if note not in cast["_comment"]:
        cast["_comment"].append(note)
    CAST.write_text(json.dumps(cast, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_personas(assignment)
    foreign = [p for p, v in assignment.items() if cast["voices"][v]["accent"] != "indian"]
    print(f"cast: {len(assignment)} interviewers, foreign accent for {len(foreign)}: {foreign}")
    counts: dict[str, int] = {}
    for v in assignment.values():
        counts[v] = counts.get(v, 0) + 1
    print("per voice:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
