"""Listening-test clips: the same interviewer lines in a human-like voice.

Run from Backend/'s venv:  ..\\Backend\\.venv\\Scripts\\python make_samples.py
Writes WAVs beside this file (gitignored: *.wav). Reads GROQ_API_KEYS from
the projects/ keys.txt; prints no key.

Each line exists twice on purpose — as the interviewer writes it today, and
rewritten for the ear — so the page can separate what the VOICE adds from
what the WORDS add.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
KEYS = HERE.parents[2] / "keys.txt"

LINES = {
    "greeting_written": "Hi, I'm Meera, thanks for making the time. We'll keep this conversational. Let's start with something easy.",
    "greeting_spoken": "Hi! I'm Meera. Thanks for making the time. So, we'll keep this pretty relaxed, okay? Let's start with something easy.",
    "question_written": "Two keys hash to the same bucket. Walk me through how a hash map can handle that, and what it costs.",
    "question_spoken": "Okay, so. Say two keys land in the same bucket. How would a hash map deal with that? And, um, what does it cost you?",
    "followup_spoken": "Hmm, right, chaining. And if one bucket just keeps getting longer, what happens to your lookups?",
}

# (voice, direction) — Orpheus takes a 1-2 word direction in brackets.
TAKES = [
    ("hannah", None),
    ("hannah", "[warm]"),
    ("daniel", None),
    ("daniel", "[thoughtful]"),
]


def groq_key() -> str:
    for raw in KEYS.read_text(encoding="utf-8").splitlines():
        name, _, value = raw.partition("=")
        if name.strip() == "GROQ_API_KEYS":
            return value.split(",")[0].strip().strip('"')
    raise SystemExit("GROQ_API_KEYS not in keys.txt")


def speak(key: str, voice: str, text: str) -> bytes:
    body = json.dumps(
        {"model": "canopylabs/orpheus-v1-english", "voice": voice, "input": text, "response_format": "wav"}
    ).encode()
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/speech",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Groq's edge refuses urllib's default agent (Cloudflare 1010).
            "User-Agent": "mnemos-voice-engine/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> None:
    key = groq_key()
    made = []
    for line_id, text in LINES.items():
        for voice, direction in TAKES:
            # The written lines only in the plain take: they are the baseline.
            if line_id.endswith("_written") and direction:
                continue
            said = f"{direction} {text}" if direction else text
            if len(said) > 200:
                raise SystemExit(f"{line_id}: {len(said)} chars, Orpheus takes 200")
            name = f"orpheus_{voice}_{(direction or 'plain').strip('[]')}_{line_id}.wav"
            try:
                audio = speak(key, voice, said)
            except urllib.error.HTTPError as exc:
                print("FAILED", name, exc.code, exc.read()[:300])
                continue
            (HERE / name).write_bytes(audio)
            made.append({"file": name, "voice": voice, "direction": direction, "line": line_id, "text": text})
            print("ok", name, len(audio), "bytes")
    (HERE / "samples.json").write_text(json.dumps({"lines": LINES, "clips": made}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
