"""A sentence heard while it is being made (`stream.py`, `Engine.speak_stream`).

The arithmetic and the seam are tested alone; the engine is the fake one of
`test_tts_parallel.py` (960 samples a token, no model). What no test here can
say is how a seam *sounds* on the real decoder: that is listened to, with M11
stopped, before this is switched on in a room (TODO, open problem 3).
"""

from __future__ import annotations

import time
import uuid

import numpy as np
import pytest

from backend_M11_Voice_Engine import stream, tts

from .conftest import student
from .test_tts_parallel import engine, seconds  # noqa: F401  (the fixture)

S = stream.SAMPLES_PER_TOKEN


# ── the seam ─────────────────────────────────────────────────────────────


def test_pieces_cut_from_one_signal_join_back_into_it():
    """Neighbours overlap by FADE and carry the same sound: the crossfade of
    two copies of a signal is the signal, so the join must add nothing."""
    signal = np.sin(np.arange(S * 4) / 37.0).astype(np.float32)
    step = S
    pieces = [signal[i : i + step + stream.FADE] for i in range(0, 3 * step, step)]
    st = stream.Stitcher()
    out = [st.push(p) for p in pieces[:-1]] + [st.push(pieces[-1], last=True)]
    joined = np.concatenate(out)
    assert joined.size == 3 * step + stream.FADE
    assert np.allclose(joined, signal[: joined.size], atol=1e-6)


def test_a_seam_between_different_sounds_has_no_jump():
    a = np.full(S + stream.FADE, 0.5, dtype=np.float32)
    b = np.full(S + stream.FADE, -0.5, dtype=np.float32)
    st = stream.Stitcher()
    joined = np.concatenate([st.push(a), st.push(b, last=True)])
    jump = np.abs(np.diff(joined)).max()
    assert jump < 0.1  # a hard cut would be 1.0


def test_a_piece_shorter_than_the_fade_is_held_not_lost():
    st = stream.Stitcher()
    assert st.push(np.ones(10, dtype=np.float32)).size == 0
    out = st.push(np.ones(S, dtype=np.float32), last=True)
    assert out.size >= S


def test_the_decoder_output_layouts_are_read_not_assumed():
    n, p = 40, 4
    body = np.arange(n * S, dtype=np.float32)
    assert np.array_equal(stream.speech_of(body, p, n), body)  # speech only
    padded = np.concatenate([body, np.zeros(3 * S, np.float32)])  # + silence
    assert np.array_equal(stream.speech_of(padded, p, n), body)
    with_prompt = np.concatenate([np.full(p * S, -1, np.float32), body])  # + prompt
    assert np.array_equal(stream.speech_of(with_prompt, p, n), body)
    with pytest.raises(ValueError):
        stream.speech_of(np.zeros(7 * S, np.float32), p, n)


def test_pieces_wait_for_their_look_ahead():
    assert stream.spans(0, stream.CHUNK + stream.LOOK - 1) == []
    assert stream.spans(0, stream.CHUNK + stream.LOOK) == [(0, stream.CHUNK)]
    assert stream.spans(stream.CHUNK, 2 * stream.CHUNK + stream.LOOK) == [
        (stream.CHUNK, 2 * stream.CHUNK)
    ]


def test_a_model_at_real_time_plays_at_once_a_slow_one_waits_for_a_buffer():
    assert stream.ready_to_play(25, 40.0, 300)  # well above speech: now
    assert not stream.ready_to_play(25, 0.0, 300)  # rate not known yet
    assert not stream.ready_to_play(100, 9.0, 300)
    assert stream.ready_to_play(290, 9.0, 300)


def test_the_buffer_rule_never_lets_playback_run_dry():
    """Simulate playback from the first moment the rule says go, for models
    from half to twice as fast as speech, against a sentence 20 % longer than
    estimated and a model 15 % slower than it measured itself."""
    estimate = 300
    for measured in (8.0, 12.0, 18.0, 22.0, 30.0, 50.0):
        actual_total = int(estimate * 1.2)
        actual_rate = measured * 0.85
        buffered = 0
        for buffered in range(stream.CHUNK, actual_total + 1, stream.CHUNK):
            if stream.ready_to_play(buffered, measured, estimate):
                break
        # From then on: made = buffered + rate * t, played = 25 * t.
        t_end = (actual_total - buffered) / actual_rate
        t = 0.0
        while t <= t_end:
            made = min(actual_total, buffered + actual_rate * t)
            assert made >= stream.PLAY_RATE * t - 1e-6, (measured, t)
            t += 0.05


def test_a_model_too_slow_for_a_buffer_to_help_is_not_streamed():
    assert not stream.worth_streaming(9.0)  # the q4 laptop: only costs CPU
    assert stream.worth_streaming(27.0)  # fp32 as the team measured it
    assert stream.worth_streaming(45.0)  # int8
    assert stream.worth_streaming(0.0)  # not known yet: try


def test_a_decoder_slower_than_speech_makes_streaming_not_worth_it():
    # The 2026-10-10 laptop: the model 30 tokens/s alone, a 1 s piece 1.9 s.
    assert stream.throughput(30.0, 1.9) == pytest.approx(25 / 1.9)
    assert not stream.worth_streaming(30.0, 1.9)
    assert stream.worth_streaming(30.0, 0.5)  # a decoder with room to spare
    assert stream.worth_streaming(30.0, 0.0)  # not measured yet: try
    assert stream.throughput(0.0, 0.0) == 0.0


def test_the_estimate_never_falls_below_what_is_already_made():
    assert stream.estimate_tokens("hi", have=100) == 100 + stream.CHUNK
    assert stream.estimate_tokens("x" * 200) == int(200 * stream.TOKENS_PER_CHAR)


# ── the engine ───────────────────────────────────────────────────────────

LONG = " ".join(["word"] * 20) + "."  # 3 tokens a word in the fake: 60


def test_a_long_sentence_is_heard_in_pieces_before_it_is_whole(engine, monkeypatch):
    voice = engine.cast.resolve(persona_id="professor")
    step = engine._step

    def slow(kv, rows):  # the real model is slower than the fake's microseconds
        time.sleep(0.01)
        return step(kv, rows)

    monkeypatch.setattr(engine, "_step", slow)
    pieces, first_before_done = [], None
    for samples, _key in engine.speak_stream(LONG, voice, line="s1"):
        if first_before_done is None:
            job = next(iter(engine._inflight.values()), None)
            first_before_done = job is not None and not job.done.is_set()
        pieces.append(samples)
    assert len(pieces) >= 2
    assert first_before_done, "the first piece came only when the sentence was whole"
    whole, cached, _ = engine.speak(LONG, voice, line="s1")
    assert cached
    assert sum(p.size for p in pieces) == int(seconds(whole) * tts.SAMPLE_RATE)


def test_a_slow_model_is_not_heard_until_the_buffer_holds(engine, monkeypatch):
    """With the rule saying "not yet", nothing plays until the sentence is whole
    — and then all of it does, once, in order."""
    voice = engine.cast.resolve(persona_id="professor")
    monkeypatch.setattr(stream, "ready_to_play", lambda *a, **k: False)
    jobs_done_at_first_piece = []
    pieces = []
    for samples, _ in engine.speak_stream(LONG, voice, line="slow"):
        job = engine._inflight.get(engine.cache_key(engine.prepare(LONG, voice), voice))
        jobs_done_at_first_piece.append(job is None or job.done.is_set())
        pieces.append(samples)
    assert all(jobs_done_at_first_piece)
    whole = engine.speak(LONG, voice, line="slow")[0]
    assert sum(p.size for p in pieces) == int(seconds(whole) * tts.SAMPLE_RATE)


def test_a_sentence_already_made_is_one_piece(engine):
    voice = engine.cast.resolve(persona_id="professor")
    engine.speak(LONG, voice, line="s2")
    pieces = list(engine.speak_stream(LONG, voice, line="s2"))
    assert len(pieces) == 1


def test_a_short_sentence_is_one_piece_not_a_stutter(engine):
    voice = engine.cast.resolve(persona_id="professor")
    pieces = list(engine.speak_stream("Just a few words here.", voice, line="s3"))
    assert len(pieces) == 1


def test_a_stream_that_cannot_be_made_raises_as_speak_does(engine):
    engine.state, engine.reason = "off", "turned off"
    voice = engine.cast.resolve(persona_id="professor")
    with pytest.raises(tts.EngineUnavailable):
        next(engine.speak_stream("Anything at all.", voice))


# ── the route ────────────────────────────────────────────────────────────


def test_speak_stream_is_for_signed_in_callers(client, engine):
    tts.set_engine(engine)
    body = {"text": "Hello there.", "persona_id": "professor"}
    assert client.post("/v1/voice/speak_stream", json=body).status_code == 401


def test_speak_stream_sends_the_whole_sentence_as_pcm(client, engine):
    tts.set_engine(engine)
    body = {"text": LONG, "persona_id": "professor", "line": "r1"}
    r = client.post("/v1/voice/speak_stream", json=body, headers=student(uuid.uuid4()))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/L16")
    assert r.headers["x-sample-rate"] == "24000" and r.headers["x-face"]
    whole = client.post("/v1/voice/speak", json=body, headers=student(uuid.uuid4()))
    assert len(r.content) == len(whole.content) - 44  # 16-bit samples, no WAV header
