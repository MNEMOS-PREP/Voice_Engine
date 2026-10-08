"""Where the silences in a spoken line come from (2026-10-09).

The user, after a mock: "I could feel gaps in speech, awkward pauses,
sometimes if the text is too long". A line is cut into pieces (`@ai/core`'s
`sentencesOf`: sentences, the first cut at its first clause, any sentence of
twelve words or more cut at its clauses), M11 makes them side by side, and the
browser plays them back to back. Two kinds of silence can sit between two
pieces:

  * a STALL — the next piece is not made when the one before it ends;
  * a JOIN — the silence each piece carries at its end and its start, which
    adds up at every cut, mid-sentence included.

This makes realistic interviewer lines with the engine in-process, the
browser's order simulated (each piece played the moment the one before it
ends, if it is ready), and prints both per line.

    cd Backend
    set M11_TTS_PRECISION=q4 & set M11_TTS_ROWS=3
    .venv\\Scripts\\python ..\\research\\listening\\gap_bench.py [--out results.json]
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import time
import wave

import numpy as np

os.environ.setdefault("M11_TTS_CACHE", tempfile.mkdtemp(prefix="m11-gap-"))

from backend_M11_Voice_Engine import tts  # noqa: E402

#: Lines as the room says them. The long one is an LLM-written follow-up, the
#: kind the user meant; the hand-over is two voices.
LINES = {
    "short": [("os_suresh", "Okay. Tell me about the last project you worked on.")],
    "question": [
        (
            "os_suresh",
            "That's a good start. Can you walk me through how a hash map finds a key, "
            "and what happens when two keys collide?",
        )
    ],
    "long": [
        (
            "professor",
            "Thanks for that, it is a fair answer, though I would like you to go a little deeper. "
            "Suppose the table has grown to millions of entries and most of the keys now land in a "
            "handful of buckets. What would you look at first, how would you confirm it, and what "
            "would you change so that lookups stay fast?",
        )
    ],
    "handover": [
        ("methodical_engineer", "Thank you, that is all from me for this part. Dr. Raghavan, over to you."),
        ("professor", "Thanks, Priya. I would like to pick up on the project you mentioned earlier."),
    ],
}

NOT_AN_END = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof|St|vs|etc|e\.g|i\.e)\.$")


def words(text: str) -> int:
    return len(text.split())


def split_sentences(text: str) -> list[str]:
    pieces: list[str] = []
    for piece in re.split(r"(?<=[.?!])\s+", text):
        if pieces and NOT_AN_END.search(pieces[-1]):
            pieces[-1] = f"{pieces[-1]} {piece}"
        else:
            pieces.append(piece)
    return [p.strip() for p in pieces if p.strip()]


def first_clause(sentence: str, min_words: int = 4, long_words: int = 12) -> list[str]:
    if words(sentence) <= long_words:
        return [sentence]
    for match in re.finditer(r"[,;:—–] ", sentence):
        head, tail = sentence[: match.start() + 1].strip(), sentence[match.start() + 1 :].strip()
        if words(head) >= min_words and words(tail) >= min_words:
            return [head, tail]
    return [sentence]


def clauses(sentence: str, long_words: int = 12, min_words: int = 4) -> list[str]:
    total = words(sentence)
    if total <= long_words:
        return [sentence]
    best = None
    for match in re.finditer(r"[,;:—–] ", sentence):
        head, tail = sentence[: match.start() + 1].strip(), sentence[match.start() + 1 :].strip()
        if words(head) < min_words or words(tail) < min_words:
            continue
        off = abs(words(head) - total / 2)
        if best is None or off < best[2]:
            best = (head, tail, off)
    if best is None:
        return [sentence]
    return [*clauses(best[0], long_words, min_words), *clauses(best[1], long_words, min_words)]


def pieces_of(line: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """`@ai/core`'s sentencesOf, as of v0.28.0."""
    out: list[tuple[str, str]] = []
    for persona, text in line:
        for i, sentence in enumerate(split_sentences(text)):
            if not out and i == 0:
                head, *rest = first_clause(sentence)
                chunks = [head, *[c for tail in rest for c in clauses(tail)]]
            else:
                chunks = clauses(sentence)
            out += [(persona, chunk) for chunk in chunks]
    return out


def silences(data: bytes, floor_db: float = -40.0) -> tuple[float, float, float]:
    """(seconds, leading silence, trailing silence) of a WAV."""
    with wave.open(io.BytesIO(data)) as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    seconds = len(samples) / rate
    hop = rate // 100
    frames = [np.sqrt(np.mean(samples[i : i + hop] ** 2) + 1e-12) for i in range(0, len(samples) - hop, hop)]
    loud = np.array(frames) > 10 ** (floor_db / 20) * max(frames)
    if not loud.any():
        return seconds, seconds, 0.0
    first, last = int(np.argmax(loud)), len(loud) - int(np.argmax(loud[::-1]))
    return seconds, first / 100, max(0.0, seconds - last / 100)


def main() -> None:
    engine = tts.Engine(tts.Cast.load())
    engine.start()
    while engine.state == "loading":
        time.sleep(0.5)
    assert engine.state == "ready", engine.reason
    config = {
        "precision": engine.precision,
        "rows": tts.ROWS,
        "threads": tts.THREADS,
        "decoder_threads": tts.DECODER_THREADS,
    }
    print(json.dumps(config), flush=True)
    results = {"config": config, "lines": {}}
    for name, line in LINES.items():
        pieces = pieces_of(line)
        voices = [engine.cast.resolve(persona_id=persona) for persona, _ in pieces]
        t0 = time.perf_counter()
        engine.plan([(text, voice) for (_, text), voice in zip(pieces, voices, strict=True)], name)
        clock, rows = None, []
        for (persona, text), voice in zip(pieces, voices, strict=True):
            data, _, _ = engine.speak(text, voice, line=name)
            ready = time.perf_counter() - t0
            seconds, lead, trail = silences(data)
            start = ready if clock is None else max(ready, clock)
            stall = 0.0 if clock is None else max(0.0, ready - clock)
            clock = start + seconds
            rows.append(
                {
                    "persona": persona,
                    "text": text,
                    "ready_s": round(ready, 2),
                    "audio_s": round(seconds, 2),
                    "lead_s": round(lead, 2),
                    "trail_s": round(trail, 2),
                    "stall_s": round(stall, 2),
                }
            )
        joins = [rows[i]["trail_s"] + rows[i + 1]["lead_s"] for i in range(len(rows) - 1)]
        summary = {
            "first_audio_s": rows[0]["ready_s"],
            "speech_s": round(sum(r["audio_s"] for r in rows), 2),
            "stalls_s": round(sum(r["stall_s"] for r in rows), 2),
            "worst_stall_s": round(max(r["stall_s"] for r in rows), 2),
            "join_silence_s": [round(j, 2) for j in joins],
            "pieces": len(rows),
        }
        results["lines"][name] = {"summary": summary, "pieces": rows}
        print(f"{name}: {json.dumps(summary)}", flush=True)
        for r in rows:
            print(
                f"   ready {r['ready_s']:6.2f}  {r['audio_s']:5.2f}s  lead {r['lead_s']:.2f} trail {r['trail_s']:.2f}"
                f"  stall {r['stall_s']:.2f}  [{r['persona']}] {r['text']}",
                flush=True,
            )
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
