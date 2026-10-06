/**
 * Words students flagged as said wrong (EC-11.11), for the team — most
 * flagged first, and whether the lexicon already respells it.
 */
import { Card, SkeletonRows } from "@ai/core";

import { useLexiconFlags } from "../api";

export function FlaggedWords() {
  const flags = useLexiconFlags(true);
  return (
    <Card title="Words flagged as said wrong" icon="alert" meta="Staff">
      {flags.isLoading ? (
        <SkeletonRows label="Reading the flags" rows={3} />
      ) : flags.isError ? (
        <p className="text-sm text-ink-soft">The flags couldn't be read just now.</p>
      ) : (flags.data ?? []).length === 0 ? (
        <p className="text-sm text-ink-soft">Nobody has flagged a word yet.</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {(flags.data ?? []).map((f) => (
            <li key={f.word} className="flex flex-wrap items-baseline gap-x-3 py-2">
              <span className="font-medium text-ink">{f.word}</span>
              <span className="tabular-nums text-ink-soft">
                {f.flags} {f.flags === 1 ? "flag" : "flags"}
              </span>
              {f.heard_as.length > 0 && <span className="text-ink-faint">heard as “{f.heard_as.join("”, “")}”</span>}
              <span className={`ml-auto text-2xs ${f.fixed ? "text-confirmed" : "text-ink-faint"}`}>
                {f.fixed ? "In the lexicon" : "Not fixed yet — run research/lexicon/probe.py"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
