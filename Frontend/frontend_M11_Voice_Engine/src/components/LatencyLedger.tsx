/**
 * The latency ledger, for the team (spec §11, §13; TODO §7 day 2).
 *
 * Every line the interviewer spoke, across the cohort, as stages with their
 * p50 and p95 against the spec's budget — "measure the browser voice
 * honestly". Staff only: it is the product's timing, not a student's, and the
 * route refuses students anyway (`require_role`).
 *
 * What it can see is what the browser can see today. "Answer sent" stands in
 * for the end of speech until VAD (day 3) and server ASR (day 4) find where
 * speech really ended; the table says so rather than labelling it otherwise.
 */

import { useState } from "react";

import { Card, SkeletonRows } from "@ai/core";

import { useTimingSummary } from "../api";
import type { StageSummary } from "../types";

const WINDOWS = [1, 7, 30] as const;

function ms(value: number | null): string {
  if (value === null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}

function Verdict({ stage }: { stage: StageSummary }) {
  if (stage.met === null) return <span className="text-ink-faint">—</span>;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-2xs font-semibold text-ink ${
        stage.met ? "border-confirmed-line bg-confirmed-soft" : "border-contested/40 bg-contested/10"
      }`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${stage.met ? "bg-confirmed" : "bg-contested"}`} />
      {stage.met ? "Within" : "Over"}
    </span>
  );
}

export function LatencyLedger() {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(7);
  const summary = useTimingSummary(days, true);
  const data = summary.data;

  return (
    <Card
      title="Latency ledger"
      icon="clock"
      meta="Staff"
      action={
        <div className="flex gap-1" role="group" aria-label="Window">
          {WINDOWS.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={days === d}
              onClick={() => setDays(d)}
              className={`h-7 rounded-md px-2.5 text-xs font-medium ${
                days === d ? "bg-brand text-on-brand" : "text-ink-soft hover:bg-surface-sunken"
              }`}
            >
              {d === 1 ? "24 h" : `${d} days`}
            </button>
          ))}
        </div>
      }
    >
      {summary.isLoading ? (
        <SkeletonRows label="Reading the ledger" rows={4} />
      ) : summary.isError || !data ? (
        <p className="text-sm text-ink-soft">The ledger couldn't be read just now.</p>
      ) : data.lines === 0 ? (
        <p className="text-sm text-ink-soft">
          No line has been spoken in an interview in this window. Each one is recorded as it is said.
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-soft">
            {data.lines} {data.lines === 1 ? "line" : "lines"} spoken in {data.sessions}{" "}
            {data.sessions === 1 ? "interview" : "interviews"}.
            {data.no_audio + data.blocked > 0 &&
              ` ${data.no_audio + data.blocked} never made a sound${data.blocked ? ` (${data.blocked} refused by the browser before a click)` : ""}.`}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-2xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="py-2 pr-3 font-medium">Stage</th>
                  <th className="py-2 pr-3 text-right font-medium">n</th>
                  <th className="py-2 pr-3 text-right font-medium">p50</th>
                  <th className="py-2 pr-3 text-right font-medium">p95</th>
                  <th className="py-2 pr-3 text-right font-medium">Budget</th>
                  <th className="py-2 font-medium">p95</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.stages.map((stage) => (
                  <tr key={stage.name}>
                    <td className="py-2 pr-3 text-ink">
                      {stage.label}
                      {stage.gate && <span className="ml-1.5 text-2xs text-ink-faint">{stage.gate}</span>}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink-soft">{stage.n}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink">{ms(stage.p50)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink">{ms(stage.p95)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink-faint">{ms(stage.target_ms)}</td>
                    <td className="py-2">
                      <Verdict stage={stage} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {Object.keys(data.stops).length > 0 && (
            <p className="mt-3 text-xs text-ink-faint">
              Cut short:{" "}
              {Object.entries(data.stops)
                .sort((a, b) => b[1] - a[1])
                .map(([why, n]) => `${n} by ${STOP_LABEL[why] ?? why}`)
                .join(" · ")}
            </p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-ink-faint">
            "Answer sent" stands in for the end of speech until the voice detector and server
            recognition arrive; "stopped" is when the browser reported the line stopped.
          </p>
        </>
      )}
    </Card>
  );
}

const STOP_LABEL: Record<string, string> = {
  barge_in: "the student speaking",
  mic: "the mic opening",
  send: "an answer sent",
  pause: "a pause",
  end: "the interview ending",
  repeat: "a repeat",
  off: "the voice turned off",
  leave: "leaving the room",
};
