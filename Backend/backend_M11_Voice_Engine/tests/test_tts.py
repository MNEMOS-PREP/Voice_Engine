"""The server voice (tts.py) — the cast, the sampling, and the routes.

The real model is never loaded here (2.5 GB, minutes on a CPU): a fake engine
stands in for the synthesis, and everything around it — who speaks for whom,
the cache, what a caller gets when the voice is not ready — is the real code.
"""

from __future__ import annotations

import io
import pathlib
import uuid
import wave

import numpy as np
import pytest

from backend_M11_Voice_Engine import tts

from .conftest import student

M06_PERSONAS = (
    pathlib.Path(__file__).resolve().parents[4]
    / "Mock_Interview_Engine/Backend/backend_M06_Mock_Interview_Engine/personas"
)


class FakeEngine(tts.Engine):
    """The real engine with its synthesis replaced by 0.1 s of silence."""

    def __init__(self, state: str = "ready") -> None:
        super().__init__(tts.Cast.load(), precision="fake")
        self.state, self.reason = state, "a fake engine"
        self.made: list[tuple[str, str]] = []

    def start(self) -> None:
        pass

    def _synthesize(self, text: str, voice: tts.Voice):
        self.made.append((voice.key, text))
        return np.zeros(2400, dtype=np.float32)


# ── the cast ─────────────────────────────────────────────────────────────


def test_every_voice_has_its_recording_its_licence_and_its_credit():
    cast = tts.Cast.load()
    soundfile = pytest.importorskip("soundfile")
    for voice in cast.voices.values():
        assert voice.file.exists(), voice.key
        info = soundfile.info(voice.file)
        assert info.samplerate == tts.SAMPLE_RATE and 5 <= info.duration <= 15.5, voice.key
        assert voice.licence and voice.credit and voice.source, voice.key
    assert set(cast.cast.values()) <= set(cast.voices)


@pytest.mark.skipif(not M06_PERSONAS.exists(), reason="M06 is not checked out next door")
def test_every_m06_interviewer_is_cast_and_no_one_else_is():
    """Read from M06's persona files, not a copy: a persona added there and
    not here would speak in a voice nobody chose."""
    personas = {p.stem for p in M06_PERSONAS.glob("*.yaml")}
    cast = tts.Cast.load()
    assert set(cast.cast) == personas


def test_the_roster_is_mostly_indian_and_every_interviewer_sounds_different():
    """The team's brief (2026-10-06): a mix of accents, mostly Indian — and
    FR-11.21, a distinct voice per persona."""
    cast = tts.Cast.load()
    voices = [cast.voices[k] for k in cast.cast.values()]
    assert len(set(cast.cast.values())) == len(cast.cast)
    indian = sum(v.accent == "indian" for v in voices)
    assert indian > len(voices) / 2 and indian < len(voices)


def test_a_cast_persona_gets_its_voice():
    cast = tts.Cast.load()
    assert cast.resolve(persona_id="friendly_recruiter").key == cast.cast["friendly_recruiter"]


def test_an_uncast_persona_gets_a_voice_that_fits_what_it_asked_for():
    cast = tts.Cast.load()
    indian_higher = cast.resolve(persona_id="new_one", voice_id="en-IN-female-warm")
    assert (indian_higher.accent, indian_higher.register) == ("indian", "higher")
    foreign_lower = cast.resolve(persona_id="visitor", voice_id="en-US-male-brisk")
    assert (foreign_lower.accent, foreign_lower.register) == ("foreign", "lower")
    # The same persona gets the same voice every time.
    assert cast.resolve(persona_id="new_one", voice_id="en-IN-female-warm") == indian_higher


def test_an_explicit_voice_wins_and_nonsense_falls_back_to_the_default():
    cast = tts.Cast.load()
    assert cast.resolve(persona_id="friendly_recruiter", voice="dailytalk-0").key == "dailytalk-0"
    assert cast.resolve(voice_id="a nice voice").key == cast.default


def test_a_cast_naming_a_voice_that_does_not_exist_is_refused_at_load(tmp_path):
    raw = (
        (tts.CAST_FILE)
        .read_text(encoding="utf-8")
        .replace('"startup_founder": "dailytalk-0"', '"startup_founder": "ghost"')
    )
    bad = tmp_path / "cast.json"
    bad.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="ghost"):
        tts.Cast.load(bad)


# ── text and tokens ──────────────────────────────────────────────────────


def test_text_is_cleaned_the_way_the_model_was_trained():
    assert tts.punc_norm("hello there") == "Hello there."
    # An ellipsis becomes a pause the model knows (a comma), not a full stop.
    assert tts.punc_norm("Wait — what’s that…") == "Wait - what's that,"
    assert tts.punc_norm("   ") == ""
    assert tts.punc_norm("Really?") == "Really?"


def test_sampling_at_zero_temperature_is_the_most_likely_token():
    rng = np.random.default_rng(0)
    logits = np.array([[0.1, 5.0, 0.2, 0.3]])
    assert tts.sample_next(logits, np.array([], dtype=np.int64), rng, temperature=0) == 1


def test_a_narrow_nucleus_only_ever_picks_the_top_token():
    rng = np.random.default_rng(1)
    logits = np.array([[0.0, 4.0, 1.0, 0.5]])
    picks = {
        tts.sample_next(logits, np.array([], dtype=np.int64), rng, top_p=0.5) for _ in range(50)
    }
    assert picks == {1}


def test_the_repetition_penalty_makes_a_said_token_less_likely():
    rng = np.random.default_rng(2)
    logits = np.array([[3.0, 3.0]])
    said = np.array([0] * 5, dtype=np.int64)
    picks = [tts.sample_next(logits, said, rng, repetition_penalty=3.0) for _ in range(200)]
    assert picks.count(1) > picks.count(0)


def test_audio_is_16_bit_mono_wav_at_24_khz():
    data = tts.to_wav(np.zeros(24_000, dtype=np.float32))
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (
            1,
            2,
            24_000,
            24_000,
        )


# ── the engine around the model ─────────────────────────────────────────


def test_turned_off_it_says_so_and_why():
    engine = tts.Engine(tts.Cast.load())
    engine.start()  # conftest sets M11_TTS=off
    assert engine.state == "off" and "M11_TTS" in engine.reason


def test_a_line_said_once_is_never_made_again():
    engine = FakeEngine()
    voice = engine.cast.resolve(persona_id="professor")
    first = engine.speak("Let's think about this carefully.", voice)
    again = engine.speak("Let's think about this carefully.", voice)
    assert (first[1], again[1]) == (False, True)
    assert len(engine.made) == 1
    # And it survives a restart: a new engine reads the disk cache.
    fresh = FakeEngine()
    assert fresh.speak("Let's think about this carefully.", voice)[1] is True and fresh.made == []


def test_a_cached_line_plays_even_while_the_model_is_loading():
    ready = FakeEngine()
    voice = ready.cast.resolve(persona_id="professor")
    ready.speak("Good to meet you.", voice)
    loading = FakeEngine(state="loading")
    assert loading.speak("Good to meet you.", voice)[1] is True
    with pytest.raises(tts.EngineUnavailable):
        loading.speak("Something new.", voice)


# ── the routes ───────────────────────────────────────────────────────────


@pytest.fixture
def fake():
    engine = FakeEngine()
    tts.set_engine(engine)
    return engine


def test_speak_returns_the_cast_voice_as_wav(client, fake):
    r = client.post(
        "/v1/voice/speak",
        json={"text": "Hi, I'm Arjun.", "persona_id": "bar_raiser"},
        headers=student(uuid.uuid4()),
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["x-voice"] == tts.Cast.load().cast["bar_raiser"]
    assert r.headers["x-cache"] == "miss"
    again = client.post(
        "/v1/voice/speak",
        json={"text": "Hi, I'm Arjun.", "persona_id": "bar_raiser"},
        headers=student(uuid.uuid4()),
    )
    assert again.headers["x-cache"] == "hit" and len(fake.made) == 1


def test_speak_is_for_signed_in_callers_only(client, fake):
    assert client.post("/v1/voice/speak", json={"text": "Hello."}).status_code == 401
    assert fake.made == []


def test_speak_says_when_the_voice_is_not_ready_so_the_browser_can(client):
    tts.set_engine(FakeEngine(state="loading"))
    r = client.post("/v1/voice/speak", json={"text": "Hello."}, headers=student(uuid.uuid4()))
    assert r.status_code == 503 and "not ready" in r.json()["detail"]


def test_speak_refuses_nothing_to_say(client, fake):
    who = student(uuid.uuid4())
    assert client.post("/v1/voice/speak", json={"text": ""}, headers=who).status_code == 422
    assert client.post("/v1/voice/speak", json={"text": "   "}, headers=who).status_code == 422
    assert client.post("/v1/voice/speak", json={"text": "x" * 401}, headers=who).status_code == 422


def test_engine_and_cast_say_what_they_are(client, fake):
    state = client.get("/v1/voice/engine").json()
    assert state["state"] == "ready" and state["model"] == tts.MODEL_ID
    cast = client.get("/v1/voice/cast").json()
    assert cast["default"] in {v["key"] for v in cast["voices"]}
    assert all(v["credit"] for v in cast["voices"])
