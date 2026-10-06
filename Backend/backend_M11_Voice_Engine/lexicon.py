"""How the interviewers say the words they get wrong — EC-11.11.

"TTS mispronounces a technical term → lexicon override table; crowd-
flaggable." The voices take text, not phonemes, so an override is a
respelling ("DNS" → "D N S") applied before a line is spoken and cached.

The table is not a guess. `research/lexicon/probe.py` has the voice say every
term the interviewers use — M04's concept names, the personas' own names — in
a sentence, has Whisper read it back, and a term earns an entry only when it
did NOT come back; the respelling stays only if IT comes back right. Anyone
who hears another word said wrong flags it (`POST /v1/voice/lexicon/flags`);
staff see the flags, and a flagged word goes through the same check.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

LEXICON = Path(__file__).resolve().parent / "voices" / "lexicon.json"


@cache
def entries() -> tuple[dict, ...]:
    """The table: each entry a `term`, what to `say`, and `exact` when only
    that exact casing is meant (an acronym, not the same word in lower case)."""
    if not LEXICON.exists():
        return ()
    data = json.loads(LEXICON.read_text(encoding="utf-8"))
    return tuple(e for e in data.get("entries", []) if e.get("term") and e.get("say"))


@cache
def _patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    out = []
    # Longest first, so "HTTPS" is respelled before "HTTP" could be.
    for entry in sorted(entries(), key=lambda e: -len(e["term"])):
        flags = 0 if entry.get("exact") else re.IGNORECASE
        out.append(
            (re.compile(rf"(?<![\w-]){re.escape(entry['term'])}(?![\w-])", flags), entry["say"])
        )
    return tuple(out)


def apply(text: str) -> str:
    """The line as the voice should read it."""
    for pattern, say in _patterns():
        text = pattern.sub(say, text)
    return text


def reload() -> None:
    entries.cache_clear()
    _patterns.cache_clear()


__all__ = ["LEXICON", "apply", "entries", "reload"]
