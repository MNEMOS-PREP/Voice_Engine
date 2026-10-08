"""Does each voice say what it is given? A read-back probe (2026-10-08).

For each voice, two interview lines are spoken through the running M11
(`/v1/voice/speak` with that voice) and read back by M11's own recogniser
(`/v1/voice/transcribe`). A clone that garbles, mumbles or hallucinates shows
up as words lost (word error rate) or as speech far too fast or slow for
the words. The ear is still the judge — `listen.html` holds the clips — but a
voice that fails here is not worth a listen.

    python research/listening/probe_voices.py [VOICE_KEY ...]

Writes research/listening/probe/<voice>_<n>.wav and probe/results.json.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import wave

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "probe"
CAST = HERE.parents[1] / "Backend" / "backend_M11_Voice_Engine" / "voices" / "cast.json"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}
LINES = (
    "Walk me through how a hash map finds a key, and what happens when two keys collide.",
    "That's a good start. Can you tell me what you would change if the data no longer fits in memory?",
)


def call(
    path: str, body: bytes, content_type: str, timeout: int = 600
) -> tuple[bytes, dict]:
    request = urllib.request.Request(
        f"{M11}{path}",
        data=body,
        headers={**WHO, "Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), dict(response.headers)


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


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cast = json.loads(CAST.read_text(encoding="utf-8"))
    keys = sys.argv[1:] or sorted(cast["voices"])
    results = []
    for key in keys:
        for n, line in enumerate(LINES):
            t0 = time.time()
            try:
                audio, _headers = call(
                    "/v1/voice/speak",
                    json.dumps({"text": line, "voice": key}).encode(),
                    "application/json",
                )
            except urllib.error.HTTPError as exc:
                print(f"{key}: speak failed {exc.code}", flush=True)
                continue
            made_s = time.time() - t0
            path = OUT / f"{key}_{n}.wav"
            path.write_bytes(audio)
            with wave.open(str(path)) as w:
                seconds = w.getnframes() / w.getframerate()
            heard_raw, _ = call("/v1/voice/transcribe", audio, "audio/wav")
            heard = json.loads(heard_raw).get("text", "")
            row = {
                "voice": key,
                "line": n,
                "wer": round(wer(line, heard), 3),
                "words_per_s": round(len(words(line)) / max(seconds, 0.1), 2),
                "seconds": round(seconds, 2),
                "made_s": round(made_s, 1),
                "heard": heard,
            }
            results.append(row)
            print(
                f"{key} #{n}: WER {row['wer']:.2f}, {row['words_per_s']} w/s, {seconds:.1f}s | {heard}",
                flush=True,
            )
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
