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

from backend_M11_Voice_Engine.app import app


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
