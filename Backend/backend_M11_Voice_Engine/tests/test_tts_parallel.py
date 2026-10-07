"""A line's sentences made side by side (tts.py, 2026-10-07).

The real model is never loaded (2.5 GB). Its three sessions are replaced by
fakes that keep the real ones' contract, checked on every call:

- The language model is onnxruntime's GroupQueryAttention. Each row's cache is
  valid from its start and padded on the right; its valid length is the mask's
  sum minus the new tokens; the new tokens' positions continue from there; and
  `present` is `past` one entry wider. A scheduler that padded on the left, or
  placed a token at the wrong position, fails an assertion here instead of
  speaking garbage.
- Each sentence carries how many speech tokens it should make (the fake
  tokenizer's first id). The fake writes it into the cache entry it adds, and
  reads it back from the row's last valid entry, so a row that read another
  row's cache, or a pad, stops at the wrong length — and its audio, 960 samples
  per token, has the wrong length.
"""

from __future__ import annotations

import io
import threading
import time
import uuid
import wave

import numpy as np
import pytest

from backend_M11_Voice_Engine import tts

from .conftest import student

HIDDEN, PREFIX = 8, 5
NAMES = [f"past_key_values.{i}.{kind}" for i in range(2) for kind in ("key", "value")]


class FakeInput:
    def __init__(self, name: str) -> None:
        self.name, self.type = name, "tensor(float)"


class FakeTokenizer:
    """`encode(text).ids`: the sentence's speech length first (its word count
    times three), then one id per word."""

    class _Ids:
        def __init__(self, ids: list[int]) -> None:
            self.ids = ids

    def encode(self, text: str) -> FakeTokenizer._Ids:
        words = text.split()
        return self._Ids([3 * len(words)] + [7] * len(words))


class FakeEmbed:
    def run(self, _outputs, feed):
        ids = feed["input_ids"]
        embeds = np.zeros(ids.shape + (HIDDEN,), dtype=np.float32)
        embeds[..., 0] = ids
        return [embeds]


class FakeLM:
    """The language model's contract, asserted on every call."""

    def __init__(self) -> None:
        self.batches: list[int] = []
        self.lock = threading.Lock()

    def get_inputs(self):
        return [FakeInput("inputs_embeds")] + [FakeInput(n) for n in NAMES]

    def run(self, _outputs, feed):
        embeds, mask, pos = feed["inputs_embeds"], feed["attention_mask"], feed["position_ids"]
        batch, new, _ = embeds.shape
        past = {n: feed[n] for n in NAMES}
        width = past[NAMES[0]].shape[2]
        assert mask.shape == (batch, width + new)
        with self.lock:
            self.batches.append(batch)
        logits = np.zeros((batch, new, 4), dtype=np.float32)
        present = {
            n: np.concatenate([v, np.zeros(v.shape[:2] + (new,) + v.shape[3:], v.dtype)], axis=2)
            for n, v in past.items()
        }
        for b in range(batch):
            valid = int(mask[b].sum()) - new
            # Right padding: a contiguous run of ones, then zeros.
            assert mask[b, : valid + new].all() and not mask[b, valid + new :].any(), mask[b]
            assert list(pos[b]) == list(range(valid, valid + new)), (pos[b], valid)
            if new > 1 and valid == 0:
                target = 0.0  # the voice's conditioning: nothing to say yet
            elif new > 1:
                target = float(embeds[b, 1, 0]) if embeds.shape[1] > 1 else 0.0
                target = float(embeds[b, 0, 0])  # the text's first id: the length
            else:
                target = float(past[NAMES[0]][b, 0, valid - 1, 0])
            for n in NAMES:
                present[n][b, :, valid : valid + new, :] = 0.0
                present[n][b, 0, valid : valid + new, 0] = target
                if valid + new < present[n].shape[2]:
                    present[n][b, :, valid + new :, :] = 0.0
            logits[b, -1, 0] = target
        return [logits] + [present[n] for n in NAMES]


class FakeDecoder:
    """960 samples of silence per speech token after the voice's prompt."""

    def __init__(self) -> None:
        self.order: list[int] = []

    def run(self, _outputs, feed):
        tokens = feed["speech_tokens"]
        spoken = tokens.shape[1] - 4 - 3  # minus the prompt and the trailing silence
        self.order.append(spoken)
        time.sleep(0.01)
        return [np.zeros((1, 960 * spoken), dtype=np.float32)]


def fake_sample(logits, generated, _rng, **_):
    """Stop once the row has made as many tokens as its sentence asked for."""
    target = int(round(float(logits.reshape(-1)[0])))
    return tts.STOP_SPEECH if generated.size + 1 >= max(1, target) else 100


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(tts, "sample_next", fake_sample)
    monkeypatch.setattr(tts, "NUM_KV_HEADS", 2)
    monkeypatch.setattr(tts, "HEAD_DIM", 3)
    e = tts.Engine(tts.Cast.load(), precision="fake-parallel")
    e._sessions = {
        "embed_tokens": FakeEmbed(),
        "language_model": FakeLM(),
        "conditional_decoder": FakeDecoder(),
    }
    e._tokenizer = FakeTokenizer()
    e._rng = np.random.default_rng(0)
    for key in e.cast.voices:
        e._conds[key] = (
            np.zeros((1, PREFIX, HIDDEN), dtype=np.float32),
            np.zeros((1, 4), dtype=np.int64),
            np.zeros((1, 192), dtype=np.float32),
            np.zeros((1, 8, 80), dtype=np.float32),
        )
    e._begin()
    e.state, e.reason = "ready", "fake sessions"
    return e


def seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def test_a_planned_line_is_made_three_at_a_time_and_each_sentence_is_its_own(engine):
    voice = engine.cast.resolve(persona_id="professor")
    line = [
        "One two three four five six seven eight nine ten.",
        "Short one.",
        "A middling sentence of six.",
        "Another rather long sentence that keeps on going for a while.",
        "Done.",
    ]
    # The fake model is so fast it could finish a sentence before the next is
    # planned; hold the queue until the whole line is in it, as a real line is.
    with engine._jobs:
        assert engine.plan([(s, voice) for s in line], "line-1") == len(line)
    for text in line:
        data, _, _ = engine.speak(text, voice, line="line-1")
        words = len(engine.prepare(text, voice).split())
        # 3 tokens a word, minus the stop token: each row kept its own length.
        # (Made by the time it is asked for, it comes from the cache: the point.)
        assert seconds(data) == pytest.approx((3 * words - 1) * 960 / tts.SAMPLE_RATE), text
    batches = engine._sessions["language_model"].batches
    assert max(batches) == tts.ROWS == 3


def test_a_sentence_planned_and_then_asked_for_is_made_once(engine):
    voice = engine.cast.resolve(persona_id="professor")
    engine.plan([("Tell me about your project.", voice)], "line-2")
    engine.speak("Tell me about your project.", voice, line="line-2")
    assert engine.speak("Tell me about your project.", voice, line="line-2")[1] is True
    assert engine.plan([("Tell me about your project.", voice)], "line-3") == 0
    assert len(engine._sessions["conditional_decoder"].order) == 1


def test_dropping_a_line_skips_what_has_not_started_and_it_can_be_asked_again(engine, monkeypatch):
    voice = engine.cast.resolve(persona_id="professor")
    gate = threading.Event()
    original = engine._join

    def held_join(kv, rows, job):  # hold the model until the queue is checked
        gate.wait(5)
        return original(kv, rows, job)

    monkeypatch.setattr(engine, "_join", held_join)
    line = [
        f"Sentence number {word} of six." for word in ("one", "two", "three", "four", "five", "six")
    ]
    engine.plan([(s, voice) for s in line], "stopped")
    time.sleep(0.1)
    dropped = engine.drop(["stopped"])
    gate.set()
    # At most three rows had been taken from the queue; the rest were waiting.
    assert 3 <= dropped <= 5
    # A dropped sentence asked for again is made, not refused.
    data, cached, _ = engine.speak(line[-1], voice, line="later")
    assert cached is False and seconds(data) > 0


def test_a_sentence_two_lines_share_is_not_dropped_with_one_of_them(engine, monkeypatch):
    voice = engine.cast.resolve(persona_id="professor")
    gate = threading.Event()
    original = engine._join
    monkeypatch.setattr(
        engine, "_join", lambda kv, rows, job: (gate.wait(5), original(kv, rows, job))[1]
    )
    filler = [f"Filler sentence {word}." for word in ("one", "two", "three")]
    engine.plan([(s, voice) for s in filler], "a")
    engine.plan([("Shared words here.", voice)], "a")
    engine.plan([("Shared words here.", voice)], "b")
    time.sleep(0.1)
    shared = engine._inflight[engine.cache_key("Shared words here.", voice)]
    engine.drop(["a"])  # the fillers still waiting go; the shared one stays
    assert not shared.done.is_set() and shared.lines == {"b"}
    gate.set()
    assert seconds(engine.speak("Shared words here.", voice, line="b")[0]) > 0


# ── the routes ───────────────────────────────────────────────────────────


def test_plan_and_drop_are_for_signed_in_callers(client, engine):
    tts.set_engine(engine)
    body = {"line": "l1", "sentences": [{"text": "Hello there.", "persona_id": "professor"}]}
    assert client.post("/v1/voice/plan", json=body).status_code == 401
    r = client.post("/v1/voice/plan", json=body, headers=student(uuid.uuid4()))
    assert r.status_code == 202 and r.json() == {"planned": 1}
    r = client.post("/v1/voice/drop", json={"lines": ["l1"]}, headers=student(uuid.uuid4()))
    assert r.status_code == 200 and "dropped" in r.json()
    assert client.post("/v1/voice/drop", json={"lines": ["l1"]}).status_code == 401


def test_speak_collects_a_planned_sentence(client, engine):
    tts.set_engine(engine)
    who = student(uuid.uuid4())
    client.post(
        "/v1/voice/plan",
        json={
            "line": "l2",
            "sentences": [
                {"text": "First words.", "persona_id": "professor"},
                {"text": "Second words.", "persona_id": "professor"},
            ],
        },
        headers=who,
    )
    r = client.post(
        "/v1/voice/speak",
        json={"text": "Second words.", "persona_id": "professor", "line": "l2"},
        headers=who,
    )
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"


def test_a_long_first_sentence_is_made_alone_only_when_the_next_can_still_be_ready(engine):
    voice = engine.cast.resolve(persona_id="professor")
    with engine._jobs:  # look at the queue before the model takes from it
        engine.plan(
            [
                ("Let's practise defending one line from your resume.", voice),
                ("Two minutes.", voice),
            ],
            "long-first",
        )
        engine.plan(
            [
                ("Thanks, that's clear.", voice),
                ("What would you change about the harness today?", voice),
            ],
            "short-first",
        )
        lead = {job.text: job.lead for job in engine._queue}
    # A long first sentence and a short next one: the first alone, heard sooner.
    assert lead["Let's practise defending one line from your resume."] is True
    assert lead["Two minutes."] is False
    # A short first sentence and a longer next one: together, or a gap follows it.
    assert lead["Thanks, that's clear."] is False
