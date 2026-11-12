// Contract tests of web/speak.js (slice read-aloud, Seam 4), written by the slice tester from the sealed
// contract `.engine/slices/read-aloud.md`, without the code. `fetch` answers with real `Response`
// objects whose audio is the text `audio-part-<i>`; the player finds the part in whatever it is handed
// (the response, a Blob, an ArrayBuffer or bytes) and finishes when the test lets it, through the promise
// it returns and through a callback, if one is passed.
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

test("parts_play_in_order_and_next_is_requested_while_current_plays", async () => {
  const world = new World(3, { manual: true });
  const done = speak(world.fetch, world.play, TEXT);

  await world.until(() => world.started.length === 1);
  assert.equal(await world.part(0), 0);
  await world.until(() => world.fetched.some((f) => f.body.part === 1));
  await settle(20);
  assert.equal(world.started.length, 1, "part 1 must not start before part 0 ends");

  world.finish(0);
  await world.until(() => world.started.length === 2);
  assert.equal(await world.part(1), 1);
  await world.until(() => world.fetched.some((f) => f.body.part === 2));
  await settle(20);
  assert.equal(world.started.length, 2, "part 2 must not start before part 1 ends");

  world.finish(1);
  await world.until(() => world.started.length === 3);
  assert.equal(await world.part(2), 2);
  world.finish(2);

  assert.equal(await done, null);
  assert.deepEqual(
    world.fetched.map((f) => f.body),
    [0, 1, 2].map((part) => ({ text: TEXT, part })),
  );
  for (const f of world.fetched) {
    assert.ok(f.url.endsWith("/api/speak"), f.url);
    assert.equal(f.method, "POST");
  }
});

test("one_part_is_one_request_and_one_play", async () => {
  const world = new World(1);
  assert.equal(await speak(world.fetch, world.play, TEXT), null);
  assert.deepEqual(world.fetched.map((f) => f.body), [{ text: TEXT, part: 0 }]);
  assert.deepEqual(await world.playedParts(), [0]);
});

test("error_of_a_later_part_stops_and_returns_failed", async () => {
  const world = new World(3, { failAt: 1 });
  assert.equal(await speak(world.fetch, world.play, TEXT), FAILED_TEXT);
  assert.deepEqual(await world.playedParts(), [0]);
});

test("error_of_the_first_part_plays_nothing_and_returns_failed", async () => {
  const world = new World(3, { failAt: 0 });
  assert.equal(await speak(world.fetch, world.play, TEXT), FAILED_TEXT);
  assert.deepEqual(await world.playedParts(), []);
});

test("network_error_of_a_part_stops_and_returns_failed", async () => {
  const world = new World(2, { rejectAt: 1 });
  assert.equal(await speak(world.fetch, world.play, TEXT), FAILED_TEXT);
  assert.deepEqual(await world.playedParts(), [0]);
});
