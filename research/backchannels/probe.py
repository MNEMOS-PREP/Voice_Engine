"""Which "mm-hm" sounds like one? — M11 day 11, FR-11.11.

A backchannel is the shortest thing an interviewer says and the easiest to get
wrong: a synthetic "Mm-hm." can come out as a spelled-out "em-em", a sigh, or
two seconds of breath. So each candidate is spoken by every voice in the cast,
timed, and read back by Whisper. A word earns a place in M06's phrasebook only
if it comes back as itself and is short enough to sit inside a pause.

Needs M11 (:8111, voice ready) and a Groq key in keys.txt. Run with M11's venv:
    ..\..\Backend\.venv\Scripts\python.exe probe.py
Writes probe.json and prints a table.
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import time
import wave

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))
sys.path.insert(0, str(HERE.parent / "lexicon"))

from probe import get, hear, speak  # noqa: E402  (the lexicon probe's helpers)

from backend_M11_Voice_Engine import wer  # noqa: E402
from backend_M11_Voice_Engine.keys import KeyRing, load_keys  # noqa: E402

M11 = "http://127.0.0.1:8111"
#: What a listener says while someone else talks — none of them a verdict.
CANDIDATES = ["Mm-hm.", "Mm-hmm.", "Mhm.", "Hmm.", "Okay.", "I see.", "Sure.", "Got it.", "Uh-huh."]
#: What Whisper writes for each, when it heard the thing itself.
HEARD_AS = {
    "Mm-hm.": {"mmhmm", "mmhm", "mhm", "mm hmm", "mm hm", "uh huh", "hmm"},
    "Mm-hmm.": {"mmhmm", "mmhm", "mhm", "mm hmm", "mm hm", "uh huh", "hmm"},
    "Mhm.": {"mmhmm", "mmhm", "mhm", "mm hmm", "mm hm", "hmm"},
    "Hmm.": {"hmm", "hm", "mm", "mmm", "hmmm"},
    "Uh-huh.": {"uh huh", "uhhuh", "mm hmm", "mhm"},
}
#: Longer than this and it is not a backchannel but an interruption.
LONGEST_MS = 1100


def seconds(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    load_keys()
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    voices = sorted(set(get(f"{M11}/v1/voice/cast")["cast"].values()))
    rows = []
    for text in CANDIDATES:
        for voice in voices:
            t0 = time.perf_counter()
            audio = speak(text, voice)
            made_ms = round((time.perf_counter() - t0) * 1000)
            heard = hear(ring, audio).strip()
            got = " ".join(wer.normalise(heard))
            want = HEARD_AS.get(text, {" ".join(wer.normalise(text))})
            rows.append(
                {
                    "text": text,
                    "voice": voice,
                    "ms": round(seconds(audio) * 1000),
                    "made_ms": made_ms,
                    "heard": heard,
                    "came_back": got in want
                    or got.replace(" ", "") in {w.replace(" ", "") for w in want},
                }
            )
            r = rows[-1]
            print(
                f"{text:9} {voice:20} {r['ms']:5} ms  {'ok ' if r['came_back'] else 'MISS'}  {heard!r}"
            )
    (HERE / "probe.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print()
    for text in CANDIDATES:
        mine = [r for r in rows if r["text"] == text]
        ok = [r for r in mine if r["came_back"] and r["ms"] <= LONGEST_MS]
        print(
            f"{text:9} {len(ok)}/{len(mine)} voices short and heard as itself;"
            f" median {sorted(r['ms'] for r in mine)[len(mine) // 2]} ms"
        )


if __name__ == "__main__":
    main()
