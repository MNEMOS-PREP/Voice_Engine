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

from . import lexicon, notation

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


#: Threads for the language model. ONNX Runtime's default is one per physical
#: core, and on a hybrid CPU (this laptop: 4 fast cores, 8 efficiency cores)
#: every operation is then split across the slow cores too and waits for them:
#: 7x slower than real time, measured 2026-10-07. With the decoder running
#: beside it (below), 4 and 4 measured best (research/listening/threads.md).
THREADS = int(os.getenv("M11_TTS_THREADS", "4"))


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
        self._inflight: dict[str, _Job] = {}
        self._seq = itertools.count()
        # Finished rows wait here in speaking order, not finishing order: a short
        # second sentence must not be decoded before the first.
        self._decode: queue.PriorityQueue[tuple[int, int, _Row]] = queue.PriorityQueue()
        self._prefix: dict[str, dict[str, Any]] = {}
        self._kv: list[tuple[str, Any]] = []

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
                self._sessions[name] = onnxruntime.InferenceSession(
                    graph(name, dtype), session_options(onnxruntime, name)
                )
            self._tokenizer = Tokenizer.from_file(hf_hub_download(MODEL_ID, "tokenizer.json"))
            self._rng = np.random.default_rng()
            for voice in self.cast.voices.values():
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
            self._begin()
            self.state, self.reason = "ready", f"{len(self._conds)} voices, {self.precision}"
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
        # Every sentence starts with its voice's conditioning: run it once.
        for key, (cond, *_) in self._conds.items():
            n = cond.shape[1]
            self._prefix[key] = self._run_lm(
                cond, self._empty(1), np.ones((1, n), np.int64), np.arange(n)[np.newaxis, :]
            )[1]
        threading.Thread(target=self._make_loop, name="m11-tts-make", daemon=True).start()
        threading.Thread(target=self._decode_loop, name="m11-tts-decode", daemon=True).start()

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

    @staticmethod
    def prepare(text: str, voice: Voice) -> str:
        """The words as the voice will say them. Notation no voice can read,
        in words (`notation.py`), then words the voices get wrong, respelled
        (EC-11.11, `lexicon.py`) — before the cache, so a fixed word is a new
        line, not the old one."""
        return punc_norm(lexicon.apply(notation.say(text), voice.key))

    def plan(self, sentences: list[tuple[str, Voice]], line: str) -> int:
        """Start making a line's sentences now, in order, without waiting for
        any of them; `speak` collects each. Returns how many were new."""
        if not self._prefix or self.state != "ready":
            return 0
        pieces = [(self.prepare(raw, voice), voice) for raw, voice in sentences]
        todo = [
            (text, voice) for text, voice in pieces if text and self.cached(text, voice) is None
        ]
        # The first sentence alone gets its audio sooner (two more rows slow
        # each of its steps by ~40%), and the rest start the moment its words
        # are chosen. That pays when the next piece can still be made while the
        # first is decoded and heard: measured, when it is at most half as long
        # (threads.md). Otherwise all start together.
        lead = False
        if todo and pieces and todo[0][0] == pieces[0][0]:
            following = todo[1][0] if len(todo) > 1 else ""
            lead = len(following) <= len(todo[0][0]) / 2
        made = 0
        for i, (text, voice) in enumerate(todo):
            made += self._enqueue(text, voice, line, lead=lead and i == 0)[1]
        return made

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
                for job in dropped:
                    self._inflight.pop(job.key, None)
        for job in dropped:
            job.error = "dropped"
            job.done.set()
        return len(dropped)

    def speak(self, text: str, voice: Voice, line: str | None = None) -> tuple[bytes, bool, int]:
        """(wav, from_cache, ms). Raises EngineUnavailable when it cannot."""
        text = self.prepare(text, voice)
        if not text:
            raise ValueError("nothing to say")
        hit = self.cached(text, voice)
        if hit is not None:
            return hit, True, 0
        if self.state != "ready":
            raise EngineUnavailable(self.reason)
        t0 = time.perf_counter()
        if self._prefix:
            job, _ = self._enqueue(text, voice, line or "*")
            return job.result(), False, round((time.perf_counter() - t0) * 1000)
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
        return data, False, round((time.perf_counter() - t0) * 1000)

    # ── making, in parallel ──────────────────────────────────────────────

    def _enqueue(
        self, text: str, voice: Voice, line: str, lead: bool = False
    ) -> tuple[_Job, bool]:
        """The job for this sentence: the one already planned, or a new one."""
        key = self.cache_key(text, voice)
        with self._jobs:
            job = self._inflight.get(key)
            if job is not None:
                job.lines.add(line)
                return job, False
            job = _Job(next(self._seq), key, text, voice)
            job.lead = lead
            job.lines.add(line)
            self._inflight[key] = job
            heapq.heappush(self._queue, job)
            self._jobs.notify()
            return job, True

    def _empty(self, batch: int) -> dict[str, Any]:
        import numpy as np

        return {
            name: np.zeros([batch, NUM_KV_HEADS, 0, HEAD_DIM], dtype=dt) for name, dt in self._kv
        }

    def _run_lm(
        self, embeds: Any, past: dict[str, Any], mask: Any, pos: Any
    ) -> tuple[Any, dict[str, Any]]:
        logits, *present = self._sessions["language_model"].run(
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
        while True:
            with self._jobs:
                while not rows and not self._queue:
                    self._jobs.wait()
                joining = []
                # A line's first sentence is made alone: two more rows would
                # slow each of its steps by ~40%, and it is the one the student
                # is waiting for. The rest join the moment its words are chosen,
                # and its decoding runs beside them.
                leading = any(row.job.lead for row in rows)
                while self._queue and len(rows) + len(joining) < ROWS and not leading:
                    job = heapq.heappop(self._queue)
                    joining.append(job)
                    if job.lead:
                        leading = True
                        break
            try:
                for job in joining:
                    kv = self._join(kv, rows, job)
                if rows:
                    kv = self._step(kv, rows)
            except Exception as exc:  # noqa: BLE001 - a failed step fails its sentences, not the thread
                log.warning("M11 TTS step failed: %s", exc)
                for job in [row.job for row in rows] + joining:
                    self._fail(job, f"{type(exc).__name__}: {exc}")
                rows, kv = [], {}

    def _join(self, kv: dict[str, Any], rows: list[_Row], job: _Job) -> dict[str, Any]:
        """Start a sentence on its voice's cached conditioning and add its row."""
        import numpy as np

        if job.done.is_set():
            return kv
        prefix = self._prefix[job.voice.key]
        start = next(iter(prefix.values())).shape[2]
        ids = np.array([self._tokenizer.encode(job.text).ids], dtype=np.int64)
        embeds = self._sessions["embed_tokens"].run(None, {"input_ids": ids})[0]
        n = start + ids.shape[1]
        logits, own = self._run_lm(
            embeds, prefix, np.ones((1, n), np.int64), np.arange(start, n)[np.newaxis, :]
        )
        row = _Row(job, length=n, max_new=min(1000, 60 + len(job.text) * 4))
        row.tokens.append(sample_next(logits[:, -1, :], np.array([], dtype=np.int64), self._rng))
        if row.tokens[-1] == STOP_SPEECH:
            self._decode.put((job.seq, id(row), row))
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
        logits, kv = self._run_lm(embeds, kv, mask, pos)
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
            self._decode.put((rows[b].job.seq, id(rows[b]), rows[b]))
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
            _, _, row = self._decode.get()
            job = row.job
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
                wav = (
                    self._sessions["conditional_decoder"]
                    .run(
                        None,
                        dict(
                            speech_tokens=tokens,
                            speaker_embeddings=spk_emb,
                            speaker_features=spk_feat,
                        ),
                    )[0]
                    .squeeze(axis=0)
                )
                self._finish(job, to_wav(self._watermark(wav)))
            except Exception as exc:  # noqa: BLE001
                self._fail(job, f"{type(exc).__name__}: {exc}")

    def _finish(self, job: _Job, data: bytes) -> None:
        self._remember(job.key, data)
        try:
            (CACHE_DIR / job.voice.key).mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / job.voice.key / f"{job.key}.wav").write_bytes(data)
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
