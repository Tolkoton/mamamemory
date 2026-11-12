// Contract tests of web/speak.js (slice speak-control, Seam 3 «зупинка черги» and I2), written by the slice
// tester from the sealed contract `.engine/slices/speak-control.md`, without the code. `fetch` answers with
// real `Response` objects; every answer carries `X-Parts`. Every fetch and every play is recorded with
// whether the world's signal was already aborted when it was made. A fetch or a play the test holds waits
// until the test lets it go; on the world's abort a held fetch rejects with an `AbortError` and a held play
// fulfils — what a real `fetch` and the player of the contract do on an aborted signal.
import { test } from "node:test";
import assert from "node:assert/strict";

import { speak } from "./speak.js";

const FAILED_TEXT = "Не вдалося озвучити.";
const LIMIT = { timeout: 10000 };

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function settle(ticks = 30) {
  for (let i = 0; i < ticks; i += 1) await tick();
}

let serial = 0;
function freshText() {
  serial += 1;
  return `Зупинка озвучення, текст номер ${serial}. Візьміть паспорт і довідку.`;
}

const abortError = () => new DOMException("The operation was aborted.", "AbortError");

/**
 * xParts: the `X-Parts` of every answer.
 * holdFetch: the parts whose fetch waits for `releaseFetch(part)` (or the abort).
 * autoPlay: every play ends on its own a tick later; otherwise it waits for `endPlay(i)` (or the abort).
 * rejectPlayAt / failAt: the play index whose promise rejects / the part the server answers 502.
 */
class StopWorld {
  constructor({ xParts = "3", holdFetch = [], autoPlay = false, rejectPlayAt = [], failAt = null } = {}) {
    this.xParts = xParts;
    this.holdFetch = holdFetch;
    this.autoPlay = autoPlay;
    this.rejectPlayAt = rejectPlayAt;
    this.failAt = failAt;
    this.controller = new AbortController();
    this.fetched = [];
    this.played = [];
    this.heldFetches = new Map();
    this.plays = [];

    this.fetch = (input, init = {}) => {
      const body = JSON.parse(init.body ?? "{}");
      const part = body.part;
      this.fetched.push({ part, signal: init.signal, afterAbort: this.controller.signal.aborted });
      if (this.controller.signal.aborted) return Promise.reject(abortError());
      const answer = () => {
        const headers = { "X-Parts": this.xParts };
        if (part === this.failAt) {
          return new Response(JSON.stringify({ error: FAILED_TEXT }), {
            status: 502,
            headers: { ...headers, "Content-Type": "application/json" },
          });
        }
        return new Response(`audio-part-${part}`, {
          status: 200,
          headers: { ...headers, "Content-Type": "audio/ogg", "Cache-Control": "no-store" },
        });
      };
      if (!this.holdFetch.includes(part)) return Promise.resolve(answer());
      return new Promise((resolve, reject) => {
        this.heldFetches.set(part, () => resolve(answer()));
        this.controller.signal.addEventListener("abort", () => reject(abortError()), { once: true });
      });
    };

    this.play = (audio, signal) => {
      const index = this.played.length;
      this.played.push({ audio, signal, afterAbort: this.controller.signal.aborted });
      if (this.controller.signal.aborted) return Promise.resolve();
      return new Promise((resolve, reject) => {
        const end = () => {
          if (this.rejectPlayAt.includes(index)) {
            reject(new DOMException("The element has no supported sources.", "NotSupportedError"));
          } else {
            resolve();
          }
        };
        this.plays.push(end);
        this.controller.signal.addEventListener("abort", () => resolve(), { once: true });
        if (this.autoPlay) setImmediate(end);
      });
    };
  }

  get signal() {
    return this.controller.signal;
  }

  abort() {
    this.controller.abort();
  }

  releaseFetch(part) {
    this.heldFetches.get(part)();
  }

  endPlay(index) {
    this.plays[index]();
  }

  async untilPlayed(count) {
    for (let i = 0; i < 300 && this.played.length < count; i += 1) await tick();
    return this.played.length;
  }

  async untilFetched(part) {
    for (let i = 0; i < 300 && !this.fetched.some((f) => f.part === part); i += 1) await tick();
    return this.fetched.some((f) => f.part === part);
  }

  async untilHeld(part) {
    for (let i = 0; i < 300 && !this.heldFetches.has(part); i += 1) await tick();
    return this.heldFetches.has(part);
  }

  fetchesAfterAbort() {
    return this.fetched.filter((f) => f.afterAbort).map((f) => f.part);
  }

  playsAfterAbort() {
    return this.played.filter((p) => p.afterAbort).length;
  }
}

/** Probes how a promise settled; `value` holds what it settled with. */
function probe(promise) {
  const result = { outcome: "pending", value: undefined };
  promise.then(
    (value) => {
      result.outcome = "fulfilled";
      result.value = value;
    },
    (error) => {
      result.outcome = "rejected";
      result.value = error;
    },
  );
  return result;
}

async function settled(result) {
  for (let i = 0; i < 300 && result.outcome === "pending"; i += 1) await tick();
  return result;
}

// ------------------------------------------------------------------ Seam 3

test("abort_during_part_0_of_3_returns_null_part_2_never_fetched_part_1_never_played", LIMIT, async () => {
  const world = new StopWorld({ xParts: "3" });
  const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
  assert.equal(await world.untilPlayed(1), 1, "part 0 must start playing");
  await settle();

  world.abort();
  await settled(result);
  await settle();

  assert.equal(result.outcome, "fulfilled", "a stop is not an error");
  assert.equal(result.value, null);
  assert.ok(!world.fetched.some((f) => f.part === 2), "part 2 must never be requested");
  assert.equal(world.played.length, 1, "part 1 (perhaps already requested) must not play");

  // The signal reached fetchFn as `signal` of the request and reached play; both are aborted now.
  assert.ok(world.fetched.length >= 1);
  for (const f of world.fetched) {
    assert.ok(f.signal instanceof AbortSignal, `fetch of part ${f.part} got no signal`);
    assert.equal(f.signal.aborted, true, `fetch of part ${f.part}: its signal is not aborted`);
  }
  assert.ok(world.played[0].signal instanceof AbortSignal, "play got no signal");
  assert.equal(world.played[0].signal.aborted, true, "the signal play got is not aborted");
});

// ------------------------------------------------------------------ the rules as they were, with a signal

test("with_a_signal_never_aborted_the_rules_are_as_they_were", LIMIT, async () => {
  const all = new StopWorld({ xParts: "3", autoPlay: true });
  assert.equal(await speak(all.fetch, all.play, freshText(), all.signal), null, "every part played");
  assert.equal(all.played.length, 3);

  const rejected = new StopWorld({ xParts: "3", autoPlay: true, rejectPlayAt: [1] });
  assert.equal(await speak(rejected.fetch, rejected.play, freshText(), rejected.signal), FAILED_TEXT);
  assert.equal(rejected.played.length, 2, "a part after a rejected play must not play");

  const failing = new StopWorld({ xParts: "3", autoPlay: true, failAt: 2 });
  assert.equal(await speak(failing.fetch, failing.play, freshText(), failing.signal), FAILED_TEXT);
});

// ------------------------------------------------------------------ I2

test("test_I2_speak_control_after_abort_no_new_request_no_new_play_and_null", LIMIT, async () => {
  const check = async (label, world, result) => {
    await settled(result);
    await settle();
    assert.equal(result.outcome, "fulfilled", `${label}: a stop is not an error`);
    assert.equal(result.value, null, `${label}: speak must return null`);
    assert.deepEqual(world.fetchesAfterAbort(), [], `${label}: parts requested after the abort`);
    assert.equal(world.playsAfterAbort(), 0, `${label}: parts handed to the player after the abort`);
  };

  // Before the first request: the signal is aborted before speak is called (1 and 3 parts).
  for (const xParts of ["1", "3"]) {
    const world = new StopWorld({ xParts });
    world.abort();
    const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
    await check(`aborted before the call, X-Parts ${xParts}`, world, result);
    assert.equal(world.fetched.length, 0, "aborted before the call: nothing may be requested");
  }

  // During the request of part 0.
  {
    const world = new StopWorld({ xParts: "3", holdFetch: [0] });
    const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
    assert.ok(await world.untilHeld(0), "part 0 must be requested");
    world.abort();
    await check("during the request of part 0", world, result);
    assert.equal(world.played.length, 0);
  }

  // During the play of every part k of 1 and of 3 parts, the earlier ones played to the end.
  for (const [xParts, k] of [["1", 0], ["3", 0], ["3", 1], ["3", 2]]) {
    const world = new StopWorld({ xParts });
    const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
    for (let i = 0; i < k; i += 1) {
      assert.equal(await world.untilPlayed(i + 1), i + 1);
      world.endPlay(i);
    }
    assert.equal(await world.untilPlayed(k + 1), k + 1, `part ${k} must start playing`);
    await settle();
    world.abort();
    await check(`during the play of part ${k} of ${xParts}`, world, result);
    assert.equal(world.played.length, k + 1);
  }

  // Between parts: part 0 ends and the abort comes before speak goes on.
  {
    const world = new StopWorld({ xParts: "3" });
    const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
    assert.equal(await world.untilPlayed(1), 1);
    await settle();
    world.endPlay(0);
    world.abort();
    await check("between part 0 and part 1", world, result);
    assert.equal(world.played.length, 1);
  }

  // During the request of part 1, part 0 already played to the end.
  {
    const world = new StopWorld({ xParts: "3", holdFetch: [1] });
    const result = probe(speak(world.fetch, world.play, freshText(), world.signal));
    assert.equal(await world.untilPlayed(1), 1);
    world.endPlay(0);
    assert.ok(await world.untilHeld(1), "part 1 must be requested");
    await settle();
    world.abort();
    await check("during the request of part 1", world, result);
    assert.equal(world.played.length, 1);
  }
});
