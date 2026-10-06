"""Hearing the student — M11 day 4: speech recognition with word timestamps.

Groq's `whisper-large-v3-turbo`, through its OpenAI-compatible
`/audio/transcriptions` with `verbose_json` and BOTH granularities. Confirmed
on 2026-10-06 (the build order asked): `words` carries each word's start and
end, `segments` carries `avg_logprob` and `no_speech_prob`; twelve seconds of
audio came back in ~0.5 s. The browser's own recognition stays as the no-key
fallback — it is what M06's room used before this, and still shows the live
caption while the student speaks.

What this adds over the browser's recognition, and why it matters here:

- **Word timestamps** (FR-11.3): where each word fell, so a stop can be placed
  in the answer (`heard_up_to`, day 9) and speech's real end is known — the
  clock the latency budget is measured from (FR-11.20).
- **Confidence** (FR-11.15): Whisper gives none per word, but each segment's
  mean log-probability is a calibrated-enough signal. Words take their
  segment's; runs of low-confidence words become `low_confidence_spans`,
  which M13 must not cite as evidence (a quote nobody is sure was said).
- **Accuracy on technical Indian English** — "Dijkstra", "hash map", "B-tree":
  the question being answered is passed as Whisper's prompt, which biases the
  vocabulary toward the words the answer is likely to use.

Whisper's known failure is inventing text over silence ("Thank you."); a
segment that is probably not speech AND unlikely as text is dropped, the
standard filter. Overlapping word times — Whisper's alignment is not
monotonic — are clamped so every word starts where the last one ended at the
earliest.

Nothing is stored. The audio is sent to Groq to be transcribed and dropped
here; keeping it is FR-11.19's, with consent (day 12).

**The language is detected, not assumed** (FR-11.22, EC-11.10; 2026-10-07,
`research/codeswitch`). Told "English", Whisper invented English for half of
eight Hindi recordings ("This is the end of the day.", once the prompt read
back) — a Hindi answer judged on words never said, which is the penalty the
spec forbids and fabricated evidence besides. Left to detect, it heard all
eight as Hindi and wrote them as said, and all eight English recordings came
back word for word as before. A detection outside the languages students here
speak (a short "Yes." heard as Welsh) is asked again as English.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from .keys import KeyRing

ASR_MODEL = os.getenv("M11_ASR_MODEL", "whisper-large-v3-turbo")
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
#: Groq is behind Cloudflare, which refuses Python's default agent (error 1010).
USER_AGENT = "AI-Interviewer/1.0 (+https://github.com/MNEMOS-PREP)"
#: Groq's own limit is 25 MB; a five-minute answer at 16 kHz WAV is ~10 MB.
MAX_AUDIO_BYTES = 12 * 1024 * 1024
#: A word below this confidence is a word nobody should quote.
LOW_CONFIDENCE = 0.45
#: "auto" (detect) or a language code to force — "en" is the old behaviour.
LANGUAGE = os.getenv("M11_ASR_LANGUAGE", "auto")
#: What a student here may answer in; a detection outside it is retried as
#: English. Whisper names languages in English ("Hindi"), any case.
SPOKEN_HERE = frozenset(
    {
        "english",
        "hindi",
        "urdu",
        "bengali",
        "marathi",
        "gujarati",
        "punjabi",
        "tamil",
        "telugu",
        "kannada",
        "malayalam",
        "odia",
        "assamese",
        "nepali",
        "sanskrit",
    }
)
#: Whisper's hallucination filter: not speech AND unlikely as text.
NO_SPEECH = 0.6
UNLIKELY_LOGPROB = -1.0

Transport = Callable[[str, bytes, dict[str, str], float], dict[str, Any]]


class AsrUnavailable(Exception):
    """Recognition cannot run: no key, the provider refused, or the network.
    The browser's own recognition carries the answer instead."""


class Word(BaseModel):
    word: str
    start_ms: int
    end_ms: int
    #: The word's segment's confidence, 0–1 (Whisper gives none per word).
    confidence: float


class ASRResult(BaseModel):
    """Spec §5's `ASRResult`, as far as one transcription call can fill it."""

    text: str
    words: list[Word]
    duration_ms: int
    language: str | None
    mean_confidence: float
    #: (start_ms, end_ms) runs of low-confidence words — not citable (FR-11.15).
    low_confidence_spans: list[tuple[int, int]]
    #: The first word's start and the last word's end: where speech was.
    speech_start_ms: int | None
    speech_end_ms: int | None
    model: str
    latency_ms: int


def _keys() -> KeyRing:
    return KeyRing.from_env("GROQ_API_KEYS", "GROQ_API_KEY")


_ring: KeyRing | None = None


def ring() -> KeyRing:
    global _ring
    if _ring is None or not _ring:
        _ring = _keys()
    return _ring


def state() -> dict[str, Any]:
    """Whether recognition can run, and if not, why — in words for the team."""
    keys = ring()
    if not keys:
        return {"available": False, "model": ASR_MODEL, "reason": "No Groq key is configured."}
    return {"available": True, "model": ASR_MODEL, "reason": f"{len(keys)} key(s)"}


def _http(url: str, body: bytes, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


_transport: Transport = _http


def set_transport(transport: Transport | None) -> None:
    """Tests replace the network; None restores it."""
    global _transport
    _transport = transport or _http


def _multipart(
    audio: bytes, content_type: str, prompt: str | None, language: str | None = None
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    fields = [
        ("model", ASR_MODEL),
        *([("language", language)] if language else []),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("timestamp_granularities[]", "segment"),
        ("temperature", "0"),
    ]
    if prompt:
        fields.append(("prompt", prompt))
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields
    ]
    extension = "wav" if "wav" in content_type else "webm" if "webm" in content_type else "audio"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="answer.{extension}"\r\nContent-Type: {content_type}\r\n\r\n'
    )
    body = "".join(parts).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    return body, boundary


def prompt_for(context: str | None) -> str | None:
    """The question being answered, as Whisper's prompt: it biases the words
    toward the ones the answer is likely to use. Whisper reads ~224 tokens."""
    if not context or not context.strip():
        return None
    return "Interview question: " + " ".join(context.split())[:400]


def transcribe(
    audio: bytes, content_type: str = "audio/wav", *, context: str | None = None
) -> ASRResult:
    if not audio:
        raise ValueError("No audio.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("That answer is too long to transcribe in one piece.")
    keys = ring()
    if not keys:
        raise AsrUnavailable("No Groq key is configured.")
    prompt = prompt_for(context)
    forced = None if LANGUAGE == "auto" else LANGUAGE
    result = _ask(keys, audio, content_type, prompt, forced)
    if forced is None and (result.language or "") not in SPOKEN_HERE:
        # Detected as a language nobody here answers in: heard again as English.
        result = _ask(keys, audio, content_type, prompt, "en")
    return result


def _ask(
    keys: KeyRing, audio: bytes, content_type: str, prompt: str | None, language: str | None
) -> ASRResult:
    body, boundary = _multipart(audio, content_type, prompt, language)
    last = "no attempt"
    # Each key once: a pool of keys is a pool of quota (keys.py).
    for _ in range(len(keys)):
        key = keys.next()
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": USER_AGENT,
        }
        started = time.perf_counter()
        try:
            raw = _transport(URL, body, headers, 30.0)
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in (401, 403, 429):
                continue  # this key is spent or refused; the next may not be
            raise AsrUnavailable(f"The recogniser refused the audio ({last}).") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AsrUnavailable(
                f"The recogniser could not be reached ({type(exc).__name__})."
            ) from None
        return shape(raw, latency_ms=round((time.perf_counter() - started) * 1000))
    raise AsrUnavailable(f"Every key was refused ({last}).")


def _confidence(segment: dict[str, Any]) -> float:
    logprob = segment.get("avg_logprob")
    if logprob is None:
        return 1.0
    return max(0.0, min(1.0, math.exp(float(logprob))))


def _is_hallucination(segment: dict[str, Any]) -> bool:
    return (
        float(segment.get("no_speech_prob") or 0.0) > NO_SPEECH
        and float(segment.get("avg_logprob") or 0.0) < UNLIKELY_LOGPROB
    )


def shape(raw: dict[str, Any], *, latency_ms: int = 0) -> ASRResult:
    """Groq's `verbose_json`, as spec §5's `ASRResult`. Pure."""
    segments = [s for s in raw.get("segments") or [] if isinstance(s, dict)]
    dropped = [s for s in segments if _is_hallucination(s)]
    kept = [s for s in segments if not _is_hallucination(s)]

    def segment_at(seconds: float) -> dict[str, Any] | None:
        for segment in kept:
            if float(segment.get("start", 0)) <= seconds < float(segment.get("end", 0)) + 0.01:
                return segment
        return None

    def in_dropped(seconds: float) -> bool:
        return any(
            float(s.get("start", 0)) <= seconds < float(s.get("end", 0)) + 0.01 for s in dropped
        )

    words: list[Word] = []
    floor_ms = 0
    for item in raw.get("words") or []:
        text = str(item.get("word", "")).strip()
        if not text:
            continue
        start = float(item.get("start", 0.0))
        if in_dropped(start):
            continue
        start_ms = max(floor_ms, round(start * 1000))
        end_ms = max(start_ms, round(float(item.get("end", start)) * 1000))
        segment = segment_at(start)
        words.append(
            Word(
                word=text,
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=round(_confidence(segment) if segment else 1.0, 3),
            )
        )
        floor_ms = end_ms

    if words:
        text = " ".join(w.word for w in words)
    elif dropped and not kept:
        text = ""
    else:
        text = str(raw.get("text", "")).strip()

    spans: list[tuple[int, int]] = []
    for w in words:
        if w.confidence >= LOW_CONFIDENCE:
            continue
        if spans and w.start_ms - spans[-1][1] <= 300:
            spans[-1] = (spans[-1][0], w.end_ms)
        else:
            spans.append((w.start_ms, w.end_ms))

    total = sum(max(0.0, float(s.get("end", 0)) - float(s.get("start", 0))) for s in kept)
    if total > 0:
        mean = (
            sum(
                _confidence(s) * max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
                for s in kept
            )
            / total
        )
    else:
        mean = 1.0 if words else 0.0

    return ASRResult(
        text=text,
        words=words,
        duration_ms=round(float(raw.get("duration") or 0.0) * 1000),
        language=str(raw["language"]).lower() if raw.get("language") else None,
        mean_confidence=round(mean, 3),
        low_confidence_spans=spans,
        speech_start_ms=words[0].start_ms if words else None,
        speech_end_ms=words[-1].end_ms if words else None,
        model=ASR_MODEL,
        latency_ms=latency_ms,
    )


__all__ = [
    "ASRResult",
    "ASR_MODEL",
    "AsrUnavailable",
    "MAX_AUDIO_BYTES",
    "Word",
    "prompt_for",
    "set_transport",
    "shape",
    "state",
    "transcribe",
]
