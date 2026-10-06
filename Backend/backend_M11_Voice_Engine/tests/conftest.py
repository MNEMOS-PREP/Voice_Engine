"""Shared fixtures for M11 tests.

**No test in this repo opens a socket.** The suite runs on a laptop with
nothing else up and no key.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from ai_core.db import get_session
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend_M11_Voice_Engine import dependencies
from backend_M11_Voice_Engine.app import app


@pytest.fixture(autouse=True)
def no_upstream_probes(monkeypatch):
    """`/v1/deps` would probe M06 over HTTP — and answer differently on a
    laptop where M06 happens to be running. Every upstream reads as down; a
    test that wants one up says so with `upstream_up`."""
    from ai_core.dependencies import DependencyRegistry

    monkeypatch.setattr(
        DependencyRegistry, "_probe", lambda self, dep: (False, "tests open no sockets")
    )
    dependencies.reload()
    yield
    dependencies.reload()


@pytest.fixture
def upstream_up(monkeypatch):
    from ai_core.dependencies import DependencyRegistry

    monkeypatch.setattr(DependencyRegistry, "_probe", lambda self, dep: (True, "healthy (200)"))
    dependencies.reload()


@pytest.fixture(autouse=True)
def no_voice_model(monkeypatch, tmp_path):
    """The real voice model is 2.5 GB and loads in a thread: no test starts it.
    Lines a test does make are cached under its own temporary folder."""
    from backend_M11_Voice_Engine import tts

    monkeypatch.setenv("M11_TTS", "off")
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path / "tts_cache")
    tts.set_engine(None)
    yield
    tts.set_engine(None)


@pytest.fixture(autouse=True)
def no_asr_network(monkeypatch):
    """Server recognition calls Groq: no test does. No key either, unless a
    test sets one — the developer's keys.txt must not decide a test."""
    from backend_M11_Voice_Engine import asr

    def refuse(*_args, **_kwargs):
        raise AssertionError("tests open no sockets")

    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(asr, "_ring", None)
    asr.set_transport(refuse)
    yield
    asr.set_transport(None)
    monkeypatch.setattr(asr, "_ring", None)


@pytest.fixture(autouse=True)
def _service_secret(monkeypatch):
    """A known platform secret, so no test reads or writes the developer's
    machine secret under their home directory (Platform_Core v0.12.0)."""
    monkeypatch.setenv("SERVICE_SECRET", "m11-test-secret")


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    # Not a context manager: the lifespan would create tables in dev.db.
    yield TestClient(app)
    app.dependency_overrides.clear()


def student(candidate: uuid.UUID | str) -> dict[str, str]:
    """The dev resolver's headers (ai_core.identity, AI_AUTH_MODE=dev)."""
    return {"X-Role": "student", "X-Candidate-Id": str(candidate)}


def admin() -> dict[str, str]:
    return {"X-Role": "admin", "X-Candidate-Id": "ops"}
