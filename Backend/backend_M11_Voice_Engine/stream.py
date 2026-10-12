"""A sentence heard while it is still being made (TODO, open problem 3).

The voice makes a sentence as speech tokens, one after another, and only
turns them to sound when the sentence is whole. A long sentence therefore
makes the student wait for all of it. Here the tokens already chosen are
turned to sound in pieces, while the model goes on choosing the rest:

- a piece is `CHUNK` tokens (1 s of speech);
- each is decoded with `CONTEXT` tokens before it, so its start sounds as the
  sentence's own, and `LOOK` tokens after it, so its end does too â€” and only
  its own `CHUNK` tokens' samples are kept (`SAMPLES_PER_TOKEN` each);
- neighbours overlap by `FADE` samples, crossfaded, so a seam is not a click.

This module is the arithmetic and the seam; the decoder is `tts.Engine`'s.
Nothing here needs the model, so it is tested without one.
"""

from __future__ import annotations

from typing import Any

#: S3 speech tokens are 25 a second; at 24 kHz that is 960 samples a token
#: (the same figure `tests/test_tts_parallel.py` holds the decoder to).
SAMPLES_PER_TOKEN = 960
CHUNK = 25
CONTEXT = 25
LOOK = 5
#: 10 ms at 24 kHz.
FADE = 240
#: Speech tokens a second that playback uses.
PLAY_RATE = 25
#: Speech tokens per character of text, from two real sentences (1.31, 1.42).
#: An over-estimate only makes playback wait longer, never stutter.
TOKENS_PER_CHAR = 1.4
#: Margins on what is measured (q4 on a laptop, 2026-10-10): the model slows
#: by up to a fifth while pieces are decoded beside it, and a sentence came in
#: 7 % longer than its text predicted.
RATE_MARGIN = 0.8
TOTAL_MARGIN = 1.25


class Stitcher:
    """Joins pieces of one sentence into a stream with no seam.

    Each piece is `kept` samples plus `FADE` more, the first `FADE` of the
    next piece's overlapping them. `push` returns what can be played now; the
    last `FADE` samples are held until the next piece shows how they end.
    """

    def __init__(self, fade: int = FADE) -> None:
        self.fade = fade
        self._carry: Any = None

    def push(self, piece: Any, last: bool = False) -> Any:
        """Samples that are final, as a float32 array (maybe empty)."""
        import numpy as np

        piece = np.asarray(piece, dtype=np.float32)
        if self._carry is None:
            body = piece
        else:
            n = min(self.fade, self._carry.size, piece.size)
            if n:
                w = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32) + 0.5 / n
                head = self._carry[-n:] * (1.0 - w) + piece[:n] * w
                body = np.concatenate([self._carry[:-n], head, piece[n:]])
            else:
                body = np.concatenate([self._carry, piece])
            self._carry = None
        if last or body.size <= self.fade:
            if last:
                return body
            self._carry = body
            return body[:0]
        self._carry = body[-self.fade :]
        return body[: -self.fade]


def speech_of(wav: Any, n_prompt: int, n_speech: int) -> Any:
    """The part of a decoder's output that is the `n_speech` tokens.

    The decoder is given [prompt, speech, three silence tokens]; whether its
    output carries the prompt, or the trailing silence, is read from its
    length rather than assumed, so a decoder that changes does not shift every
    piece. Raises when no layout fits within 5 %: a seam from a guess is worse
    than the whole sentence, which the caller falls back to."""
    s = SAMPLES_PER_TOKEN
    layouts = (  # (leading tokens dropped, tokens in the output)
        (0, n_speech),
        (0, n_speech + 3),
        (n_prompt, n_prompt + n_speech),
        (n_prompt, n_prompt + n_speech + 3),
    )
    size = int(wav.shape[-1])
    drop, total = min(layouts, key=lambda layout: abs(size - layout[1] * s))
    if abs(size - total * s) > max(s, 0.05 * total * s):
        raise ValueError(f"decoder output {size} samples fits no layout of {n_speech} tokens")
    start = drop * s
    return wav[..., start : start + n_speech * s]


def spans(done: int, have: int) -> list[tuple[int, int]]:
    """The (start, end) token ranges now ready to be decoded: whole `CHUNK`s
    that also have `LOOK` tokens after them. What is left when the sentence
    ends is taken from the sentence's own whole decoding, not from here."""
    out = []
    while True:
        end = done + CHUNK
        if have - end >= LOOK:
            out.append((done, end))
            done = end
        else:
            break
    return out


def estimate_tokens(text: str, have: int = 0) -> int:
    """How many speech tokens the whole sentence will be: from its length,
    never less than what is made already plus one more piece."""
    return max(int(len(text) * TOKENS_PER_CHAR), have + CHUNK)


def ready_to_play(buffered: int, rate: float, total: int) -> bool:
    """Whether playing from now never runs dry.

    `buffered` tokens are decoded and waiting, `rate` tokens a second are being
    made, `total` is the sentence's estimated length. Playback eats `PLAY_RATE`
    a second, so when the making is slower the buffer must already hold the
    difference over the rest of the sentence: (PLAY_RATE - rate) / rate of
    what is left — with `RATE_MARGIN` and `TOTAL_MARGIN` on both. A model
    above real time (after the margin) starts at once. Until a rate is known
    (`rate` <= 0) the answer is no. A model too slow for any buffer to help
    ends as the sentence made whole: no worse than not streaming."""
    if rate <= 0:
        return False
    rate *= RATE_MARGIN
    total = max(total * TOTAL_MARGIN, buffered)
    left = max(0, total - buffered)
    if rate >= PLAY_RATE:
        return buffered > 0
    return buffered >= (PLAY_RATE - rate) / rate * left


#: Streaming must start playing within this fraction of the sentence's making,
#: or it only costs the pieces' decoding (measured: q4, 9 tokens a second, a
#: sentence took 42.8 s streamed against 31.8 s whole).
WORTH_IT_FRACTION = 0.5


def throughput(rate: float, decode_ratio: float) -> float:
    """Tokens a second that can reach the ear: the model's `rate`, or what the
    decoder can turn to sound if that is less. `decode_ratio` is decoder
    seconds per second of speech, measured on the pieces (0: not yet). On the
    2026-10-10 laptop the model made 30 tokens/s alone but a 1 s piece took
    1.3-1.9 s to decode: 13-19 tokens/s, and that is what the ear gets."""
    if decode_ratio <= 0:
        return rate
    return min(rate, PLAY_RATE / decode_ratio) if rate > 0 else PLAY_RATE / decode_ratio


def worth_streaming(rate: float, decode_ratio: float = 0.0) -> bool:
    """Whether streaming can gain anything at the speed (`throughput`) the
    making and decoding reach. The buffer must hold `1 - speed / PLAY_RATE` of
    the sentence before playing (`ready_to_play`); if that is most of it, play
    is no sooner than whole, and every piece decoded on the way is CPU taken
    from the model. An unknown speed (<= 0) is given the benefit of the doubt."""
    speed = throughput(rate, decode_ratio)
    if speed <= 0:
        return True
    return 1.0 - speed * RATE_MARGIN / PLAY_RATE <= WORTH_IT_FRACTION
