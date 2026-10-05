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
