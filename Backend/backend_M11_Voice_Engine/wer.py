"""Word error rate — how the recogniser is chosen (M11 day 6, AC-11.4/11.5).

"A choice made by reputation would fail it silently" (spec §0, 6.7): the
recogniser is picked by measuring it on Indian-accented English, and the
accent gate (AC-11.4) is a gap between groups measured the same way. This is
the arithmetic both use, kept in the module so the day-14 harness and the
research runner cannot disagree about what a number means.

WER = (substitutions + deletions + insertions) / reference words, over text
normalised the same way on both sides — lowercase, punctuation out, digits
spelled the way a reference transcript usually writes them is NOT attempted
(that is a rabbit hole with its own errors); both candidates face the same
normaliser, so the comparison stays fair even where a number is miscounted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_PUNCT = re.compile(r"[^\w\s']|_")
_SPACE = re.compile(r"\s+")
#: Spellings that differ without being errors.
_SAME = {"mr": "mister", "mrs": "missus", "dr": "doctor", "ok": "okay", "o.k.": "okay"}


def normalise(text: str) -> list[str]:
    words = _SPACE.sub(" ", _PUNCT.sub(" ", text.lower().replace("’", "'"))).split()
    return [_SAME.get(w.strip("'"), w.strip("'")) for w in words if w.strip("'")]


def edits(reference: list[str], hypothesis: list[str]) -> int:
    """Word-level Levenshtein distance."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        current = [i] + [0] * len(hypothesis)
        for j, hyp in enumerate(hypothesis, 1):
            current[j] = min(
                previous[j] + 1,  # deletion
                current[j - 1] + 1,  # insertion
                previous[j - 1] + (ref != hyp),  # substitution
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class Score:
    errors: int
    words: int

    @property
    def wer(self) -> float:
        return self.errors / self.words if self.words else 0.0


def score(reference: str, hypothesis: str) -> Score:
    ref, hyp = normalise(reference), normalise(hypothesis)
    return Score(errors=edits(ref, hyp), words=len(ref))


def pooled(scores: Iterable[Score]) -> float:
    """Corpus WER: total errors over total words — not a mean of ratios, which
    lets a two-word utterance weigh as much as a forty-word one."""
    scores = list(scores)
    words = sum(s.words for s in scores)
    return sum(s.errors for s in scores) / words if words else 0.0


def gap(by_group: dict[str, list[Score]]) -> float:
    """AC-11.4: the widest WER gap between groups, in points."""
    rates = [pooled(group) * 100 for group in by_group.values() if group]
    return max(rates) - min(rates) if len(rates) > 1 else 0.0


__all__ = ["Score", "edits", "gap", "normalise", "pooled", "score"]
