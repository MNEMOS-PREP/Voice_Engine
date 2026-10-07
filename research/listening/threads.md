# The gap after every full stop — measured and fixed (2026-10-07)

The user, sitting a drill: *"it speaks 1 sentence properly but then there is a
2 sec gap after full stop … every sentence gets a 2 sec gap"*.

Laptop: i7-1260P (4 performance cores, 8 efficiency cores, 16 threads), 16 GB,
Iris Xe; on AC, Ultimate Performance. Model: Chatterbox Turbo ONNX (fp32
language model, 317M parameters; GroupQueryAttention). Times are wall clock.

## Why there was a gap

The room asks M11 for each sentence while the one before it plays. On this CPU
a sentence took several times its own length to make, so the next one was
never ready when the last one ended. Live, a 4 s sentence took 28 s.

## What was measured

**Threads.** onnxruntime's default is one thread per physical core (12). On a
hybrid CPU every operation is then split across the efficiency cores too, and
each step waits for the slowest:

| language model, one step (300 cached tokens) | ms |
|---|---|
| default (12 threads) | 84 |
| 4 threads | 62 |
| 8 threads | 63 |
| 16 threads | 271 |

Whole sentences (language model + decoder): default threads 6.6–7.9× slower
than real time; 4–6 threads 2.2–3.1×.

**Rows: three sentences at once.** Each step of the language model is mostly
reading its weights, so a batch of sentences costs little more than one:

| sentences per step | ms/step | tokens/s | seconds of speech per second |
|---|---|---|---|
| 1 | 78 | 12.9 | 0.51 |
| 2 | 97 | 20.5 | 0.82 |
| 3 | 110 | 27.3 | 1.09 |
| 4 | 143 | 27.9 | 1.12 |
| 6 | 213 | 28.2 | 1.13 |

Three is the knee: faster than speech for the first time.

**Rows of different lengths.** The attention op reads each row's length from
the mask and its cache from the row's start, so rows are padded on the RIGHT.
Checked: a row padded on the right inside a batch gives the same logits as the
row alone, to the last digit (max |diff| 0.0); padded on the left, 10.5.

**The voice's conditioning, cached.** Every sentence begins with the same 151
conditioning tokens. Run once per voice and reused: the first step of a
sentence is 107 ms instead of 1,135 ms, with identical logits.

**The decoder's reference.** The decoder was given the voice's whole 10 s
reference with every sentence. For a 5.8 s sentence:

| reference | decoder | speaker similarity to the voice |
|---|---|---|
| 10 s | 5.56 s | 0.900 |
| 6 s | 4.23 s | 0.890 |
| 4 s | 3.65 s | 0.894 |
| 2 s | 3.23 s | 0.898 |

(Speaker-embedding cosine from Chatterbox's own speech encoder; a different
voice scores 0.522.) 4 s kept.

**Not faster here.** OpenVINO on the CPU: the language model 127–142 ms/step
(slower than onnxruntime's 65). DirectML on the Iris Xe: 15× slower than real
time (it recompiles as the sequence grows). OpenVINO on the Iris Xe: the
decoder does not compile, dynamic or fixed shape.

## The line, end to end (`line_bench.py`, fresh cache)

The drill's opening — 6 pieces, ~16 s of speech, planned at once, asked for in
order, played back to back:

| | first audio | gaps after it | all said by |
|---|---|---|---|
| before (one at a time, default threads) | 8.7 s | 24.5 s | 49.6 s |
| three rows, decoder 6 threads | 19.5 s | 2.1 s | 37.4 s |
| three rows, LM 4 + decoder 4 threads | 9.5 s | 0 | 26.0 s |

A typical two-sentence reply ("Thanks, that makes sense. What would you change
about the harness if you rebuilt it today?"): first audio 5.4 s, no gaps.

## What shipped

- M11 `tts.py`: 4 threads for the language model, 4 for the decoder beside it;
  three rows; right padding; each voice's conditioning cached; the decoder's
  reference 4 s; finished sentences decoded in speaking order.
- `POST /v1/voice/plan` (a line's sentences, at once) and `/v1/voice/drop` (a
  barge-in's unstarted sentences).
- Core v0.26.0: the room plans each line as it arrives; long sentences are cut
  at their clauses so the pieces are made side by side.

On a bigger machine: `M11_TTS_ROWS`, `M11_TTS_THREADS` and
`M11_TTS_DECODER_THREADS` are read from the environment.
