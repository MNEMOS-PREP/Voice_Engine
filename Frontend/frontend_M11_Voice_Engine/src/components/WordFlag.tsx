/**
 * "A voice said a word wrong" — EC-11.11, crowd-flaggable.
 *
 * Anyone who hears an interviewer mispronounce a word tells us which word,
 * and how it sounded if they like. Staff see every flag (`FlaggedWords`);
 * the word is then said by the voice and read back by the recogniser
 * (`research/lexicon/probe.py`), and a respelling goes in the lexicon only if
 * it comes back right.
 */
import { useState } from "react";

import { Button } from "@ai/core";

import { useFlagWord } from "../api";

export function WordFlag({ voice }: { voice?: string | null }) {
  const [word, setWord] = useState("");
  const [heardAs, setHeardAs] = useState("");
  const flag = useFlagWord();

  if (flag.isSuccess) {
    return (
      <p className="text-xs text-ink-soft" role="status">
        Thanks — we'll check how “{flag.variables?.word}” is said, and fix it if it's wrong.{" "}
        <button type="button" className="text-brand underline" onClick={() => flag.reset()}>
          Another word
        </button>
      </p>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (word.trim()) flag.mutate({ word: word.trim(), heard_as: heardAs.trim() || null, voice: voice ?? null });
      }}
    >
      <label className="flex flex-col gap-1 text-2xs text-ink-faint">
        A word an interviewer said wrong
        <input
          value={word}
          onChange={(e) => setWord(e.target.value)}
          maxLength={60}
          placeholder="e.g. Dijkstra"
          className="h-8 w-40 rounded-md border border-line bg-surface px-2 text-sm text-ink"
        />
      </label>
      <label className="flex flex-col gap-1 text-2xs text-ink-faint">
        It sounded like (optional)
        <input
          value={heardAs}
          onChange={(e) => setHeardAs(e.target.value)}
          maxLength={60}
          className="h-8 w-40 rounded-md border border-line bg-surface px-2 text-sm text-ink"
        />
      </label>
      <Button size="sm" variant="secondary" type="submit" disabled={!word.trim() || flag.isPending}>
        {flag.isPending ? "Sending…" : "Flag it"}
      </Button>
      {flag.isError && <span className="text-2xs text-session-degraded">That didn't send — try again.</span>}
    </form>
  );
}
