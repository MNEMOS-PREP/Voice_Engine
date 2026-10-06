"""The interviewer's voice, made on the server — Chatterbox Turbo, via ONNX.

The team's choice after a blind listening test (2026-10-06): Chatterbox Turbo
(Resemble AI, MIT) speaking in cloned voices, mostly Indian. It replaces the
browser's built-in voice where M11 is running; where it is not, the browser
voice is still there (`@ai/core`), so an outage costs realism, never sound.

Why ONNX, not the `chatterbox-tts` package: ResembleAI's own ONNX export
needs no PyTorch, and on this laptop's CPU it is 2–3× faster (research/
listening/onnx_speed.py: fp32 1.9× real time, q4 1.4×; PyTorch 4.5×). It is
still slower than speech on a laptop — accepted for now; a GPU machine later.

Three things make it usable before that machine exists:

* **One voice, prepared once.** Each voice's reference recording is encoded
  when the engine loads, not per line.
* **A line said once is never made again.** Every line is cached in memory
  and on disk, keyed by engine, voice and text — greetings, transitions and
  "repeat the question" are instant after the first time.
* **One at a time.** Synthesis is serialised: on a CPU, two at once only make
  both late.

The cast — who speaks for whom — is data (`voices/cast.json`), with each
voice's source, licence and credit (`voices/ATTRIBUTION.md`).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import threading
import time
import wave
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import lexicon

log = logging.getLogger("uvicorn.error")

HERE = Path(__file__).resolve().parent
VOICES_DIR = HERE / "voices"
CAST_FILE = VOICES_DIR / "cast.json"
CACHE_DIR = Path(os.getenv("M11_TTS_CACHE") or HERE.parent / ".tts_cache")

MODEL_ID = "ResembleAI/chatterbox-turbo-ONNX"
SAMPLE_RATE = 24_000
START_SPEECH, STOP_SPEECH, SILENCE_TOKEN = 6561, 6562, 4299
NUM_KV_HEADS, HEAD_DIM = 16, 64
#: Bump when generation changes, so cached lines made the old way are not reused.
ENGINE_VERSION = "chatterbox-turbo-onnx/1"

VOICE_ID = re.compile(r"^([a-z]{2})-([A-Z]{2})-([a-z]+)-([a-z]+)$")


# ─────────────────────────────────────────────────────────────────────────
#  The cast — pure, no model needed
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Voice:
    key: str
    label: str
    accent: str  # "indian" | "foreign"
    register: str  # "higher" | "lower" — pitch, nothing more
    pitch_hz: int
    source: str
    licence: str
    credit: str

    @property
    def file(self) -> Path:
        return VOICES_DIR / f"{self.key}.flac"


@dataclass(frozen=True)
class Cast:
    voices: dict[str, Voice]
    cast: dict[str, str]
    default: str

    @classmethod
    def load(cls, path: Path = CAST_FILE) -> Cast:
        raw = json.loads(path.read_text(encoding="utf-8"))
        voices = {
            key: Voice(key=key, **{k: v for k, v in meta.items()})
            for key, meta in raw["voices"].items()
        }
        for persona, key in raw["cast"].items():
            if key not in voices:
                raise ValueError(f"cast.json: {persona} is cast as {key!r}, which is not a voice")
        if raw["default"] not in voices:
            raise ValueError(f"cast.json: the default voice {raw['default']!r} is not a voice")
        return cls(voices=voices, cast=dict(raw["cast"]), default=raw["default"])

    def resolve(
        self, persona_id: str | None = None, voice_id: str | None = None, voice: str | None = None
    ) -> Voice:
        """The voice for a line: an explicit voice, else the persona's cast
        voice, else one matching the persona's authored `voice_id` (accent from
        the locale, register from the kind), else the default."""
        if voice and voice in self.voices:
            return self.voices[voice]
        if persona_id and persona_id in self.cast:
            return self.voices[self.cast[persona_id]]
        match = VOICE_ID.match(voice_id or "")
        if match:
            accent = "indian" if match.group(2) == "IN" else "foreign"
            register = {"female": "higher", "male": "lower"}.get(match.group(3))
            fits = sorted(
                (
                    v
                    for v in self.voices.values()
                    if v.accent == accent and (register is None or v.register == register)
                ),
                key=lambda v: v.key,
            )
            if fits:
                # Spread unknown personas across the voices that fit, the same
                # way every time, rather than all onto the first.
                digest = hashlib.sha1((persona_id or voice_id or "").encode()).digest()
                return fits[digest[0] % len(fits)]
        return self.voices[self.default]


def punc_norm(text: str) -> str:
    """Chatterbox's own clean-up, so text reads the way it was trained on."""
    text = " ".join(text.split())
    if not text:
        return ""
    if text[0].islower():
        text = text[0].upper() + text[1:]
    for old, new in (
        ("…", ", "),
        (":", ","),
        ("—", "-"),
        ("–", "-"),
        (" ,", ","),
        ("“", '"'),
        ("”", '"'),
        ("‘", "'"),
        ("’", "'"),
    ):
        text = text.replace(old, new)
    text = text.rstrip(" ")
    if not text.endswith((".", "!", "?", "-", ",")):
        text += "."
    return text


def sample_next(
    logits: Any,
    generated: Any,
    rng: Any,
    *,
    temperature: float = 0.8,
    top_k: int = 1000,
    top_p: float = 0.95,
    repetition_penalty: float = 1.2,
) -> int:
    """The next speech token, as the PyTorch model samples it — not the model
    card's greedy argmax, which was measured speaking slower (onnx_speed.py)."""
    import numpy as np

    scores = logits.astype(np.float64).reshape(-1).copy()
    if repetition_penalty != 1.0 and generated.size:
        seen = np.unique(generated)
        picked = scores[seen]
        scores[seen] = np.where(
            picked < 0, picked * repetition_penalty, picked / repetition_penalty
        )
    if temperature <= 0:
        return int(np.argmax(scores))
    scores = scores / temperature
    if 0 < top_k < scores.size:
        cutoff = np.partition(scores, -top_k)[-top_k]
        scores = np.where(scores < cutoff, -np.inf, scores)
    probs = np.exp(scores - np.max(scores))
    probs /= probs.sum()
    if top_p < 1.0:
        order = np.argsort(-probs)
        cumulative = np.cumsum(probs[order])
        keep = order[: int(np.searchsorted(cumulative, top_p)) + 1]
        mask = np.zeros_like(probs)
        mask[keep] = probs[keep]
        probs = mask / mask.sum()
    return int(rng.choice(probs.size, p=probs))


def to_wav(samples: Any, rate: int = SAMPLE_RATE) -> bytes:
    """16-bit PCM WAV, which every browser plays."""
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


# ─────────────────────────────────────────────────────────────────────────
#  The engine
# ─────────────────────────────────────────────────────────────────────────


class EngineUnavailable(RuntimeError):
    """The server voice cannot speak right now; the browser voice should."""


class Engine:
    """Loads once in the background; then speaks, one line at a time."""

    def __init__(self, cast: Cast, precision: str | None = None) -> None:
        self.cast = cast
        self.precision = precision or os.getenv("M11_TTS_PRECISION", "fp32")
        self.state = "off"
        self.reason = "not started"
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._conds: dict[str, tuple] = {}
        self._sessions: dict[str, Any] = {}
        self._tokenizer: Any = None
        self._rng: Any = None

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin loading in the background. Idempotent; never raises."""
        with self._start_lock:
            if self.state in ("loading", "ready"):
                return
            if os.getenv("M11_TTS", "on").lower() in ("off", "0", "false"):
                self.state, self.reason = "off", "turned off (M11_TTS=off)"
                return
            self.state, self.reason = "loading", "loading the voice model"
            threading.Thread(target=self._load, name="m11-tts-load", daemon=True).start()

    def _load(self) -> None:
        try:
            import numpy as np
            import onnxruntime
            import soundfile
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
        except ImportError as exc:
            self.state = "off"
            self.reason = (
                f"the voice model's packages are not installed ({exc.name}); "
                'pip install -e ".[tts]"'
            )
            log.info("M11 TTS off: %s", self.reason)
            return
        try:
            t0 = time.perf_counter()

            def graph(name: str, dtype: str) -> str:
                suffix = "" if dtype == "fp32" else "_quantized" if dtype == "q8" else f"_{dtype}"
                path = hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx")
                hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx_data")
                return path

            for name in ("speech_encoder", "embed_tokens", "language_model", "conditional_decoder"):
                dtype = self.precision if name == "language_model" else "fp32"
                self._sessions[name] = onnxruntime.InferenceSession(graph(name, dtype))
            self._tokenizer = Tokenizer.from_file(hf_hub_download(MODEL_ID, "tokenizer.json"))
            self._rng = np.random.default_rng()
            for voice in self.cast.voices.values():
                audio, rate = soundfile.read(voice.file, dtype="float32")
                if rate != SAMPLE_RATE:
                    raise ValueError(
                        f"{voice.file.name} is {rate} Hz; voices are stored at {SAMPLE_RATE}"
                    )
                audio = audio[: SAMPLE_RATE * 15][np.newaxis, :].astype(np.float32)
                self._conds[voice.key] = tuple(
                    self._sessions["speech_encoder"].run(None, {"audio_values": audio})
                )
            self.state, self.reason = "ready", f"{len(self._conds)} voices, {self.precision}"
            log.info("M11 TTS ready in %.0fs: %s", time.perf_counter() - t0, self.reason)
        except Exception as exc:  # noqa: BLE001 - a failed load is a state, not a crash
            self.state, self.reason = "failed", f"{type(exc).__name__}: {exc}"
            log.warning("M11 TTS failed to load: %s", self.reason)

    # ── speaking ─────────────────────────────────────────────────────────

    def cache_key(self, text: str, voice: Voice) -> str:
        return hashlib.sha1(
            f"{ENGINE_VERSION}|{self.precision}|{voice.key}|{text}".encode()
        ).hexdigest()

    def cached(self, text: str, voice: Voice) -> bytes | None:
        key = self.cache_key(text, voice)
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key]
        path = CACHE_DIR / voice.key / f"{key}.wav"
        if path.exists():
            data = path.read_bytes()
            self._remember(key, data)
            return data
        return None

    def _remember(self, key: str, data: bytes) -> None:
        self._memory[key] = data
        self._memory.move_to_end(key)
        while len(self._memory) > 256:
            self._memory.popitem(last=False)

    def speak(self, text: str, voice: Voice) -> tuple[bytes, bool, int]:
        """(wav, from_cache, ms). Raises EngineUnavailable when it cannot."""
        # Words the voices get wrong, respelled (EC-11.11, `lexicon.py`) —
        # before the cache, so a fixed word is a new line, not the old one.
        text = punc_norm(lexicon.apply(text, voice.key))
        if not text:
            raise ValueError("nothing to say")
        hit = self.cached(text, voice)
        if hit is not None:
            return hit, True, 0
        if self.state != "ready":
            raise EngineUnavailable(self.reason)
        t0 = time.perf_counter()
        with self._lock:
            hit = self.cached(text, voice)  # made while this request waited
            if hit is not None:
                return hit, True, 0
            data = to_wav(self._synthesize(text, voice))
        key = self.cache_key(text, voice)
        self._remember(key, data)
        try:
            (CACHE_DIR / voice.key).mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / voice.key / f"{key}.wav").write_bytes(data)
        except OSError as exc:
            log.info("M11 TTS cache not written: %s", exc)
        return data, False, round((time.perf_counter() - t0) * 1000)

    def _synthesize(self, text: str, voice: Voice) -> Any:
        import numpy as np

        s = self._sessions
        cond, prompt, spk_emb, spk_feat = self._conds[voice.key]
        input_ids = np.array([self._tokenizer.encode(text).ids], dtype=np.int64)
        generated = np.array([START_SPEECH], dtype=np.int64)
        lm = s["language_model"]
        max_new = min(1000, 60 + len(text) * 4)
        past: dict[str, Any] = {}
        mask = pos = None
        for i in range(max_new):
            embeds = s["embed_tokens"].run(None, {"input_ids": input_ids})[0]
            if i == 0:
                embeds = np.concatenate((cond, embeds), axis=1)
                batch, seq, _ = embeds.shape
                past = {
                    x.name: np.zeros(
                        [batch, NUM_KV_HEADS, 0, HEAD_DIM],
                        dtype=np.float16 if x.type == "tensor(float16)" else np.float32,
                    )
                    for x in lm.get_inputs()
                    if "past_key_values" in x.name
                }
                mask = np.ones((batch, seq), dtype=np.int64)
                pos = np.arange(seq, dtype=np.int64).reshape(1, -1)
            logits, *present = lm.run(
                None, dict(inputs_embeds=embeds, attention_mask=mask, position_ids=pos, **past)
            )
            token = sample_next(logits[:, -1, :], generated[1:], self._rng)
            generated = np.append(generated, token)
            if token == STOP_SPEECH:
                break
            input_ids = np.array([[token]], dtype=np.int64)
            mask = np.concatenate([mask, np.ones((1, 1), dtype=np.int64)], axis=1)
            pos = pos[:, -1:] + 1
            for j, name in enumerate(past):
                past[name] = present[j]
        speech = generated[1:]
        if speech.size and speech[-1] == STOP_SPEECH:
            speech = speech[:-1]
        speech = speech[speech < START_SPEECH]  # drop anything outside the codec
        tokens = np.concatenate(
            [prompt, speech[np.newaxis, :], np.full((1, 3), SILENCE_TOKEN, dtype=np.int64)], axis=1
        )
        wav = (
            s["conditional_decoder"]
            .run(
                None,
                dict(speech_tokens=tokens, speaker_embeddings=spk_emb, speaker_features=spk_feat),
            )[0]
            .squeeze(axis=0)
        )
        return self._watermark(wav)

    @staticmethod
    def _watermark(wav: Any) -> Any:
        """Resemble's inaudible Perth watermark when it is installed (it needs
        PyTorch, which this engine otherwise does not); the visible "AI
        interviewer" label carries the disclosure either way."""
        try:
            import perth
        except ImportError:
            return wav
        return perth.PerthImplicitWatermarker().apply_watermark(wav, sample_rate=SAMPLE_RATE)


_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine(Cast.load())
    return _engine


def set_engine(value: Engine | None) -> None:
    """Tests install a fake; None goes back to the real one."""
    global _engine
    _engine = value


__all__ = [
    "Cast",
    "Engine",
    "EngineUnavailable",
    "Voice",
    "engine",
    "punc_norm",
    "sample_next",
    "set_engine",
    "to_wav",
]
