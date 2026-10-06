"""Words the voices get wrong — EC-11.11: an override table, crowd-flaggable.

What is pinned: a respelling replaces the whole word and only the whole word,
an acronym only in its own casing, the longest term first; synthesis reads
the respelled line (so a fixed word is a new line in the cache, not the old
one); anyone signed in can flag a word; only staff read the flags, grouped,
with whether each is fixed.
"""

from __future__ import annotations

import json

import pytest

from backend_M11_Voice_Engine import lexicon

from .conftest import admin, student

SOMEONE = "6f1e2d3c-4b5a-4968-8776-655443322110"


@pytest.fixture
def table(tmp_path, monkeypatch):
    path = tmp_path / "lexicon.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {"term": "HTTP", "say": "H T T P", "exact": True},
                    {"term": "HTTPS", "say": "H T T P S", "exact": True},
                    {"term": "Dijkstra", "say": "Dike-struh", "why": "heard as 'dijk-stra'"},
                    {"term": "Raghavan", "say": "Raa-gha-van", "voices": ["chatterbox-default"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(lexicon, "LEXICON", path)
    lexicon.reload()
    yield
    lexicon.reload()


def test_a_respelling_replaces_the_whole_word_and_nothing_inside_another(table):
    assert lexicon.apply("Explain dijkstra's algorithm.") == "Explain Dike-struh's algorithm."
    assert lexicon.apply("HTTP and HTTPS") == "H T T P and H T T P S", "longest first"
    assert lexicon.apply("http is lowercase here") == "http is lowercase here", "exact casing"
    assert lexicon.apply("HTTPServer stays") == "HTTPServer stays"


def test_a_respelling_for_one_voice_is_that_voices_only(table):
    assert lexicon.apply("Dr. Raghavan, over to you.", "chatterbox-default") == (
        "Dr. Raa-gha-van, over to you."
    )
    assert lexicon.apply("Dr. Raghavan, over to you.", "indictts-022743") == (
        "Dr. Raghavan, over to you."
    )
    assert lexicon.apply("Dijkstra", "indictts-022743") == "Dike-struh", "unscoped: every voice"


def test_no_table_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(lexicon, "LEXICON", tmp_path / "missing.json")
    lexicon.reload()
    assert lexicon.apply("Dijkstra over HTTP") == "Dijkstra over HTTP"
    lexicon.reload()


def test_the_voice_reads_the_respelled_line(table, monkeypatch):
    from backend_M11_Voice_Engine import tts

    said: list[str] = []
    engine = tts.Engine(tts.Cast.load())
    engine.state = "ready"
    monkeypatch.setattr(engine, "_synthesize", lambda text, voice: said.append(text) or [0.0] * 240)
    monkeypatch.setattr(tts, "to_wav", lambda samples: b"RIFF")
    voice = engine.cast.resolve(persona_id=None, voice_id=None, voice=None)
    engine.speak("Explain Dijkstra's algorithm", voice)
    assert said == ["Explain Dike-struh's algorithm."]


def test_the_table_is_readable_by_anyone_signed_in(client, table):
    r = client.get("/v1/voice/lexicon", headers=student(SOMEONE))
    assert r.status_code == 200
    assert {
        "term": "Dijkstra",
        "say": "Dike-struh",
        "exact": False,
        "why": "heard as 'dijk-stra'",
        "voices": [],
    } in r.json()


def test_anyone_signed_in_flags_a_word_and_only_staff_read_the_flags(client, table):
    for word, heard in (("Kubernetes", "cube rnetes"), ("kubernetes", None), ("Dijkstra", None)):
        r = client.post(
            "/v1/voice/lexicon/flags",
            json={"word": word, "heard_as": heard, "voice": "indictts-022743"},
            headers=student(SOMEONE),
        )
        assert r.status_code == 201
    assert client.post("/v1/voice/lexicon/flags", json={"word": "x"}).status_code == 401
    assert client.get("/v1/voice/lexicon/flags", headers=student(SOMEONE)).status_code == 403
    flags = client.get("/v1/voice/lexicon/flags", headers=admin()).json()
    assert flags[0] == {
        "word": "Kubernetes",
        "flags": 2,
        "fixed": False,
        "heard_as": ["cube rnetes"],
    }
    assert {"word": "Dijkstra", "flags": 1, "fixed": True, "heard_as": []} in flags
