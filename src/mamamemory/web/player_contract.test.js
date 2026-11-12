// Contract tests of web/player.js (slice f5-measure, Seam 2 «програвач» and invariant I2), written by the
// slice tester from the sealed contract `.engine/slices/f5-measure.md`, without the code. A fake `Audio`
// records the URL it was built with, takes listeners both through `addEventListener` and through the
// `on<event>` properties, and fires `ended` / `error` only when the test says; its `play()` returns a promise
// the test fulfils or rejects. A fake `urls` hands out `blob:fake/<n>` and records every revoke.
import { test } from "node:test";
import assert from "node:assert/strict";

import { makePlay } from "./player.js";

const tick = () => new Promise((resolve) => setImmediate(resolve));

async function settle(ticks = 20) {
  for (let i = 0; i < ticks; i += 1) await tick();
}

class FakeAudio {
  static built = [];

  constructor(url) {
    this.url = url;
    this.listeners = { ended: [], error: [] };
    this.onended = null;
    this.onerror = null;
    this.playCalls = 0;
    this.playPromise = new Promise((resolve, reject) => {
      this.resolvePlay = resolve;
      this.rejectPlay = reject;
    });
    this.playPromise.catch(() => {});
    FakeAudio.built.push(this);
  }

  addEventListener(type, fn) {
    (this.listeners[type] ??= []).push(fn);
  }

  removeEventListener(type, fn) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((f) => f !== fn);
  }

  play() {
    this.playCalls += 1;
    return this.playPromise;
  }

  pause() {}

  fire(type) {
    const event = { type, target: this, currentTarget: this };
    for (const fn of [...(this.listeners[type] ?? [])]) fn.call(this, event);
    const prop = this[`on${type}`];
    if (typeof prop === "function") prop.call(this, event);
  }
}

class FakeUrls {
  constructor() {
    this.created = [];
    this.revoked = [];
  }

  createObjectURL(blob) {
    const url = `blob:fake/${this.created.length + 1}`;
    this.created.push({ blob, url });
    return url;
  }

  revokeObjectURL(url) {
    this.revoked.push(url);
  }
}

/** One part: a play of a fresh blob, and a probe of how its promise settled. */
function start() {
  FakeAudio.built = [];
  const urls = new FakeUrls();
  const blob = new Blob(["OggS-part"], { type: "audio/ogg" });
  const promise = makePlay(FakeAudio, urls)(blob);
  const state = { outcome: "pending" };
  Promise.resolve(promise).then(
    () => {
      state.outcome = "fulfilled";
    },
    () => {
      state.outcome = "rejected";
    },
  );
  return { urls, blob, promise, state, audio: () => FakeAudio.built[0] };
}

const playError = () => new DOMException("play() failed", "NotAllowedError");

test("ended_fulfils_after_object_url_audio_and_play_and_revokes_the_url_once", async () => {
  const run = start();
  await settle();
  assert.equal(run.urls.created.length, 1);
  assert.equal(run.urls.created[0].blob, run.blob, "createObjectURL must get the blob");
  assert.equal(FakeAudio.built.length, 1);
  assert.equal(run.audio().url, run.urls.created[0].url, "new AudioCtor(url) with the object URL");
  assert.equal(run.audio().playCalls, 1, "audio.play() is called");

  run.audio().resolvePlay();
  await settle();
  assert.equal(run.state.outcome, "pending", "the part has not ended yet");

  run.audio().fire("ended");
  await settle();
  assert.equal(run.state.outcome, "fulfilled");
  assert.deepEqual(run.urls.revoked, [run.urls.created[0].url]);
});

test("error_event_rejects_and_revokes_the_url_once", async () => {
  const run = start();
  await settle();
  run.audio().resolvePlay();
  await settle();
  run.audio().fire("error");
  await settle();
  assert.equal(run.state.outcome, "rejected");
  assert.deepEqual(run.urls.revoked, [run.urls.created[0].url]);
});

test("rejected_audio_play_rejects_and_revokes_the_url_once", async () => {
  const run = start();
  await settle();
  run.audio().rejectPlay(playError());
  await settle();
  assert.equal(run.state.outcome, "rejected");
  assert.deepEqual(run.urls.revoked, [run.urls.created[0].url]);
});

test("error_event_and_rejected_audio_play_together_reject_and_revoke_the_url_once", async () => {
  const run = start();
  await settle();
  run.audio().fire("error");
  run.audio().rejectPlay(playError());
  await settle();
  assert.equal(run.state.outcome, "rejected");
  assert.deepEqual(run.urls.revoked, [run.urls.created[0].url]);
});

test("test_I2_the_first_event_settles_the_play_later_events_change_nothing_url_revoked_once", async () => {
  // Each step: "ended", "error", "play-ok" (audio.play() fulfils), "play-fail" (audio.play() rejects).
  const orders = [
    [["play-ok", "ended", "error"], "fulfilled"],
    [["play-ok", "ended", "ended"], "fulfilled"],
    [["ended", "play-fail"], "fulfilled"],
    [["ended", "error", "play-fail"], "fulfilled"],
    [["play-ok", "error", "ended"], "rejected"],
    [["error", "ended", "play-ok"], "rejected"],
    [["error", "error", "play-fail"], "rejected"],
    [["play-fail", "ended"], "rejected"],
    [["play-fail", "error", "ended"], "rejected"],
  ];
  for (const [steps, expected] of orders) {
    const run = start();
    await settle();
    for (const step of steps) {
      if (step === "play-ok") run.audio().resolvePlay();
      else if (step === "play-fail") run.audio().rejectPlay(playError());
      else run.audio().fire(step);
      await settle();
    }
    await settle();
    assert.equal(run.state.outcome, expected, steps.join(" → "));
    assert.deepEqual(run.urls.revoked, [run.urls.created[0].url], `${steps.join(" → ")}: revoked once`);
  }
});
