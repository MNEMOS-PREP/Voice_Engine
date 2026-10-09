"""Does the int8 language model sound like the fp32 one? (2026-10-09)

Every voice in the cast says the same three interview sentences twice — the
fp32 model (the running M11) and the int8 one (made here, in-process) — and
each clip is read back by M11's own recogniser. A model that mispronounces
shows up as words lost (WER); one that drawls or rushes, as a different pace;
one that leaves odd silences, as a different length for the same words.

    cd Backend
    .venv\\Scripts\\python ..\\research\\listening\\int8_check.py

Writes research/listening/int8/<precision>/<voice>_<n>.wav and int8/results.json.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import wave

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "int8"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}
SENTENCES = (
    "Before we go further, tell me how you would find the middle of a linked list in one pass.",
    "Interesting. And what would change if the list could contain a cycle somewhere in the middle?",
    "Say the database slows down under load; where would you start looking, and why there first?",
)


def call(path: str, body: bytes, content_type: str) -> bytes:
    request = urllib.request.Request(
        f"{M11}{path}", data=body, headers={**WHO, "Content-Type": content_type}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def wer(reference: str, heard: str) -> float:
    ref, hyp = words(reference), words(heard)
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / max(1, len(ref))


def heard(data: bytes) -> str:
    """M11's recogniser on a clip, waiting out its provider's rate limit."""
    for attempt in range(6):
        try:
            return json.loads(call("/v1/voice/transcribe", data, "audio/wav")).get("text", "")
        except urllib.error.HTTPError as exc:
            if exc.code != 503 or attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))
    return ""


def seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    sys.path.insert(0, str(HERE.parents[1] / "Backend"))
    os.environ.setdefault("M11_TTS_CACHE", str(OUT / ".cache"))
    from backend_M11_Voice_Engine import tts

    cast = tts.Cast.load()
    voices = sorted(cast.voices)

    def path(precision: str, key: str, n: int) -> pathlib.Path:
        return OUT / precision / f"{key}_{n}.wav"

    # fp32: the running M11. Each clip saved as it is made; a rerun keeps them.
    (OUT / "fp32").mkdir(parents=True, exist_ok=True)
    for key in voices:
        for n, text in enumerate(SENTENCES):
            if not path("fp32", key, n).exists():
                body = json.dumps({"text": text, "voice": key}).encode()
                path("fp32", key, n).write_bytes(call("/v1/voice/speak", body, "application/json"))
        print(f"fp32 {key} done", flush=True)
    # int8: made here.
    (OUT / "int8").mkdir(parents=True, exist_ok=True)
    if not all(path("int8", key, n).exists() for key in voices for n in range(len(SENTENCES))):
        engine = tts.Engine(cast, precision="int8")
        engine.start()
        while engine.state == "loading":
            time.sleep(0.5)
        assert engine.state == "ready", engine.reason
        for key in voices:
            for n, text in enumerate(SENTENCES):
                if not path("int8", key, n).exists():
                    path("int8", key, n).write_bytes(engine.speak(text, cast.voices[key])[0])
            print(f"int8 {key} done", flush=True)
    rows = []
    for precision in ("fp32", "int8"):
        for key in voices:
            for n in range(len(SENTENCES)):
                data = path(precision, key, n).read_bytes()
                said = heard(data)
                length = seconds(data)
                rows.append(
                    {
                        "precision": precision,
                        "voice": key,
                        "line": n,
                        "seconds": round(length, 2),
                        "words_per_s": round(len(words(SENTENCES[n])) / length, 2),
                        "wer": round(wer(SENTENCES[n], said), 3),
                        "heard": said,
                    }
                )
    (OUT / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def mean(of: list[dict], field: str) -> float:
        return statistics.mean(r[field] for r in of)

    for precision in ("fp32", "int8"):
        mine = [r for r in rows if r["precision"] == precision]
        worst = max(r["wer"] for r in mine)
        print(
            f"{precision}: mean WER {mean(mine, 'wer'):.3f}, worst {worst:.2f}, "
            f"pace {mean(mine, 'words_per_s'):.2f} w/s"
        )
    for key in voices:
        f = [r for r in rows if r["voice"] == key and r["precision"] == "fp32"]
        i = [r for r in rows if r["voice"] == key and r["precision"] == "int8"]
        print(
            f"  {key:20s} fp32 WER {mean(f, 'wer'):.2f} {mean(f, 'words_per_s'):.2f} w/s"
            f" | int8 WER {mean(i, 'wer'):.2f} {mean(i, 'words_per_s'):.2f} w/s"
        )
    for r in rows:
        if r["wer"] > 0.1:
            print(f"  {r['precision']} {r['voice']} #{r['line']} WER {r['wer']}: {r['heard']}")


if __name__ == "__main__":
    main()
