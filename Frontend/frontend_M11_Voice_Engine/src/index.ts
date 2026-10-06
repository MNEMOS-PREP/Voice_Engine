/**
 * M11 — Voice & Conversation Engine · public surface.
 *
 * The interviewer's voice itself is not exported here: it is `@ai/core`'s
 * `useInterviewerVoice` (v0.14.0), M11's code kept in core because more than
 * one module speaks. What this package adds is M11's own screens.
 */

export { m11Routes } from "./routes";
export { VoiceCheck } from "./components/VoiceCheck";
export { LatencyLedger } from "./components/LatencyLedger";
export { FlaggedWords } from "./components/FlaggedWords";
export { MicCheck } from "./components/MicCheck";
export { WordFlag } from "./components/WordFlag";
export {
  m11Keys,
  useCast,
  useDeps,
  useEngine,
  useFlagWord,
  useInterviewers,
  useLexiconFlags,
  useTimingSummary,
} from "./api";
export type {
  CastInfo,
  CastVoice,
  EngineState,
  Interviewer,
  LexiconFlagCount,
  StageSummary,
  TimingSummary,
} from "./types";
