// Disputed contract tests of web/speak.js (slice f5-measure, Seam 1), written by the slice tester from the
// sealed contract `.engine/slices/f5-measure.md`, without the code. Each takes one reading of a question of
// the hand-in (Q1, Q2) and is sealed only after the slice planner answers. The world is the one of
// speak_silence_contract.test.js.
import { test } from "node:test";
import assert from "node:assert/strict";

import { speak } from "./speak.js";

const FAILED_TEXT = "Не вдалося озвучити.";

const tick = () => new Promise((resolve) => setImmediate(resolve));

let serial = 0;
function freshText() {
  serial += 1;
  return `Спірне читання ${serial}. Візьміть паспорт і копію довідки.`;
}

/** Every answer is 200 with `X-Parts: <xParts>`; every play ends at once. */
async function speakWith(xParts) {
  const played = [];
  const fetchFn = async (input, init = {}) => {
    const raw = init.body ?? (typeof input === "object" && input.text ? await input.text() : "{}");
    const body = JSON.parse(raw);
    return new Response(`audio-part-${body.part}`, {
      status: 200,
      headers: { "X-Parts": xParts, "Content-Type": "audio/ogg", "Cache-Control": "no-store" },
    });
  };
  const play = (audio, ended) => {
    played.push(audio);
    return new Promise((resolve) => {
      setImmediate(() => {
        if (typeof ended === "function") ended();
        resolve();
      });
    });
  };
  const result = await speak(fetchFn, play, freshText());
  for (let i = 0; i < 30; i += 1) await tick();
  return { result, played };
}

test("Q1_x_parts_with_digits_then_other_characters_returns_failed_and_plays_nothing", async () => {
  for (const xParts of ["2abc", "1;q", "3 parts"]) {
    const { result, played } = await speakWith(xParts);
    assert.equal(result, FAILED_TEXT, `X-Parts ${xParts}`);
    assert.equal(played.length, 0, `X-Parts ${xParts}: play was called`);
  }
});

test("Q2_x_parts_written_with_a_fraction_point_or_an_exponent_returns_failed_and_plays_nothing", async () => {
  for (const xParts of ["2.0", "1e0"]) {
    const { result, played } = await speakWith(xParts);
    assert.equal(result, FAILED_TEXT, `X-Parts ${xParts}`);
    assert.equal(played.length, 0, `X-Parts ${xParts}: play was called`);
  }
});
