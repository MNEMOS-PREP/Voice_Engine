"""Do the respelled interviewer names come back as names? (2026-10-12)

The listening-test round (2026-10-11) respelled 155 Indian names for English
letter rules, chosen by ear and applied in every voice. The read-back cannot
judge an accent, but it does catch a respelling that a voice breaks into
noise (Chatterbox breaks up non-words; one respelling of "Raghavan" came back
right in one voice and wrong in another). Each name is said in every cast
voice, in the sentence a panel uses ("I'm joined by A, B and C."), read back
by M11's recogniser, and scored by how close the closest heard word is.

    python research/lexicon/names_check.py [N_NAMES] [OUT_NAME]

Needs M11 running. Writes names_check.json beside it.
"""

from __future__ import annotations

import difflib
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
LEXICON = (
    HERE.parents[1] / "Backend" / "backend_M11_Voice_Engine" / "voices" / "lexicon.json"
)
CAST = HERE.parents[1] / "Backend" / "backend_M11_Voice_Engine" / "voices" / "cast.json"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}
#: Below this, the closest heard word is not the name (difflib ratio).
CLOSE = 0.6


def post(path: str, data: bytes, content_type: str) -> bytes:
    request = urllib.request.Request(
        f"{M11}{path}", data=data, headers={**WHO, "Content-Type": content_type}
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 4:
                raise
            time.sleep(6 * (attempt + 1))  # the recogniser's minute
    raise RuntimeError("unreachable")


def closest(name: str, heard: str) -> tuple[str, float]:
    words = re.findall(r"[a-z]+", heard.lower())
    best = max(
        words,
        key=lambda w: difflib.SequenceMatcher(None, name.lower(), w).ratio(),
        default="",
    )
    return best, difflib.SequenceMatcher(None, name.lower(), best).ratio()


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    # The names: the lexicon's, or another copy's (to hear them unrespelled).
    source = pathlib.Path(os.environ.get("NAMES_FROM", LEXICON))
    entries = json.loads(source.read_text(encoding="utf-8"))["entries"]
    names = [
        e["term"] for e in entries if "interviewer's own name" in (e.get("why") or "")
    ][:n]
    voices = sorted(set(json.loads(CAST.read_text(encoding="utf-8"))["cast"].values()))
    rows = []
    for i in range(0, len(names), 3):
        group = names[i : i + 3]
        sentence = f"I'm joined by {', '.join(group[:-1])} and {group[-1]}."
        for voice in voices:
            wav = post(
                "/v1/voice/speak",
                json.dumps({"text": sentence, "voice": voice}).encode(),
                "application/json",
            )
            heard = json.loads(post("/v1/voice/transcribe", wav, "audio/wav"))["text"]
            for name in group:
                word, score = closest(name, heard)
                rows.append(
                    {
                        "name": name,
                        "voice": voice,
                        "heard": word,
                        "score": round(score, 2),
                    }
                )
            print(f"{voice:22s} {heard}", flush=True)
    out = sys.argv[2] if len(sys.argv) > 2 else "names_check"
    (HERE / f"{out}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    bad = [r for r in rows if r["score"] < CLOSE]
    print(
        f"\n{len(rows) - len(bad)} of {len(rows)} name sayings came back close (>= {CLOSE})"
    )
    for r in bad:
        print(
            f"  NOT CLOSE  {r['name']:10s} in {r['voice']:22s} heard {r['heard']!r} ({r['score']})"
        )


if __name__ == "__main__":
    main()
