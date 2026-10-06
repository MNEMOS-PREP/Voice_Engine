"""Has the student finished? — M11 day 5, semantic endpointing (FR-11.5).

The browser decides when a silence is long enough to ask (FR-11.4: an
adaptive threshold per speaker, `@ai/core`'s `endpoint.ts`). This decides
whether the speech before it SOUNDS finished — a falling close, a completed
clause — or like someone drawing breath mid-thought ("so the first thing I'd
do is… "). An unfinished turn makes the browser wait a little longer.

**Smart Turn v3.2** (Pipecat, BSD-2-Clause code and weights): a Whisper-Tiny
encoder with a one-unit head, trained on 23 languages including English,
Hindi and Marathi; its own benchmark reads 92.6% over 31,527 samples. It
hears the WAVEFORM, not a transcript, so it runs before recognition and costs
no API call. 8.7 MB as int8 ONNX; milliseconds on a CPU.

The preprocessing is the reference implementation's, reproduced in numpy so
this module does not pull in `transformers` (checked against it — see
`tests/test_turn.py`): the last 8 s of 16 kHz audio, LEFT-padded with zeros,
normalised to zero mean and unit variance, as Whisper's 80-bin log-mel
spectrogram (400-point Hann window, hop 160, Slaney mel scale and norm,
log10, floored 8 below the peak, scaled by (x + 4) / 4) — 80 × 800. The model
returns a probability: above 0.5 is "finished".

Loaded in the background like the voice (`M11_TURN=off` turns it off; tests
never load it). When it is not ready the browser endpoints on silence alone.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
import wave
from functools import cache
from typing import Any

log = logging.getLogger("uvicorn.error")

REPO = "pipecat-ai/smart-turn-v3"
FILE = os.getenv("M11_TURN_MODEL", "smart-turn-v3.2-cpu.onnx")
RATE = 16_000
SECONDS = 8
N_FFT = 400
HOP = 160
N_MELS = 80
#: Above this the turn is finished (the reference implementation's line).
THRESHOLD = 0.5


class TurnUnavailable(Exception):
    """The model cannot answer; the browser endpoints on silence alone."""


# ── features: Whisper's log-mel spectrogram, in numpy ───────────────────────


def _hz_to_mel(hz):
    import numpy as np

    hz = np.asarray(hz, dtype=np.float64)
    f_sp = 200.0 / 3
    mel = hz / f_sp
    min_log_hz, min_log_mel, logstep = 1000.0, 1000.0 / f_sp, np.log(6.4) / 27.0
    return np.where(
        hz >= min_log_hz, min_log_mel + np.log(np.maximum(hz, 1e-10) / min_log_hz) / logstep, mel
    )


def _mel_to_hz(mel):
    import numpy as np

    mel = np.asarray(mel, dtype=np.float64)
    f_sp = 200.0 / 3
    hz = mel * f_sp
    min_log_hz, min_log_mel, logstep = 1000.0, 1000.0 / f_sp, np.log(6.4) / 27.0
    return np.where(mel >= min_log_mel, min_log_hz * np.exp(logstep * (mel - min_log_mel)), hz)


@cache
def mel_filters():
    """80 triangular filters over 201 frequency bins, Slaney scale and norm
    (transformers' `mel_filter_bank(..., norm="slaney", mel_scale="slaney")`)."""
    import numpy as np

    fft_freqs = np.linspace(0, RATE // 2, 1 + N_FFT // 2)
    mel_freqs = np.linspace(_hz_to_mel(0.0), _hz_to_mel(8000.0), N_MELS + 2)
    filter_freqs = _mel_to_hz(mel_freqs)
    diff = np.diff(filter_freqs)
    slopes = filter_freqs[None, :] - fft_freqs[:, None]
    down = -slopes[:, :-2] / diff[:-1]
    up = slopes[:, 2:] / diff[1:]
    filters = np.maximum(0.0, np.minimum(down, up))  # (201, 80)
    enorm = 2.0 / (filter_freqs[2 : N_MELS + 2] - filter_freqs[:N_MELS])
    return (filters * enorm[None, :]).astype(np.float64)


def last_seconds(audio, seconds: int = SECONDS):
    """The last `seconds` of the audio, left-padded with silence to exactly
    that long — the reference's `truncate_audio_to_last_n_seconds`."""
    import numpy as np

    n = seconds * RATE
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) >= n:
        return audio[-n:]
    return np.pad(audio, (n - len(audio), 0))


def features(audio):
    """16 kHz float audio (any length) → the model's input, (1, 80, 800)."""
    import numpy as np

    x = last_seconds(audio).astype(np.float64)
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)  # do_normalize
    padded = np.pad(x, (N_FFT // 2, N_FFT // 2), mode="reflect")  # center=True
    window = np.hanning(N_FFT + 1)[:-1]  # periodic Hann
    frames = 1 + (len(padded) - N_FFT) // HOP
    index = np.arange(N_FFT)[None, :] + HOP * np.arange(frames)[:, None]
    spectrum = np.abs(np.fft.rfft(padded[index] * window, n=N_FFT)) ** 2  # (801, 201)
    mel = np.maximum(1e-10, spectrum @ mel_filters())  # (801, 80)
    log_spec = np.log10(mel).T[:, :-1]  # (80, 800): the last frame is dropped
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0
    return log_spec[None, :, :].astype(np.float32)


def read_wav(data: bytes):
    """A 16-bit mono WAV (what the browser's listener sends) → float audio at
    16 kHz. Anything else is refused rather than guessed at."""
    import numpy as np

    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError("Send 16-bit mono WAV.")
            if w.getframerate() != RATE:
                raise ValueError(f"Send {RATE} Hz audio.")
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Not a WAV file: {exc}") from None
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


# ── the model ─────────────────────────────────────────────────────────────


class Classifier:
    """Smart Turn, loaded once in the background; one question at a time."""

    def __init__(self) -> None:
        self.state = "off"
        self.reason = "not started"
        self._session: Any = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if os.getenv("M11_TURN", "on").lower() in ("off", "0", "false"):
            self.state, self.reason = "off", "turned off (M11_TURN=off)"
            return
        if self.state in ("loading", "ready"):
            return
        self.state, self.reason = "loading", "downloading or loading the model"
        threading.Thread(target=self._load, name="m11-turn-load", daemon=True).start()

    def _load(self) -> None:
        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download

            path = hf_hub_download(REPO, FILE)
            options = ort.SessionOptions()
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                path, sess_options=options, providers=["CPUExecutionProvider"]
            )
            self.state, self.reason = "ready", FILE
            log.info("M11: turn model ready (%s)", FILE)
        except ImportError:
            self.state, self.reason = "off", 'pip install -e ".[tts]" for the turn model'
        except Exception as exc:  # noqa: BLE001 - any failure means "endpoint on silence"
            self.state, self.reason = "failed", f"{type(exc).__name__}: {exc}"[:200]
            log.warning("M11: turn model failed to load: %s", self.reason)

    def finished(self, audio) -> tuple[float, int]:
        """The probability the turn is over, and how long it took to say so."""
        if self.state != "ready" or self._session is None:
            raise TurnUnavailable(self.reason)
        started = time.perf_counter()
        inputs = features(audio)
        with self._lock:
            out = self._session.run(None, {"input_features": inputs})
        probability = float(out[0].reshape(-1)[0])
        return probability, round((time.perf_counter() - started) * 1000)


_classifier: Classifier | None = None


def classifier() -> Classifier:
    global _classifier
    if _classifier is None:
        _classifier = Classifier()
    return _classifier


def set_classifier(value: Classifier | None) -> None:
    """Tests stand a fake in; None goes back to the real one, unloaded."""
    global _classifier
    _classifier = value


__all__ = [
    "THRESHOLD",
    "Classifier",
    "TurnUnavailable",
    "classifier",
    "features",
    "last_seconds",
    "mel_filters",
    "read_wav",
    "set_classifier",
]
