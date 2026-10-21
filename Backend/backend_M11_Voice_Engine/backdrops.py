"""The rooms the interviewers sit in (2026-10-21).

The user: "use realistic Zoom-meeting-like backgrounds, around a hundred, for
the 39-40 interviewers, each getting a random one every time". Until now the
room painted a blurred office per persona (Platform_Core `officeBackdrop`):
no file, no network, and always the same room for the same person.

These are photographs: tidy home offices, living rooms and bookshelf walls,
each with an open licence (CC0, public domain or CC BY) recorded in
`backdrops/CREDITS.md`. They are served beside the interviewers' photos, so
one module holds every picture an interviewer is shown in, and the browser
chooses one per interviewer per interview (`officeBackdrop.ts`).

`backdrops/local/` is for pictures that may not go in git — a pack someone
bought, say. They are served on that machine and nowhere else.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKDROPS_DIR = Path(os.getenv("M11_BACKDROPS_DIR") or HERE / "backdrops")
#: A backdrop's name: its file name without `.webp`.
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,60}$")


def _folders() -> list[Path]:
    return [BACKDROPS_DIR, BACKDROPS_DIR / "local"]


def names() -> list[str]:
    """Every backdrop there is, the shared ones then this machine's own."""
    out: list[str] = []
    for folder in _folders():
        if folder.is_dir():
            out += sorted(p.stem for p in folder.glob("*.webp") if NAME.match(p.stem))
    return list(dict.fromkeys(out))


def path_of(name: str) -> Path | None:
    """The file for `name`, or None. Never a path outside the folders."""
    if not NAME.match(name):
        return None
    for folder in _folders():
        path = folder / f"{name}.webp"
        if path.is_file():
            return path
    return None


__all__ = ["BACKDROPS_DIR", "names", "path_of"]
