r"""How do the voices say an interviewer's notation? — M11, EC-11.11.

Questions in M05's bank carry big-O notation ("O(n log n)"), and a voice
that reads "O(n)" as "on" asks a question nobody can answer. Each form is
spoken by every voice in the cast in a carrier sentence and read back by
Whisper with no prompt, as a listener would hear it cold. A form that comes
back as itself — or as its spoken words, "O of n" — is said right.

Needs M11 (:8111, voice ready) and a Groq key in keys.txt. Run with M11's venv:
    ..\..\Backend\.venv\Scripts\python.exe probe.py [--said "O of n"]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))
sys.path.insert(0, str(HERE.parent / "lexicon"))

import urllib.request

from probe import WHO, get, speak


def hear(_ring, audio: bytes) -> str:
    """Read back by M11's own recogniser, with no question as its prompt:
    the product's ears on the product's voice, as a listener hears it cold."""
    request = urllib.request.Request(
        f"{M11}/v1/voice/transcribe",
        data=audio,
        headers={**WHO, "Content-Type": "audio/wav"},
    )
    import json as _json

    with urllib.request.urlopen(request, timeout=120) as response:
        return _json.loads(response.read())["text"]


from backend_M11_Voice_Engine.keys import KeyRing, load_keys

M11 = "http://127.0.0.1:8111"
FORMS = [
    "O(1)",
    "O(n)",
    "O(log n)",
    "O(n log n)",
    "O(n^2)",
    "O(n²)",
    "O(V + E)",
    "O(2^n)",
]
CARRIER = "The time complexity here is {said}, in the worst case."


def spoken(heard: str) -> str:
    """What was heard, as words: "O(n)" and "O of n" are the same answer."""
    text = heard.lower()
    text = text.replace("big o", "o").replace("big-o", "o")
    text = re.sub(r"[()\[\],.]", " ", text)
    return " ".join(text.replace(" of ", " ").split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--said", action="append", help="a respelling to try instead of the forms"
    )
    args = parser.parse_args()
    load_keys()
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    voices = sorted(set(get(f"{M11}/v1/voice/cast")["cast"].values()))
    rows = []
    for form in args.said or FORMS:
        for voice in voices:
            heard = hear(ring, speak(CARRIER.format(said=form), voice)).strip()
            rows.append({"form": form, "voice": voice, "heard": heard})
            print(f"{form:12} {voice:20} {heard!r}")
    name = "said.json" if args.said else "probe.json"
    (HERE / name).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
