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

import type { Interviewer } from "./types";

export const m11Keys = {
  deps: ["m11", "deps"] as const,
  interviewers: ["m11", "interviewers"] as const,
};

export function useDeps() {
  return useQuery({
    queryKey: m11Keys.deps,
    queryFn: () => api.get<DependencyStatus[]>("/v1/deps"),
    staleTime: 30_000,
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
