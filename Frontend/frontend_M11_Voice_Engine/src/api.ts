/**
 * M11's client — one hook per route a screen reads.
 *
 * `useInterviewers` reads M06's route, not M11's: the interviewers and the
 * voice each speaks in are authored in M06's persona files, and a second list
 * here would fall behind the next persona added there. Through the shell and
 * standalone alike, `/v1/interviews` is proxied to M06.
 */

import { useQuery } from "@tanstack/react-query";

import { api, type DependencyStatus } from "@ai/core";

import type { CastInfo, EngineState, Interviewer, TimingSummary } from "./types";

export const m11Keys = {
  deps: ["m11", "deps"] as const,
  interviewers: ["m11", "interviewers"] as const,
  summary: (days: number) => ["m11", "timings", "summary", days] as const,
  engine: ["m11", "engine"] as const,
  cast: ["m11", "cast"] as const,
};

/** Whether M11's voice is ready — polled while it warms up, then left alone. */
export function useEngine() {
  return useQuery({
    queryKey: m11Keys.engine,
    queryFn: () => api.get<EngineState>("/v1/voice/engine"),
    refetchInterval: (query) => (query.state.data?.state === "loading" ? 3000 : false),
    retry: false,
  });
}

/** Who speaks for whom, and each voice's credit. */
export function useCast() {
  return useQuery({
    queryKey: m11Keys.cast,
    queryFn: () => api.get<CastInfo>("/v1/voice/cast"),
    staleTime: Infinity,
    retry: false,
  });
}

export function useDeps() {
  return useQuery({
    queryKey: m11Keys.deps,
    queryFn: () => api.get<DependencyStatus[]>("/v1/deps"),
    staleTime: 30_000,
  });
}

/** The latency ledger across the cohort — staff only, so only asked for by staff. */
export function useTimingSummary(days: number, enabled: boolean) {
  return useQuery({
    queryKey: m11Keys.summary(days),
    queryFn: () => api.get<TimingSummary>(`/v1/voice/timings/summary?days=${days}`),
    enabled,
    staleTime: 15_000,
  });
}

export function useInterviewers() {
  return useQuery({
    queryKey: m11Keys.interviewers,
    queryFn: () => api.get<Interviewer[]>("/v1/interviews/personas"),
    staleTime: Infinity,
    retry: false,
  });
}
