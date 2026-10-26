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
* **Lines made before they are said** (2026-10-09). The user, after a mock:
  "gaps in speech, awkward pauses, sometimes if the text is too long". On
  this CPU speech is made barely faster than it is spoken, so a line made
  when it is needed keeps the student waiting. Most of what an interviewer
  says is known before it is said — the next question, the hand-over — and
  the room plans those as WARM lines while the student answers: made only
  while nothing is being said, set aside the moment a live line arrives, and
  promoted the moment one is asked for. `plan` says which sentences of a
  line are made already, so the room knows what it need not wait for. Two
  levels: `next` (the opening, the next question) before `warm` (the
  panel's stock phrases), each in the order the room asked — the room asks
  for what is needed first first, and drops what a newer guess replaced.
* **Live lines on a faster model** (2026-10-09). What no one could make
  ahead — a follow-up adapted to the answer — is made the moment it is
  needed, so it is made by an int8 copy of the language model (`int8_graph`):
  2.5x faster alone, at the cost of a few more misread words (read back over
  14 voices, WER 0.033 against fp32's 0.018; research/listening/int8.md).
  Every line made ahead stays fp32. Each clip is kept under its own
  precision's key, and a sentence made both ways is said in fp32.
* **Three sentences at once** (2026-10-07). Speech is a language model choosing
  ~25 tokens per second of audio, one token at a time, and on a CPU each step
  is mostly reading the model's weights: stepping three sentences together
  costs little more than one. Measured on this laptop: 13 tokens/s alone, 27
  with three, faster than speech. A line's sentences are planned the moment
  it arrives (`plan`), made side by side, each joining as another finishes,
  and turned into audio on a second thread while the next ones are made. Each
  voice's conditioning, the same prefix before every sentence, is run through
  the model once, at load: 1.1 s per sentence saved. The browser asks for the
  sentences in order, as before; most are made by the time it asks.

The cast — who speaks for whom — is data (`voices/cast.json`), with each
voice's source, licence and credit (`voices/ATTRIBUTION.md`).
"""

from __future__ import annotations

import hashlib
import heapq
import io
import itertools
import json
import logging
import os
import queue
import re
import threading
import time
import wave
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import lexicon, notation, stream

log = logging.getLogger("uvicorn.error")

HERE = Path(__file__).resolve().parent
VOICES_DIR = HERE / "voices"
CAST_FILE = VOICES_DIR / "cast.json"
CACHE_DIR = Path(os.getenv("M11_TTS_CACHE") or HERE.parent / ".tts_cache")
#: Each cast voice's encoding (the speech encoder's outputs), kept between starts.
COND_CACHE = CACHE_DIR / "conds"

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
            if not fits and register is not None:
                # No voice of that accent and register (2026-10-11: the roster
                # kept after the team's listening test has no foreign man):
                # the register first — a man's voice for a man — the accent second.
                fits = sorted(
                    (v for v in self.voices.values() if v.register == register),
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
    temperature: float = 0.5,
    top_k: int = 1000,
    top_p: float = 0.95,
    repetition_penalty: float = 1.2,
) -> int:
    """The next speech token, as the PyTorch model samples it — not the model
    card's greedy argmax, which was measured speaking slower (onnx_speed.py).

    Temperature 0.5, not the model card's 0.8 (2026-10-11): 151 common Indian
    names said at each and read back by Whisper, 73 came back exactly at 0.5
    against 62 at 0.8 (107 against 91 within a letter or two). Below this the
    prosody flattens."""
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


#: Threads for the language model. ONNX Runtime's default is one per physical
#: core, and on a hybrid CPU (this laptop: 4 fast cores, 8 efficiency cores)
#: every operation is then split across the slow cores too and waits for them:
#: 7x slower than real time, measured 2026-10-07. With the decoder running
#: beside it (below), 4 and 4 measured best (research/listening/threads.md).
THREADS = int(os.getenv("M11_TTS_THREADS", "4"))


#: Where the int8 language model is kept once made: it is not in ResembleAI's
#: export, so M11 makes it from the fp32 one, once (`int8_graph`).
INT8_DIR = Path(os.getenv("M11_TTS_INT8_DIR") or HERE.parent / ".tts_models")


def int8_graph(fp32_path: str) -> str:
    """The language model with its weights in int8 (2026-10-09), made once.

    Dynamic quantization — weights int8, activations quantized as they come —
    runs on the CPU's int8 (VNNI) kernels: on this laptop's i7-1260P a
    sentence alone is made at 41.5 speech tokens a second against fp32's
    16.4, faster than speech (25), and three side by side at 56.6 against 35
    (research/listening/int8.md). ResembleAI's own 8-bit export runs 2 a
    second here, so this one is M11's."""
    # 7-bit weights (`reduce_range`) unless told otherwise. On a CPU without
    # VNNI (AVX2 only: e.g. an i5-10300H) onnxruntime's u8s8 int8 kernel
    # saturates with 8-bit weights, and the model speaks gibberish and never
    # emits its stop token (found 2026-10-11: a 3-word line ran to its 128-token
    # cap). The i7-1260P this was tuned on has VNNI and does not need it;
    # M11_TTS_INT8_REDUCE_RANGE=0 keeps 8-bit there.
    reduce = os.getenv("M11_TTS_INT8_REDUCE_RANGE", "1").lower() not in ("0", "false", "off")
    suffix = "_rr" if reduce else ""
    target = INT8_DIR / f"language_model_int8{suffix}.onnx"
    done = INT8_DIR / f"language_model_int8{suffix}.done"
    if target.exists() and done.exists():
        return str(target)
    from onnxruntime.quantization import QuantType, quantize_dynamic

    INT8_DIR.mkdir(parents=True, exist_ok=True)
    log.info("M11 TTS: making the int8 language model (once, ~40 s)")
    quantize_dynamic(
        fp32_path,
        str(target),
        weight_type=QuantType.QInt8,
        op_types_to_quantize=["MatMul"],
        per_channel=True,
        reduce_range=reduce,
        use_external_data_format=True,
        extra_options={"MatMulConstBOnly": True},
    )
    done.write_text(
        f"quantize_dynamic: MatMul weights int8, per channel, reduce_range={reduce}",
        encoding="utf-8",
    )
    return str(target)


def session_options(onnxruntime: Any, name: str) -> Any:
    """How each model runs: `THREADS` threads; the token lookup on one, idle
    rather than spinning, so it never takes cores from the language model."""
    options = onnxruntime.SessionOptions()
    if name == "embed_tokens":
        options.intra_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    elif name == "conditional_decoder" and DECODER_THREADS > 0:
        options.intra_op_num_threads = DECODER_THREADS
    elif THREADS > 0:
        options.intra_op_num_threads = THREADS
    return options


#: The DirectML device the decoder runs on, by index; unset keeps it on the CPU.
#: Measured on the dev laptop (2026-10-11): an NVIDIA GTX 1650 ran it at 0.12-0.19x
#: real time against 0.45-0.60 on the CPU, with the same sound (log-spectral
#: distance to the CPU's 0.57, CPU to itself 0.52). The integrated Intel GPU
#: (device 0) made no output at all. Needs the `onnxruntime-directml` package
#: in place of `onnxruntime`.
DECODER_DEVICE = os.getenv("M11_TTS_DECODER_DEVICE", "").strip()


def decoder_providers(available: list[str], device: str = "") -> list[Any] | None:
    """The decoder's execution providers when it is to run on a GPU, or None
    for the CPU as before. A device that is asked for but not there (the
    package is the CPU one, or the index is not a number) is the CPU, never a
    failure: the voice must not depend on a GPU."""
    if not device.isdigit() or "DmlExecutionProvider" not in available:
        return None
    return [("DmlExecutionProvider", {"device_id": int(device)}), "CPUExecutionProvider"]


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


def _samples_of(wav: bytes) -> Any:
    """A 16-bit WAV (`to_wav`'s) as float32 samples."""
    import numpy as np

    with wave.open(io.BytesIO(wav)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767


def _speech_of(tokens: list[int]) -> Any:
    """The codec tokens among a row's tokens so far, as the decoder is given
    them (a stop token and anything outside the codec are not speech)."""
    import numpy as np

    speech = np.array(tokens, dtype=np.int64)
    return speech[speech < START_SPEECH]


def _pad_right(value: Any, width: int) -> Any:
    """A cache tensor [batch, heads, length, dim] widened with zeros at the end."""
    import numpy as np

    pad = np.zeros(value.shape[:2] + (width - value.shape[2], value.shape[3]), dtype=value.dtype)
    return np.concatenate([value, pad], axis=2)


# ─────────────────────────────────────────────────────────────────────────
#  The engine
# ─────────────────────────────────────────────────────────────────────────

#: Sentences made at once. Measured on this laptop's CPU (2026-10-07,
#: research/listening/threads.md): 1 row 13 tokens/s, 2 rows 20, 3 rows 27,
#: then flat (6 rows 28) — so three. A bigger machine wants more.
ROWS = int(os.getenv("M11_TTS_ROWS", "3"))

#: Seconds of the voice's reference the decoder is given with every sentence.
#: It was all of it (10 s), re-read for each sentence: 3 s of a 5.8 s
#: sentence's decoding. 4 s cuts that by a third with the voice unchanged —
#: speaker-embedding similarity to the reference 0.894, against 0.900 with
#: 10 s and 0.522 for a different voice (threads.md, 2026-10-07).
DECODER_PROMPT_S = float(os.getenv("M11_TTS_DECODER_PROMPT_S", "4"))
#: Threads for the decoder, which runs beside the language model.
DECODER_THREADS = int(os.getenv("M11_TTS_DECODER_THREADS", "4"))


class EngineUnavailable(RuntimeError):
    """The server voice cannot speak right now; the browser voice should."""


class _Job:
    """One sentence to make, and the lines that want it."""

    def __init__(self, seq: int, key: str, text: str, voice: Voice) -> None:
        self.seq, self.key, self.text, self.voice = seq, key, text, voice
        #: The browser's line ids it belongs to; "*" is a caller with no line,
        #: who is never dropped.
        self.lines: set[str] = set()
        #: The first sentence of a planned line, made alone until its words are
        #: chosen (`plan` decides when that pays).
        self.lead = False
        #: A line the room expects to say, not one being said (2026-10-09),
        #: and how soon: 1 the likely next line, 2 a stock phrase.
        self.warm = False
        self.level = 0
        #: Made by the live (faster) model, and kept under its key.
        self.fast = False
        self.stored_as: str | None = None
        #: The row making it now (`speak_stream` reads its tokens as they come).
        self.row: _Row | None = None
        self.done = threading.Event()
        self.wav: bytes | None = None
        self.error: str | None = None

    def __lt__(self, other: _Job) -> bool:  # the queue: first planned, first made
        return self.seq < other.seq

    def result(self) -> bytes:
        self.done.wait()
        if self.wav is None:
            raise EngineUnavailable(self.error or "the sentence was not made")
        return self.wav


class _Row:
    """A sentence being made: its job, its speech tokens so far, and how many
    entries of the model's cache are its own (rows are padded on the right)."""

    def __init__(self, job: _Job, length: int, max_new: int) -> None:
        self.job, self.length, self.max_new = job, length, max_new
        self.tokens: list[int] = []


class Engine:
    """Loads once in the background; then speaks, three sentences at a time."""

    def __init__(self, cast: Cast, precision: str | None = None) -> None:
        self.cast = cast
        self.precision = precision or os.getenv("M11_TTS_PRECISION", "fp32")
        #: The model for live lines (2026-10-09); none when it is the same one.
        live = os.getenv("M11_TTS_LIVE_PRECISION", "int8")
        self.live_precision = live if live and live != self.precision else None
        self.state = "off"
        self.reason = "not started"
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._conds: dict[str, tuple] = {}
        self._sessions: dict[str, Any] = {}
        self._tokenizer: Any = None
        self._rng: Any = None
        # Parallel making (2026-10-07): the queue, what is being made, and the
        # model's cache of each voice's conditioning.
        self._jobs = threading.Condition()
        self._queue: list[_Job] = []
        #: Warm sentences: made only while no live one waits or is being made.
        #: (level, seq, job): the likely next line first, in the order asked.
        self._warm: list[tuple[int, int, _Job]] = []
        self._inflight: dict[str, _Job] = {}
        self._seq = itertools.count()
        # Finished rows wait here in speaking order, not finishing order: a short
        # second sentence must not be decoded before the first. Live before warm.
        self._decode: queue.PriorityQueue[tuple[bool, int, int, _Row]] = queue.PriorityQueue()
        self._prefix: dict[str, dict[str, Any]] = {}
        self._prefix_live: dict[str, dict[str, Any]] = {}
        self._parallel = False
        #: Live sentences in the language model right now (its thread's count).
        self._live_rows = 0
        self._kv: list[tuple[str, Any]] = []
        #: DirectML sessions do not take two Run calls at once (a segfault, seen
        #: 2026-10-11 with a streamed piece and a whole sentence together): one
        #: at a time on the GPU. The CPU decoder runs freely, as before.
        self._decoder_lock = threading.Lock()

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
                if dtype == "int8":
                    return int8_graph(graph(name, "fp32"))
                suffix = "" if dtype == "fp32" else "_quantized" if dtype == "q8" else f"_{dtype}"
                path = hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx")
                hf_hub_download(MODEL_ID, subfolder="onnx", filename=f"{name}{suffix}.onnx_data")
                return path

            for name in ("embed_tokens", "language_model", "conditional_decoder"):
                dtype = self.precision if name == "language_model" else "fp32"
                providers = (
                    decoder_providers(onnxruntime.get_available_providers(), DECODER_DEVICE)
                    if name == "conditional_decoder"
                    else None
                )
                if providers:
                    try:
                        options = onnxruntime.SessionOptions()
                        options.enable_mem_pattern = False  # DirectML's requirement
                        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
                        # Part of the graph stays on the CPU beside the model's
                        # threads: few of them, and idle rather than spinning,
                        # or the two starve each other (measured 2026-10-11:
                        # a 0.3 s decode took 2.5 s while the model ran).
                        if DECODER_THREADS > 0:
                            options.intra_op_num_threads = DECODER_THREADS
                        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
                        self._sessions[name] = onnxruntime.InferenceSession(
                            graph(name, dtype), options, providers=providers
                        )
                        log.info("M11 TTS decoder on DirectML device %s", DECODER_DEVICE)
                        continue
                    except Exception as exc:  # noqa: BLE001 - the CPU is always there
                        log.warning("M11 TTS decoder: GPU not used (%s); on the CPU", exc)
                self._sessions[name] = onnxruntime.InferenceSession(
                    graph(name, dtype), session_options(onnxruntime, name)
                )
            if self.live_precision:
                self._sessions["language_model_live"] = onnxruntime.InferenceSession(
                    graph("language_model", self.live_precision),
                    session_options(onnxruntime, "language_model"),
                )
            self._tokenizer = Tokenizer.from_file(hf_hub_download(MODEL_ID, "tokenizer.json"))
            self._rng = np.random.default_rng()
            t_models = time.perf_counter()
            encoder = graph("speech_encoder", "fp32")
            for voice in self.cast.voices.values():
                # A voice's encoding is kept (2026-10-11: encoding all 14 at
                # each start was 22 s of the 62 before M11 could speak); the
                # encoder is loaded only for a voice not kept, or changed.
                kept = COND_CACHE / f"{voice.key}.npz"
                stat = voice.file.stat()
                revision = Path(encoder).parent.parent.name
                made_from = (
                    ENGINE_VERSION,
                    revision,
                    stat.st_size,
                    stat.st_mtime_ns,
                    DECODER_PROMPT_S,
                )
                meta = "|".join(map(str, made_from))
                try:
                    with np.load(kept) as z:
                        if str(z["meta"]) == meta:
                            self._conds[voice.key] = tuple(
                                z[name] for name in ("cond", "prompt", "spk_emb", "spk_feat")
                            )
                            continue
                except (OSError, KeyError, ValueError):
                    pass
                if "speech_encoder" not in self._sessions:
                    self._sessions["speech_encoder"] = onnxruntime.InferenceSession(
                        encoder, session_options(onnxruntime, "speech_encoder")
                    )
                audio, rate = soundfile.read(voice.file, dtype="float32")
                if rate != SAMPLE_RATE:
                    raise ValueError(
                        f"{voice.file.name} is {rate} Hz; voices are stored at {SAMPLE_RATE}"
                    )
                audio = audio[: SAMPLE_RATE * 15][np.newaxis, :].astype(np.float32)
                cond, prompt, spk_emb, spk_feat = self._sessions["speech_encoder"].run(
                    None, {"audio_values": audio}
                )
                # The decoder's share of the reference: its last DECODER_PROMPT_S
                # seconds (25 speech tokens and 50 mel frames a second).
                keep = max(1, int(DECODER_PROMPT_S * 25))
                self._conds[voice.key] = (
                    cond,
                    prompt[:, -keep:],
                    spk_emb,
                    spk_feat[:, -2 * keep :],
                )
                try:
                    COND_CACHE.mkdir(parents=True, exist_ok=True)
                    c, pr, se, sf = self._conds[voice.key]
                    np.savez(kept, meta=np.array(meta), cond=c, prompt=pr, spk_emb=se, spk_feat=sf)
                except OSError as exc:
                    log.info("M11 voice encoding not kept: %s", exc)
            t_voices = time.perf_counter()
            self._begin()
            # Where the load's time goes (2026-10-11: ~85 s, and a mock begun
            # before it ended opened in the browser's voice).
            log.info(
                "M11 TTS load: models %.1fs, %d voices %.1fs (%s)",
                t_models - t0,
                len(self._conds),
                t_voices - t_models,
                "some encoded" if "speech_encoder" in self._sessions else "all kept",
            )
            live = f" (live lines {self.live_precision})" if self._live else ""
            self.state, self.reason = "ready", f"{len(self._conds)} voices, {self.precision}{live}"
            log.info("M11 TTS ready in %.0fs: %s", time.perf_counter() - t0, self.reason)
        except Exception as exc:  # noqa: BLE001 - a failed load is a state, not a crash
            self.state, self.reason = "failed", f"{type(exc).__name__}: {exc}"
            log.warning("M11 TTS failed to load: %s", self.reason)

    def _begin(self) -> None:
        """With the models loaded: each voice's conditioning run once, and the
        two threads that make speech started."""
        import numpy as np

        lm = self._sessions["language_model"]
        self._kv = [
            (x.name, np.float16 if x.type == "tensor(float16)" else np.float32)
            for x in lm.get_inputs()
            if "past_key_values" in x.name
        ]
        # Every sentence starts with its voice's conditioning, run once
        # through each language model — by the language model's own thread
        # (`_prefix_for`): while nobody is waiting yet, or when the voice's
        # first sentence starts. Run here for every voice it was 14 s of the
        # 62 before M11 could speak (2026-10-11).
        self._parallel = True
        self._warm_decoder()
        threading.Thread(target=self._make_loop, name="m11-tts-make", daemon=True).start()
        threading.Thread(target=self._decode_loop, name="m11-tts-decode", daemon=True).start()

    def _run_decoder(self, tokens: Any, spk_emb: Any, spk_feat: Any) -> Any:
        """The decoder's output for these tokens, one call at a time when it is
        on a GPU (`_decoder_lock`)."""
        decoder = self._sessions["conditional_decoder"]
        feed = dict(speech_tokens=tokens, speaker_embeddings=spk_emb, speaker_features=spk_feat)
        if "DmlExecutionProvider" in getattr(decoder, "get_providers", lambda: [])():
            with self._decoder_lock:
                return decoder.run(None, feed)[0]
        return decoder.run(None, feed)[0]

    def _warm_decoder(self) -> None:
        """Run the decoder once on each shape a streamed piece has (the first
        piece, and a middle one with its context and look-ahead), so a GPU's
        compile for them is paid here and not in a student's first sentence.
        Not for the CPU, which has nothing to compile."""
        import numpy as np

        decoder = self._sessions.get("conditional_decoder")
        providers = getattr(decoder, "get_providers", lambda: [])()
        if "DmlExecutionProvider" not in providers:
            return
        key = next(iter(self._conds), None)
        if key is None:
            return
        _, prompt, spk_emb, spk_feat = self._conds[key]
        t0 = time.perf_counter()
        for n in (stream.CHUNK + stream.LOOK, stream.CONTEXT + stream.CHUNK + stream.LOOK):
            speech = np.full((1, n), START_SPEECH - 1, dtype=np.int64)
            tokens = np.concatenate(
                [prompt, speech, np.full((1, 3), SILENCE_TOKEN, dtype=np.int64)], axis=1
            )
            try:
                self._run_decoder(tokens, spk_emb, spk_feat)
            except Exception as exc:  # noqa: BLE001 - warm-up is a courtesy
                log.info("M11 TTS decoder warm-up skipped: %s", exc)
                return
        log.info("M11 TTS decoder warmed in %.1fs", time.perf_counter() - t0)

    # ── speaking ─────────────────────────────────────────────────────────

    @property
    def _live(self) -> bool:
        """A second, faster model is loaded for live lines."""
        return "language_model_live" in self._sessions

    def cache_key(self, text: str, voice: Voice, precision: str | None = None) -> str:
        return hashlib.sha1(
            f"{ENGINE_VERSION}|{precision or self.precision}|{voice.key}|{text}".encode()
        ).hexdigest()

    def cached(self, text: str, voice: Voice) -> bytes | None:
        hit = self.cached_keyed(text, voice)
        return hit[0] if hit else None

    def cached_keyed(self, text: str, voice: Voice) -> tuple[bytes, str] | None:
        """The sentence's audio and the key it is kept under — the one made
        ahead (the main model) before one made live."""
        precisions = [self.precision, *([self.live_precision] if self.live_precision else [])]
        for precision in precisions:
            key = self.cache_key(text, voice, precision)
            if key in self._memory:
                self._memory.move_to_end(key)
                return self._memory[key], key
            path = CACHE_DIR / voice.key / f"{key}.wav"
            if path.exists():
                data = path.read_bytes()
                self._remember(key, data)
                return data, key
        return None

    def audio_by_key(self, key: str) -> bytes | None:
        """A sentence's audio by its cache key, wherever it is kept — what
        the face's frames (`face.py`) are made from."""
        if key in self._memory:
            return self._memory[key]
        for path in CACHE_DIR.glob(f"*/{key}.wav"):
            return path.read_bytes()
        return None

    def _remember(self, key: str, data: bytes) -> None:
        self._memory[key] = data
        self._memory.move_to_end(key)
        while len(self._memory) > 256:
            self._memory.popitem(last=False)

    @staticmethod
    def prepare(text: str, voice: Voice) -> str:
        """The words as the voice will say them. Notation no voice can read,
        in words (`notation.py`), then words the voices get wrong, respelled
        (EC-11.11, `lexicon.py`) — before the cache, so a fixed word is a new
        line, not the old one."""
        return punc_norm(lexicon.apply(notation.say(text), voice.key))

    def plan(
        self, sentences: list[tuple[str, Voice]], line: str, priority: str = "live"
    ) -> tuple[int, list[bool]]:
        """Start making a line's sentences now, in order, without waiting for
        any of them; `speak` collects each. Returns how many were new, and
        which of the sentences were made already. A `next` or `warm` line is
        one the room expects to say: made only while no live line waits —
        `next` (the likely next line) before `warm` (a stock phrase)."""
        level = {"next": 1, "warm": 2}.get(priority, 0)
        warm = level > 0
        pieces = [(self.prepare(raw, voice), voice) for raw, voice in sentences]
        ready = [bool(text) and self.cached(text, voice) is not None for text, voice in pieces]
        if not self._parallel or self.state != "ready":
            return 0, ready
        todo = [
            (text, voice)
            for (text, voice), made in zip(pieces, ready, strict=True)
            if text and not made
        ]
        # The first sentence alone gets its audio sooner (two more rows slow
        # each of its steps by ~40%), and the rest start the moment its words
        # are chosen. That pays when the next piece can still be made while the
        # first is decoded and heard: measured, when it is at most half as long
        # (threads.md). Otherwise all start together.
        lead = False
        if todo and pieces and todo[0][0] == pieces[0][0] and not warm:
            following = todo[1][0] if len(todo) > 1 else ""
            lead = len(following) <= len(todo[0][0]) / 2
        made = 0
        for i, (text, voice) in enumerate(todo):
            made += self._enqueue(text, voice, line, lead=lead and i == 0, level=level)[1]
        return made, ready

    def drop(self, lines: list[str]) -> int:
        """The browser stopped these lines (a barge-in, a repeat): their
        sentences not yet started are not made. Started ones finish, cached."""
        wanted = set(lines)
        dropped: list[_Job] = []
        with self._jobs:
            for job in self._queue:
                job.lines -= wanted
                if not job.lines:
                    dropped.append(job)
            if dropped:
                self._queue = [job for job in self._queue if job.lines]
                heapq.heapify(self._queue)
            gone = []
            for _, _, job in self._warm:
                job.lines -= wanted
                if not job.lines:
                    gone.append(job)
            if gone:
                self._warm = [entry for entry in self._warm if entry[2].lines]
                heapq.heapify(self._warm)
                dropped += gone
            for job in dropped:
                self._inflight.pop(job.key, None)
        for job in dropped:
            job.error = "dropped"
            job.done.set()
        return len(dropped)

    def speak(self, text: str, voice: Voice, line: str | None = None) -> tuple[bytes, bool, int]:
        """(wav, from_cache, ms). Raises EngineUnavailable when it cannot."""
        data, cached, ms, _ = self.speak_keyed(text, voice, line)
        return data, cached, ms

    def speak_keyed(
        self, text: str, voice: Voice, line: str | None = None
    ) -> tuple[bytes, bool, int, str]:
        """`speak`, and the key the audio is kept under — what its face's
        frames are named by, since one sentence may be kept twice (made ahead,
        and made live)."""
        text = self.prepare(text, voice)
        if not text:
            raise ValueError("nothing to say")
        hit = self.cached_keyed(text, voice)
        if hit is not None:
            return hit[0], True, 0, hit[1]
        if self.state != "ready":
            raise EngineUnavailable(self.reason)
        t0 = time.perf_counter()
        if self._parallel:
            job, _ = self._enqueue(text, voice, line or "*")
            wav = job.result()
            return wav, False, round((time.perf_counter() - t0) * 1000), job.stored_as or job.key
        # No parallel making (a fake engine in tests): one at a time, here.
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
        return data, False, round((time.perf_counter() - t0) * 1000), key


    def speak_stream(self, text: str, voice: Voice, line: str | None = None):
        """The sentence as float32 pieces, the first one as soon as a second
        of it is chosen, not when it is whole (`stream.py`). Yields
        `(samples, key)`: `key` is what the face's frames are named by.

        What was made already is one piece. A sentence still waiting, or one
        the model has not started, is waited for as `speak` waits; a decoder
        output that fits no layout (`stream.speech_of`) ends the streaming and
        the rest comes from the sentence's own whole decoding — never silence,
        never a sentence made twice for the student. Raises
        `EngineUnavailable` as `speak` does."""
        import numpy as np

        text = self.prepare(text, voice)
        if not text:
            raise ValueError("nothing to say")
        hit = self.cached_keyed(text, voice)
        if hit is not None:
            yield _samples_of(hit[0]), hit[1]
            return
        if self.state != "ready":
            raise EngineUnavailable(self.reason)
        if not self._parallel:  # no parallel making (a fake engine): whole
            data, _, _, key = self.speak_keyed(text, voice, line)
            yield _samples_of(data), key
            return
        job, _ = self._enqueue(text, voice, line or "*")
        stitch = stream.Stitcher()
        done = 0  # tokens decoded and passed on
        row = None
        streaming = True
        held: list[Any] = []  # pieces waiting until playing them cannot run dry
        released = False
        seen_at = seen_n = None  # when the row was first seen, and its tokens then
        ratio = 0.0  # decoder seconds per second of speech: best of the pieces so far
        ratios: list[float] = []
        total = stream.estimate_tokens(text)
        while not job.done.is_set():
            if streaming and job.row is not None and not job.warm:
                if row is not None and job.row is not row:
                    # Remade (a warm row that made way): its tokens are another
                    # draw. What was played stands; the rest is the new whole.
                    log.warning("M11 TTS stream: %r restarted after %d tokens", text[:40], done)
                    streaming = False
                    continue
                row = job.row
                speech = _speech_of(list(row.tokens))
                now = time.perf_counter()
                if seen_at is None:
                    seen_at, seen_n = now, len(speech)
                rate = (len(speech) - seen_n) / (now - seen_at) if now - seen_at > 0.5 else 0.0
                if not released and not stream.worth_streaming(rate, ratio):
                    # Too slow, in the model or in the decoder, for a buffer
                    # to help: stop spending CPU on pieces; the sentence is
                    # played whole, as `speak` does. Never after playing has
                    # begun: the buffer was promised, and it is kept.
                    streaming = False
                    continue
                for start, end in stream.spans(done, len(speech)):
                    t_piece = time.perf_counter()
                    try:
                        piece = self._decode_span(voice, speech, start, end)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("M11 TTS stream stopped: %s", exc)
                        streaming = False
                        break
                    ratios.append(
                        (time.perf_counter() - t_piece) / ((end - start) / stream.PLAY_RATE)
                    )
                    # What a middle piece costs, not the first: the first has
                    # no left context and is cheap (0.33 s against 2.5 s for
                    # the next on the dev laptop, with the model running), so
                    # judging by it lets playback start and then run dry. The
                    # best of the middle ones, since a decoder compiles each
                    # new shape on its first use. None until one is made.
                    ratio = min(ratios[1:]) if len(ratios) >= 2 else 0.0
                    out = stitch.push(piece)
                    done = end
                    if out.size:
                        held.append(out)
                if held and not released and ratio > 0:
                    # A model slower than speech would make the student hear a
                    # second, then wait: so wait first, once, for as much as
                    # the rest of the sentence needs (`stream.ready_to_play`).
                    total = stream.estimate_tokens(text, len(speech))
                    released = stream.ready_to_play(
                        done, stream.throughput(rate, ratio), total
                    )
                if held and released:
                    for out in held:
                        yield out, job.stored_as or self._key_for(job)
                    held.clear()
            job.done.wait(0.03)
        data = job.result()  # raises EngineUnavailable if it could not be made
        whole = _samples_of(data)
        rest = whole[done * stream.SAMPLES_PER_TOKEN :] if done else whole
        out = stitch.push(rest, last=True) if done else rest
        key = job.stored_as or self._key_for(job)
        for piece in held:  # made whole before the buffer rule let them go
            yield piece, key
        if out.size:
            yield np.asarray(out, dtype=np.float32), key

    def _key_for(self, job: _Job) -> str:
        precision = self.live_precision if job.fast and self._live else self.precision
        return self.cache_key(job.text, job.voice, precision)

    def _decode_span(self, voice: Voice, speech: Any, start: int, end: int) -> Any:
        """Samples for tokens [start, end) and `FADE` more, decoded with the
        tokens either side (`stream.py`)."""
        import numpy as np

        lo = max(0, start - stream.CONTEXT)
        hi = min(len(speech), end + stream.LOOK)
        _, prompt, spk_emb, spk_feat = self._conds[voice.key]
        tokens = np.concatenate(
            [prompt, speech[np.newaxis, lo:hi], np.full((1, 3), SILENCE_TOKEN, dtype=np.int64)],
            axis=1,
        )
        wav = self._run_decoder(tokens, spk_emb, spk_feat).squeeze(axis=0)
        sound = stream.speech_of(wav, prompt.shape[1], hi - lo)
        s = stream.SAMPLES_PER_TOKEN
        piece = sound[(start - lo) * s : (end - lo) * s + stream.FADE]
        return self._watermark(piece)

    # ── making, in parallel ──────────────────────────────────────────────

    def _enqueue(
        self, text: str, voice: Voice, line: str, lead: bool = False, level: int = 0
    ) -> tuple[_Job, bool]:
        """The job for this sentence: the one already planned, or a new one. A
        warm one asked for live is promoted: it is being waited for now. One
        asked for again as warm moves up, to the level and recency asked."""
        key = self.cache_key(text, voice)
        with self._jobs:
            job = self._inflight.get(key)
            if job is not None:
                job.lines.add(line)
                waiting = next((entry for entry in self._warm if entry[2] is job), None)
                if job.warm and level == 0:
                    job.warm, job.level = False, 0
                    if waiting is not None:
                        job.fast = self._live
                        self._warm.remove(waiting)
                        heapq.heapify(self._warm)
                        heapq.heappush(self._queue, job)
                        self._jobs.notify()
                elif job.warm and waiting is not None:
                    self._warm.remove(waiting)
                    job.level = min(job.level, level)
                    heapq.heappush(self._warm, (job.level, job.seq, job))
                    heapq.heapify(self._warm)
                return job, False
            job = _Job(next(self._seq), key, text, voice)
            job.lead = lead
            job.warm, job.level = level > 0, level
            # Live: the faster model, when there is one (made ahead: the main).
            job.fast = self._live and level == 0
            job.lines.add(line)
            self._inflight[key] = job
            if job.warm:
                heapq.heappush(self._warm, (level, job.seq, job))
            else:
                heapq.heappush(self._queue, job)
            self._jobs.notify()
            return job, True

    def _empty(self, batch: int) -> dict[str, Any]:
        import numpy as np

        return {
            name: np.zeros([batch, NUM_KV_HEADS, 0, HEAD_DIM], dtype=dt) for name, dt in self._kv
        }

    def _run_lm(
        self, embeds: Any, past: dict[str, Any], mask: Any, pos: Any, fast: bool = False
    ) -> tuple[Any, dict[str, Any]]:
        name = "language_model_live" if fast and self._live else "language_model"
        logits, *present = self._sessions[name].run(
            None, dict(inputs_embeds=embeds, attention_mask=mask, position_ids=pos, **past)
        )
        return logits, {name: value for (name, _), value in zip(self._kv, present, strict=True)}

    def _make_loop(self) -> None:
        """The language model's thread: up to ROWS sentences stepped together.

        The model's attention (onnxruntime's GroupQueryAttention) reads each
        row's length from the mask and its cache from the start of the row,
        so rows of different lengths share a batch padded on the RIGHT — the
        same logits as alone, checked to the last digit (threads.md)."""
        rows: list[_Row] = []
        kv: dict[str, Any] = {}
        # Each voice's conditioning while nobody is waiting yet; a voice asked
        # for sooner is run when its sentence starts.
        for key in list(self._conds):
            if self._queue or self._warm:
                break
            self._prefix_for(key, False)
            if self._live:
                self._prefix_for(key, True)
        while True:
            with self._jobs:
                while not rows and not self._queue and not self._warm:
                    self._jobs.wait()
                joining = []
                # A live sentence waiting: warm rows make way (they start again
                # later) — the student is waiting for this one, not for them —
                # and so does a live one still on the slow model (promoted from
                # warm mid-making): it starts again on the fast one.
                evict = []
                if self._queue:
                    for b, row in enumerate(rows):
                        job = row.job
                        if job.warm:
                            evict.append(b)
                            if not job.done.is_set():
                                heapq.heappush(self._warm, (job.level, job.seq, job))
                        elif self._live and not job.fast:
                            evict.append(b)
                            job.fast = True
                            heapq.heappush(self._queue, job)
                staying = [row for b, row in enumerate(rows) if b not in evict]
                # A line's first sentence is made alone: two more rows would
                # slow each of its steps by ~40%, and it is the one the student
                # is waiting for. The rest join the moment its words are chosen,
                # and its decoding runs beside them.
                leading = any(row.job.lead for row in staying)
                while self._queue and len(staying) + len(joining) < ROWS and not leading:
                    job = heapq.heappop(self._queue)
                    joining.append(job)
                    if job.lead:
                        leading = True
                        break
                # Warm sentences only while nothing live waits or is being made.
                if not self._queue and not joining and all(row.job.warm for row in staying):
                    while self._warm and len(staying) + len(joining) < ROWS:
                        joining.append(heapq.heappop(self._warm)[2])
            # What the decoder reads to keep warm work out of a live line's way.
            self._live_rows = sum(not job.warm for job in joining) + sum(
                not row.job.warm for b, row in enumerate(rows) if b not in evict
            )
            try:
                if evict:
                    kv = self._without(kv, rows, evict)
                for job in joining:
                    kv = self._join(kv, rows, job)
                if rows:
                    kv = self._step(kv, rows)
            except Exception as exc:  # noqa: BLE001 - a failed step fails its sentences, not the thread
                log.warning("M11 TTS step failed: %s", exc)
                for job in [row.job for row in rows] + joining:
                    self._fail(job, f"{type(exc).__name__}: {exc}")
                rows, kv = [], {}

    def _prefix_for(self, key: str, fast: bool) -> dict[str, Any]:
        """A voice's conditioning through a language model: run the first time
        it is needed, then kept. Only the language model's thread calls it."""
        import numpy as np

        store = self._prefix_live if fast and self._live else self._prefix
        if key not in store:
            cond = self._conds[key][0]
            n = cond.shape[1]
            mask, pos = np.ones((1, n), np.int64), np.arange(n)[np.newaxis, :]
            store[key] = self._run_lm(cond, self._empty(1), mask, pos, fast)[1]
        return store[key]

    def _without(self, kv: dict[str, Any], rows: list[_Row], gone: list[int]) -> dict[str, Any]:
        """Rows taken out of the batch (warm ones, making way); the cache keeps
        the rest, as when rows finish."""
        keep = [b for b in range(len(rows)) if b not in gone]
        rows[:] = [rows[b] for b in keep]
        if not rows:
            return {}
        longest = max(row.length for row in rows)
        return {name: value[keep][:, :, :longest] for name, value in kv.items()}

    def _join(self, kv: dict[str, Any], rows: list[_Row], job: _Job) -> dict[str, Any]:
        """Start a sentence on its voice's cached conditioning and add its row."""
        import numpy as np

        if job.done.is_set():
            return kv
        fast = job.fast and self._live
        prefix = self._prefix_for(job.voice.key, fast)
        start = next(iter(prefix.values())).shape[2]
        ids = np.array([self._tokenizer.encode(job.text).ids], dtype=np.int64)
        embeds = self._sessions["embed_tokens"].run(None, {"input_ids": ids})[0]
        n = start + ids.shape[1]
        logits, own = self._run_lm(
            embeds, prefix, np.ones((1, n), np.int64), np.arange(start, n)[np.newaxis, :], fast
        )
        row = _Row(job, length=n, max_new=min(1000, 60 + len(job.text) * 4))
        job.row = row
        row.tokens.append(sample_next(logits[:, -1, :], np.array([], dtype=np.int64), self._rng))
        if row.tokens[-1] == STOP_SPEECH:
            self._decode.put((job.warm, job.seq, id(row), row))
            return kv
        rows.append(row)
        if len(rows) == 1:
            return own
        width = next(iter(kv.values())).shape[2]
        if n < width:
            own = {name: _pad_right(value, width) for name, value in own.items()}
        elif n > width:
            kv = {name: _pad_right(value, n) for name, value in kv.items()}
        return {name: np.concatenate([kv[name], own[name]], axis=0) for name in kv}

    def _step(self, kv: dict[str, Any], rows: list[_Row]) -> dict[str, Any]:
        """One token for every row; finished rows go to the decoder."""
        import numpy as np

        width = next(iter(kv.values())).shape[2]
        ids = np.array([[row.tokens[-1]] for row in rows], dtype=np.int64)
        embeds = self._sessions["embed_tokens"].run(None, {"input_ids": ids})[0]
        mask = np.zeros((len(rows), width + 1), dtype=np.int64)
        for b, row in enumerate(rows):
            mask[b, : row.length + 1] = 1
        pos = np.array([[row.length] for row in rows], dtype=np.int64)
        # A batch is all one model: live rows never share it with warm ones.
        logits, kv = self._run_lm(embeds, kv, mask, pos, rows[0].job.fast)
        finished = []
        for b, row in enumerate(rows):
            row.length += 1
            said = np.array(row.tokens, dtype=np.int64)
            row.tokens.append(sample_next(logits[b : b + 1, -1, :], said, self._rng))
            if row.tokens[-1] == STOP_SPEECH or len(row.tokens) >= row.max_new:
                finished.append(b)
        if not finished:
            return kv
        for b in finished:
            self._decode.put((rows[b].job.warm, rows[b].job.seq, id(rows[b]), rows[b]))
        keep = [b for b in range(len(rows)) if b not in finished]
        rows[:] = [rows[b] for b in keep]
        if not rows:
            return {}
        # The cache keeps only what the longest remaining row needs.
        longest = max(row.length for row in rows)
        return {name: value[keep][:, :, :longest] for name, value in kv.items()}

    def _decode_loop(self) -> None:
        """The decoder's thread: a finished sentence's tokens to audio, while
        the language model makes the next ones."""
        import numpy as np

        while True:
            item = self._decode.get()
            *_, row = item
            job = row.job
            if job.warm and (self._queue or self._live_rows):
                # A live sentence is being made: its decoding must not wait
                # behind a warm one, nor share the CPU with it (2026-10-09).
                self._decode.put(item)
                time.sleep(0.05)
                continue
            try:
                speech = np.array(row.tokens, dtype=np.int64)
                if speech.size and speech[-1] == STOP_SPEECH:
                    speech = speech[:-1]
                speech = speech[speech < START_SPEECH]  # drop anything outside the codec
                _, prompt, spk_emb, spk_feat = self._conds[job.voice.key]
                tokens = np.concatenate(
                    [
                        prompt,
                        speech[np.newaxis, :],
                        np.full((1, 3), SILENCE_TOKEN, dtype=np.int64),
                    ],
                    axis=1,
                )
                wav = self._run_decoder(tokens, spk_emb, spk_feat).squeeze(axis=0)
                self._finish(job, to_wav(self._watermark(wav)))
            except Exception as exc:  # noqa: BLE001
                self._fail(job, f"{type(exc).__name__}: {exc}")

    def _finish(self, job: _Job, data: bytes) -> None:
        # Kept under the key of the model that made it.
        precision = self.live_precision if job.fast and self._live else self.precision
        stored = self.cache_key(job.text, job.voice, precision)
        job.stored_as = stored
        self._remember(stored, data)
        try:
            (CACHE_DIR / job.voice.key).mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / job.voice.key / f"{stored}.wav").write_bytes(data)
        except OSError as exc:
            log.info("M11 TTS cache not written: %s", exc)
        with self._jobs:
            self._inflight.pop(job.key, None)
        job.wav = data
        job.done.set()

    def _fail(self, job: _Job, reason: str) -> None:
        with self._jobs:
            self._inflight.pop(job.key, None)
        job.error = reason
        job.done.set()

    # ── the reference: one sentence alone (tests' fakes replace it) ───────

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
