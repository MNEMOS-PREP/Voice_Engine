"""Upstream probing — spec §10, `module.json`.

Platform Rule 2: **a missing dependency narrows the SCOPE, never the quality,
and never silently.** M11 has one upstream, and nothing is `required: true`:
every spoken line is also on screen (FR-11.18), so voice is never the only way
through an interview.

* **M06 absent** — the voice check has no interviewers to play, so it plays one
  sample voice and says why.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ai_core.dependencies import DependencyRegistry

MANIFEST = Path(__file__).resolve().parents[2] / "module.json"


@lru_cache(maxsize=1)
def deps() -> DependencyRegistry:
    return DependencyRegistry.from_manifest(MANIFEST)


def reload() -> None:
    deps.cache_clear()


__all__ = ["MANIFEST", "deps", "reload"]
