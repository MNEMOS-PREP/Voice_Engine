"""Can a long sentence be cut where a reader breathes? (2026-10-10)

The user, after a mock: "when a large sentence is followed by a sentence,
the gap in audio is huge and makes it feel AI-like". A sentence with no comma
("Recall a situation where you were asked a question you didn't know the
answer to during an interview.") was one piece, made in one row of the
language model, and one row makes ~19 speech tokens a second while speech
needs 25: a long piece is always late. Cut where a reader breathes, its
pieces are made side by side.

The risk is the tune. A piece made alone may END like a sentence — the pitch
falling, the last syllable drawn out — and then the next piece starts, and
it sounds like a list of fragments. This probe says each sentence whole and
cut, in several cast voices, with and without a comma closing each cut, and
measures for the end of every non-final piece:

  - fall: the pitch over its last voiced 250 ms against the piece's median,
    in semitones (a sentence's end falls several; a continuation stays level
    or rises);
  - read-back: does M11's recogniser hear every word (a cut must not lose one).

The whole sentence's own end is the reference for "final".

    python research/listening/breath_probe.py

Writes research/listening/breath/results.json (clips beside it).
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import time
import urllib.request

import numpy as np
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "breath"
M11 = "http://127.0.0.1:8111"
WHO = {"X-Role": "student", "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004"}

sys.path.insert(0, str(HERE))
from probe_voices import wer  # noqa: E402

#: Long questions from the mocks, and where a reader would breathe.
SENTENCES = (
    [
        "Recall a situation where you were asked a question you didn't know the answer to during an interview.",
        ["Recall a situation where you were asked a question", "you didn't know the answer to during an interview."],
    ],
    [
        "Tell me about a time you had to solve a technical problem while thinking aloud with a teammate.",
        ["Tell me about a time you had to solve a technical problem", "while thinking aloud with a teammate."],
    ],
    [
        "Why is it important to choose a proper primary key for the Orders table and what could go wrong if you pick a mutable attribute?",
        ["Why is it important to choose a proper primary key for the Orders table", "and what could go wrong if you pick a mutable attribute?"],
    ],
)
PERSONAS = ("hr_nisha", "db_neha", "bar_raiser", "mgr_sanjay")


def speak(text: str, persona: str) -> tuple[np.ndarray, int]:
    body = json.dumps({"text": text, "persona_id": persona}).encode()
    request = urllib.request.Request(
        f"{M11}/v1/voice/speak", data=body, headers={**WHO, "Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        audio, rate = sf.read(io.BytesIO(response.read()), dtype="float32")
    return (audio if audio.ndim == 1 else audio.mean(axis=1)), rate


def heard(audio: np.ndarray, rate: int) -> str:
    buffer = io.BytesIO()
    sf.write(buffer, audio, rate, format="WAV")
    request = urllib.request.Request(
        f"{M11}/v1/voice/transcribe", data=buffer.getvalue(), headers={**WHO, "Content-Type": "audio/wav"}, method="POST"
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read())["text"]
        except Exception:  # noqa: BLE001 - a rate limit: wait and ask again
            time.sleep(5 * (attempt + 1))
    return ""


def trimmed(audio: np.ndarray, rate: int) -> np.ndarray:
    hop = rate // 100
    levels = np.sqrt(np.convolve(audio**2, np.ones(hop) / hop, mode="same"))
    loud = np.nonzero(levels > levels.max() * 10 ** (-42 / 20))[0]
    return audio[loud[0] : loud[-1] + 1] if loud.size else audio


def fall(audio: np.ndarray, rate: int) -> float | None:
    """Semitones from the piece's median pitch to its last voiced 250 ms."""
    import librosa

    f0, voiced, _ = librosa.pyin(trimmed(audio, rate), fmin=70, fmax=400, sr=rate, frame_length=1024)
    times = librosa.times_like(f0, sr=rate, hop_length=256)
    pitch = f0[voiced & np.isfinite(f0)]
    if pitch.size < 10:
        return None
    last_voiced = times[voiced][-1]
    tail = f0[(times > last_voiced - 0.25) & voiced & np.isfinite(f0)]
    return float(12 * np.log2(np.median(tail) / np.median(pitch)))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []
    for persona in PERSONAS:
        for n, (whole, cut) in enumerate(SENTENCES):
            audio, rate = speak(whole, persona)
            sf.write(OUT / f"{persona}_{n}_whole.wav", audio, rate)
            row = {
                "persona": persona,
                "sentence": n,
                "whole_end_fall": fall(audio, rate),
                "whole_seconds": round(len(trimmed(audio, rate)) / rate, 2),
            }
            for style, close in (("bare", ""), ("comma", ",")):
                texts = [piece + close for piece in cut[:-1]] + [cut[-1]]
                clips = [speak(text, persona) for text in texts]
                joined = np.concatenate(
                    [np.concatenate([trimmed(a, r), np.zeros(int(0.1 * r), np.float32)]) for a, r in clips]
                )
                sf.write(OUT / f"{persona}_{n}_{style}.wav", joined, rate)
                row[f"{style}_cut_fall"] = [fall(a, r) for a, r in clips[:-1]]
                row[f"{style}_seconds"] = round(sum(len(trimmed(a, r)) / r for a, r in clips), 2)
                row[f"{style}_wer"] = round(wer(whole, heard(joined, rate)), 3)
            row["whole_wer"] = round(wer(whole, heard(audio, rate)), 3)
            rows.append(row)
            print(json.dumps(row), flush=True)
    (OUT / "results.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for style in ("bare", "comma"):
        falls = [f for row in rows for f in row[f"{style}_cut_fall"] if f is not None]
        print(f"{style}: cut end {np.mean(falls):+.2f} st (median {np.median(falls):+.2f}); "
              f"wer {np.mean([row[f'{style}_wer'] for row in rows]):.3f}")
    ends = [row["whole_end_fall"] for row in rows if row["whole_end_fall"] is not None]
    print(f"a sentence's own end: {np.mean(ends):+.2f} st; whole wer {np.mean([row['whole_wer'] for row in rows]):.3f}")


if __name__ == "__main__":
    main()
