"""Which acknowledgements does every cast voice say cleanly? (2026-10-21)

The user: after a correct answer the interviewer moves on with nothing —
"hmm", "good", "well said" — and should use a mix. Each candidate is spoken by
every voice in M11's cast (the render M11 caches, so the one students hear),
timed, and read back by Whisper, as research/backchannels/probe.py does.

Needs M11 (:8111, voice ready) and a Groq key in keys.txt; one
organisation's key is used. Run with M11's venv:
    ..\..\Backend\.venv\Scripts\python.exe probe.py probe.json
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import time
import wave

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))
sys.path.insert(0, str(HERE.parent / "lexicon"))

from backend_M11_Voice_Engine.keys import load_keys  # noqa: E402

load_keys()
# One Groq organisation's key per running app (its terms forbid pooling
# organisations): the first of GROQ_API_KEYS, and only that one.
_first = os.environ.pop("GROQ_API_KEYS", "").strip().strip("'\"").split(",")[0].strip().strip("'\"")
if _first:
    os.environ["GROQ_API_KEY"] = _first

from probe import get, hear, speak  # noqa: E402

from backend_M11_Voice_Engine import wer  # noqa: E402
from backend_M11_Voice_Engine.keys import KeyRing  # noqa: E402

M11 = "http://127.0.0.1:8111"
RECEIPTS = [
    "Okay.", "Alright.", "I see.", "Right.", "Got it.", "Sure.", "Understood.",
    "Fair enough.", "Hmm.", "Hmm, okay.", "Hmm, I see.", "Okay, thank you.",
]  # fmt: skip
CREDIT = [
    "Good.", "Nice.", "Well said.", "Nicely put.", "That makes sense.", "Very good.",
    "Good, thank you.", "Nice, thank you.",
]  # fmt: skip
HEARD_AS = {
    "Hmm.": {"hmm", "hm", "mm", "mmm", "hmmm"},
    "Hmm, okay.": {"hmm okay", "hm okay", "mm okay", "mmm okay", "hmmm okay"},
    "Hmm, I see.": {"hmm i see", "hm i see", "mm i see", "mmm i see", "hmmm i see"},
}
#: Longer than this and the acknowledgement drags before the next question.
LONGEST_MS = 1600


def seconds(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as w:
        return w.getnframes() / w.getframerate()


def main(out: pathlib.Path) -> None:
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    voices = sorted(set(get(f"{M11}/v1/voice/cast")["cast"].values()))
    rows = []
    for text in RECEIPTS + CREDIT:
        for voice in voices:
            t0 = time.perf_counter()
            audio = speak(text, voice)
            made_ms = round((time.perf_counter() - t0) * 1000)
            heard = hear(ring, audio).strip()
            got = " ".join(wer.normalise(heard))
            want = HEARD_AS.get(text, {" ".join(wer.normalise(text))})
            ok = got in want or got.replace(" ", "") in {w.replace(" ", "") for w in want}
            ms = round(seconds(audio) * 1000)
            rows.append(
                {"text": text, "voice": voice, "ms": ms, "made_ms": made_ms, "heard": heard, "came_back": ok}
            )
            print(f"{text:18} {voice:22} {ms:5} ms  {'ok ' if ok else 'MISS'}  {heard!r}", flush=True)
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print()
    for text in RECEIPTS + CREDIT:
        mine = [r for r in rows if r["text"] == text]
        good = [r for r in mine if r["came_back"] and r["ms"] <= LONGEST_MS]
        median = sorted(r["ms"] for r in mine)[len(mine) // 2]
        print(f"{text:18} {len(good)}/{len(mine)} clean   median {median} ms", flush=True)


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
