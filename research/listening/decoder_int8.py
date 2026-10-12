"""Can the decoder run in int8, as the language model does? (2026-10-12)

On this laptop live speech is made at ~0.75x real time: for 8 s of speech,
~5 s choosing tokens (the int8 language model) and ~4 s turning them into
sound (the decoder, fp32 on the CPU). Streaming (stream.py) cannot start
early until the two together beat real time, and the GPU is not for now.
The language model went 2.5x faster in int8 (int8.md); the decoder is the
other half.

The decoder is made in int8 the language model's way (MatMul weights int8,
per channel), real speech tokens are made for long interview sentences,
and each is decoded by fp32 twice (the decoder samples noise, so two fp32
runs differ: the baseline) and by int8 once. Reported: decode time against
the speech's length, and the log-spectral distance of int8 to fp32 against
fp32 to itself. The clips are kept for a read-back (`--readback`, M11 up).

    ..\\..\\Backend\\.venv\\Scripts\\python.exe decoder_int8.py           (M11 stopped: RAM)
    ..\\..\\Backend\\.venv\\Scripts\\python.exe decoder_int8.py --readback (M11 running)
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import statistics
import sys
import time
import urllib.request

import numpy as np
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "decoder_int8"
sys.path.insert(0, str(HERE.parents[1] / "Backend"))

SENTENCES = (
    (
        "Recall a situation where you were asked a question you did not know the answer to "
        "during an interview, and tell me how you handled it while thinking aloud."
    ),
    (
        "Why is it important to choose a proper primary key for the orders table, and what "
        "could go wrong if you pick a non-unique or mutable attribute?"
    ),
    (
        "Walk me through how you would design a rate limiter for a public interface that "
        "serves a few thousand requests a second."
    ),
    (
        "That's a good start. Can you tell me what you would change if the data no longer "
        "fits in memory?"
    ),
)
RATE = 24_000


def lsd(a: np.ndarray, b: np.ndarray) -> float:
    """Log-spectral distance in dB, frame by frame, over the shorter clip."""
    n = min(len(a), len(b))
    window = np.hanning(1024).astype(np.float32)

    def power(x: np.ndarray) -> np.ndarray:
        frames = np.lib.stride_tricks.sliding_window_view(x[:n], 1024)[::256] * window
        return np.abs(np.fft.rfft(frames, axis=1)) ** 2 + 1e-10

    diff = 10 * np.log10(power(a)) - 10 * np.log10(power(b))
    return float(np.mean(np.sqrt(np.mean(diff**2, axis=1))))


def make_int8(fp32: str, reduce: bool) -> str:
    from backend_M11_Voice_Engine import tts
    from onnxruntime.quantization import QuantType, quantize_dynamic

    target = tts.INT8_DIR / f"conditional_decoder_int8{'_rr' if reduce else ''}.onnx"
    if not target.exists():
        t0 = time.perf_counter()
        quantize_dynamic(
            fp32,
            str(target),
            weight_type=QuantType.QInt8,
            op_types_to_quantize=["MatMul"],
            per_channel=True,
            reduce_range=reduce,
            use_external_data_format=True,
            extra_options={"MatMulConstBOnly": True},
        )
        print(
            f"int8 decoder made in {time.perf_counter() - t0:.0f}s: {target.name}",
            flush=True,
        )
    return str(target)


def measure() -> None:
    import onnxruntime
    from backend_M11_Voice_Engine import tts
    from huggingface_hub import hf_hub_download

    OUT.mkdir(exist_ok=True)
    fp32_path = hf_hub_download(
        tts.MODEL_ID, subfolder="onnx", filename="conditional_decoder.onnx"
    )
    reduce = os.getenv("M11_TTS_INT8_REDUCE_RANGE", "1").lower() not in (
        "0",
        "false",
        "off",
    )
    int8_path = make_int8(fp32_path, reduce)

    engine = tts.Engine(tts.Cast.load())
    engine._load()  # in this process, synchronously
    assert engine.state == "ready", engine.reason
    voice = engine.cast.resolve(persona_id="db_neha")
    fp32 = engine._sessions["conditional_decoder"]
    int8 = onnxruntime.InferenceSession(
        int8_path, tts.session_options(onnxruntime, "conditional_decoder")
    )
    feeds: list[dict] = []

    class Recorder:
        """The engine's decoder, keeping what it is given."""

        def run(self, names, feed):
            feeds.append({k: v.copy() for k, v in feed.items()})
            return fp32.run(names, feed)

        def get_providers(self):
            return fp32.get_providers()

    engine._sessions["conditional_decoder"] = Recorder()
    for text in SENTENCES:
        engine._synthesize(text, voice)
    engine._sessions["conditional_decoder"] = fp32

    def decode(session, feed) -> tuple[np.ndarray, float]:
        t0 = time.perf_counter()
        wav = session.run(None, feed)[0].squeeze()
        return wav.astype(np.float32), time.perf_counter() - t0

    rows = []
    for i, feed in enumerate(feeds):
        decode(fp32, feed)  # the first run of a shape pays for it once
        decode(int8, feed)
        a, ta = decode(fp32, feed)
        b, tb = decode(fp32, feed)
        c, tc = decode(int8, feed)
        seconds = len(a) / RATE
        for tag, wav in (("fp32", a), ("int8", c)):
            sf.write(OUT / f"{i}_{tag}.wav", wav, RATE)
        row = {
            "sentence": i,
            "speech_s": round(seconds, 2),
            "fp32_rtf": round(statistics.mean([ta, tb]) / seconds, 3),
            "int8_rtf": round(tc / seconds, 3),
            "lsd_fp32_fp32": round(lsd(a, b), 3),
            "lsd_int8_fp32": round(lsd(c, a), 3),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    summary = {
        "reduce_range": reduce,
        "decoder_threads": tts.DECODER_THREADS,
        "fp32_rtf": round(statistics.mean(r["fp32_rtf"] for r in rows), 3),
        "int8_rtf": round(statistics.mean(r["int8_rtf"] for r in rows), 3),
        "lsd_fp32_fp32": round(statistics.mean(r["lsd_fp32_fp32"] for r in rows), 3),
        "lsd_int8_fp32": round(statistics.mean(r["lsd_int8_fp32"] for r in rows), 3),
    }
    print(json.dumps(summary), flush=True)
    (OUT / "results.json").write_text(
        json.dumps({"rows": rows, "summary": summary}, indent=1)
    )


def readback() -> None:
    sys.path.insert(0, str(HERE))
    from probe_voices import wer

    who = {
        "X-Role": "student",
        "X-Candidate-Id": "4d0aa1c0-0000-4000-8000-000000000004",
    }
    scores = {"fp32": [], "int8": []}
    for i, text in enumerate(SENTENCES):
        for tag, found in scores.items():
            data = io.BytesIO()
            audio, rate = sf.read(OUT / f"{i}_{tag}.wav", dtype="float32")
            sf.write(data, audio, rate, format="WAV")
            request = urllib.request.Request(
                "http://127.0.0.1:8111/v1/voice/transcribe",
                data=data.getvalue(),
                headers={**who, "Content-Type": "audio/wav"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                heard = json.loads(response.read())["text"]
            found.append(wer(text, heard))
            print(f"{i} {tag}: wer {found[-1]:.3f}  {heard[:80]}", flush=True)
    print({tag: round(statistics.mean(v), 3) for tag, v in scores.items()})


if __name__ == "__main__":
    readback() if "--readback" in sys.argv else measure()
