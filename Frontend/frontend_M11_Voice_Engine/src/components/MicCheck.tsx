/**
 * Check your microphone — M11 day 10 (FR-11.2, spec §2.3, EC-11.6).
 *
 * Three steps, each one a student can act on:
 *   1. Quiet for three seconds: the room's noise floor, measured and kept
 *      for this browser — the listener starts from it in every interview, so
 *      a noisy hostel room has its raised bar from the first frame.
 *   2. Read one sentence aloud: M11's recogniser writes it down, and the page
 *      says how much came back — a real transcription round trip, not a
 *      level meter that only proves sound arrived.
 *   3. The verdict, in words: clear; mostly (closer to the mic); or barely
 *      (check the mic, somewhere quieter, headphones).
 *
 * Nothing is kept but the noise number. The sentence's audio goes to M11's
 * recogniser and is dropped there.
 */
import { useEffect, useRef, useState } from "react";

import {
  Button,
  firstWordLost,
  heardBack,
  looksLikeBluetooth,
  roomFrom,
  saveNoiseFloor,
  savedNoiseFloor,
  serverAsrAvailable,
  transcribeOnServer,
  useListening,
  type Room,
} from "@ai/core";

const SENTENCE = "I'm ready for my interview with the panel today.";
const QUIET_MS = 3000;

type Step = "idle" | "quiet" | "read" | "writing" | "done";

const ROOM_ADVICE: Record<Room, string> = {
  quiet: "Your room is quiet.",
  "some noise": "There's some noise in your room — fine, but headphones with a mic help.",
  noisy: "Your room is noisy. Headphones with a mic, or somewhere quieter, will make you easier to hear.",
};

export function MicCheck() {
  const [step, setStep] = useState<Step>("idle");
  const [room, setRoom] = useState<Room | null>(() => {
    const saved = savedNoiseFloor();
    return saved === null ? null : roomFrom(saved);
  });
  const [heard, setHeard] = useState<{ text: string; share: number; sure: number } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const began = useRef<number | null>(null);

  const listening = useListening({
    enabled: step === "quiet" || step === "read",
    keepAudio: true,
    onSpeechStart: (startedAt) => {
      if (step === "read") began.current = startedAt;
    },
    onSpeechEnd: (endedAt) => {
      if (step !== "read" || began.current === null) return;
      const audio = listening.audioBetween(began.current - 300, endedAt + 250);
      began.current = null;
      setStep("writing");
      if (!audio) {
        setProblem("The microphone stopped before the sentence was kept. Try again.");
        setStep("done");
        return;
      }
      void serverAsrAvailable().then((ready) => {
        if (!ready) {
          // No recogniser: the mic works (we heard speech), and that is all
          // this browser can be told.
          setHeard({ text: "", share: 1, sure: 1 });
          setStep("done");
          return;
        }
        transcribeOnServer(audio, SENTENCE)
          .then((result) => {
            setHeard({ text: result.text, share: heardBack(SENTENCE, result.text), sure: result.mean_confidence });
          })
          .catch(() => setProblem("The voice service couldn't write it down just now — your mic did pick you up."))
          .finally(() => setStep("done"));
      });
    },
  });

  // Step 1: three quiet seconds, then the floor.
  useEffect(() => {
    if (step !== "quiet" || !listening.active) return;
    const timer = window.setTimeout(() => {
      const floor = listening.floorDb();
      if (floor !== null) {
        saveNoiseFloor(floor);
        setRoom(roomFrom(floor));
      }
      setStep("read");
    }, QUIET_MS);
    return () => window.clearTimeout(timer);
  }, [step, listening.active, listening]);

  const start = () => {
    setHeard(null);
    setProblem(null);
    setStep("quiet");
  };

  const verdict = heard
    ? heard.text === ""
      ? "Your microphone works — we heard you. (The voice service isn't running, so we couldn't check the words.)"
      : heard.share >= 0.8
        ? "We heard you clearly."
        : heard.share >= 0.4
          ? "We heard most of it. Speaking a little closer to the mic will help."
          : "We could barely make you out. Check that the right microphone is chosen, or try somewhere quieter."
    : null;
  // EC-11.7: a Bluetooth headset in its calling mode clips the first moment
  // of speech — known by its name or rate, or seen: the first word is gone.
  const device = listening.device;
  const clipped = heard !== null && heard.text !== "" && firstWordLost(SENTENCE, heard.text);
  const bluetooth = device !== null && looksLikeBluetooth(device.label, device.sampleRate);
  const headsetAdvice = clipped
    ? "Your first word didn't come through — Bluetooth headsets often cut the start of speech. Take a breath before you start, or use a wired or built-in mic."
    : bluetooth && step === "done"
      ? "This looks like a Bluetooth headset, which can cut off your first word. Take a breath before you start, or use a wired or built-in mic."
      : null;

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-soft">
        Check your microphone before an interview: three quiet seconds to hear your room, then one sentence read
        aloud, written down the way your answers will be.
      </p>
      {step === "idle" || step === "done" ? (
        <Button size="sm" onClick={start}>
          {step === "done" ? "Check again" : "Check my microphone"}
        </Button>
      ) : (
        <p className="text-sm font-medium text-ink" role="status">
          {step === "quiet"
            ? listening.active
              ? "Stay quiet for three seconds…"
              : "Opening the microphone…"
            : step === "read"
              ? `Now read this aloud: “${SENTENCE}”`
              : "Writing down what you said…"}
        </p>
      )}
      {listening.error && <p className="text-xs text-session-degraded">{listening.error}</p>}
      {room && <p className="text-xs text-ink-soft">{ROOM_ADVICE[room]}</p>}
      {verdict && (
        <div className="rounded-lg border border-line bg-surface-sunken px-3 py-2 text-sm">
          <p className="font-medium text-ink">{verdict}</p>
          {heard && heard.text && (
            <p className="mt-1 text-xs text-ink-soft">
              We heard: “{heard.text}” ({Math.round(heard.share * 100)}% of the sentence)
            </p>
          )}
        </div>
      )}
      {headsetAdvice && <p className="text-xs text-session-degraded">{headsetAdvice}</p>}
      {problem && <p className="text-xs text-session-degraded">{problem}</p>}
    </div>
  );
}
