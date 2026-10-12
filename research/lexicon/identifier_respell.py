"""Respellings for what `identifiers.py` found the voices still get wrong
(2026-10-12): "dept ID" heard "debt ID" / "depth ID", and "AS PATH" heard
"Aspath" / "SPATH" — in all eight voices. A respelling earns a lexicon entry
only by coming back right in every voice.

    python research/lexicon/identifier_respell.py
"""

from __future__ import annotations

import json
import re

from identifiers import CAST, post

#: The sentence as the room says it, the term, what it must come back as,
#: and the respellings to try.
CASES = [
    (
        "You have a table Employees, with employee ID, name, dept ID and salary.",
        "dept",
        "department",
        ["department"],
    ),
    (
        "Think about how AS PATH is used by BGP to detect loops.",
        "AS PATH",
        "as path",
        ["A S path", "A.S. path", "A-S path"],
    ),
]


def plain(text: str) -> str:
    """Lowercase letters and spaces, letters said one by one run together:
    "A. S. path" and "A S path" are both "as path"."""
    text = re.sub(r"[^a-z ]", " ", text.lower())
    text = re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", text)
    return " ".join(text.split())


def main() -> None:
    voices = sorted(set(json.loads(CAST.read_text(encoding="utf-8"))["cast"].values()))
    results = {}
    for sentence, term, want, respellings in CASES:
        for say in respellings:
            line = sentence.replace(term, say)
            ok = []
            for voice in voices:
                wav = post(
                    "/v1/voice/speak",
                    json.dumps({"text": line, "voice": voice}).encode(),
                    "application/json",
                )
                heard = json.loads(post("/v1/voice/transcribe", wav, "audio/wav"))[
                    "text"
                ]
                ok.append(plain(want) in plain(heard))
                print(
                    f"{say!r:14} {voice:22s} {'ok ' if ok[-1] else 'MISS'} {heard[:80]}",
                    flush=True,
                )
            results[f"{term} -> {say}"] = f"{sum(ok)}/{len(ok)}"
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
