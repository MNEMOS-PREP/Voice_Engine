/**
 * The voice check — M11's first screen (TODO §7, day 1).
 *
 * Every interviewer, in the voice THIS browser gives them, one press to hear
 * each. It answers the two questions a student has before a spoken interview:
 * "will I hear it?" and "what will they sound like?" — and, for the team,
 * which voice the browser actually chose, which is the thing FR-11.21 (a
 * distinct voice per persona) depends on and nothing else on screen shows.
 *
 * The interviewers are read from M06's persona files through its route, never
 * listed here. When M06 is down the check still plays one sample voice and
 * says why, with M06's own sentence from `module.json`.
 *
 * The microphone half of the check (spec §2.3: a real transcription round
 * trip and a noise floor) is day 10.
 *
 * 2026-10-06: where M11's own voice is ready, each interviewer plays in the
 * Chatterbox voice the team cast for them (`voices/cast.json`) — what students
 * will hear — and the page credits every voice as its licence asks.
 */

import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Card,
  DegradedSection,
  PageHeader,
  SkeletonRows,
  VOICE_SUPPORTED,
  isStaff,
  parseVoiceId,
  pickVoice,
  useInterviewerVoice,
  useSession,
} from "@ai/core";

import { useCast, useDeps, useEngine, useInterviewers } from "../api";
import type { CastVoice, Interviewer } from "../types";
import { FlaggedWords } from "./FlaggedWords";
import { LatencyLedger } from "./LatencyLedger";
import { MicCheck } from "./MicCheck";
import { WordFlag } from "./WordFlag";

/** "Dr. Raghavan" sorts under R, as people look for him. */
function sortName(name: string): string {
  return name.replace(/^(Dr\.|Professor|Prof\.)\s+/, "");
}

/** Played when M06 cannot say who the interviewers are. */
const SAMPLE: Interviewer = {
  id: "sample",
  name: "A sample voice",
  title: "Indian English",
  style: "",
  voice_id: "en-IN-female-neutral",
  greeting: "Hello. This is how your interviewer will sound, and every line is on your screen as well.",
};

/** The browser's voices, as they arrive: Chrome lists none until `voiceschanged`. */
function useBrowserVoices(): { voices: SpeechSynthesisVoice[]; settled: boolean } {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() =>
    VOICE_SUPPORTED ? window.speechSynthesis.getVoices() : [],
  );
  // A browser with no voices at all never fires the event, so "none" is only
  // believed after a moment.
  const [settled, setSettled] = useState(voices.length > 0 || !VOICE_SUPPORTED);
  useEffect(() => {
    if (!VOICE_SUPPORTED) return;
    const synth = window.speechSynthesis;
    const load = () => {
      const now = synth.getVoices();
      setVoices(now);
      if (now.length) setSettled(true);
    };
    load();
    synth.addEventListener("voiceschanged", load);
    const timer = window.setTimeout(() => setSettled(true), 1500);
    return () => {
      synth.removeEventListener("voiceschanged", load);
      window.clearTimeout(timer);
    };
  }, []);
  return { voices, settled };
}

function languageName(locale: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(locale) ?? locale;
  } catch {
    return locale; // an engine without DisplayNames keeps the code
  }
}

/** "Microsoft Prabhat Online (Natural) - English (India)" → "Prabhat". */
function shortVoiceName(name: string): string {
  return name.replace(/^(Microsoft|Google|Apple)\s+/, "").split(/\s+(?:Online|Desktop|\(|-)/)[0] ?? name;
}

/**
 * What a row says about its voice: the browser's voice, whether it is a
 * natural one, and what the interviewer asked for — with the language only
 * when the browser could not match it, which is the case worth knowing.
 */
function describe(voiceId: string, chosen: SpeechSynthesisVoice | null): string {
  const spec = parseVoiceId(voiceId);
  const asked = [spec.kind, spec.manner && `${spec.manner} pace`].filter(Boolean).join(", ");
  if (!chosen) return `This browser's default voice · asked for ${languageName(spec.locale)}, ${asked}`;
  const natural = /\b(natural|neural)\b/i.test(chosen.name) ? " (natural)" : "";
  const sameLanguage = chosen.lang.replace("_", "-").toLowerCase() === spec.locale.toLowerCase();
  return `${shortVoiceName(chosen.name)}${natural} · ${asked}${sameLanguage ? "" : ` · asked for ${languageName(spec.locale)}`}`;
}

function initials(name: string): string {
  return name
    .replace(/^(Dr|Mr|Ms|Mrs)\.?\s+/i, "")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/** A speaker, drawn: the icon set has none, and M06's room draws its own. */
function SpeakerIcon({ playing }: { playing: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      {playing ? <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /> : <path d="M15.5 8.5a5 5 0 0 1 0 7" />}
    </svg>
  );
}

function InterviewerRow({
  who,
  chosen,
  cast,
}: {
  who: Interviewer;
  chosen: SpeechSynthesisVoice | null;
  /** The M11 voice cast for this interviewer, when M11's voice is ready. */
  cast: CastVoice | null;
}) {
  const voice = useInterviewerVoice(who.voice_id, { personaId: who.id, server: cast !== null });
  // An online voice takes about a second to start, and M11's a few more on
  // this laptop the first time a line is said. The press is answered at once —
  // the button turns to Stop — rather than looking ignored until then.
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (voice.speakingKey !== null) setPending(false);
  }, [voice.speakingKey]);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(() => setPending(false), cast ? 60_000 : 5000);
    return () => window.clearTimeout(timer);
  }, [pending, cast]);
  const speaking = pending || voice.speakingKey !== null;
  const play = () => {
    if (speaking) {
      setPending(false);
      voice.stop();
      return;
    }
    setPending(true);
    // A press here is a request to hear it, so it plays even when the student
    // has turned the interview voice off; `repeat` honours that switch, and
    // `replay` says the line it just remembered regardless.
    voice.repeat(who.greeting, who.id);
    if (!voice.enabled) voice.replay();
  };
  return (
    <li className="flex items-center gap-3 py-3">
      <span
        aria-hidden
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-brand transition-shadow ${
          speaking ? "ring-2 ring-brand ring-offset-2 ring-offset-surface" : ""
        }`}
      >
        {initials(who.name)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-ink">
          {who.name}
          {who.title && <span className="font-normal text-ink-soft"> · {who.title}</span>}
        </span>
        <span className="block truncate text-xs text-ink-faint">
          {cast
            ? `${cast.label} · ${cast.accent === "indian" ? "Indian English" : "a foreign accent"} · made by M11`
            : describe(who.voice_id, chosen)}
        </span>
      </span>
      <Button size="sm" variant="secondary" onClick={play} aria-pressed={speaking} aria-label={speaking ? `Stop ${who.name}` : `Hear ${who.name}`}>
        <SpeakerIcon playing={speaking} />
        {speaking ? "Stop" : "Play"}
      </Button>
    </li>
  );
}

/** Who speaks with which of this browser's voices — FR-11.21 is "one each". */
function voicesByPerson(people: Interviewer[], voices: SpeechSynthesisVoice[]): Map<string, SpeechSynthesisVoice | null> {
  return new Map(people.map((who) => [who.id, pickVoice(voices, parseVoiceId(who.voice_id))]));
}

/** "Arjun and Kabir share Prabhat's voice; …", or null when nobody shares. */
function sharedNote(people: Interviewer[], chosen: Map<string, SpeechSynthesisVoice | null>): string | null {
  const byVoice = new Map<string, string[]>();
  for (const who of people) {
    const voice = chosen.get(who.id);
    if (voice) byVoice.set(voice.name, [...(byVoice.get(voice.name) ?? []), who.name]);
  }
  const shared = [...byVoice.entries()].filter(([, names]) => names.length > 1);
  if (!shared.length) return null;
  const said = shared.map(([voice, names]) => `${listNames(names)} share ${shortVoiceName(voice)}'s voice`).join("; ");
  return `${said}. This browser has ${byVoice.size} ${byVoice.size === 1 ? "voice" : "voices"} for ${people.length} interviewers; each keeps their own pace.`;
}

function listNames(names: string[]): string {
  return names.length < 3 ? names.join(" and ") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

export function VoiceCheck() {
  const interviewers = useInterviewers();
  const deps = useDeps();
  const { voices, settled } = useBrowserVoices();
  const switchboard = useInterviewerVoice(null);
  const staff = isStaff(useSession());
  const engine = useEngine();
  const castInfo = useCast();
  const serverReady = engine.data?.state === "ready";
  const castFor = (who: Interviewer): CastVoice | null => {
    if (!serverReady || !castInfo.data) return null;
    const key = castInfo.data.cast[who.id] ?? castInfo.data.default;
    return castInfo.data.voices.find((v) => v.key === key) ?? null;
  };
  const credits = [...new Map((castInfo.data?.voices ?? []).map((v) => [v.credit, v.licence])).entries()];

  // By name: thirty-nine of them now (2026-10-07), and in file order a
  // student looking for "Meera" had to read the whole list.
  const people = interviewers.data?.length
    ? [...interviewers.data].sort((a, b) => sortName(a.name).localeCompare(sortName(b.name)))
    : interviewers.isError
      ? [SAMPLE]
      : [];
  const chosen = useMemo(() => voicesByPerson(people, voices), [people, voices]);
  const shared = sharedNote(people, chosen);
  const natural = voices.some((v) => /\b(natural|neural)\b/i.test(v.name) && v.lang.replace("_", "-") === "en-IN");
  const m06 = deps.data?.find((row) => row.module_id === "M06");

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="Voice"
        title="Hear your interviewers"
        subtitle="Each one speaks in the voice this browser gives them. Play one to check your sound before an interview."
        how={
          <>
            <p>
              The voice is your browser's own speech, so nothing you hear here is sent anywhere. Each
              interviewer asks for a kind of voice (Indian English, a woman's or a man's, a pace), and
              the browser's closest match speaks for them.
            </p>
            <p>
              Every line an interviewer says is also on screen, so an interview works with the sound
              off. Answering by voice, and the microphone check, come next.
            </p>
          </>
        }
      />

      {!VOICE_SUPPORTED ? (
        <Card title="This browser can't speak" icon="alert">
          <p className="text-sm text-ink-soft">
            Interviews still work here: every line is on screen. For the interviewer's voice, open
            this page in Microsoft Edge or Chrome.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card
            title="Voice in your interviews"
            icon="mic"
            action={
              <Button
                size="sm"
                variant={switchboard.enabled ? "secondary" : "primary"}
                onClick={() => switchboard.setEnabled(!switchboard.enabled)}
                aria-pressed={switchboard.enabled}
              >
                {switchboard.enabled ? "Turn off" : "Turn on"}
              </Button>
            }
          >
            <p className="text-sm text-ink-soft">
              {switchboard.enabled
                ? "On — the interviewer reads each question aloud."
                : "Off — questions appear on screen only. The buttons below still play."}
            </p>
            <p className="mt-2 text-xs text-ink-faint">
              {serverReady
                ? "Each interviewer speaks in their own voice, made by the voice service. A line it has not said before takes a few seconds the first time."
                : engine.data?.state === "loading"
                  ? "The interviewers' own voices are warming up — this browser's voice speaks until they are ready."
                  : "The interviewers' own voices are not running, so this browser's voice speaks for them."}
            </p>
            {settled && voices.length > 0 && !natural && (
              <p className="mt-2 text-xs text-ink-faint">
                The most natural Indian-English voices (Neerja and Prabhat) come with Microsoft Edge.
                This browser uses the closest it has.
              </p>
            )}
            {settled && voices.length === 0 && (
              <p className="mt-2 text-xs text-ink-faint">
                This browser lists no voices, so it may stay silent. Questions are still on screen.
              </p>
            )}
          </Card>

          {interviewers.isError && (
            <DegradedSection
              title="Your interviewers"
              needs={{ needs_module: "M06", needs_module_name: m06?.name ?? "Mock Interview Engine" }}
            >
              {m06?.on_missing}
            </DegradedSection>
          )}

          <Card title={interviewers.isError ? "A sample voice" : "Your interviewers"}>
            {interviewers.isLoading ? (
              <SkeletonRows label="Finding your interviewers" rows={4} />
            ) : (
              <ul className="divide-y divide-line">
                {people.map((who) => (
                  <InterviewerRow key={who.id} who={who} chosen={chosen.get(who.id) ?? null} cast={castFor(who)} />
                ))}
              </ul>
            )}
            {shared && !serverReady && (
              <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-ink-faint">{shared}</p>
            )}
            {serverReady && credits.length > 0 && (
              <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-ink-faint">
                AI voices, made with Chatterbox (Resemble AI, MIT). Voices from{" "}
                {credits.map(([credit, licence]) => `${credit} (${licence})`).join(" · ")}.
              </p>
            )}
            {serverReady && (
              // EC-11.11: a word said wrong is one a student noticed.
              <div className="mt-3 border-t border-line pt-3">
                <WordFlag />
              </div>
            )}
          </Card>

          <Card title="Your microphone" icon="mic">
            <MicCheck />
          </Card>
        </div>
      )}

      {staff && (
        <div className="mt-4 space-y-4">
          <LatencyLedger />
          <FlaggedWords />
        </div>
      )}
    </div>
  );
}
