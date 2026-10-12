# The decoder in int8, or on more threads (2026-10-12)

**Question.** Live speech is made at ~0.75x real time on this laptop: for 8 s
of speech, ~5 s choosing tokens (the int8 language model) and ~4 s turning
them into sound (the decoder, fp32 on the CPU). Streaming (`stream.py`)
cannot start early until the two together beat real time. The language
model went 2.5x faster in int8 (`int8.md`); can the decoder?

**Method.** `decoder_int8.py`: the decoder quantized the language model's
way (MatMul weights int8, per channel, 7-bit), real tokens made for four
interview sentences (5.8-9.3 s of speech), each decoded by fp32 twice and
int8 once; time against the speech's length; log-spectral distance of int8
to fp32 against fp32 to itself (the decoder samples noise, so two fp32 runs
differ). Then the same with 8 decoder threads instead of 4.

**Result: neither helps.**

| | fp32 | int8 |
|---|---|---|
| decode time / speech, 4 threads | 0.40 | 0.37 |
| decode time / speech, 8 threads | 0.41 | 0.37 |
| distance to fp32 (dB) | 8.95 (fp32 to itself) | 8.81 |

int8 sounds the same (its distance to fp32 is within fp32's own) but is
only ~7 % faster: the decoder's time is not in the MatMuls int8 speeds up.
More threads change nothing. The decoder runs at ~0.4x real time here
whatever is done on the CPU, so live speech stays slower than it is spoken
and a stream cannot start early. A GPU decoder can: abhinav's GTX 1650 ran
it at 0.12-0.19x (`tts.decoder_providers`, `M11_TTS_DECODER_DEVICE`). The
GPU is not for now (the user, 2026-10-10); this is where streaming waits.
