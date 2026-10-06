"""Has the student finished? — spec §6.3, FR-11.5 (TODO §7, day 5).

What is pinned: the features are Whisper's, reproduced without
`transformers` — the numbers below came from `WhisperFeatureExtractor`
itself, on the same signal, on 2026-10-06; the last 8 s are kept and a
shorter stretch is padded at the START (the reference implementation's
choice, and the model's training); the route takes WAV from a signed-in
student and says 503 when the model is not ready, so the browser ends turns
on silence alone.
"""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from backend_M11_Voice_Engine import turn

from .conftest import student

SOMEONE = "4d2c9b1a-7e6f-4a3b-9c8d-1e2f3a4b5c6d"


def two_tones() -> np.ndarray:
    """2 s of 440 Hz and 1,700 Hz — the signal the reference numbers are for."""
    t = np.arange(32000) / 16000
    return (0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 1700 * t)).astype(
        np.float32
    )


def wav(audio: np.ndarray, rate: int = 16000, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_the_features_are_whispers_as_the_reference_computes_them():
    f = turn.features(two_tones())
    assert f.shape == (1, 80, 800) and f.dtype == np.float32
    f = f[0]
    # From transformers' WhisperFeatureExtractor(chunk_length=8), do_normalize.
    assert abs(float(f.mean()) - -0.143036) < 1e-4
    assert int(np.argmax(f[:, 799])) == 11
    for (mel_bin, frame), want in {
        (0, 0): -0.196949,
        (10, 700): 1.713585,
        (25, 650): -0.196949,
        (40, 799): 1.516574,
        (79, 700): -0.196949,
        (12, 799): 1.661871,
    }.items():
        assert abs(float(f[mel_bin, frame]) - want) < 1e-4, (mel_bin, frame)


def test_the_last_eight_seconds_are_kept_and_a_short_stretch_padded_at_the_start():
    long = np.arange(16000 * 9, dtype=np.float32)
    kept = turn.last_seconds(long)
    assert len(kept) == 16000 * 8 and kept[-1] == long[-1] and kept[0] == long[16000]
    short = np.ones(16000, dtype=np.float32)
    padded = turn.last_seconds(short)
    assert len(padded) == 16000 * 8
    assert padded[: 16000 * 7].sum() == 0 and padded[-1] == 1.0


def test_only_16k_16_bit_mono_wav_is_read():
    audio = turn.read_wav(wav(np.full(1600, 0.5, dtype=np.float32)))
    assert len(audio) == 1600 and abs(float(audio[0]) - 0.5) < 1e-3
    with pytest.raises(ValueError, match="16000"):
        turn.read_wav(wav(np.zeros(1600, dtype=np.float32), rate=48000))
    with pytest.raises(ValueError, match="Not a WAV"):
        turn.read_wav(b"not audio")


class Fake(turn.Classifier):
    def __init__(self, probability: float) -> None:
        super().__init__()
        self.state, self.reason = "ready", "fake"
        self.probability = probability
        self.heard = 0

    def finished(self, audio):
        self.heard = len(audio)
        return self.probability, 3


def test_the_model_off_means_silence_alone_decides(client):
    state = client.get("/v1/voice/turn", headers=student(SOMEONE)).json()
    assert state["state"] == "off"
    r = client.post(
        "/v1/voice/turn",
        content=wav(np.zeros(16000, dtype=np.float32)),
        headers={**student(SOMEONE), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 503


def test_a_finished_turn_and_an_unfinished_one(client):
    for probability, finished in ((0.93, True), (0.04, False)):
        fake = Fake(probability)
        turn.set_classifier(fake)
        r = client.post(
            "/v1/voice/turn",
            content=wav(np.zeros(24000, dtype=np.float32)),
            headers={**student(SOMEONE), "Content-Type": "audio/wav"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"probability": probability, "finished": finished, "latency_ms": 3}
        assert fake.heard == 24000


def test_nobody_signed_in_and_anything_but_wav_are_refused(client):
    turn.set_classifier(Fake(0.9))
    body = wav(np.zeros(1600, dtype=np.float32))
    assert (
        client.post(
            "/v1/voice/turn", content=body, headers={"Content-Type": "audio/wav"}
        ).status_code
        == 401
    )
    r = client.post(
        "/v1/voice/turn", content=body, headers={**student(SOMEONE), "Content-Type": "audio/webm"}
    )
    assert r.status_code == 415
