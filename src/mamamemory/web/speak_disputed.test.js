// Disputed contract test of web/speak.js (slice read-aloud, Seam 4), written by the slice tester from the
// sealed contract `.engine/slices/read-aloud.md`, without the code. It takes one reading of question Q8 and
// is sealed only after the slice planner answers. The world is the one of speak_contract.test.js.
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveObjectURL } from "node:buffer";

import { speak } from "./speak.js";

const FAILED_TEXT = "Не вдалося озвучити.";

// ------------------------------------------------------------------ the world: fetch and a player

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function settle(ticks) {
  for (let i = 0; i < ticks; i += 1) await tick();
}

function urlOf(input) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** The part a player was handed: the response itself, a Blob, its object URL, an ArrayBuffer or bytes. */
async function partOf(audio) {
  if (audio && typeof audio.part === "number") return audio.part;
  let text;
  if (typeof audio === "string" && audio.startsWith("blob:")) text = await resolveObjectURL(audio)?.text();
  else if (typeof audio === "string") text = audio;
  else if (audio instanceof Blob) text = await audio.text();
  else if (audio instanceof ArrayBuffer) text = new TextDecoder().decode(audio);
  else if (ArrayBuffer.isView(audio)) text = new TextDecoder().decode(audio);
  const found = /audio-part-(\d+)/.exec(text ?? "");
  return found ? Number(found[1]) : NaN;
}

class World {
  constructor(count, { manual = false, failAt = null, rejectAt = null } = {}) {
    this.count = count;
    this.manual = manual;
    this.failAt = failAt;
    this.rejectAt = rejectAt;
    this.fetched = [];
    this.started = [];
    this.finishers = [];
    this.fetch = async (input, init = {}) => {
      const raw = init.body ?? (typeof input === "object" && input.text ? await input.text() : "{}");
      const body = JSON.parse(raw);
      this.fetched.push({ url: urlOf(input), method: (init.method ?? input.method ?? "GET").toUpperCase(), body });
      if (body.part === this.rejectAt) throw new TypeError("fetch failed");
      const headers = { "X-Parts": String(this.count) };
      if (body.part === this.failAt) {
        return new Response(JSON.stringify({ error: FAILED_TEXT }), {
          status: 502,
          headers: { ...headers, "Content-Type": "application/json" },
        });
      }
      const resp = new Response(`audio-part-${body.part}`, {
        status: 200,
        headers: { ...headers, "Content-Type": "audio/ogg", "Cache-Control": "no-store" },
      });
      return Object.assign(resp, { part: body.part });
    };
    this.play = (audio, ended) => {
      const index = this.started.length;
      this.started.push(audio);
      return new Promise((resolve) => {
        const finish = () => {
          if (typeof ended === "function") ended();
          resolve();
        };
        this.finishers[index] = finish;
        if (!this.manual) setImmediate(finish);
      });
    };
  }

  part(index) {
    return partOf(this.started[index]);
  }

  async playedParts() {
    return Promise.all(this.started.map(partOf));
  }

  finish(index) {
    this.finishers[index]();
  }

  async until(cond, ticks = 500) {
    for (let i = 0; i < ticks; i += 1) {
      if (cond()) return;
      await tick();
    }
    assert.fail(`never came: ${cond}`);
  }
}

const TEXT = "Завтра о десятій нотаріус. Візьміть паспорт і копію довідки з банку.";

// Q8: «одне озвучення за раз на відповідь» / «повторний натиск під час озвучення нічого не робить» holds in
// speak.js itself: a second call for the same text while the first plays makes no request and plays nothing.
test("second_speak_of_the_same_text_while_speaking_does_nothing", async () => {
  const world = new World(2, { manual: true });
  const first = speak(world.fetch, world.play, TEXT);
  await world.until(() => world.started.length === 1);
  await world.until(() => world.fetched.length === 2);

  speak(world.fetch, world.play, TEXT);
  await settle(20);
  assert.equal(world.fetched.length, 2, "the second press made a request");
  assert.equal(world.started.length, 1, "the second press played something");

  world.finish(0);
  await world.until(() => world.started.length === 2);
  world.finish(1);
  assert.equal(await first, null);
  await settle(20);
  assert.equal(world.fetched.length, 2);
  assert.deepEqual(await world.playedParts(), [0, 1]);
});
