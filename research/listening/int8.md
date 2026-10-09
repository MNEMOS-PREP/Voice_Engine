# An int8 language model for live lines (2026-10-09)

Chatterbox Turbo's language model chooses ~25 speech tokens per second of
audio, one token at a time; on a laptop CPU each step is mostly reading the
model's weights. ResembleAI's export ships it in fp32 (1.2 GB), q4 and 8-bit;
their 8-bit file runs at 2 tokens/s here (a quantization format this CPU has
no fast kernels for). onnxruntime's own dynamic quantization — MatMul weights
to int8, per channel, activations quantized as they come — uses the CPU's
int8 (AVX-VNNI) kernels instead. `tts.int8_graph` makes it once (~40 s,
344 MB) from the fp32 file.

## Speed (`dml_lm_bench`-style, 4 threads, random inputs, i7-1260P)

| model | one sentence | three side by side |
|---|---|---|
| fp32 | 16.4 tokens/s | 35.0 |
| q4 (ResembleAI) | 17.6 | 29.8 |
| **int8 (dynamic)** | **41.5** | **56.6** |

Speech needs 25 tokens/s, so a sentence made alone on int8 is made faster
than it is spoken — fp32 takes 1.5x as long as the speech itself.

## Quality (`int8_check.py`: 14 voices x 3 sentences, read back by M11)

| | mean WER | worst | pace |
|---|---|---|---|
| fp32 | 0.018 | 0.12 | 3.24 words/s |
| int8 | 0.033 | 0.21 | 3.29 words/s |

Much of both columns is the recogniser, not the voice ("one pass" heard as
"OnePass" for fp32 and int8 alike). What is int8's own: "under load" heard as
"on the load" for three voices, and one clear slip — voice 103607 (Dr.
Raghavan's) heard "Demiho you would find… in one bus" for "tell me how you
would find… in one pass". Pace is unchanged.

## So: both

Lines made ahead (`plan` with priority `next` or `warm`: the next question,
the panel's phrases, a prefill's line) are made by fp32 — their time is free.
Lines no one could make ahead (a follow-up adapted to the answer) are made by
int8 the moment they are needed: a few seconds against fp32's ten or more,
for a slightly higher chance of a misread word. Each clip is kept under its
own model's cache key; a sentence made both ways is said in fp32.

`M11_TTS_PRECISION` (default fp32) is the main model; `M11_TTS_LIVE_PRECISION`
(default int8, empty for none) the live one.
