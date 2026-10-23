"""Hearing the student — spec §6.7, FR-11.3, FR-11.15 (TODO §7, day 4).

What is pinned: Groq's `verbose_json` becomes spec §5's `ASRResult` — words
with times that never run backwards, confidence from each word's segment,
low-confidence runs as spans nobody may quote, and Whisper's invented text
over silence dropped; a refused key hands over to the next; the question is
the recogniser's prompt; and the route is for signed-in students sending
audio, saying 503 when recognition cannot run so the browser's own carries on.
"""

from __future__ import annotations

import urllib.error

import pytest

from backend_M11_Voice_Engine import asr

from .conftest import student

SOMEONE = "9b6a7d3e-1f2c-4a5b-8c9d-0e1f2a3b4c5d"

#: What Groq returned for a real answer, trimmed: two segments, the second
#: mumbled; one overlapping word time, as Whisper's alignment produces.
RAW = {
    "task": "transcribe",
    "language": "English",
    "duration": 9.4,
    "text": " A hash map hashes the key. Then it um reads the bucket.",
    "segments": [
        {"start": 0.0, "end": 3.0, "avg_logprob": -0.2, "no_speech_prob": 0.01},
        {"start": 3.0, "end": 6.2, "avg_logprob": -1.4, "no_speech_prob": 0.05},
    ],
    "words": [
        {"word": "A", "start": 0.4, "end": 0.5},
        {"word": "hash", "start": 0.5, "end": 0.8},
        {"word": "map", "start": 0.8, "end": 1.1},
        {"word": "hashes", "start": 1.0, "end": 1.6},  # starts before "map" ends
        {"word": "the", "start": 1.6, "end": 1.7},
        {"word": "key.", "start": 1.7, "end": 2.2},
        {"word": "Then", "start": 3.1, "end": 3.4},
        {"word": "it", "start": 3.4, "end": 3.5},
        {"word": "um", "start": 3.5, "end": 3.9},
        {"word": "reads", "start": 4.0, "end": 4.4},
        {"word": "the", "start": 4.4, "end": 4.5},
        {"word": "bucket.", "start": 4.5, "end": 5.1},
    ],
}


def test_words_keep_their_times_and_never_run_backwards():
    result = asr.shape(RAW, latency_ms=480)
    assert [w.word for w in result.words][:4] == ["A", "hash", "map", "hashes"]
    starts = [w.start_ms for w in result.words]
    assert starts == sorted(starts)
    assert all(w.end_ms >= w.start_ms for w in result.words)
    hashes = result.words[3]
    assert hashes.start_ms == 1100, "clamped to where 'map' ended"
    assert result.speech_start_ms == 400 and result.speech_end_ms == 5100
    assert result.duration_ms == 9400 and result.latency_ms == 480
    assert result.text.startswith("A hash map hashes the key.")


def test_a_mumbled_stretch_is_marked_and_not_citable():
    """FR-11.15: the second segment's words are unsure; they form one span."""
    result = asr.shape(RAW)
    sure = result.words[0]
    unsure = result.words[-1]
    assert sure.confidence > 0.8
    assert unsure.confidence < asr.LOW_CONFIDENCE
    assert result.low_confidence_spans == [(3100, 5100)]
    assert 0.3 < result.mean_confidence < 0.6


def test_text_whisper_invents_over_silence_is_dropped():
    """Five seconds of room tone came back as "Thank you." — not speech, and
    not likely as text: the standard filter."""
    silence = {
        "duration": 5.0,
        "text": " Thank you.",
        "segments": [{"start": 0.0, "end": 5.0, "avg_logprob": -1.3, "no_speech_prob": 0.9}],
        "words": [
            {"word": "Thank", "start": 1.0, "end": 1.4},
            {"word": "you.", "start": 1.4, "end": 1.8},
        ],
    }
    result = asr.shape(silence)
    assert result.text == ""
    assert result.words == [] and result.speech_end_ms is None


def test_the_question_is_the_recognisers_prompt():
    prompt = asr.prompt_for("Explain   Dijkstra's\nalgorithm.")
    assert prompt.startswith("Interview question: Explain Dijkstra's algorithm. ")
    long = asr.prompt_for("x " * 900)
    assert len(long) <= len("Interview question: ") + 400 + 1 + len(asr.SPOKEN_STYLE)


def test_the_prompt_is_written_the_way_people_talk_so_fillers_are_kept():
    """research/fillers (2026-10-23): on the question alone Whisper wrote 0 of
    53 "um"s and "uh"s; ending the prompt on a line with them kept 65 of 97
    and invented none. With no question, the line is the whole prompt."""
    assert asr.prompt_for("Explain Dijkstra's algorithm.").endswith(asr.SPOKEN_STYLE)
    words = asr.SPOKEN_STYLE.lower().replace(",", " ").replace(".", " ").split()
    assert "um" in words and "uh" in words
    assert asr.prompt_for(None) == asr.SPOKEN_STYLE
    assert asr.prompt_for("  ") == asr.SPOKEN_STYLE


def test_no_key_means_no_recognition_and_says_so():
    assert asr.state()["available"] is False
    with pytest.raises(asr.AsrUnavailable, match="No Groq key"):
        asr.transcribe(b"RIFF....", "audio/wav")


def test_a_refused_key_hands_over_to_the_next(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "key-one,key-two")
    used: list[str] = []

    def transport(url, body, headers, timeout):
        used.append(headers["Authorization"])
        if len(used) == 1:
            raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
        assert b'name="prompt"' in body and b"Dijkstra" in body
        assert headers["User-Agent"].startswith("AI-Interviewer")
        return RAW

    asr.set_transport(transport)
    result = asr.transcribe(b"RIFF....", "audio/wav", context="Explain Dijkstra's algorithm.")
    assert len(used) == 2 and used[0] != used[1]
    assert result.words[0].word == "A"


def test_the_language_is_detected_not_assumed(monkeypatch):
    """FR-11.22: no language is sent, and a Hindi answer comes back as said,
    tagged — not as the English Whisper invents when told to expect it."""
    monkeypatch.setenv("GROQ_API_KEYS", "key-one")
    hindi = {**RAW, "language": "Hindi", "text": " हैश मैप की को बकेट में रखता है",
             "words": [{"word": "हैश", "start": 0.4, "end": 0.8}]}
    bodies: list[bytes] = []

    def transport(url, body, headers, timeout):
        bodies.append(body)
        return hindi

    asr.set_transport(transport)
    result = asr.transcribe(b"RIFF....", "audio/wav")
    assert len(bodies) == 1 and b'name="language"' not in bodies[0]
    assert result.language == "hindi"
    assert result.text == "हैश"


def test_a_language_nobody_here_speaks_is_heard_again_as_english(monkeypatch):
    """A short answer detected as Welsh is asked again, as English."""
    monkeypatch.setenv("GROQ_API_KEYS", "key-one")
    bodies: list[bytes] = []

    def transport(url, body, headers, timeout):
        bodies.append(body)
        return {**RAW, "language": "Welsh"} if len(bodies) == 1 else RAW

    asr.set_transport(transport)
    result = asr.transcribe(b"RIFF....", "audio/wav")
    assert len(bodies) == 2
    assert b'name="language"\r\n\r\nen\r\n' in bodies[1]
    assert result.language == "english"


def test_every_key_refused_is_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "only-key")

    def transport(url, body, headers, timeout):
        raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)

    asr.set_transport(transport)
    with pytest.raises(asr.AsrUnavailable, match="refused"):
        asr.transcribe(b"RIFF....", "audio/wav")


# ── the route ─────────────────────────────────────────────────────────────


def test_nobody_signed_in_cannot_send_audio(client):
    r = client.post(
        "/v1/voice/transcribe", content=b"RIFF....", headers={"Content-Type": "audio/wav"}
    )
    assert r.status_code == 401


def test_only_audio_is_transcribed(client):
    r = client.post(
        "/v1/voice/transcribe",
        content=b"{}",
        headers={**student(SOMEONE), "Content-Type": "application/json"},
    )
    assert r.status_code == 415


def test_without_a_key_the_route_says_503_so_the_browser_carries_on(client):
    assert client.get("/v1/voice/asr", headers=student(SOMEONE)).json()["available"] is False
    r = client.post(
        "/v1/voice/transcribe",
        content=b"RIFF....",
        headers={**student(SOMEONE), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 503
    assert "not available" in r.json()["detail"]


def test_an_answer_comes_back_as_words_with_times(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "a-key")
    asr.set_transport(lambda url, body, headers, timeout: RAW)
    r = client.post(
        "/v1/voice/transcribe?context=What+is+a+hash+map%3F",
        content=b"RIFF....",
        headers={**student(SOMEONE), "Content-Type": "audio/webm;codecs=opus"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["words"][0] == {"word": "A", "start_ms": 400, "end_ms": 500, "confidence": 0.819}
    assert body["low_confidence_spans"] == [[3100, 5100]]
    assert client.get("/v1/voice/asr", headers=student(SOMEONE)).json()["available"] is True
