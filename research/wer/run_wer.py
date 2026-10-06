"""Which recogniser hears Indian English best? — M11 day 6 (spec §0 6.7, AC-11.4/11.5).

Measures word error rate for each candidate on Indian-accented English and
writes RESULTS.md. "A choice made by reputation would fail it silently."

Data: IndicTTS English (SMT Lab, IIT Madras; CC BY 4.0), the Hugging Face
mirror `SPRINGLab/IndicTTS-English` — speakers of Indian languages reading
English. The mirror has no speaker or L1 labels, so this picks the
recogniser; it cannot measure AC-11.4's gap BETWEEN accent groups. That
needs Svarah (AI4Bharat, 117 speakers with self-reported L1; gated on
Hugging Face — the user's account must accept) or the pilot's own
recordings, and this runner takes either the day they exist (`--rows`).

Candidates: Groq's `whisper-large-v3-turbo` (what M11 runs) and
`whisper-large-v3`. The browser's own recogniser cannot be fed a file, so it
is not in this table; it stays the caption and the no-key fallback.

Run with M11's venv (numpy, soundfile):
    ..\\..\\Backend\\.venv\\Scripts\\python.exe run_wer.py [--points 40 --per 3]
Audio is cached under cache/ (not committed).
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter

import numpy as np
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "Backend"))

from backend_M11_Voice_Engine import wer  # noqa: E402
from backend_M11_Voice_Engine.keys import KeyRing, load_keys  # noqa: E402

DATASET = "SPRINGLab/IndicTTS-English"
TOTAL = 151_640
MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
AGENT = "AI-Interviewer/1.0 (+https://github.com/MNEMOS-PREP)"
CACHE = HERE / "cache"


def rows(offset: int, length: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "train", "offset": offset, "length": length}
    )
    request = urllib.request.Request(
        f"https://datasets-server.huggingface.co/rows?{query}", headers={"User-Agent": AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())["rows"]


def to_16k_wav(data: bytes) -> bytes:
    audio, rate = sf.read(io.BytesIO(data), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != 16000:
        positions = np.arange(0, len(audio), rate / 16000)
        audio = np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)
    out = io.BytesIO()
    sf.write(out, audio, 16000, format="WAV", subtype="PCM_16")
    return out.getvalue()


def sample(points: int, per: int) -> list[dict]:
    """`per` consecutive utterances at `points` evenly spaced offsets — the
    corpus is stored speaker by speaker, so each point is (very likely) a
    different speaker. Cached."""
    CACHE.mkdir(exist_ok=True)
    index = CACHE / f"sample_{points}x{per}.json"
    if index.exists():
        return json.loads(index.read_text(encoding="utf-8"))
    out = []
    step = TOTAL // points
    for point in range(points):
        offset = point * step + step // 2
        try:
            batch = rows(offset, per)
        except Exception as exc:  # noqa: BLE001 - a point that fails is skipped
            print(f"offset {offset}: {exc}")
            continue
        for k, r in enumerate(batch):
            audio = r["row"]["audio"]
            src = audio[0]["src"] if isinstance(audio, list) and audio else None
            if not src:
                continue
            request = urllib.request.Request(src, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                wav = to_16k_wav(response.read())
            path = CACHE / f"{offset}_{k}.wav"
            path.write_bytes(wav)
            out.append({"path": path.name, "text": r["row"]["text"], "group": f"point {point:02d}"})
        print(f"point {point + 1}/{points}", flush=True)
    index.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def transcribe(ring: KeyRing, model: str, audio: bytes) -> tuple[str, int]:
    boundary = uuid.uuid4().hex
    fields = [("model", model), ("language", "en"), ("temperature", "0"), ("response_format", "json")]
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n' for n, v in fields
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    )
    body = "".join(parts).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    for attempt in range(8):
        key = ring.next()
        request = urllib.request.Request(
            URL,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": AGENT,
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                text = json.loads(response.read())["text"]
            return text, round((time.perf_counter() - started) * 1000)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 7:
                raise
            # The free tier allows ~20 a minute per key: wait as told.
            time.sleep(float(exc.headers.get("retry-after") or 10) + 1)
    raise RuntimeError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=40)
    parser.add_argument("--per", type=int, default=3)
    args = parser.parse_args()
    load_keys()
    ring = KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")
    if not ring:
        raise SystemExit("GROQ_API_KEYS is not configured (keys.txt).")
    items = sample(args.points, args.per)
    results: dict[str, list[dict]] = {}
    for model in MODELS:
        done_path = CACHE / f"hyp_{model}_{args.points}x{args.per}.json"
        done = json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else {}
        for i, item in enumerate(items):
            if item["path"] in done:
                continue
            text, ms = transcribe(ring, model, (CACHE / item["path"]).read_bytes())
            done[item["path"]] = {"text": text, "ms": ms}
            done_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
            print(f"{model} {i + 1}/{len(items)}", flush=True)
        results[model] = [
            {**item, "hyp": done[item["path"]]["text"], "ms": done[item["path"]]["ms"]} for item in items
        ]
    report(results, args)


def report(results: dict[str, list[dict]], args) -> None:
    lines = [
        "# Which recogniser hears Indian English best — M11 day 6",
        "",
        f"IndicTTS English (IIT Madras, CC BY 4.0), {args.points} points × {args.per} "
        "consecutive utterances across the corpus (very likely one speaker per point). "
        "Groq, `language=en`, `temperature=0`, no prompt. Written by `run_wer.py`.",
        "",
        "| Recogniser | Utterances | Words | WER | Worst point | Best point | Spread (points) | Latency p50 / p95 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    summary = {}
    for model, rows_ in results.items():
        scores = [wer.score(r["text"], r["hyp"]) for r in rows_]
        groups: dict[str, list] = {}
        for r, s in zip(rows_, scores, strict=True):
            groups.setdefault(r["group"], []).append(s)
        rates = {g: wer.pooled(v) * 100 for g, v in groups.items()}
        ms = sorted(r["ms"] for r in rows_)
        p95 = ms[max(0, round(0.95 * len(ms)) - 1)]
        summary[model] = wer.pooled(scores) * 100
        lines.append(
            f"| `{model}` | {len(rows_)} | {sum(s.words for s in scores)} | "
            f"**{summary[model]:.1f}%** | {max(rates.values()):.1f}% | {min(rates.values()):.1f}% | "
            f"{wer.gap(groups):.1f} | {statistics.median(ms):.0f} / {p95} ms |"
        )
    best = min(summary, key=summary.get)
    lines += ["", f"**By the number: `{best}`.**", ""]
    for model, rows_ in results.items():
        confusions: Counter = Counter()
        for r in rows_:
            ref, hyp = wer.normalise(r["text"]), wer.normalise(r["hyp"])
            for a, b in zip(ref, hyp, strict=False):
                if a != b:
                    confusions[(a, b)] += 1
        common = ", ".join(f"{a} → {b} ({n})" for (a, b), n in confusions.most_common(8))
        lines.append(f"- `{model}` — most common same-position differences: {common or 'none'}")
    lines += [
        "",
        "Caveats: read speech, not interview answers; no L1 labels, so the spread between "
        "points is between SPEAKERS, not accent groups — AC-11.4's gap needs Svarah or pilot "
        "recordings; IndicTTS references are lowercase without punctuation and both sides are "
        "normalised the same way (`wer.normalise`); numbers are not spelled out, which costs "
        "both candidates alike.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
