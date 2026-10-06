/**
 * The shapes M11's screens read. Every field here is one a backend sends; a
 * field the screen needs and no route returns is a promise with nothing behind
 * it, so none is declared ahead of its route.
 */

/** One of M06's interviewers, as `GET /v1/interviews/personas` lists them. */
export interface Interviewer {
  id: string;
  name: string;
  title: string;
  style: string;
  /** `locale-kind-manner`, e.g. `en-IN-female-warm`. */
  voice_id: string;
  /** The line this interviewer opens with — what the check plays. */
  greeting: string;
}

/** Whether M11's own voice can speak (`GET /v1/voice/engine`). */
export interface EngineState {
  state: "off" | "loading" | "ready" | "failed";
  reason: string;
  precision: string;
  model: string;
}

/** One of M11's voices and where it comes from (`GET /v1/voice/cast`). */
export interface CastVoice {
  key: string;
  label: string;
  accent: "indian" | "foreign";
  register: "higher" | "lower";
  pitch_hz: number;
  source: string;
  licence: string;
  credit: string;
}

/** Who speaks for whom. */
export interface CastInfo {
  default: string;
  /** M06 persona id → voice key. */
  cast: Record<string, string>;
  voices: CastVoice[];
}

/** A word students flagged as said wrong (EC-11.11). */
export interface LexiconFlagCount {
  word: string;
  flags: number;
  /** The lexicon already respells it. */
  fixed: boolean;
  heard_as: string[];
}

/** One stage of the latency ledger across the cohort (`GET /v1/voice/timings/summary`). */
export interface StageSummary {
  name: string;
  label: string;
  n: number;
  p50: number | null;
  p95: number | null;
  /** The spec's p95 budget for the stage, when it has one (§11). */
  target_ms: number | null;
  /** The acceptance gate it is, if any (§13): "AC-11.1", "AC-11.2". */
  gate: string | null;
  /** p95 within target; null when unbudgeted or nothing measured. */
  met: boolean | null;
}

export interface TimingSummary {
  days: number;
  lines: number;
  sessions: number;
  stages: StageSummary[];
  /** Lines the browser refused to speak before a click. */
  blocked: number;
  /** Lines whose audio never began, for no reason the browser gave. */
  no_audio: number;
  /** Why lines were cut short: "mic", "send", "repeat", … */
  stops: Record<string, number>;
  voices: Record<string, number>;
}
