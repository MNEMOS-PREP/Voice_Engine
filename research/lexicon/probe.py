"""Which words do the interviewers' voices get wrong? — M11, EC-11.11.

Not a guess: every term the interviewers say — M04's concept names (what a
round is about) and the personas' own names (said at every introduction and
hand-over) — is spoken by M11's voice in a carrier sentence, read back by
Whisper, and kept only if it comes back. A term that does not is a lexicon
candidate; a respelling earns its place in `voices/lexicon.json` only by
coming back right (`--retry` checks the respellings in RESPELL).

Needs M11 (:8111, voice ready), M04 (:8104) and M06 (:8106) running, and a
Groq key in keys.txt. Run with M11's venv:
    ..\\..\\Backend\\.venv\\Scripts\\python.exe probe.py [--retry]
Writes probe.json and prints the misses.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))

from backend_M11_Voice_Engine import wer  # noqa: E402
from backend_M11_Voice_Engine.keys import KeyRing, load_keys  # noqa: E402

M11, M04, M06 = "http://127.0.0.1:8111", "http://127.0.0.1:8104", "http://127.0.0.1:8106"
WHO = {"X-Role": "student", "X-Candidate-Id": "59ea5ceb-8fdd-4e17-a552-49fa68781f10"}
AGENT = "AI-Interviewer/1.0 (+https://github.com/MNEMOS-PREP)"
#: The panel's most-heard voice, and an Indian voice for the names.
VOICES = ("chatterbox-default", "indictts-022743")

#: Respellings to try for a term that did not come back (--retry).
RESPELL: dict[str, str] = {}


def get(url: str) -> object:
    request = urllib.request.Request(url, headers={**WHO, "User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def speak(text: str, voice: str) -> bytes:
    body = json.dumps({"text": text, "voice": voice}).encode()
    request = urllib.request.Request(
        f"{M11}/v1/voice/speak", data=body, headers={**WHO, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def hear(ring: KeyRing, audio: bytes) -> str:
    boundary = uuid.uuid4().hex
    fields = [("model", "whisper-large-v3-turbo"), ("language", "en"), ("temperature", "0")]
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n' for n, v in fields
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    )
    body = "".join(parts).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    for attempt in range(8):
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {ring.next()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read())["text"]
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 7:
                raise
            time.sleep(float(exc.headers.get("retry-after") or 10) + 1)
    raise RuntimeError("unreachable")


def came_back(term: str, heard: str) -> bool:
    """The term's words, in order, somewhere in what was heard."""
    want, got = wer.normalise(term), wer.normalise(heard)
    n = len(want)
    return any(got[i : i + n] == want for i in range(len(got) - n + 1))


def terms() -> list[tuple[str, str]]:
    """(term, kind): M04's concept names and M06's persona names."""
    concepts = get(f"{M04}/v1/concepts")
    items = concepts if isinstance(concepts, list) else concepts.get("concepts") or []
    out = [(c["name"], "concept") for c in items if c.get("name")]
    people = get(f"{M06}/v1/interviews/personas")
    for p in people:
        for part in p["name"].replace("Dr. ", "").split():
            out.append((part, "name"))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry", action="store_true", help="check the respellings in RESPELL")
    args = parser.parse_args()
    load_keys()
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    out_path = HERE / ("retry.json" if args.retry else "probe.json")
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    work = (
        [(term, "respelling") for term in RESPELL]
        if args.retry
        else terms()
    )
    for i, (term, kind) in enumerate(work):
        voices = VOICES if kind == "name" else VOICES[:1]
        for voice in voices:
            key = f"{term}|{voice}"
            if key in done:
                continue
            said = RESPELL.get(term, term) if args.retry else term
            sentence = f"Next, let's talk about {said}."
            heard = hear(ring, speak(sentence, voice))
            done[key] = {"term": term, "said": said, "voice": voice, "kind": kind, "heard": heard,
                         "ok": came_back(term, heard)}
            out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print(f"{i + 1}/{len(work)} {'ok  ' if done[key]['ok'] else 'MISS'} {term} [{voice}] -> {heard}", flush=True)
    misses = [v for v in done.values() if not v["ok"]]
    print(f"\n{len(done) - len(misses)} of {len(done)} came back; misses:")
    for m in misses:
        print(f"  {m['term']!r} [{m['voice']}] said {m['said']!r} heard {m['heard']!r}")


if __name__ == "__main__":
    main()
