/**
 * Make every interviewer's stock phrases once, ahead (2026-10-09).
 *
 * What an interviewer says between questions — "Okay, let's leave that
 * there.", "Next question.", "That's a different question. Here's mine
 * again." — is the same words in the same voice in every interview. Made
 * once into M11's cache (kept on disk), they are instant from then on; made
 * when they are needed, they open a line with a pause. A live mock heard 7 s
 * before "Okay, let's leave that there." while the room's own warm-up was
 * still working through them (research/listening/gaps.md).
 *
 * Each phrase is cut into the pieces the room will ask for with the room's
 * own code (`@ai/core`'s `sentencesOf`), so the cache keys match exactly, and
 * planned as WARM lines: M11 makes them only while nothing is being said.
 * Names and topics are filled in per interview; those are made then.
 *
 *   node --experimental-strip-types scripts/warm_phrases.ts [M06] [M11]
 */
import { sentencesOf } from "../../Platform_Core/src/voice/core.ts";

const M06 = process.argv[2] ?? "http://127.0.0.1:8106";
const M11 = process.argv[3] ?? "http://127.0.0.1:8111";
// Not a real student: nothing here lands in anyone's history.
const WHO = {
  "X-Role": "student",
  "X-Candidate-Id": "1a7e0c10-0000-4000-8000-000000000012",
  "Content-Type": "application/json",
};

const response = await fetch(`${M06}/v1/interviews/phrases`, { headers: WHO });
if (!response.ok) throw new Error(`M06 said ${response.status} for /v1/interviews/phrases`);
const { personas } = (await response.json()) as { personas: Record<string, string[]> };

let phrases = 0;
let pieces = 0;
let toMake = 0;
for (const [persona, said] of Object.entries(personas)) {
  for (const text of said) {
    const { sentences } = sentencesOf([{ text, personaId: persona }], { personaId: persona, voiceId: null });
    const planned = await fetch(`${M11}/v1/voice/plan`, {
      method: "POST",
      headers: WHO,
      body: JSON.stringify({
        line: `phrases-${persona}`,
        priority: "warm",
        sentences: sentences.map((sentence) => ({ text: sentence.text, persona_id: persona })),
      }),
    });
    if (!planned.ok) throw new Error(`M11 said ${planned.status} for /v1/voice/plan`);
    const body = (await planned.json()) as { planned?: number };
    phrases += 1;
    pieces += sentences.length;
    toMake += body.planned ?? 0;
  }
}
console.log(
  `${phrases} phrases (${pieces} pieces) for ${Object.keys(personas).length} interviewers: ` +
    `${toMake} to make now, ${pieces - toMake} made already or shared.`,
);
