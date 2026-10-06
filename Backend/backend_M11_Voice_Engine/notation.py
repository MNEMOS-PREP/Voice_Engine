"""Notation, said as words — M11, EC-11.11's other half (2026-10-07).

The lexicon fixes words a voice gets wrong; this fixes what no voice can
read. M05's questions carry big-O notation, and `research/notation/probe.py`
had every cast voice say each form in a sentence, read back by Whisper cold:
"O(n)" came back as "on", "OR in", "Rn"; "O(n^2)" as "O and 2" in all seven
voices; "O(n log n)" once as "O, N, N, N, N, N, N". A question the student
cannot hear is a question they cannot answer.

Which words, measured rather than guessed (`research/notation/`): every "O
of …" respelling lost what followed the "O" in most voices ("The time
complexity here is O, in the worst case") — "O of n" came back in 1 voice of
7, "O of en" in 2, "O of N" in 2. "order N" came back in 5 of 7 and nearly in
the other two, and it is how an interviewer here says it aloud anyway. Single
letters are written capital: "N" is said as a letter, "n" swallowed.

So big-O is rewritten to its spoken words before synthesis, for every voice:
`O(n)` → "order N", `O(n log n)` → "order N log N", `O(n^2)` / `O(n²)` →
"order N squared", `O(2^n)` → "order two to the N", `O(1)` → "order one",
`O(V + E)` → "order V plus E". Only the interviewer's audio changes; the line
on screen keeps its notation. Pure.
"""

from __future__ import annotations

import re

#: Small numbers as words: "O(1)" is "order one".
_NUMBERS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "10": "ten",
}
_POWERS = {"2": "squared", "3": "cubed"}
_SUPERSCRIPT = {"²": "^2", "³": "^3"}

#: O( … ) with something short and notation-like inside — not "O(" in prose.
_BIG_O = re.compile(r"\b(?:big[- ])?O\s*\(\s*([A-Za-z0-9 ^²³+*·×/.\-]{1,32}?)\s*\)")


def _number(token: str) -> str:
    return _NUMBERS.get(token, token)


def _power(base: str, exponent: str) -> str:
    base, exponent = base.strip(), exponent.strip()
    if exponent in _POWERS:
        return f"{_number(base)} {_POWERS[exponent]}"
    return f"{_number(base)} to the {_number(exponent)}"


def spoken(inner: str) -> str:
    """What is inside the brackets, as a person would say it."""
    text = inner
    for mark, power in _SUPERSCRIPT.items():
        text = text.replace(mark, power)
    text = re.sub(r"(\w+)\s*\^\s*(\w+)", lambda m: _power(m.group(1), m.group(2)), text)
    text = re.sub(r"\s*\+\s*", " plus ", text)
    text = re.sub(r"\s*[*·×]\s*", " times ", text)
    text = re.sub(r"\s*/\s*", " over ", text)
    text = re.sub(r"(?<![\w.])(\d+)(?![\w.])", lambda m: _number(m.group(1)), text)
    # A single letter said as a letter: "N", not a swallowed "n".
    text = re.sub(r"\b([a-z])\b", lambda m: m.group(1).upper(), text)
    return " ".join(text.split())


def say(text: str) -> str:
    """The line with its notation in words."""
    return _BIG_O.sub(lambda m: f"order {spoken(m.group(1))}", text)


__all__ = ["say", "spoken"]
