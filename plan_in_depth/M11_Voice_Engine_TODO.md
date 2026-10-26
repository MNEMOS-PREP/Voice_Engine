# M11 — TODO · Voice & Conversation Engine

> **Completion: 95%** — 21 of 22 functional requirements met; the one open is FR-11.20, the 1.2 s budget, which is this laptop's CPU (measured: p50 2.5 s; the user's call — a faster machine later). **Every day of the build order that is M11's own work is done (2026-10-07); what remains waits on hardware, on the user's decisions, on real students, or on M18** — the "Later" list in the checkpoint below. A whole panel interview has been sat live, spoken, three times.
>
> _Method: `(met + ½ × partial) ÷ total`, counted from the spec, 2026-08-28. One measure applied the same way to all nineteen modules so they compare; it counts requirements, not screens or gates._

Task list for taking **M11 — Voice & Conversation Engine** to 100% of [M11_Voice_Engine.md](M11_Voice_Engine.md).

> **This is the branch that holds the plan.** The `todo` branch carries the
> spec and this list and nothing else, so the module's own history stays
> about its code. Sync it here when something lands.

> **Read this first when starting a session on M11.** It is the running state of
> the module: what is done, what is next, and what is deliberately deferred.
> Update it as things land — a stale list is worse than no list, because the
> next session trusts it.

- **Repo:** `Voice_Engine`

Legend: ✅ done · 🟡 partly done · ⬜ not started

---

### 2026-10-26 — abhinav's last voice commit merged, and a crash fixed (`c65ec7b`, `28db005`)

- ✅ **Merged c32cf3e with parts held back.** Taken: sampling temperature
  0.8 → 0.5 (his read-back of 151 names: 73 exact at 0.5 against 62 at 0.8).
  Held back: `startup_founder` → `indictts-048013`, a higher-register voice four
  women speak in, for a persona authored `en-IN-male-casual` — and M06's persona
  file still names `indictts-012635`, which the parity test reads; and his
  `voices/lexicon.json`, which applies the team's respellings in every voice
  again (measured 10-12: 190 name-voice pairs broken against 88 fixed) and adds
  36 unheard names. It is kept whole as
  `research/lexicon/team_lexicon_2026-10-22.json`.
- ⬜ **Next for names:** `names_ab.py run plain`, `run respelled`, then
  `decide research/lexicon/team_lexicon_2026-10-22.json` — at temperature 0.5,
  which the 10-12 scopes were not measured at.
- ✅ **`speak` could raise instead of speaking.** With no parallel making, a
  sentence made while its request waited for the lock came back as three values
  where `speak` takes four: a `ValueError`, not the line.
- ✅ **The latency harness's student voice** was `dailytalk-0`, retired on
  10-11, so it was quietly the default voice two panelists speak in. It now
  takes a roster voice the room has not played.
- 🟡 `test_a_line_made_ahead_is_made_by_the_main_model_and_preferred` failed
  once under a loaded CPU (its 5 s wait ran out and the live model raced the
  main one); it passes alone. A timing test, not a product defect. 147 tests.

### 2026-10-23 — the "um"s and "uh"s, kept (`7043463`)

- ✅ **Whisper keeps filled pauses now.** On the question alone as its prompt
  it wrote down none of 53, so M06's delivery notes never had any to count.
  The prompt now ends on a line written the way people talk
  (`asr.SPOKEN_STYLE`): it kept 65 of 97 across two sets of clips, invented
  none on clean speech, and wrote the other words more accurately (WER 10.5%
  → 6.5%). Hindi detection was unchanged (16 of 16).
  `research/fillers` (DisfluencySpeech, Apache-2.0; one key, paced). M06
  names them in its notes since `11ec08c`.
- ⬜ **Still owed:** the same measure on real Indian-English interview
  answers, from consenting students; "er", "ah" and "hmm" were not measured.

### Voice — open problems, their causes, and the plan (2026-10-10, to work on)

What is still wrong with the voice, each with its cause as measured (or
marked unconfirmed) and the fix the user chose (their notes, 2026-10-10),
fitted to how M11 works. **The GPU is not for now** (the user's call).

1. ✅ **Done 2026-10-11.** Measured, not guessed: the plan page's pieces
   and the room's are the same (8 of 8, `sentencesOf` both sides); with M11
   ready the whole opening is made while the plan is read (all hits, joins
   0.09–0.34 s, the room driven headless with every voice request logged).
   It failed when M11 was **still loading**: the plan page asked once and
   gave up, and the room's first line chose the browser's voice for the
   whole interview. Core v0.31.0: `prepareLine` waits for M11 (≤ 3 min);
   the room's first line waits ≤ 15 s, then starts in the browser's voice and
   moves to M11's from the first line after it is ready (verified live).
   M11's load cut from ~85 s to **16 s** (`0ec9b1c`: voice encodings kept,
   prefixes lazy). And the candidate questions are made a piece of each in
   turn (`prepareLines`, M06 `eaa4779`): an alternative asked no longer
   waits 4–6 s for its second piece.
   *Was:* **Long silences in the opening** — 23.8, 11.4, 11.0 s in a clean live
   run (CPU free, stock phrases made). *Cause unconfirmed:* the plan page
   should have made the opening ahead (~25 s of audio, ~18–20 s to make at
   fp32); suspected (a) what the plan page makes is not what the room asks
   for — different sentence cuts, the panel's introductions with names in
   place — so the cache misses; (b) not done in the 25 s the plan was read.
   *Fix:* compare the plan page's planned pieces with the room's requested
   pieces key by key; make both go through the same text normalisation and
   `sentencesOf`, names filled the same way, so every piece made ahead is
   found. Then the Start button can wait for M11's `ready` on the opening.
2. ✅ **Done 2026-10-11.** Split from the ledger: the live run's 9.5 and
   10.6 s were **M06 8+ s** (answer → line) + voice 1.4–2 s. That night the
   guard took 6.3 s and the strategist 6.7 s against 1.5 s and 4 s timeouts
   (`urlopen` bounds each read, not the call); normally 0.3 s and 0.7 s.
   M06 `cdceaff`: wall-clock deadlines (the guard fails open, the move comes
   from the rules), every step timed in the log. Now: M06 0.76–0.95 s, a
   reply heard 2.33 s after the answer. FR-11.20's 1.2 s still needs the
   faster machine.
   *Was:* **The reply after an answer: 9.5 / 10.5 / 4.9 s to first sound**
   (FR-11.20 wants p95 ≤ 1.2 s; the best here was p50 2.5 s). *Causes:* M06
   writes the reply with the language model before any audio can start; the
   reply is made live (int8), and nothing plays until its first sentence is
   whole; the calibrated pause before speaking (0.3–0.9 s). *Fix:* split the
   delay by stage from marks the ledger already keeps (`answer_sent_at`,
   `first_token_at`, `landed_at`, `first_audio_at`, plus M06's own model time):
   network/model, synthesis to first audio, the pause — then work on the
   largest.
3. 🟡 **2026-10-12: streaming is in, and on this laptop it cannot help.**
   abhinav's `stream.py` and `/voice/speak_stream` are merged (`761cbed`):
   1 s pieces with 1 s of context, crossfaded, played only once the buffer
   cannot run dry, not streamed when the making is too slow to gain. Timed
   here on fresh long sentences: it never started early, and took 3–6 s
   longer than the whole sentence (as abhinav measured: 42.8 s streamed
   against 31.8 s whole). Live speech is made at ~0.75× real time on this
   CPU (8.4 s of speech in 11–12 s: ~5 s choosing tokens, ~4 s decoding),
   with 8-bit or 7-bit int8 alike. A GPU decoder (GTX 1650: 0.12–0.19× real
   time) would let it stream; the GPU is not for now. Left to try on the
   CPU: the decoder in int8. The room does not call `speak_stream` yet.
   **Tried 2026-10-12, not adopted** (`research/listening/decoder_int8.md`):
   the int8 decoder sounds the same but runs at 0.37x real time against
   fp32's 0.40; 8 threads 0.41. The decoder is ~0.4x real time on this CPU
   whatever is done: streaming waits for a GPU decoder.
   *Was:* **A gap before a long sentence** (the user's `demo_2`). *Causes:* (A)
   the CPU shared with a face build — fixed, builds wait during interviews
   (`8913aa2`); (B) a sentence with no comma is one piece, and one row of
   three makes ~19 speech tokens/s where speech needs 25, so a long piece
   made beside others is late. Cutting it was measured and refused (the
   parts' pitch falls like full stops, `breath.md`). v0.30.0 already moves a
   wait to the sentence's start (≤ 1.2 s). *Fix:* **stream the sentence** —
   decode its speech tokens in chunks while the model is still choosing the
   rest (~1 s of left context, a short look-ahead, a crossfade at each seam),
   each chunk put on the room's one Web Audio track as it arrives (barge-in
   stops it as now). Keeps the sentence's own tune; first sound after ~1 s
   whatever its length. Test the seams first, with M11 stopped (RAM).
4. ✅ **Done 2026-10-12.** Core v0.32.0–v0.34.0: identifiers by shape
   (`Employees(emp_id, …)` "Employees, with employee ID, …", `COUNT(*)`
   "count star", `OrderID` "Order ID", `log_b a` "log base B of A", `f(n)`
   "F of N", comparisons in words). And a seam fixed: Core rewrote `O(n)`
   to "O of n" before M11's probed `notation.py` could make it "order N",
   so every big-O went out in the form its probe rejected; ported to Core.
   `research/lexicon/identifiers.py` on all eight voices: 69 of 96 sayings
   whole; "dept" → "department" earned an entry (8 of 8); "AS PATH" none.
   *Was:* **Identifiers read wrong** — `emp_id` heard as "Benite", `dept_id` as
   "deputy". *Cause:* `speakable()` only turns `_` into a space; "emp", "dept"
   and `Employees(…)` reach the voice as written. *Fix:* the lexicon
   (EC-11.11) — scan the question bank for identifiers (`snake_case`,
   `camelCase`, `Table(col, …)`), probe each in the cast voices with
   read-back, and add the respellings that come back right ("employee I D",
   "department I D"); a table's columns said as a list. Chatterbox takes
   text, not SSML or phonemes, so entries are respellings, kept per voice
   where one voice needs its own.
5. ✅ **Done 2026-10-12** (`research/listening/heads_cpu.md`): measured in
   the real room, live speech was made at 2.2x real time with two 3D heads
   open against 1.0x with photos — the renderer drew at 60 frames a second
   (~1.9 cores, and the integrated GPU's share of the power). Core v0.35.0
   paces each head: 30 a second while it speaks (lip sync's rate), 15
   otherwise — 0.4 cores, speech at 1.5x real time.
   *Was:* **The browser's 3D heads share the CPU with the voice** — unmeasured.
   *Fix:* measure the room's CPU with heads on and off during a line; if it
   matters, draw only the speaker's head at full rate and the others slower
   (or as their photo), or move the renderer off the main thread.
6. ⬜ **Small quality costs, accepted for now:** the live int8 model misreads a
   few more words (WER 0.033 against 0.018), so only lines nobody could make
   ahead use it; one long whole sentence was misread at 0.28 in one voice;
   the comma cuts in use since v0.26.0 have not been measured for the
   full-stop fall the breath cuts showed — measure them with `breath_probe.py`.
7. ⏸ **A GPU — not yet** (the user, 2026-10-10). The ceiling on this CPU:
   ~27 speech tokens/s fp32 with three rows; int8 41.5 alone, 56.6 with three;
   DirectML on the Iris Xe crashed or recompiled per length. FR-11.20 /
   AC-11.1 stay open until a faster machine.

**Order:** ~~1~~ → ~~2~~ → 3 (hardware: a GPU decoder) → ~~4~~ → ~~5~~ → 6.

**2026-10-12 — the team's branches, merged** (`761cbed`, M06 `2bbcba5`):
int8 with 7-bit weights by default (8-bit spoke gibberish on CPUs without
VNNI), the opt-in DirectML decoder, streaming, the listening-test cast
(eight voices kept; `Cast.resolve` now gives a man's voice to a man before
the accent), and 155 name respellings. Measured before keeping them
(`research/lexicon/names_ab.py`, 1,240 sayings each way): recognisable as
written 1,125, respelled 1,023; a respelling fixed 88 name-voice pairs and
broke 190 — kept wherever it did not break the name (`e9ddcc8`).

### 2026-10-10 — a photo for everyone; where the user's gaps came from; faces checked for marks

The user, after two recorded mocks (`demo_1.mp4`, `demo_2.mp4`): *"when a
large sentence is followed by a sentence, the gap in audio is huge and makes
it feel AI-like"*; and the plan page showed initials, not faces.

- ✅ **A photo for all 39** (`df756ca`): only the four team-look heads had a
  still; `--stills` now makes one from the portrait each head was built
  from (its `meta.json` names it; the newest copy no newer than the head).
- ✅ **Faces revalidated, not cached a day** (`2229c50`): ETag from the file's
  time and size, `no-cache`; a rebuilt head or photo is fetched, an unchanged
  one is a 304.
- ✅ **Why `demo_2` stopped 5.3 s and 14.3 s:** clips made during the mock took
  2–4× as long as the same lengths before it — the stills job shared the CPU.
  `GET /v1/voice/activity` (seconds since a student last waited on the voice)
  and `make_faces.py` holds between steps while it is under 5 min (`8913aa2`).
- ✅ **Cutting long sentences where a reader breathes: measured, refused**
  (`research/listening/breath.md`): a part made alone ends 3–9 semitones lower
  than the whole sentence at that point in about half the cases — heard as
  a string of sentences.
- ✅ **Core v0.30.0**: a sentence whose later pieces are late waits before its
  first word, never halfway (`sentenceEnd`, tested).
- 🟡 **Re-measured live** (warm phrases made, CPU free): joins inside a line
  ≤ 0.29 s; but the opening still stalled 23.8, 11.4, 11.0 s and answers waited
  9.5 / 10.5 / 4.9 s for audio. **First thing next:** why the opening is not
  made ahead on the plan page (its keys against the room's pieces).
- ✅ **Faces in the team's look: 39 of 39** (finished 2026-10-10 15:19).
  Seven had a bindi or tilak: the prompt named them ("no bindi") and FLUX
  at cfg 1.0, with no negative prompt, drew them. The prompt now describes
  the look ("unadorned … a clear bare forehead", `1442e39`) and the seven
  were redone (`--force --only`); seeds already rejected are skipped
  (`cbc8146`). Four keep a dot of 2–3 px between the brows (dl_shreya,
  hr_ritu, db_neha, cn_divya): **accepted by the user** ("tiny dot is fine").
  `forehead_mark()` stays report-only (`ef5a779`).
- ⬜ Stream long sentences: decode a sentence's tokens in chunks while the
  model is still choosing the rest (~1 s left context, a crossfade), so it
  keeps its tune and starts at once. The seam test needs M11 stopped (RAM).
- ⬜ Identifiers read wrong (`emp_id` → "Benite"): the lexicon probe over the
  bank's identifiers.

### 2026-10-09 — no gaps in a spoken line; faces in the team's look; a photo for each

The user, after a mock: *"I could feel gaps in speech, awkward pauses,
sometimes if the text is too long … use the smartest ideas"*, and *"no
noticeable gaps, awkward pauses, or breaks between speakers"*; for faces,
the team's LAM look (Avatar_Lab), *"ultra-realistic and authentically
Indian"*, and *"we don't want dummy faces in the interview"*.

**Why there were gaps** (`research/listening/gap_bench.py`, `gaps.md`): on
this CPU the language model tops out near 27 speech tokens/s with three
sentences side by side, and speech needs 25. Measured: 2–3 s stalls after
"Okay.", 10.9 s before a long follow-up's first word, and 0.2–0.5 s of
silence baked into every join. q4, or more rows, changed none of it.

- ✅ **One track** (Core v0.29.0 `player.ts`, `track.ts`): each clip decoded
  as it arrives, trimmed to its sound, scheduled on one Web Audio clock with
  the pause a person leaves (~0.1 s at a comma, ~0.3 s at a full stop,
  ~0.22 s at a change of speaker, by tempo); a long line holds its first
  word up to 1.2 s rather than stalling mid-sentence; lip sync on the output
  clock. Live: every join inside a line 0.11–0.41 s, none over 0.6 s.
- ✅ **Lines made ahead** (`4884a11`, M06 `49e7e7c`): `/voice/plan` takes
  priority `next` (the opening, the next question) or `warm` (stock
  phrases) — made only while nothing live waits, set aside when a live line
  arrives, promoted when asked for, in the order asked — and says which
  sentences are `ready`. A warm sentence's decoding waits while a live one
  is made. M06's `/upcoming` (the questions M05 would choose now, phrases
  with names in place) and its prefill's would-be line are made while the
  student reads the plan and answers. `scripts/warm_phrases.ts` makes every
  interviewer's stock phrases once.
- ✅ **An int8 model for live lines** (`tts.int8_graph`, `int8.md`): 41.5
  speech tokens/s alone against fp32's 16.4. It misreads a few more words
  (14 voices: WER 0.033 against 0.018), so made-ahead lines stay fp32 and
  only what no one could make ahead (an adapted follow-up) is int8; each
  clip under its own model's key; `speak_keyed` names the face's frames by
  the clip returned. A live sentence under warm load: 13.6 s → 7.9 s.
- ✅ **Not faster here** (`gaps.md`): DirectML on the Iris Xe — the language
  model 3.8 tokens/s, and with its cache on the GPU onnxruntime-directml
  crashes; the decoder 0.33–0.46× real time once compiled but recompiling
  for every new length.
- ✅ **Faces in the team's look** (`36c04be`, `7223f71`): `portraits.json`
  is Avatar_Lab's CAST.md prompt word for word; Ananya, Arjun, Sameer and
  Vikram use the team's own portraits; gender and expression come from the
  persona's voice_id. `build_face.py` checks each portrait on 68 landmarks
  (calibrated on the team's ten: mouth closed, eyes open, facing, level) and
  `make_faces.py` asks for another seed on a fail, rebuilds into a staging
  folder and swaps each head in whole, and pauses on a file. Each head comes
  with its still, `/v1/voice/faces/{persona}.webp`. `faces/ATTRIBUTION.md`
  (academic use only: LAM's weights CC BY-NC, FLAME non-commercial) and
  `scripts/faces/README.md` (the setup, rebuilt from what this machine ran).
- ✅ **No drawn faces** (Core `InterviewerPhoto`, M06): each interviewer's
  photo wherever a face was drawn, the 3D head fading in over it; initials
  when there is no photo yet. **The asker thinks** (Core `faceDriver`):
  glances down and aside while the reply is worked out, back to speak.
- 🟡 **Re-measured once, before the last two fixes** (`flow_check.mjs`): the
  first line stalled 19 s inside (its question made after later requests —
  fixed: in the order asked, the opening made ahead first); answers waited
  7–7.5 s for audio because the line's phrases were still in the room's
  warm-up (fixed by `warm_phrases.ts`, to be run once). To measure again.

**Next:** run `warm_phrases.ts` once; re-run the live flow (the harness must
wait for first sound before ending a turn); let the face rebuild finish (5 of
39 at this checkpoint, ~8 min a head) and look at the room's tiles; the
nightly latency run (register with `-Register`, the user's call); FR-11.20.

### 2026-10-08 — Day 13: the faces (spec §15.6, decided); more Indian voices

The user decided §15.6: *"add faces to the interviews with perfect lip
syncing"* — option B, built.

- ✅ **The lip sync is the voice's own audio** (`face.py`, `a339fb6`,
  `b2f8cc3`): wav2arkit (Apache-2.0, ONNX on M11's CPU — 0.3 s for a
  4.6-second sentence) turns each sentence into 52 ARKit blendshapes at
  30 fps, a light zero-phase smoothing and the mouth's channels a little
  emphasised for a small tile. Frames are keyed like the audio (`X-Face`,
  the cache key of the *prepared* text), made as the sentence is, and
  `GET /v1/voice/face/{key}` waits up to 3 s for frames still being made.
- ✅ **The heads** (`scripts/make_faces.py`, `scripts/build_face.py`): one
  AI-generated portrait per interviewer (FLUX.1-schnell Q4 through
  stable-diffusion.cpp on this laptop's Iris Xe, Vulkan, weights streamed
  from disk), lifted into ~20,000 Gaussians on a FLAME head by LAM on the
  CPU, placed on the rig from its own FBX. About eight minutes a head; built
  locally (setup once: `scripts/faces/README.md`), gitignored, served
  as `/v1/voice/faces/{persona}.zip`. Every portrait is generated, never a
  real person's, and every head is labelled AI. **Academic use only:** LAM's
  code is Apache-2.0 but its weights are CC BY-NC 4.0, and FLAME 2023 is
  under MPI's non-commercial licence (the faces' `ATTRIBUTION.md`).
- ✅ **In the browser** (Core v0.27.0 → v0.28.0, `TalkingHead`, `faceDriver`):
  gsplat-flame-avatar-renderer (MIT) draws each head; every frame is all 52
  channels at the audio element's `currentTime` plus one frame, interpolated
  between the 30 fps frames; blinks seeded per persona; nods into stressed
  words and while listening. Not the spec sketch's way in two places: the
  frames are made on M11, not by onnxruntime-web in the browser, and the eyes
  follow the rig's idle clip rather than the renderer's camera look-at.
- ✅ **Measured, not assumed:** in the live room the mouth each head was given
  matched the frame for the audio's own time exactly once playback started
  (a test-side hook on the renderer, nothing in the product); offline, over
  eight voices, M11's frames open the mouth a median 83 ms before the sound
  and close it a median 89 ms after, as natural speech does.
- ✅ **Seven more Indian voices** (`62c4a0b`, `research/listening/
  add_indian_voices.py`): IndicTTS English speakers 7–13 (CC BY 4.0), four
  higher and three lower; 37 of the 39 interviewers speak in an Indian voice,
  a foreign accent only for the two the team cast (Priya, Kabir). A
  read-back probe (`research/listening/probe_voices.py`) passed all nine
  probed: WER ≤ 0.18, 3.0–4.1 words a second.

### 2026-10-07 (evening) — Checkpoint: where to pick up

**Finish first (an hour, no new code):**
1. **Sit the nightly once, end to end, then register it.**
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\nightly_latency.ps1`
   with the stack running, and check `research\latency\history.jsonl`. Then run
   it again with `-Register` (02:30 daily, this user; `-Unregister` removes it).
   The first manual run stopped at the shell's welcome gate: the harness now
   onboards its own student through M04 and stops at once if Start is missing
   (`latency_harness.mjs`). The second run was stopped at the user's request to
   close, so this is still unverified end to end.
2. **Sit this evening's features live through the harness.** All of them are
   pinned by tests, but none has been heard in a real page yet:
   - the strict prefill: its `prefill: N used of M tried` line gives AC-11.7;
   - "did you say …?";
   - the re-offer;
   - captions from M11 (Firefox has no speech recognition of its own);
   - a call pausing the clock (headless Edge can mute the fake microphone's
     track);
   - offline answers.

**Later — none of it is M11 code:**
- **A faster machine:**
  - FR-11.20 and AC-11.1: p95 ≤ 1.2 s from end of speech to first audio. The
    p50 is 2.5 s, and synthesis takes ~2× real time on this CPU.
  - The device matrix: the Arc A370M needs its driver (Windows code 28) before
    OpenVINO, plus phones over the LAN and Bluetooth headsets in hand. This is
    also where AC-11.2's p95 comes from.
- **The user's decisions:**
  - Svarah's terms on Hugging Face (AC-11.4, the accent gap).
  - Groq Orpheus terms (day 8; optional now that Chatterbox is the voice).
  - ~~The face (day 13, spec §15.6)~~ — decided and built 2026-10-08 (above).
  - Consented recordings of real students. These give Smart Turn its 200
    endings, AC-11.5's WER, and real Hinglish for FR-11.22.
- **Real students (a pilot), measured rather than built:**
  - AC-11.3, the premature cut-off rate (counted live by `cutShort`);
  - AC-11.6, "it kept cutting me off";
  - AC-11.8, voice against text completion;
  - AC-11.9, hold-to-talk engaging before a student gives up.
- **Other modules:**
  - EC-11.2, a second speaker: M11 can diarise, but the signal is M18
    Integrity's, and M18 is not built.
  - M12 (delivery: fillers, pauses) and M14 (group discussion) will consume
    M11's word times and Core's turn-taking. That is their work, not M11's.

### 2026-10-07 (evening) — FR-11.3, 11.6 and 11.16; four edge cases; the nightly

- ✅ **FR-11.6, in its strict form** (M06 `8152191`; Core v0.25.0 `42b7b88`;
  room `364bef9`):
  - **The user's rule:** *"the reply should be based on what the answer is,
    not assume what he/she is gonna say"*.
  - **At a pause:** in a turn of 3 s or more, what has been said so far is
    written down and sent as a prefill. M06 runs the step in memory, writing
    nothing, and keeps each model answer by its exact request.
  - **On the answer:** the real step uses a kept answer only for a
    byte-identical request — the same words and the same state.
  - **Exact words, by construction:** the prefill's words and the answer's come
    from the same audio cut, so they match exactly when nothing more was said.
  - **Pinned:** no second model call, and the same line as without a prefill.
    One word more and the model is asked.
- ✅ **FR-11.16, naming the word** (M06 `28fdc2e`, `clarify.py`):
  - "Did you say quick sort or quick select?" — once a question, three a
    session.
  - **The terms are the question's own:** its key points, each rung's
    expected points, its label and stem.
  - **Never asked** when what was heard is one of those terms, or the same word
    with an ending.
  - **The reply is judged with the answer it clarifies,** and sent to M13 and
    M04 together with it.
- ✅ **FR-11.3, captions from M11** (Core v0.25.0, `caption.ts`): where the
  browser cannot caption, the last 10 s of the turn are captioned every 2.5 s,
  with unsure words lighter. The browser's own captions are used everywhere
  else.
- ✅ **EC-11.1** (M06 `28fdc2e`, room `364bef9`): when the student comes in at
  the very start of a line, the interviewer yields aside ("Sorry — go ahead.").
  M06 then puts the question again, and what was said before it was heard is
  not judged.
- ✅ **EC-11.7** (Core v0.25.0; M11 `634c678`; room): the mic check and the room
  warn of a Bluetooth headset — by its name, by an 8–16 kHz rate, or by a first
  word that never came back.
- ✅ **EC-11.12** (M06 `7846920`; Core; room): a phone call takes the
  microphone, the interviewer falls quiet, and the clock stops. No pause is
  spent and no reconnect is counted. Five seconds back in, then the question
  again.
- ✅ **EC-11.15** (Core `isOffline`; room): offline, the answer's audio is kept
  and goes when the network is back. A send that fails puts the words back in
  the box.
- 🟡 **Day 14, the nightly** (`scripts/nightly_latency.ps1`, M11): runs the
  harness on a good network and on 2G, skips when the stack is down, uses its
  own student, and appends to `research/latency/history.jsonl` (gitignored).
  `-Register` / `-Unregister`. Not yet sat end to end (see the checkpoint).
- ✅ **Found by sitting it and fixed the same evening:**
  - "No, that's all from me." was filed as a panel question (M06 `2b6fec0`).
  - An answer of 2–4 s was still cut after one sentence (Core v0.24.1
    `40df116`).

### 2026-10-06/07 — Days 9 to 12 and 14, and an interview sat live

- ✅ **Day 9, second half (FR-11.15, FR-11.16):** low-confidence words travel
  with the answer.
  - M06 (`3eeb88d`): when the answer's mean confidence is under 0.4, the
    interviewer says "Sorry, I didn't catch that", once per question, and does
    not judge the answer.
  - M13 (`382678a`): rejects any quote that overlaps an unsure span.
  - The room dots the unsure words.
- ✅ **EC-11.11, the lexicon** (`7d561e1`, `619d40b`, `cbd4981`, `4ff540e`):
  - 127 terms probed; 125 came back right. One entry, for one voice:
    Raghavan → Raghaavan.
  - Big-O said as words (`notation.py`, `f2e29e8`), after four rounds of
    probing (`research/notation/RESULTS.md`). Every "O of …" spelling lost the
    words after the "O" in most voices. "order N log N" came back in all
    seven.
- ✅ **Day 10 (FR-11.2, EC-11.8)** (`277c69e`, Core v0.22.0): a mic check.
  - It measures the room's noise floor, keeps it, and seeds the VAD with it.
  - It then has the student read a sentence and reads it back, saying how much
    came through and what the room is like.
  - In the interview, the interviewer's own voice heard back through the mic
    is not sent as an answer.
- ✅ **Day 11 (FR-11.10 to FR-11.12)** (Core v0.23.0; M06 `fda446f`,
  `870f184`):
  - **Calibrated silence:** before answering, the interviewer waits 300–900 ms,
    set by their persona's patience. In Final Boss they sometimes hold the
    silence on purpose.
  - **Lines appear as they are said:** a fresh line shows up part by part as
    it is spoken, so nothing on screen gives the silence away.
  - **Backchannels:** "Okay.", "I see." and "Sure.", chosen by a probe of every
    voice ("Mm-hm" broke up, `5267a23`). They play on their own channel, more
    often the warmer the persona, and never in Final Boss.
  - **The note-taking pause:** 1.5 s, inside the line.
- ✅ **Day 12 (FR-11.19, FR-11.17)** (M11 `7d81077`; M06 `870f184`,
  `779146c`):
  - **Kept answers:** saved only with consent, readable only by the student
    or staff, and deleted as files. They play back in the notes.
  - **Hold-to-talk:** the student's own choice, or switched on by the room
    when the connection is poor, after two drops, or after repeated echo.
  - **Typing:** after two answers nobody could write down.
  - **Talk freely off mid-answer** keeps what was said (FR-11.14).
- ✅ **FR-11.22, measured first** (`research/codeswitch`, M11 `c50b943`, M06
  `1b45581`):
  - Told to expect English, the recogniser invented English for 4 of 8 Hindi
    recordings.
  - Left to detect the language, it wrote all 8 as said, and the 8 English
    recordings came back unchanged.
- ✅ **Day 14** (`1b6488e`): `scripts/latency_harness.mjs`.
  - It sits a spoken panel interview through the shell and grades it with the
    ledger's own targets.
  - `--profile 2g` degrades the connection partway through, and the harness
    checks that the room switches to hold-to-talk.
- **Sat live** (2026-10-06/07; two runs plus one through the harness):
  - **The panel:** introduced part by part. Priya at +1.4 s, Dr. Raghavan at
    +6.5 s, Priya's question at +10.1 s, each only once they began speaking.
  - **Hand-over and hand-back,** each speaker in their own cast voice:
    `chatterbox-default` and `indictts-103607`.
  - **Spoken answers:** 20 s and 31 s answers of two and three sentences
    each arrived as one turn.
  - **Answer audio** was kept (four uploads, all 201).
  - **Backchannels:** four in the harness run, five in the first run.
  - **The lead closed** the interview.
  - **Ledger:**
    - stop p95 **1 ms** (AC-11.2's stage, met);
    - barge-in **260 ms**;
    - end of speech → first audio p50 **2.5 s** (AC-11.1, over). Synthesis on
      this CPU explains it, made worse in the harness by the student's voice
      being made on the same CPU.
- **Found by sitting it, all fixed:**
  1. The same question three times in one interview (M06 `26f987e`, M05
     `897748d`).
  2. "Take your time." said the moment a spoken answer ended (`779146c`).
  3. A three-sentence explanation answered after its first sentence. Fixed in
     Core v0.24.0–v0.24.1: an answer of 2 s or more gets a full second of
     quiet before the turn model is asked, and a cut-off is learned from.
  4. "No, that's all from me." filed as the student's question for the panel
     (`2b6fec0`).
  5. Big-O unreadable in every voice (`f2e29e8`).
  6. M05's disclosure for a deliberate re-ask was never said (`26f987e`).

### 2026-10-06 — Day 9, first half: what the student heard

- ✅ **Where the student came in** (`@ai/core` v0.21.0 `2f1e049`): `bargeIn`
  reports the line being heard, the part being heard and how far through it
  (`partRanges`, `cutAt`; pure, pinned); a Final Boss contest reports it when
  it yields.
- ✅ **M06 records it and both readers use it** (M06 `7b67a60`, FR-11.9):
  `POST /v1/interviews/{id}/heard`, a `turn.heard` event, once per line. The
  line of record stays whole; the transcript dims the words the student never
  heard, with a mark where they came in; the interviewer model reads the line
  as far as it was heard, marked "[cut off: the student started speaking
  here]", so a follow-up does not assume a question they never finished
  hearing. Snapped to whole words. 448 pass.

### 2026-10-06 — Day 5: has the student finished?

- ✅ **The speaker's own pauses** (FR-11.4, `@ai/core` v0.20.0 `0006f45`,
  `endpoint.ts`, pure, 7 tests): a silence ends a turn once it has lasted
  `550 + 1.2 × (their mean pause − 250)` ms, within 400–1,400 (§6.2) —
  learned from pauses they came back from, across the session.
- ✅ **Does it sound finished?** (FR-11.5, Voice_Engine `5f3adf1`, `turn.py`):
  at that moment **Smart Turn v3.2** (Pipecat, BSD-2; a Whisper-Tiny encoder,
  8.7 MB int8 ONNX, ~25 ms on this CPU) hears the last 8 s; "not finished"
  waits 600 ms more and asks again, never past 2.5 s of silence (§6.3).
  Without the model, silence alone decides. It hears the waveform, not a
  transcript: no API call, and it runs before recognition.
- **Decided: Smart Turn on the server, not in the browser.** M11 already
  runs onnxruntime; one 8 MB model on the server beats onnxruntime-web and a
  model download in every browser, and works on the demo laptop offline.
- **Its preprocessing, checked rather than trusted:** the reference
  implementation (fetched from Pipecat's repo) left-pads to 8 s and uses
  `transformers`' Whisper feature extractor. Reproduced in numpy; compared
  with the real extractor in a throwaway venv: **within 4.5e-6** on speech,
  noise and tones. The test pins numbers taken from it.
- **Checked on real speech:** the seven human reference recordings, cut at
  Whisper's word times — after "and / the / of…" median **0.03** (53 of 57
  heard as unfinished); at sentence ends median **0.86** (10 of 15 finished;
  the misses are mid-paragraph sentence ends where the reader goes on — when
  an interviewer should wait). Chopped synthetic speech fooled it: that was
  the wrong test, kept out of the suite. **Still owed** (the spec's "200
  labelled endings of real answers"): students' own answers — needs
  recordings, with consent (day 12).
- ✅ **A spoken turn, start to finish** (`useTurnTaking`): listens, decides,
  and hands the room the whole turn — one transcription per turn, not per
  breath (more accurate, and fewer calls against a free tier's minute).
- ✅ **M06's room sends a spoken answer when the student finishes** (M06
  `7cad60c`) — nobody presses a button to stop talking in a spoken interview.
  Without the recogniser, the words wait in the box for "Answer".
- ✅ **AC-11.1 measured as the spec states it** (Core v0.20.1 `cb0f99c`): a
  spoken answer carries `speech_ended_at`; the ledger's `end_to_audio` (end
  of speech → first audio) is the gate, `endpoint` shows the wait for
  "finished", `total` keeps the budget from the send for typed answers.
- **Live** (headless Edge, a fake microphone over a panel's opening): the
  student cut in (261 ms) and finished; Smart Turn: finished, 0.87, 61 ms;
  Whisper: the whole turn, 469 ms; sent; the next line played — **~1.9 s
  from the end of speech** (AC-11.1 asks 1.2 s: the 550 ms silence, the
  model, recognition, M06's step and synthesis add up; speed is the user's
  "later, on a better machine").

### 2026-10-06 — Day 4: the student's words, with the time of each

- ✅ **Confirmed: Groq returns word timestamps** (the build order asked):
  `verbose_json` with `timestamp_granularities[]=word` and `segment` gives
  each word's start and end, and each segment's `avg_logprob` and
  `no_speech_prob`; 12 s of audio in ~0.5 s.
- ✅ **`POST /v1/voice/transcribe`** (Voice_Engine `2811fb6`, `asr.py`): an
  answer's audio in, spec §5's `ASRResult` out — word times clamped so they
  never run backwards (Whisper's alignment overlaps); each word takes its
  segment's confidence, and runs of unsure words become
  `low_confidence_spans` (FR-11.15's marking); Whisper's text over silence
  ("Thank you.") dropped by the standard filter; the question as Whisper's
  prompt, so "Dijkstra" comes out as Dijkstra; a key refused for quota hands
  over to the next. Nothing is stored. `GET /v1/voice/asr`. The shared
  `keys.txt` loads at boot (names only; `keys.py`, the seventh copy —
  PLATFORM_TODO §2). 12 tests, none open a socket.
- ✅ **The browser keeps the audio for a moment** (Core v0.19.0 `822cfdb`):
  the listener's audio thread also keeps the last minutes at 16 kHz, and
  `audioBetween` cuts exactly what was said — from 300 ms before the
  detector decided, where the first word is — as a WAV. **Decided: WAV from
  our own audio thread, not MediaRecorder's WebM**: a WebM cut mid-stream
  loses its header and the recogniser cannot read it.
- **Live:** 4.5 s of a fake student's speech, cut in the browser,
  transcribed in 450 ms.

### 2026-10-06 — Day 3: barge-in, measured from the student's first word

- ✅ **The mic, listening** (`@ai/core` v0.18.0 `734f2f8`, v0.18.1 `d63a4c8`):
  `useListening` opens the microphone with echo cancellation, noise
  suppression and gain control, cuts it into 20 ms frames on the audio thread
  (an AudioWorklet from a Blob; an analyser where there is none), and says
  when speech starts — dated from its first loud frame — and ends. Nothing is
  recorded or sent: the frames are levels, read and dropped.
- ✅ **The rule is the spec's own** (§6.5, `vad.ts`, pure, 8 tests): 12 dB over
  the noise floor, sustained 250 ms (EC-11.14), dips between syllables
  forgiven. The floor follows the room down fast and up slow, never on speech,
  so a talker does not raise the bar against themselves; the bar rises 6 dB
  while the interviewer speaks (Trap 5 — echo cancellation leaves some); loud
  but FLAT energy (a fan switching on) is learned as the room, because
  syllables rise and fall and noise does not.
- **Decided: energy, not Silero, for the stop.** §6.5's barge-in rule is
  energy; it needs no model download and works on the demo laptop with no
  network. Silero (and Smart Turn) stay for endpointing — day 5 — where
  telling a pause from an end is the hard part.
- ✅ **`bargeIn(startedAt, { contest })`** stops every line still to be heard —
  the sentence playing, those queued, those still being asked of M11 (Trap 3:
  a stop that only silenced the speaker resumes mid-sentence) — and records
  `speech_started_at`. In our design a line lands whole before it is spoken,
  so there is no model stream to cancel; with v0.17.1's ordered requests, at
  most one sentence is being made, and nothing after it is asked for.
- ✅ **Final Boss contests, once a round** (§6.5; spec open decision 2 —
  **decided: on**, for the user's "test you, stress you"): the interviewer
  finishes up to 1.5 s before yielding. The line says `contested`, and the
  ledger lists it as its own stage, against no budget — the first live one
  read 1,763 ms against `barge_in`'s 600 before that.
- ✅ **The ledger** (Voice_Engine `0257db8`): `speech_started_at`, `contested`;
  stages `barge_in` (first word → silent, 600 ms = 250 + 350) and `contested`.
  45 tests.
- ✅ **M06's room: "Talk freely"** (M06 `cc4619c`): the mic open while the
  interviewer speaks; starting to talk stops them and starts dictation into
  the box. Off unless the student turns it on (remembered); a level meter;
  a blocked mic says how to allow it.
- **Measured live** (headless Edge, a fake microphone — room tone, then a
  voice at 6 s — over a panel's opening, M11's voices): Mock — first word to
  silence **261 ms** (speech decided at 260 ms, stopped in 1 ms; 56 of 221
  characters heard). Final Boss — the contest held 1.5 s, then stopped in 1 ms.
- **Next: day 4**, server ASR with word timestamps — the student's answer as
  audio, so the end of speech, not the send button, starts the clock.

### 2026-10-06 — The panel speaks, each in their own voice

- ✅ **M06's panel** (FR-6.3; M06 `d8a86ec`, `18c8c66`, `6e51c0a`): seated from
  the personas' data, introduced at the start, handing over in two voices,
  an expert's follow-up and the take-back, someone sitting in on a panel of
  one. Every line records who said it, part by part.
- ✅ **Each part in its speaker's voice** (`@ai/core` v0.17.0 `cacf1bb`):
  `speak([{ text, personaId, voiceId, id }, …])` says every sentence in its own
  speaker's voice — M11's cast voice, or the browser voice their `voice_id`
  picks; the ledger keeps the line as one line; `speakingPart` lights the
  right face. Heard live: Priya (`chatterbox-default`), Arjun
  (`indictts-022743`), Vikram (`indictts-063175`) in one opening.
- ✅ **Fixed: "Dr. Raghavan" was split after "Dr."** — a voice said "Dr." alone
  and paused, and M11 made two clips. A title's full stop no longer ends a
  sentence, and is said "Doctor".
- ✅ **Fixed: a line's first sentence waited behind its last** (v0.17.1
  `5e2ac60`). Every sentence was asked of M11 at once; M11 makes one at a
  time and which request won its lock was a race — a panel's opening waited
  five seconds while "Expect a follow-up or two." was made first. Sentences
  are now asked in speaking order, each when the one before is made; the
  next is made while the first plays. Throughput unchanged.

### 2026-10-06 — Day 7 pulled forward: the interviewers' own voices

- ✅ **Chatterbox Turbo on the server, via ONNX** (Voice_Engine `2aed9bb`):
  `tts.py` runs ResembleAI's ONNX export with no PyTorch, sampling as the
  PyTorch model does (temperature 0.8, top-p 0.95) — the model card's greedy
  loop spoke slower. `GET /v1/voice/engine` (off / loading / ready / failed),
  `GET /v1/voice/cast`, `POST /v1/voice/speak` (one sentence → 24 kHz WAV in
  the cast voice; signed-in callers; 503 until ready, so the browser voice
  speaks meanwhile). Every sentence is cached in memory and on disk: said
  once, instant after — which is what makes "repeat" (FR-11.13) instant.
  Synthesis is one at a time; two at once on a CPU only make both late. The
  model loads in the background at boot (~22 s).
- ✅ **The cast** (`voices/cast.json`, the user's picks after the blind
  test): Meera → IndicTTS 123823, Sunita → 017689, Arjun → 022743,
  Dr. Raghavan → 103607, Vikram → 063175 (all IndicTTS, IIT Madras, CC BY
  4.0, recorded for speech synthesis), Priya → Chatterbox's own voice, Kabir →
  DailyTalk speaker 0 (CC BY-SA, academic use). Seven personas, seven voices
  (FR-11.21). `ATTRIBUTION.md` credits each; the voice check shows the credits
  and says the voices are AI (India's IT Rules 2026 label synthetic audio).
- ✅ **The voice check speaks in them** (Voice_Engine `90063c9`): each
  interviewer in the voice students will hear, with whether it is ready.
- **Measured on this laptop** (i7-1260P, fp32): ready in 22 s; a line ~2.1×
  real time (Arjun's greeting 4.8 s); a cached line 0 ms. **The user's call:
  speed does not matter now — better machines later.** Live lines need a GPU
  box or the speculative pre-rendering idea in §0; neither is done.
- **Decided: Chatterbox replaces Kokoro / HeadTTS as tier 1** — the blind
  listening test chose it for sounding human, which is the user's measure
  ("not about accent — whether it sounds human").

### 2026-10-05 — Day 2: the latency ledger, and the first honest numbers

- ✅ **The browser records every spoken line** (Platform_Core `6791beb`, tag
  **v0.15.0**): landed, first audio, ended, or stop asked / stopped and why
  (mic, send, pause, end, repeat, off, leave; `barge_in` reserved for day 3),
  and how much was heard — through the word covering that point (§6.5). Rooms
  mark `answer_sent` and `first_token`. 7 tests (`npm test`).
- ✅ **M11 keeps them** (Voice_Engine `1f8ffe1`): `m11_line_timing`, marks not
  durations; `ledger.py` derives §11's stages on read and holds the targets;
  `POST/GET /v1/voice/{session_id}/timings` (idempotent on the browser's line
  id; the student who posts an interview's first line owns it; Platform_Core's
  stranger check pointed at `session_id`); `GET /v1/voice/timings/summary`
  staff-only, shown to staff on `/voice`. 23 tests; upstream probes stubbed
  so no test opens a socket.
- ✅ **M06 wired** (M06 `404647e`): the room passes its interview id, says why
  it stops the voice, marks the answer and the first token.
- **First numbers, live** (headless Edge, Neerja online voice, real model,
  6 lines in 4 interviews): answer sent → first audio p50 **1.11 s**, p95
  **1.41 s** (AC-11.1's 1.2 s — over); first token p50 718 ms / p95 957 ms;
  line on screen → first audio ~0.3 s, but **2–3 s for a page's first line**
  (the online voice's cold start); stop asked → stopped **6–9 ms**.
- **A false alarm, checked:** after End mid-line the browser was still
  "speaking" — the session's closing line ("That's time…"), said on purpose.
  The stop itself took 10 ms.
- **Next: day 3**, browser VAD barge-in — but see §0's entry of this evening:
  the voice's realism is now the open question, and its answer may reorder
  the days after it.

### 2026-10-05 — Day 1: the frame, and the voice client becomes M11's

- ✅ **The voice client moved to core** (Platform_Core `da448d5`, tag
  **v0.14.0**): `useInterviewerVoice` and `pickVoice` / `speakable` /
  `splitSentences` / `parseVoiceId` / `rateFor` / `kindOf`, with their 11
  tests (`npm test` in Platform_Core). M11's code, kept in core because M06's
  room and M11's voice check both use it and M14 will — §6's "graduate when a
  second module needs it", which day 1 triggered. M06 imports it from there
  (M06 `b3b401a`, core bumped in both package files and the lockfile).
- ✅ **The repo's frame** (Voice_Engine `77511e4`, `main`): `module.json`
  (M06 optional, with a sentence), ports 8111 / 5211 (8211 reserved for the
  WebSocket), the launcher (`start_voice.bat`, `start.bat`, `scripts/`), the
  identity guard on the router before any route, Platform_Core's stranger
  check from the first commit, and a gate that reads Platform_Shell's live
  proxy table to hold `/v1/voice` to M11. 6 tests, ruff clean, clean `tsc`.
- ✅ **The voice check, `/voice`**: every M06 interviewer, read from M06's
  persona files (`/v1/interviews/personas` now carries `voice_id` and the
  opening line — M06 `b3b401a`), each with the browser voice chosen for it and
  a Play button; the interview voice's on/off switch; "Arjun, Vikram,
  Dr. Raghavan and Kabir share Prabhat's voice; Meera, Sunita and Priya share
  Neerja's" — FR-11.21 measured in the browser, not assumed; when M06 is down,
  one sample voice under M06's own sentence.
- ✅ **Mounted in the shell** (Platform_Shell `f64d03e`): `/v1/voice` → :8111,
  source aliased, Tailwind scans it, reached from Settings → Voice and Ctrl K
  "Hear your interviewers". `start.bat` starts M11 and the HOME card checks it.
- **Checked live** in headless Edge through the shell: 326 voices; each
  interviewer gets Neerja or Prabhat (natural) by kind, at its manner's pace
  (Meera 0.97); Play speaks the greeting and the button turns to Stop at once
  (an online voice takes ~1 s to start); the degraded path renders. The M06
  room, now on core's hook, says its opening whole and the follow-up after an
  answer — the same speak/cancel trace as before the move.
- **Found on the way, fixed first** (M06 `ddd6fa5`): StrictMode's dev-only
  remount ran the room's unmount `cancel()`, which silenced every first
  question. The cancel now waits a tick and runs only if the room is gone.
- **Next: day 2**, the latency ledger.

---

### 2026-10-05 — Revision 2: browser-first and free; M06 speaks

- ✅ **Research (2026-10-04):** a sweep of ~480 GitHub repositories — faces,
  TTS, ASR, turn-taking, voice-agent frameworks, AI interviewers — plus README
  and licence checks on the candidates. The verdicts are §0 below; the
  decisions are the spec's new §0 (Revision 2) and §15.6.
- ✅ **M06 ships the first slice** (`voice-core.ts`, `voice.ts`, `ui/Face.tsx`):
  each line of record read aloud in the persona's `voice_id`; the face's mouth
  moves on each word; the voice stops when the mic opens, the answer is sent or
  the session pauses; one button turns it off. Verified in a headless Edge:
  Meera (`en-IN-female-warm`) → "Microsoft Neerja Online (Natural) - English
  (India)" at 0.97; first audio ~1.1 s after the line lands (the online voice's
  fetch); word boundaries reported. The persona card now carries `voice_id`,
  validated at load.
- ⬜ Everything below is still M11's: streaming the first clause, a VAD-driven
  barge-in, server ASR with word timestamps, Kokoro for browsers without a
  neural voice, audio-driven lip-sync, and the latency ledger.
- **Hardware note:** the development laptop's Intel Arc A370M (4 GB) has no
  driver installed (Windows problem code 28). Once installed it runs Intel's
  OpenVINO notebooks for Kokoro, Whisper, Wav2Lip, Parler-TTS and Qwen3-TTS/ASR —
  useful for the device matrix (day 14). No CUDA either way.

---

## 0. Ideas and scouting

Things worth building that did not come from the spec — usually from reading
somebody else's implementation. **New ideas go at the top of this section.**

The rule we keep arriving at: borrow a **technique**, not a **component**. The
platform's contracts — character offsets, per-fact provenance, permanent
evidence — are more demanding than general-purpose tools assume, so integration
usually costs more than reimplementing the one idea we actually wanted.

**2026-10-06 — the user's verdict, and a mostly-Indian roster.** After the
blind listening test: Chatterbox's built-in voice and the DailyTalk clones
were "pretty close — use both"; the roster should mix Indian and foreign
accents, mostly Indian. The engine is therefore **Chatterbox Turbo (MIT)**,
with cloned voices; persona `voice_id`s already carry the accent (`en-IN-…`,
and `en-US-…` / `en-GB-…` for the foreign few).

- **Indian voices:** IndicTTS (SMT Lab, IIT Madras; MeitY consortium) —
  English recorded by native speakers of Indian languages *for speech
  synthesis*, CC BY 4.0 (credit "IndicTTS, SMT Lab, IIT Madras"), confirmed on
  IndiaAI's AIKosh. Read via `SPRINGLab/IndicTTS-English` (151,640 utterances,
  no speaker labels): 29 samples at even offsets → **21 distinct voices** by
  Chatterbox's own speaker encoder (cosine > 0.86 = same voice) → six cast by
  pitch band and mutual difference (`pick_voices.py`), 18 clips, all but one
  read back right by Whisper (one garbled the word under a `[chuckle]`).
  Trade-off: IndicTTS is READ speech, so its clones lean narration;
  conversational Indian references would come from Svarah (AI4Bharat,
  CC BY 4.0, spontaneous speech, 117 speakers — gated on Hugging Face, the
  user's account must accept) or the team's own recorded voices.
- **Speed, measured (i7-1260P CPU):** PyTorch ≈ 7–9 speech tokens/s (real
  time needs 25) → 4.5× too slow. ResembleAI's ONNX export: **q4 27.2 tok/s**
  (language model 0.9× real time, one-step decoder +0.47× → 1.4× overall),
  fp32 17.6 tok/s (1.9×), q8 2.0 tok/s (pathological here). All read back
  right; greedy decoding (the model card's) speaks slower than PyTorch's
  sampling. **Not live on a laptop CPU** — an 8 s line needs ~3 s of buffer.
  Live lines need a GPU server (one cohort-wide box); fixed lines pre-render
  on CPU.
- **Idea — speculative synthesis:** M05's next bank question is one of a few
  candidates known before the student finishes answering; rendering those
  while the student talks (60–120 s of slack) would make most questions
  instant even on CPU. Probes adapted to the answer cannot be pre-rendered.

**2026-10-05 (evening) — "it sounds like an AI": what makes a voice human.**
The user's verdict on the browser voice, and the question it opened: not the
accent — whether it sounds like a person. Researched the same evening; the
listening test is in `research/listening/` (Voice_Engine).

- **What listeners hear as human** (the research): turns follow each other
  after ~200 ms on average across 10 languages (Stivers et al., PNAS 2009);
  natural talk carries ~6 disfluencies per 100 words, and "uh" / "um" are
  signals of a short / long delay, not noise (Clark & Fox Tree 2002); filled
  pauses raise perceived authenticity and audible breaths beat silent pauses
  for naturalness and recall (Székely et al. 2019, 2020); listeners say
  "mm-hm" on a low-pitch cue, ~700 ms after it (Ward & Tsukahara 2000).
- **The deciding result — Sesame's CSM:** blind raters could not tell its
  single lines from real recordings (≈ 50/50), but with 90 s of conversation
  around them they consistently picked the human. The gap left is
  conversational behaviour — timing, pauses, interruptions, emphasis — not
  timbre. So: voice AND behaviour, or the uncanny valley.
- **Why ours sounds like an AI**, cause by cause: a newsreader-style engine;
  our own sentence-by-sentence utterances (prosody resets, a gap per
  sentence); lines written for the eye, not the ear; 1.1–1.4 s answer →
  voice and a 2–3 s cold start on a page's first line (day 2's ledger); no
  backchannels; no breaths, "hmm", laughter.
- **Engines, ranked by blind "more natural" votes** (Artificial Analysis
  Speech Arena, Sep 2026): ElevenLabs v4 1321 · Qwen-Audio 3.1 1292 ·
  Cartesia Sonic 3.6 1278 · **Gemini 3.8 Flash TTS 1275** — free tier per
  third-party guides, ≈ $0.81 / audio hour paid; a `style` field and inline
  `<breath>` `<chuckle>` `<sigh>` `<short pause>` `<throat-clearing>`; Voice
  Design (a voice from a description) and Voice Replication (from reference
  AND consent audio). Groq Orpheus is on our key but needs the org admin to
  accept its terms; $22 / M chars.
- **Open weights:** best ranked are non-commercial (Breeze TTS 2, Fish S2,
  Voxtral — research / NC licences). **Chatterbox Turbo (MIT, 350M)** clones
  from ~10 s and performs `[laugh]` `[chuckle]` `[cough]`, watermarked —
  measured on this laptop (i7-1260P, CPU): **≈ 4.5× slower than real time**
  (a 7 s line in ~30 s). Too slow to voice live lines here; fine for
  pre-rendering fixed lines once.
- **Cloning a voice from an open dataset** (the user's question): technically
  the same trick. Licences differ — LibriTTS-R / Hi-Fi TTS CC BY 4.0 (but
  audiobook narration, and a clone copies the style of its reference),
  DailyTalk CC BY-SA 4.0 (conversational, recorded for conversational TTS),
  Expresso CC BY-NC 4.0 (improvised dialogue, 26 styles). A dataset licence
  is not the speaker's consent to become a product voice (Hugging Face,
  "Voice cloning with consent"); a celebrity or character voice is out —
  Arijit Singh v. Codible Ventures (Bombay HC, July 2024) enjoined AI voice
  cloning without consent; India's IT Rules (in force 20 Feb 2026) require
  synthetic audio that passes for real to be labelled.
- **Open decisions (the user's):** a Gemini key for the test; accepting
  Orpheus's terms; real human voices — who records, with consent — which
  would revise FR-11.21's "no cloning of real people" to "only with written
  and recorded consent, never a public figure, revocable, labelled as AI".

**2026-10-05 — the free field, by component.** Adopt = in the Revision 2
build; evaluate = measured against the alternatives before choosing; avoid =
licence or hardware rules it out.

| Component | What it is | Licence | Runs on | Verdict |
|---|---|---|---|---|
| Browser speech synthesis | Edge: neural en-IN voices (Neerja, Prabhat) + Indian languages; Windows Heera/Ravi; macOS Veena/Rishi | browser API | browser | **Adopted** (M06, 2026-10-05) |
| Kokoro-82M via `kokoro-js` / HeadTTS | TTS with word timestamps and visemes; RTF 0.27 on WebGPU, 1.45 on WASM | Apache-2.0 / MIT | browser | Adopt as tier 1 — American English only, 90–330 MB download, so opt-in |
| Pocket TTS (Kyutai) | 100M-param TTS, ~200 ms to first audio, ~6× real time on 2 CPU cores | MIT code; voices licensed one by one | CPU server | Evaluate against Kokoro |
| KittenTTS | tiny CPU TTS (15–80M ONNX) | Apache-2.0 code; KittenTTS 2 weights under a community licence | CPU | Watch the licence |
| Piper | fast local TTS | now `piper1-gpl`, GPL-3.0 | CPU | Replaced by Kokoro |
| Indic Parler-TTS (AI4Bharat) | Indian-language TTS, 880M | Apache-2.0 | Arc (OpenVINO) or GPU | Evaluate for Indian-English voices |
| Veena (Maya Research) | Hindi, Hinglish and English TTS | Apache-2.0 | GPU | Server-only option |
| Groq Orpheus | managed streaming TTS, American voices | paid, $22 per 1M chars | API | Tier 2, behind a flag |
| Silero VAD + `ricky0123/vad` | voice activity detection in the browser | MIT / ISC | browser | Adopt |
| Smart Turn v3.2 (Pipecat) | semantic end-of-turn, 8 MB, ~10–65 ms CPU, 23 languages | BSD-2 (code and weights) | CPU | Adopt — replaces training our own |
| TEN VAD | VAD | Apache-2.0 + Agora non-compete | — | Avoid |
| Groq `whisper-large-v3-turbo` | ASR; free tier 2,000 requests/day | free tier, then $0.04/hour | API | Adopt as primary |
| `faster-whisper`, `whisper.cpp`, WhisperX | local ASR; word alignment | MIT, MIT, BSD-2 | CPU (GPU for large-v3 live) | Fallback; WhisperX for M12 |
| Moonshine | low-latency streaming ASR | MIT (streaming and English models) | CPU | Evaluate |
| Vosk `en-in` | offline Indian-English ASR, 36 MB / 1 GB | Apache-2.0 | CPU | Evaluate — WER 36–49 on NPTEL |
| Oriserve Whisper-Hindi2Hinglish-Apex | Whisper fine-tuned for Indian-accented English | open | CPU/GPU | Evaluate on Svarah |
| Pipecat / LiveKit Agents | voice-agent orchestration, interruptions | BSD-2 / Apache-2.0 | server | Borrow techniques; LiveKit's SFU for M14 |
| DeepInterview | an open AI interviewer (LiveKit + Kokoro + Whisper, fully local option) | Apache-2.0 | — | Reference; its crossfaded video-loop avatar |
| LAM + gsplat renderer + `wav2arkit` | realistic 3D head from one photo, lip-synced in the browser | Apache-2.0 / MIT / Apache-2.0 | browser | Face option B (spec §15.6) |
| TalkingHead + HeadAudio | stylised 3D head, lip-sync from audio | MIT | browser | Face option C |
| MuseTalk, LiveTalking, Ditto, LatentSync | photoreal real-time lip-sync | various | NVIDIA GPU | Out on our hardware |
| Duix | avatar toolkit | custom licence | — | Avoid |
| Wav2Lip | lip-sync (an OpenVINO notebook exists) | research only | Arc (OpenVINO) | Avoid for the product |

---

## 1. Where the module stands

| | |
|---|---|
| Status | **95% — every day of the build order that is M11's own work is done (2026-10-07).** Left: FR-11.20 on a faster machine, the nightly sat once and registered, and the "Later" list (hardware, the user's decisions, real students, M18). The voice client is M11's code in `@ai/core` (v0.30.0: one gapless track, photos, faces; a late sentence waits before its first word). |
| Spec | Written, and the source of every row below. |
| Scope | 22 functional requirements (18 of them P0), 9 acceptance metrics (4 release-blocking), 15 edge cases. |

### 1b. What the voice client already does (M11's, in `@ai/core` since v0.14.0)

| FR | What the browser voice does since 2026-10-05 (built in M06, M11's since day 1) | |
|---|---|---|
| FR-11.3 | Browser recognition in en-IN: final phrases into the answer box; no word timestamps — still M06's `speech.ts`, not counted here | 🟡 interim (M06) |
| FR-11.7 | The line read aloud after it lands, a sentence at a time — not a streamed first clause | 🟡 interim |
| FR-11.8 | The voice stops when the mic button is pressed — no VAD, not measured | 🟡 interim |
| FR-11.13 | "Repeat the question" says it again, interrupting | 🟡 interim |
| FR-11.18 | The room is text-first: every spoken line is on screen — M06's room, not counted here | ✅ in M06 |
| FR-11.21 | One voice per persona from its `voice_id`, paced by its manner; Edge has two neural en-IN voices, so personas of a kind share one | 🟡 interim |

Everything else below is ⬜. That is the honest state and
it is worth writing down rather than leaving three sections saying
_To fill in._ — the point of this list is that the next session can start from
it instead of re-reading a six-hundred-line spec.

---

## 2. Functional requirements

Spec §4, verbatim. This is the authoritative list.

| FR | | Priority |
|---|---|---|
| FR-11.1 | ✅ WebRTC audio capture with echo cancellation and noise suppression — Revision 2's form: `getUserMedia` with echo cancellation, noise suppression and gain control (`useListening`, day 3), and the answer's audio cut from the same audio thread and sent per turn (day 4) | P0 |
| FR-11.2 | ✅ Real mic check with a live transcription round-trip — the room's noise floor (kept, and the VAD starts from it), then a sentence read aloud and read back by M11's recogniser, with how much came back and a word on the room (M11 `277c69e`, Core v0.22.0) | P0 |
| FR-11.3 | ✅ Streaming ASR with word-level timestamps — Revision 2's form: the words of record per turn with word times (day 4); the live caption from M11's recogniser where the browser has none — its last 10 s every 2.5 s, unsure words marked (Core v0.25.0) — and the browser's own elsewhere. Chunked, not a socket stream | P0 |
| FR-11.4 | ✅ VAD-based endpointing with a per-speaker adaptive threshold — §6.2's formula over the speaker's own pauses, learned across the session (`endpoint.ts`, day 5) | P0 |
| FR-11.5 | ✅ Semantic endpointing to avoid cutting incomplete utterances — Smart Turn v3.2 on M11 (`turn.py`); "not finished" waits longer, capped at 2.5 s (day 5) | P0 |
| FR-11.6 | ✅ Speculative LLM prefill on stabilised partial transcripts — strictly: used only for a byte-identical model request, so only for the exact words said (M06 `8152191`, `prefill.py`; Core v0.25.0). The spec's 15% tolerance is not used, by the user's rule | P1 |
| FR-11.7 | ✅ Streaming TTS with clause-level first chunk — sentences asked in speaking order, the first playing while the next is made; a long first sentence cut at its first clause (Core v0.23.0). Lines land whole from M06, so there is no token stream to start earlier | P0 |
| FR-11.8 | ✅ Barge-in: full stop of LLM + TTS + playback within 350 ms — the detector stops playback, the queue and the requests; 261 ms first word → silent, 1 ms after the decision (day 3). Lines land whole, so no model stream is running to cancel | P0 |
| FR-11.9 | ✅ Truncate the interviewer turn at `heard_up_to_ms` on barge-in — the cut (part and fraction) recorded on the turn; the transcript dims the rest and the interviewer model reads the line as heard (day 9, M06 `7b67a60`) | P0 |
| FR-11.10 | ✅ Calibrated silence per persona/mode with no UI change — 300–900 ms by the speaker's patience, Final Boss sometimes holding 1.8–3.5 s before a new question (Core `silence.ts`); the line appears as it is said, so nothing on screen gives the silence away (M06 `870f184`) | P0 |
| FR-11.11 | ✅ Backchannels on a separate bus, disabled in Final Boss — its own audio element at lower volume, never queued or on the ledger; words chosen by a probe of every voice ("Okay.", "I see.", "Sure."; "Mm-hm" broke up), by warmth; heard live five times in one interview | P1 |
| FR-11.12 | ✅ Note-taking pauses — the line said on its own, then 1.5 s of quiet inside the line (M06 `fda446f`, Core v0.23.0) | P1 |
| FR-11.13 | ✅ Repeat-last-utterance from cache — M11 caches every sentence it makes (memory and disk), so a repeat is instant; said by whoever asked it | P0 |
| FR-11.14 | ✅ Mid-turn modality switch preserving the partial transcript — Talk freely off (or hold-to-talk on) mid-answer writes what was said into the box (`flush`, Core v0.23.0; M06 `870f184`) | P0 |
| FR-11.15 | ✅ Low-confidence spans marked and excluded from evidence citation — carried with the answer to M06 (`3eeb88d`) and on to M13, which rejects a quote overlapping them (`382678a`); dotted in the transcript | P0 |
| FR-11.16 | ✅ Natural clarification on low ASR confidence — "didn't catch that" for an answer nobody could make out (`3eeb88d`); "did you say quick sort or quick select?" for an unsure word near one of the question's own terms, once a question and three a session, the reply judged with the answer (`28fdc2e`) | P1 |
| FR-11.17 | ✅ Degradation ladder down to push-to-talk — Revision 2's form: hold-to-talk (a big button, the interviewer stops on press, one upload per answer, a live caption) by choice, on a poor connection (`navigator.connection`, checked under DevTools throttling), after two drops, or after repeated echo; the browser's voice when the connection was poor at the start; two answers nobody could write down → typing (M06 `870f184`, `779146c`) | P0 |
| FR-11.18 | ✅ Live captions always on — the student's words as they speak (the browser's recognition, in Talk freely and while holding to talk), the words of record with unsure ones dotted, and the interviewer's line appearing as it is said | P0 |
| FR-11.19 | ✅ Per-turn audio stored, aligned to the transcript clock — with consent only (refused otherwise), the student's or staff's to read, deleted as files; played back in the notes beside the words (M11 `7d81077`, M06 `870f184`) | P0 |
| FR-11.20 | ⬜ p95 end-of-speech → first audio byte < 1.2 s — measured as stated (`end_to_audio`): p50 2.5 s through the latency harness (2026-10-07), synthesis on this CPU; needs a faster machine | P0 |
| FR-11.21 | ✅ Distinct voice per persona; no cloning of real people — seven personas, seven cast voices from speakers recorded for speech synthesis under CC BY (IndicTTS) / CC BY-SA (DailyTalk), each credited; no celebrity or character voice; labelled AI | P0 |
| FR-11.22 | ✅ Code-switch tolerance without penalty — the language detected, not forced: forced English invented English for 4 of 8 Hindi recordings; detection wrote all 8 as said and left 8 English recordings unchanged (`research/codeswitch`, M11 `c50b943`); M06 carries it, M13 scores content never language, the notes say so (M06 `1b45581`). Owed: real within-sentence Hinglish | P0 |

---

## 3. Acceptance gates

Spec §13. A **[GATE]** is release-blocking; the rest are tracked.

| AC | | Target |
|---|---|---|
| AC-11.1 **[GATE]** | ⬜ p95 end-of-speech → first audio — p50 2.5 s live through the harness (2026-10-07, n=4), over: synthesis on this CPU (~2× real time). The user's call: a faster machine later; `scripts/latency_harness.mjs` measures it there | ≤ 1.2 s |
| AC-11.2 **[GATE]** | 🟡 Barge-in stop — first word → silent 261 ms live (n=1, day 3), stopped 1 ms after the decision; needs the device matrix for a p95 | ≤ 350 ms |
| AC-11.3 **[GATE]** | 🟡 Premature cut-off rate — one live cut at a sentence pause (2026-10-06), fixed in Core v0.24.0; turns taken too soon are now counted (`cutShort`), so the rate can be measured | < 3% |
| AC-11.4 **[GATE]** | ⬜ ASR WER gap between accent groups | ≤ 8 points |
| AC-11.5 | ⬜ Overall WER on pilot audio | ≤ 12% |
| AC-11.6 | ⬜ "It kept cutting me off" complaints | < 5% of sessions |
| AC-11.7 | ⬜ Prefill cancel rate — measured by the latency harness from M06's own record (each answer's prefills tried and used); no number yet | 25–40% (outside → tune the window) |
| AC-11.8 | ⬜ Voice session completion rate vs text | within 10 points |
| AC-11.9 | ⬜ Push-to-talk fallback engages before abandonment | ≥ 80% of poor-network sessions |

---

## 4. Edge cases

Spec §12. Listed in full, because several are one afternoon each and are the
difference between a demo and a product.

| EC | | Expected behaviour |
|---|---|---|
| EC-11.1 | ✅ Candidate speaks over the very first word | Barge-in from t=0; the interviewer yields aside ("Sorry — go ahead."); M06 puts the question again (`28fdc2e`) |
| EC-11.2 | ⬜ Two people speaking (roommate) | Later: diarisation is M11's, the signal is M18 Integrity's — not built |
| EC-11.3 | ✅ Candidate silent for 45 s | One prompt, then a second, then offer to move on — M06's EC-6.1, spoken, and counted only while the interviewer is quiet and the student silent |
| EC-11.4 | ✅ Extremely fast speaker | The threshold shortens with their pauses (down to 400 ms) |
| EC-11.5 | ✅ Very slow / halting speaker | Lengthens to 1,400 ms; Smart Turn waits on "not finished"; a long answer gets a full second; a cut-off is learned from |
| EC-11.6 | ✅ Heavy background noise (hostel) | Noise suppression on; the mic check's floor seeds the VAD; headphones suggested by the mic check for a noisy room |
| EC-11.7 | ✅ Bluetooth headset cuts the first 200 ms | 300 ms of prefix kept; the mic check and the room warn — by name, rate, or a first word lost (Core v0.25.0, M11 `634c678`) |
| EC-11.8 | ✅ Echo (speakers, no headphones) | Echo cancellation on; the interviewer's own words heard back are not sent, headphones suggested, twice → hold-to-talk |
| EC-11.9 | ✅ ASR returns empty for a long utterance | The asker says their "didn't catch that" aloud; twice → typing |
| EC-11.10 | ✅ Candidate answers entirely in Hindi | Written as said, scored on content (M13's rule 4), noted in the report, never penalised |
| EC-11.11 | ✅ TTS mispronounces a technical term | The lexicon (per voice, probed: one entry), crowd-flaggable; big-O said as words (`notation.py`, probed) |
| EC-11.12 | ✅ Phone call interrupts on mobile | The clock stops (no pause spent), five seconds back in, the question again (M06 `7846920`, Core v0.25.0) |
| EC-11.13 | ✅ Tab backgrounded | The voice carries on; back from another tab after a line was said, the room says so with the way to hear it again |
| EC-11.14 | ✅ Barge-in right after the first syllable | The 250 ms sustain (`vad.ts`) |
| EC-11.15 | ✅ Network dies mid-answer | The answer's audio is kept and goes when the network is back; a failed send puts the words back in the box (Core `isOffline`, room `364bef9`) |

---

## 5. Data model

Spec §5 declares 7 types; six exist in Revision 2's form.

| Type | | |
|---|---|---|
| `AudioSessionConfig` | ⬜ | No WebRTC session in Revision 2; the mic's constraints live in `useListening` |
| `VADState` | ✅ | `@ai/core` `vad.ts` (`VadState`) |
| `TranscriptWord` | ✅ | `asr.py` `Word` — the word, its times, its segment's confidence |
| `ASRResult` | ✅ | `asr.py` — words, spans not to cite, the language detected |
| `UtteranceCompleteness` | ✅ | `turn.py` — Smart Turn's probability and verdict |
| `TTSRequest` | ✅ | `SpeakIn` — text, persona, voice |
| `TurnTiming` | ✅ | `m11_line_timing` and `ledger.py`'s stages, including `barge_in`, `contested`, `end_to_audio` |

---|---|---|
| `AudioSessionConfig` | ⬜ | Not written |
| `VADState` | ⬜ | Not written |
| `TranscriptWord` | ⬜ | Not written |
| `ASRResult` | ⬜ | Not written |
| `UtteranceCompleteness` | ⬜ | Not written |
| `TTSRequest` | ⬜ | Not written |
| `TurnTiming` | 🟡 | The browser's marks and §11's stages (`m11_line_timing`, `ledger.py`); `vad_decision` and `asr_final` wait for days 3–4 |

---

## 6. Deferred — inter-module

Not gaps in this module. Each needs a module that is not built or not wired
yet, and each is listed so it is not mistaken for an oversight.

**The voice client is in `@ai/core`** (v0.14.0, day 1) — M11's code, there
because M06 and M11 both use it and M14 will. Changes to it are planned here and
released as core versions; each consumer bumps its pin when ready. M06's
`speech.ts` (browser recognition) stays M06's until day 4's ASR route.

The spec names **M12, M13, M14, M18**. Until those are wired, anything
depending on them is blocked rather than unstarted, and the distinction
matters: one is work waiting to be done and the other is work that cannot
begin.

---

## 7. First moves

When work begins, the order that has worked on M01 and M02:

1. **The manifest and the ports.** `module.json` with `depends_on` declaring
   every upstream as OPTIONAL, each with an `on_missing` sentence a student
   can act on. Rule 2: a missing dependency narrows scope, never quality, and
   never silently.
2. **Identity before endpoints.** Router-level `enforce_access` on
   `ai_core.identity`, so no route can be written without it. A per-route
   check is the one somebody omits on the sixteenth endpoint, and the
   sixteenth endpoint is the one that leaks.
3. **The P0 that carries the module's name**, not the easiest one.
4. **Contract gates from the first commit** — every route has a client, every
   hook has a screen, every response field is declared on the frontend. M01
   shipped ten routes nobody could reach before these existed.
5. **A golden corpus before the third extraction fix**, not after. On M02 it
   found four real bugs within an hour of existing.

### Revision 2 build order (2026-10-05)

Replaces the spec's Revision 1 order (§14), which starts at the media worker
Revision 2 removes. Days are the spec's unit — a focused day each.

| Day | Task |
|---|---|
| 1 | ✅ Repo scaffold — `module.json`, ports from PORTS.txt, identity — and M06's `voice-core.ts` / `voice.ts` as the client baseline (moved to `@ai/core` v0.14.0; the voice check at `/voice`) |
| 2 | ✅ The latency ledger (`TurnTiming`) in the browser from day one; measure M06's browser voice honestly: first audio after a line lands, stop time after the mic (Core v0.15.0, M11 `1f8ffe1`; p95 answer → audio 1.41 s, cold start 2–3 s, stop 6–9 ms) |
| 3 | ✅ Barge-in (2026-10-06): §6.5's energy rule in the browser (`vad.ts`, `useListening`), the stop chain (`bargeIn`), Final Boss's contest, the ledger's `barge_in` stage; 261 ms measured live (Core v0.18.1, M11 `0257db8`, M06 `cc4619c`). Silero moves to day 5 |
| 4 | ✅ ASR route on Groq `whisper-large-v3-turbo` with word timestamps — confirmed; per turn; browser recognition the caption and the no-key fallback (M11 `2811fb6`, Core v0.19.0, M06 `76daf78`) |
| 5 | ✅ Smart Turn v3.2 for semantic endpointing, with the adaptive VAD threshold (FR-11.4, FR-11.5) — on M11, features checked against the reference, scored on real speech (M11 `5f3adf1`, Core v0.20.0–1, M06 `7cad60c`). Still owed: 200 labelled endings of students' own answers |
| 6 | 🟡 Accent WER across the ASR candidates; choose by the number — ✅ chosen: `whisper-large-v3-turbo`, 4.9% vs 5.2% on 1,785 words of IndicTTS (`research/wer/RESULTS.md`); ⬜ the gap between accent groups (AC-11.4) needs Svarah's labelled speakers or pilot audio |
| 7 | ✅ (pulled forward, 2026-10-06) TTS tier 1 is **Chatterbox Turbo via ONNX on the server**, cast per persona and cached (M11 `2aed9bb`, `90063c9`) — the blind listening test's choice, replacing Kokoro. Still open from this row: clause-level streaming (FR-11.7) and the lexicon (EC-11.11) |
| 8 | TTS tier 2 behind a flag: Groq Orpheus streaming; first-audio p95 against tiers 0 and 1 |
| 9 | ✅ `heard_up_to_ms` truncation (FR-11.9, M06 `7b67a60`); repeat from cache (FR-11.13); clarification on low confidence and unsure words never quoted (FR-11.15/16, M06 `3eeb88d`, M13 `382678a`) |
| 10 | ✅ Mic check with a live transcription round trip and a noise floor (FR-11.2); echo detection (EC-11.8) — M11 `277c69e`, Core v0.22.0 |
| 11 | ✅ Calibrated silence, backchannels and note-taking pauses from the persona files (FR-11.10 to FR-11.12) — Core v0.23.0, M06 `fda446f`, `870f184` |
| 12 | ✅ Per-turn audio stored with consent (FR-11.19, M11 `7d81077`); the push-to-talk ladder (FR-11.17, M06 `870f184`) |
| 13 | The face — only if chosen (spec §15.6): lip-sync from the audio itself (HeadAudio or `wav2arkit`) |
| 14 | 🟡 ✅ Latency harness (`scripts/latency_harness.mjs`; `--profile 2g`: the room moved to hold-to-talk, checked live) and the nightly (`scripts/nightly_latency.ps1`) — not yet sat end to end or registered; ⬜ the device matrix (hardware) |
