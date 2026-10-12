"""Do the voices say the bank's identifiers the way a person would? (2026-10-12)

The user's demo: `emp_id` was heard as "Benite", `dept_id` as "deputy". Core
v0.32.0 (`sayIdentifiers`) now turns the bank's identifiers into words before
the voice gets them — "Employees, with employee ID, name, dept ID and
salary". What is left is for M11's lexicon, and only what a read-back shows
the voices still get wrong.

Every bank text with an identifier is turned into what the room would send
(Core's own `speakable`, run by node), said in every cast voice, and read
back; each expected word must come back. A miss is a lexicon candidate; a
respelling earns an entry only by coming back right (`--try WORD=SAY`).

    python research/lexicon/identifiers.py [--try dept=department ...]

Needs M11 running and node. Writes identifiers.json beside it.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BANK = (
    ROOT
    / "Question_Intelligence"
    / "Backend"
    / "backend_M05_Question_Intelligence"
    / "bank"
)
CORE = (ROOT / "Platform_Core" / "src" / "voice" / "core.ts").as_uri()
CAST = HERE.parents[1] / "Backend" / "backend_M11_Voice_Engine" / "voices" / "cast.json"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}
IDENTIFIER = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b|\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b|\b[A-Z]{3,}\(\*\)"
)


def bank_texts() -> list[str]:
    texts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("stem", "follow_ups", "hint_ladder") and isinstance(
                    value, str
                ):
                    texts.append(value)
                elif key in ("stem", "follow_ups", "hint_ladder") and isinstance(
                    value, list
                ):
                    texts.extend(v for v in value if isinstance(v, str))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in sorted(BANK.glob("*.yaml")):
        walk(yaml.safe_load(path.read_text(encoding="utf-8")))
    return [t for t in dict.fromkeys(texts) if IDENTIFIER.search(t.replace("`", ""))]


def speakable(texts: list[str]) -> list[str]:
    script = (
        f"import {{ speakable }} from {json.dumps(CORE)};"
        "const lines = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify(lines.map(speakable)));"
    )
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script.replace("require('fs')", "(await import('node:fs'))"),
        ],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(out.stdout)


def post(path: str, data: bytes, content_type: str) -> bytes:
    request = urllib.request.Request(
        f"{M11}{path}", data=data, headers={**WHO, "Content-Type": content_type}
    )
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503) or attempt == 7:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def expected(said: str) -> list[str]:
    """The words an identifier became: what must come back."""
    words: list[str] = []
    for phrase in re.findall(
        r"\b(?:[A-Za-z]+ (?:ID|star|base [a-z0-9])|[A-Z][a-z]+ [A-Z][a-z]+|AS PATH|[a-z]+ (?:date|at|name|id))\b",
        said,
    ):
        words.extend(w.lower() for w in phrase.split())
    return list(dict.fromkeys(words))


def came_back(word: str, heard: str) -> bool:
    heard = heard.lower().replace(".", "").replace("-", " ")
    if word == "id":
        return bool(re.search(r"\b(id|i d|i\.d|eye dee|i\s?d)\b", heard))
    return re.search(rf"\b{re.escape(word)}s?\b", heard) is not None


def main() -> None:
    tries = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)
    texts = bank_texts()
    said = speakable(texts)
    voices = sorted(set(json.loads(CAST.read_text(encoding="utf-8"))["cast"].values()))
    rows = []
    # The sentences that carry an identifier, one request each, as the room
    # sends a line (a request takes 400 characters at most).
    lines = [
        s for line in said for s in re.split(r"(?<=[.?!])\s+", line) if expected(s)
    ]
    for line in lines:
        for word, say in tries.items():
            line = re.sub(rf"\b{re.escape(word)}\b", say, line)
        want = expected(line)
        if not want:
            continue
        for voice in voices:
            wav = post(
                "/v1/voice/speak",
                json.dumps({"text": line, "voice": voice}).encode(),
                "application/json",
            )
            heard = json.loads(post("/v1/voice/transcribe", wav, "audio/wav"))["text"]
            missed = [w for w in want if not came_back(w, heard)]
            rows.append(
                {"said": line, "voice": voice, "heard": heard, "missed": missed}
            )
            print(f"{voice:22s} missed {missed}  <- {heard[:90]}", flush=True)
    (HERE / "identifiers.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    misses: dict[str, int] = {}
    for row in rows:
        for w in row["missed"]:
            misses[w] = misses.get(w, 0) + 1
    print(
        f"\n{sum(not r['missed'] for r in rows)} of {len(rows)} sayings had every identifier word come back"
    )
    print("missed words (times):", dict(sorted(misses.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
