// Disputed contract tests of slice speak-control (web/speak_button.js and web/speak.js), written by the slice
// tester from the sealed contract `.engine/slices/speak-control.md`, without the code. Each test fixes the
// reading taken on one question to the contract (its id leads the name); the file is sealed only after the
// slice planner answers.
import { test } from "node:test";
import assert from "node:assert/strict";

import { onButton, initialButton } from "./speak_button.js";
import { speak } from "./speak.js";

const LIMIT = { timeout: 10000 };

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function settle(ticks = 30) {
  for (let i = 0; i < ticks; i += 1) await tick();
}

const abortError = () => new DOMException("The operation was aborted.", "AbortError");

/** fetch answers every part at once with `X-Parts: <xParts>`; play ends when the test says, or on the abort. */
class World {
  constructor(xParts) {
    this.xParts = xParts;
    this.controller = new AbortController();
    this.fetched = [];
    this.played = [];
    this.ends = [];
    this.fetch = (input, init = {}) => {
      const part = JSON.parse(init.body ?? "{}").part;
      this.fetched.push({ part, signal: init.signal });
      if (this.controller.signal.aborted) return Promise.reject(abortError());
      return Promise.resolve(
        new Response(`audio-part-${part}`, {
          status: 200,
          headers: { "X-Parts": this.xParts, "Content-Type": "audio/ogg", "Cache-Control": "no-store" },
        }),
      );
    };
    this.play = (audio, signal) => {
      this.played.push({ audio, signal });
      if (this.controller.signal.aborted) return Promise.resolve();
      return new Promise((resolve) => {
        this.ends.push(resolve);
        this.controller.signal.addEventListener("abort", () => resolve(), { once: true });
      });
    };
  }

  async untilPlayed(count) {
    for (let i = 0; i < 300 && this.played.length < count; i += 1) await tick();
    return this.played.length;
  }
}

test("Q2_finished_when_idle_gives_action_none", () => {
  const out = onButton(initialButton(), "finished");
  assert.equal(out.action, "none");
});

test("Q3_the_same_signal_object_is_passed_to_fetchFn_and_to_play", LIMIT, async () => {
  const world = new World("2");
  const signal = world.controller.signal;
  const call = speak(world.fetch, world.play, "Питання третє. Сигнал той самий.", signal);
  assert.equal(await world.untilPlayed(1), 1);
  world.ends[0]();
  assert.equal(await world.untilPlayed(2), 2);
  world.ends[1]();
  assert.equal(await call, null);
  assert.ok(world.fetched.length >= 2);
  for (const f of world.fetched) assert.equal(f.signal, signal, `fetch of part ${f.part}: another signal`);
  for (const p of world.played) assert.equal(p.signal, signal, "play got another signal");
});

test("Q4_after_a_stopped_call_returned_null_the_same_text_is_a_first_call_and_plays", LIMIT, async () => {
  const text = "Питання четверте. Той самий текст після зупинки.";
  const stopped = new World("2");
  const first = speak(stopped.fetch, stopped.play, text, stopped.controller.signal);
  assert.equal(await stopped.untilPlayed(1), 1);
  await settle();
  stopped.controller.abort();
  assert.equal(await first, null);
  await settle();
  assert.equal(stopped.played.length, 1, "the stopped call played on after the abort");

  const again = new World("2");
  const second = speak(again.fetch, again.play, text, again.controller.signal);
  assert.equal(await again.untilPlayed(1), 1, "the same text after a stop must play again");
  again.ends[0]();
  assert.equal(await again.untilPlayed(2), 2);
  again.ends[1]();
  assert.equal(await second, null);
});
