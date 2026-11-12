// Contract tests of web/speak.js (slice f5-measure, Seam 1 «тиша як успіх» and invariant I1), written by the
// slice tester from the sealed contract `.engine/slices/f5-measure.md`, without the code. `fetch` answers with
// real `Response` objects; the header `X-Parts` of every answer is what the test gives. The player records
// what it was handed and fulfils or rejects its promise as the test says. Every call speaks a text of its
// own, so no call is a repeat of another one still running.
import { test } from "node:test";
import assert from "node:assert/strict";

import { speak } from "./speak.js";

const FAILED_TEXT = "Не вдалося озвучити.";

const tick = () => new Promise((resolve) => setImmediate(resolve));

let serial = 0;
function freshText() {
  serial += 1;
  return `Завтра о десятій нотаріус, номер ${serial}. Візьміть паспорт.`;
}

/**
 * A world of `speak`.
 * xParts: the value of `X-Parts` on every answer (`null` → no header).
 * rejectPlayAt: the indexes of parts whose play promise is rejected.
 * failAt: the part the server answers 502; networkAt: the part whose fetch rejects.
 */
class World {
  constructor({ xParts, rejectPlayAt = [], failAt = null, networkAt = null }) {
    this.xParts = xParts;
    this.rejectPlayAt = rejectPlayAt;
    this.failAt = failAt;
    this.networkAt = networkAt;
    this.fetched = [];
    this.played = [];
    this.fetch = async (input, init = {}) => {
      const raw = init.body ?? (typeof input === "object" && input.text ? await input.text() : "{}");
      const body = JSON.parse(raw);
      this.fetched.push(body.part);
      if (body.part === this.networkAt) throw new TypeError("fetch failed");
      const headers = this.xParts === null ? {} : { "X-Parts": this.xParts };
      if (body.part === this.failAt) {
        return new Response(JSON.stringify({ error: FAILED_TEXT }), {
          status: 502,
          headers: { ...headers, "Content-Type": "application/json" },
        });
      }
      return new Response(`audio-part-${body.part}`, {
        status: 200,
        headers: { ...headers, "Content-Type": "audio/ogg", "Cache-Control": "no-store" },
      });
    };
    this.play = (audio, ended) => {
      const index = this.played.length;
      this.played.push(audio);
      return new Promise((resolve, reject) => {
        setImmediate(() => {
          if (this.rejectPlayAt.includes(index)) {
            reject(new DOMException("The element has no supported sources.", "NotSupportedError"));
            return;
          }
          if (typeof ended === "function") ended();
          resolve();
        });
      });
    };
  }

  /** `speak` of a fresh text, then a few more turns of the loop for anything it left running. */
  async speak() {
    const result = await speak(this.fetch, this.play, freshText());
    for (let i = 0; i < 30; i += 1) await tick();
    return result;
  }
}

test("play_rejected_on_part_0_stops_returns_failed_and_part_1_is_not_played", async () => {
  const world = new World({ xParts: "3", rejectPlayAt: [0] });
  assert.equal(await world.speak(), FAILED_TEXT);
  assert.equal(world.played.length, 1, "after a rejected play of part 0 no other part may play");
});

test("x_parts_of_part_0_not_an_integer_of_at_least_1_returns_failed_and_plays_nothing", async () => {
  for (const xParts of [null, "NaN", "0", "abc", "1.5", "-1"]) {
    const world = new World({ xParts });
    assert.equal(await world.speak(), FAILED_TEXT, `X-Parts ${xParts === null ? "absent" : xParts}`);
    assert.equal(world.played.length, 0, `X-Parts ${xParts === null ? "absent" : xParts}: play was called`);
  }
});

test("test_I1_first_speak_is_null_only_when_every_part_played_to_the_end", async () => {
  // Every part played to the end: one part (the lower edge of X-Parts) and three parts.
  for (const xParts of ["1", "3"]) {
    const world = new World({ xParts });
    assert.equal(await world.speak(), null, `X-Parts ${xParts}, every part played`);
    assert.equal(world.played.length, Number(xParts));
  }

  // Play rejected on a middle part and on the last part.
  for (const [xParts, at] of [["3", 1], ["3", 2], ["1", 0]]) {
    const world = new World({ xParts, rejectPlayAt: [at] });
    assert.equal(await world.speak(), FAILED_TEXT, `X-Parts ${xParts}, play of part ${at} rejected`);
    assert.equal(world.played.length, at + 1, `X-Parts ${xParts}: a part after the rejected ${at} played`);
  }

  // The server or the network fails on a part.
  assert.equal(await new World({ xParts: "3", failAt: 2 }).speak(), FAILED_TEXT, "502 on the last part");
  assert.equal(await new World({ xParts: "2", networkAt: 0 }).speak(), FAILED_TEXT, "network on part 0");

  // X-Parts absent or not an integer of at least 1, two parts long in truth.
  assert.equal(await new World({ xParts: null }).speak(), FAILED_TEXT, "X-Parts absent");
  assert.equal(await new World({ xParts: "0" }).speak(), FAILED_TEXT, "X-Parts 0");

  // The same text again after a call that failed on a rejected play is a first call: all parts play.
  const text = freshText();
  const failing = new World({ xParts: "2", rejectPlayAt: [0] });
  assert.equal(await speak(failing.fetch, failing.play, text), FAILED_TEXT);
  for (let i = 0; i < 30; i += 1) await tick();
  const again = new World({ xParts: "2" });
  assert.equal(await speak(again.fetch, again.play, text), null, "the same text after a failed call");
  assert.equal(again.played.length, 2);
});
