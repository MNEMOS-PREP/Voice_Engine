"""Word error rate — the arithmetic the recogniser is chosen by (day 6)."""

from __future__ import annotations

from backend_M11_Voice_Engine import wer


def test_the_same_words_are_no_errors_whatever_the_punctuation_and_case():
    assert (
        wer.score("white leghorns said mrs mortimer", "White Leghorns, said Mrs. Mortimer.").wer
        == 0.0
    )
    assert wer.normalise("It's O(n) — isn't it?") == ["it's", "o", "n", "isn't", "it"]


def test_substitutions_deletions_and_insertions_each_count_once():
    assert wer.edits(["a", "b", "c"], ["a", "x", "c"]) == 1
    assert wer.edits(["a", "b", "c"], ["a", "c"]) == 1
    assert wer.edits(["a", "b", "c"], ["a", "b", "b", "c"]) == 1
    assert wer.score("the cat sat", "").wer == 1.0


def test_a_corpus_rate_weighs_every_word_not_every_sentence():
    short = wer.score("yes", "no")  # 1 of 1 wrong
    long = wer.score(" ".join(["word"] * 19), " ".join(["word"] * 19))  # 0 of 19
    assert round(wer.pooled([short, long]), 3) == 0.05
    assert wer.pooled([]) == 0.0


def test_the_accent_gap_is_the_widest_between_groups():
    groups = {
        "tamil": [wer.score("a b c d e f g h i j", "a b c d e f g h i x")],  # 10 %
        "hindi": [wer.score("a b c d e f g h i j", "a b c d e f g h i j")],  # 0 %
        "bengali": [wer.score("a b c d e", "a b c x e")],  # 20 %
    }
    assert round(wer.gap(groups), 6) == 20.0
    assert wer.gap({"one": groups["tamil"]}) == 0.0
