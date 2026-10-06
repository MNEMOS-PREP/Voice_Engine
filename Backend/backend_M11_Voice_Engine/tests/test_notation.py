"""Big-O, said as words — EC-11.11 (`notation.py`).

Pinned from `research/notation/probe.py`: the forms the voices could not
read, each rewritten to what an interviewer would say aloud.
"""

from __future__ import annotations

import pytest

from backend_M11_Voice_Engine import notation


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("O(1)", "order one"),
        ("O(n)", "order N"),
        ("O(log n)", "order log N"),
        ("O(n log n)", "order N log N"),
        ("O(n^2)", "order N squared"),
        ("O(n²)", "order N squared"),
        ("O(n^3)", "order N cubed"),
        ("O(2^n)", "order two to the N"),
        ("O(V + E)", "order V plus E"),
        ("O(m*n)", "order M times N"),
        ("big-O(n)", "order N"),
    ],
)
def test_each_form_is_said_as_an_interviewer_would(written, said):
    assert notation.say(f"Is it {written} here?") == f"Is it {said} here?"


def test_prose_and_other_brackets_are_left_alone():
    for line in (
        "Walk me through the design (briefly).",
        "Which Object (in OOP terms) owns that state?",
        "What does the O stand for in SOLID?",
    ):
        assert notation.say(line) == line


def test_every_occurrence_in_a_line():
    assert (
        notation.say("Can you get from O(n^2) to O(n log n)?")
        == "Can you get from order N squared to order N log N?"
    )
