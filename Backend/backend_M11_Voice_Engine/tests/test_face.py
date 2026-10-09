"""The interviewer's face, moving with their own voice (2026-10-08).

The model is faked: these hold what M11 does around it — frames keyed like the
sentence's audio, made when the sentence is made, shaped for a face seen
small, and heads served with what their zip says about itself.
"""

from __future__ import annotations

import io
import json
import math
import uuid
import zipfile

import numpy as np
import pytest

from backend_M11_Voice_Engine import face, tts

from .conftest import student
from .test_tts import FakeEngine

NAMES = [f"shape{i}" for i in range(50)] + ["jawOpen", "mouthFunnel"]


class FakeFace(face.FaceEngine):
    """The real engine around a model that opens the jaw a little, always."""

    def __init__(self, tmp_path):
        super().__init__(cache_dir=tmp_path / "face")
        self._names = list(NAMES)
        self.calls = 0

    def infer(self, samples):
        self.calls += 1
        frames = math.ceil(face.FPS * len(samples) / face.MODEL_RATE)
        out = np.zeros((frames, len(NAMES)), dtype=np.float32)
        out[:, NAMES.index("jawOpen")] = 0.2
        out[:, NAMES.index("mouthFunnel")] = 0.9
        return out

    def prepare(self, key, audio):
        # In-line, so a test sees it done.
        self.make(key, audio)


@pytest.fixture
def fake_face(tmp_path):
    engine = FakeFace(tmp_path)
    face.set_engine(engine)
    yield engine
    face.set_engine(None)


@pytest.fixture
def fake_voice():
    engine = FakeEngine()
    tts.set_engine(engine)
    return engine


def wav(seconds: float, rate: int = 24_000) -> bytes:
    return tts.to_wav(np.zeros(int(seconds * rate), dtype=np.float32), rate)


# ── shaping ──────────────────────────────────────────────────────────────


def test_a_second_of_audio_is_thirty_frames(fake_face):
    out = fake_face.frames_for(wav(1.0))
    assert out["fps"] == 30 and len(out["frames"]) == 30
    assert out["names"] == NAMES and len(out["frames"][0]) == len(NAMES)


def test_the_mouth_is_emphasised_and_nothing_goes_past_one(fake_face):
    out = fake_face.frames_for(wav(0.5))
    jaw = out["frames"][10][NAMES.index("jawOpen")]
    funnel = out["frames"][10][NAMES.index("mouthFunnel")]
    assert jaw == pytest.approx(0.2 * face.EMPHASIS["jawOpen"], abs=1e-3)
    assert funnel == 1.0, "0.9 x 1.5 is clipped, never past one"
    assert out["frames"][10][0] == 0.0, "only the mouth is emphasised"


def test_smoothing_steadies_a_one_frame_spike_and_keeps_a_held_closure():
    names = ["jawOpen", "mouthClose"]
    raw = np.zeros((9, 2), dtype=np.float32)
    raw[4, 0] = 1.0  # one frame of jaw: a jitter
    raw[2:7, 1] = 0.6  # five frames of a closed mouth: a /p/
    shaped = face.shape(raw, names)
    assert shaped[4, 0] < 0.85, "a single-frame spike is softened"
    assert shaped[4, 1] == pytest.approx(0.6), "a closure several frames long is kept"


def test_audio_at_any_rate_is_listened_to_at_sixteen_kilohertz():
    samples, rate = face.read_wav(wav(2.0, rate=24_000))
    assert rate == 24_000 and len(face.resample(samples, rate)) == 32_000


# ── the routes ───────────────────────────────────────────────────────────


def test_a_sentence_says_where_its_face_is_and_the_frames_are_there(client, fake_voice, fake_face):
    said = client.post(
        "/v1/voice/speak",
        json={"text": "Tell me about hashing.", "persona_id": "bar_raiser"},
        headers=student(uuid.uuid4()),
    )
    assert said.status_code == 200, said.text
    key = said.headers["x-face"]
    assert "X-Face" in said.headers["access-control-expose-headers"]
    frames = client.get(f"/v1/voice/face/{key}", headers=student(uuid.uuid4()))
    assert frames.status_code == 200, frames.text
    body = frames.json()
    assert body["fps"] == 30 and body["frames"], "frames for the sentence just said"
    assert fake_face.calls == 1, "made once, when the sentence was made"


def test_frames_for_a_cached_sentence_are_made_from_its_audio(client, fake_voice, fake_face):
    """Said in an earlier run: the audio is on disk, the frames are not."""
    voice = tts.Cast.load().voices[tts.Cast.load().cast["bar_raiser"]]
    audio, _, _ = fake_voice.speak("Hello there.", voice)
    key = fake_voice.cache_key("Hello there.", voice)
    got = client.get(f"/v1/voice/face/{key}", headers=student(uuid.uuid4()))
    assert got.status_code == 200 and got.json()["frames"]


def test_no_frames_for_a_sentence_nobody_said(client, fake_voice, fake_face):
    missing = client.get(f"/v1/voice/face/{'0' * 40}", headers=student(uuid.uuid4()))
    assert missing.status_code == 404


def test_frames_are_for_signed_in_callers(client, fake_voice, fake_face):
    assert client.get(f"/v1/voice/face/{'0' * 40}").status_code == 401


def test_without_the_model_the_route_says_so(client, fake_voice, monkeypatch):
    voice = tts.Cast.load().voices[tts.Cast.load().cast["bar_raiser"]]
    fake_voice.speak("Hello there.", voice)
    key = fake_voice.cache_key("Hello there.", voice)
    monkeypatch.setenv("M11_FACE", "off")
    face.set_engine(face.FaceEngine())
    try:
        got = client.get(f"/v1/voice/face/{key}", headers=student(uuid.uuid4()))
    finally:
        face.set_engine(None)
    assert got.status_code == 503 and "switched off" in got.json()["detail"]


def head_zip(persona: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{persona}/skin.glb", b"glTF")
        archive.writestr(
            f"{persona}/meta.json",
            json.dumps({"persona": persona, "built": "2026-10-08", "ai_generated": True}),
        )
    return buffer.getvalue()


def test_heads_are_listed_with_what_they_say_about_themselves(client, tmp_path, monkeypatch):
    monkeypatch.setattr(face, "FACES_DIR", tmp_path / "faces")
    (tmp_path / "faces").mkdir()
    (tmp_path / "faces" / "bar_raiser.zip").write_bytes(head_zip("bar_raiser"))
    body = client.get("/v1/voice/faces").json()
    assert [f["persona"] for f in body["faces"]] == ["bar_raiser"]
    assert body["faces"][0]["ai_generated"] is True
    assert "AI-generated" in body["note"]
    served = client.get("/v1/voice/faces/bar_raiser.zip")
    assert served.status_code == 200 and served.headers["content-type"] == "application/zip"
    assert client.get("/v1/voice/faces/professor.zip").status_code == 404


def test_each_head_has_a_photo_for_before_it_is_ready(client, tmp_path, monkeypatch):
    """2026-10-09, the user: no drawn faces in an interview. The photo is the
    head's own portrait, served beside it, and the listing says who has one."""
    monkeypatch.setattr(face, "FACES_DIR", tmp_path / "faces")
    (tmp_path / "faces").mkdir()
    (tmp_path / "faces" / "bar_raiser.zip").write_bytes(head_zip("bar_raiser"))
    (tmp_path / "faces" / "professor.zip").write_bytes(head_zip("professor"))
    (tmp_path / "faces" / "bar_raiser.webp").write_bytes(b"RIFF0000WEBPVP8 ")
    listed = {f["persona"]: f["still"] for f in client.get("/v1/voice/faces").json()["faces"]}
    assert listed == {"bar_raiser": True, "professor": False}
    photo = client.get("/v1/voice/faces/bar_raiser.webp")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/webp"
    assert photo.headers["etag"]
    assert client.get("/v1/voice/faces/professor.webp").status_code == 404
    assert client.get("/v1/voice/faces/..%2Fsecret.webp").status_code in (404, 422)


def test_a_rebuilt_face_is_not_kept_from_a_browsers_cache(client, tmp_path, monkeypatch):
    """2026-10-10: a rebuild swaps the head and its photo at the same address.
    Each use asks M11 again; an unchanged face answers 304, a new one 200."""
    monkeypatch.setattr(face, "FACES_DIR", tmp_path / "faces")
    (tmp_path / "faces").mkdir()
    still = tmp_path / "faces" / "bar_raiser.webp"
    still.write_bytes(b"RIFF0000WEBPVP8 ")
    first = client.get("/v1/voice/faces/bar_raiser.webp")
    assert "no-cache" in first.headers["cache-control"]
    tag = first.headers["etag"]
    again = client.get("/v1/voice/faces/bar_raiser.webp", headers={"If-None-Match": tag})
    assert again.status_code == 304 and not again.content
    still.write_bytes(b"RIFF1111WEBPVP8 rebuilt")
    rebuilt = client.get("/v1/voice/faces/bar_raiser.webp", headers={"If-None-Match": tag})
    assert rebuilt.status_code == 200 and rebuilt.headers["etag"] != tag
    (tmp_path / "faces" / "bar_raiser.zip").write_bytes(head_zip("bar_raiser"))
    head = client.get("/v1/voice/faces/bar_raiser.zip")
    assert "no-cache" in head.headers["cache-control"] and head.headers["etag"]


def test_a_sentence_with_notation_keeps_its_face(client, fake_voice, fake_face):
    """The audio is keyed on the text as said ("order N", not "O(n)"): so is
    its face, or the browser asks for frames under a key nothing has."""
    said = client.post(
        "/v1/voice/speak",
        json={"text": "Is that O(n log n) in the worst case?", "persona_id": "bar_raiser"},
        headers=student(uuid.uuid4()),
    )
    key = said.headers["x-face"]
    voice = tts.Cast.load().voices[said.headers["x-voice"]]
    prepared = fake_voice.prepare("Is that O(n log n) in the worst case?", voice)
    assert key == fake_voice.cache_key(prepared, voice)
    assert client.get(f"/v1/voice/face/{key}", headers=student(uuid.uuid4())).status_code == 200


def test_frames_still_being_made_are_waited_for(tmp_path):
    import threading

    gate = threading.Event()

    class Slow(FakeFace):
        def infer(self, samples):
            gate.wait(2)
            return super().infer(samples)

    engine = Slow(tmp_path)
    face.FaceEngine.prepare(engine, "k" * 40, wav(0.5))  # the real one: off-thread
    assert engine.cached("k" * 40) is None, "not yet made"
    gate.set()
    got = engine.wait("k" * 40, timeout=3)
    assert got is not None and got["frames"]
