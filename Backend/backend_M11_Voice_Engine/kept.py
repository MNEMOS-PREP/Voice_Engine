"""A student's spoken answers, kept — M11 day 12 (FR-11.19), with consent only.

"Per-turn audio stored, aligned to the transcript clock." Each spoken answer
the room sends — the same 16 kHz WAV the recogniser heard — is kept beside
the turn it answered and when it was said, so the student can hear
themselves back in their notes. That is the preparation value: you rarely
know how you sound until you hear it.

Three rules, each enforced here rather than promised in a screen:
- **Consent or nothing.** An upload that does not say the student chose to
  keep their answers is refused; nothing is written.
- **Theirs.** An interview's answers are read by the student whose interview
  it is (the guard, `access.py`) or by staff.
- **Gone when they say.** Deleting an interview's kept answers removes the
  files, not just the rows.
"""

from __future__ import annotations

import io
import os
import shutil
import uuid
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Where the audio lives. Not in the database: files are what is deleted.
KEPT_DIR = Path(os.getenv("M11_KEPT_DIR") or HERE.parent / ".kept_audio")
#: A five-minute answer at 16 kHz mono 16-bit is ~9.6 MB.
MAX_BYTES = 12 * 1024 * 1024


def duration_ms(data: bytes) -> int:
    """How long a WAV is; ValueError when it is not one."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            return round(w.getnframes() / max(1, w.getframerate()) * 1000)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Not a WAV file: {exc}") from None


def path_for(session_id: uuid.UUID, turn_id: uuid.UUID) -> Path:
    return KEPT_DIR / str(session_id) / f"{turn_id}.wav"


def save(session_id: uuid.UUID, turn_id: uuid.UUID, data: bytes) -> Path:
    path = path_for(session_id, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def forget(session_id: uuid.UUID) -> None:
    shutil.rmtree(KEPT_DIR / str(session_id), ignore_errors=True)


__all__ = ["KEPT_DIR", "MAX_BYTES", "duration_ms", "forget", "path_for", "save"]
