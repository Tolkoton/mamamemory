// Contract tests of web/player.js (slice speak-control, Seam 2 «зупинка програвача»), written by the slice
// tester from the sealed contract `.engine/slices/speak-control.md`, without the code. A fake `Audio` records
// the URL it was built with and every `pause()`, takes listeners both through `addEventListener` and the
// `on<event>` properties, and fires `ended` / `error` only when the test says; its `play()` returns a promise
// the test fulfils or rejects. A fake `urls` hands out `blob:fake/<n>` and records every revoke. The signal
// is a real `AbortController`'s.
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
    this.pauseCalls = 0;
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

  pause() {
    this.pauseCalls += 1;
  }

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

/** One part played with a signal: a probe of how its promise settled. */
function start(signal) {
  FakeAudio.built = [];
  const urls = new FakeUrls();
  const blob = new Blob(["OggS-part"], { type: "audio/ogg" });
  const promise = makePlay(FakeAudio, urls)(blob, signal);
  const state = { outcome: "pending" };
  Promise.resolve(promise).then(
    () => {
      state.outcome = "fulfilled";
    },
    () => {
      state.outcome = "rejected";
    },
  );
  return { urls, state, audio: () => FakeAudio.built[0] };
}

const playError = () => new DOMException("play() failed", "NotAllowedError");

test("already_aborted_signal_plays_nothing_creates_no_url_and_fulfils", async () => {
  const controller = new AbortController();
  controller.abort();
  const run = start(controller.signal);
  await settle();
  assert.equal(FakeAudio.built.length, 0, "no Audio may be built for an aborted signal");
  assert.equal(run.urls.created.length, 0, "no object URL may be created for an aborted signal");
  assert.equal(run.state.outcome, "fulfilled");
});

test("abort_during_play_pauses_revokes_the_url_once_and_fulfils", async () => {
  // Abort while audio.play() is already fulfilled and the part is sounding.
  const controller = new AbortController();
  const run = start(controller.signal);
  await settle();
  assert.equal(FakeAudio.built.length, 1);
  run.audio().resolvePlay();
  await settle();
  assert.equal(run.state.outcome, "pending", "the part has not ended yet");

  controller.abort();
  await settle();
  assert.ok(run.audio().pauseCalls >= 1, "audio.pause() must be called on abort");
  assert.equal(run.state.outcome, "fulfilled", "a stop is not an error");
  assert.deepEqual(run.urls.revoked, [run.urls.created[0].url]);
});

test("after_abort_late_ended_error_and_late_play_rejection_change_nothing", async () => {
  // Abort before audio.play() settles; then audio.play() rejects late, and ended / error fire late.
  const orders = [
    ["play-fail", "ended", "error"],
    ["error", "play-fail"],
    ["ended", "error"],
    ["play-ok", "error", "ended"],
  ];
  for (const steps of orders) {
    const controller = new AbortController();
    const run = start(controller.signal);
    await settle();
    controller.abort();
    await settle();
    for (const step of steps) {
      if (step === "play-ok") run.audio().resolvePlay();
      else if (step === "play-fail") run.audio().rejectPlay(playError());
      else run.audio().fire(step);
      await settle();
    }
    const label = `abort → ${steps.join(" → ")}`;
    assert.equal(run.state.outcome, "fulfilled", label);
    assert.ok(run.audio().pauseCalls >= 1, `${label}: audio.pause() was not called`);
    assert.deepEqual(run.urls.revoked, [run.urls.created[0].url], `${label}: revoked once`);
  }
});

test("abort_after_ended_or_error_changes_nothing_the_first_event_decides", async () => {
  const cases = [
    [["play-ok", "ended"], "fulfilled"],
    [["play-ok", "error"], "rejected"],
    [["play-fail"], "rejected"],
  ];
  for (const [steps, expected] of cases) {
    const controller = new AbortController();
    const run = start(controller.signal);
    await settle();
    for (const step of steps) {
      if (step === "play-ok") run.audio().resolvePlay();
      else if (step === "play-fail") run.audio().rejectPlay(playError());
      else run.audio().fire(step);
      await settle();
    }
    controller.abort();
    await settle();
    const label = `${steps.join(" → ")} → abort`;
    assert.equal(run.state.outcome, expected, label);
    assert.deepEqual(run.urls.revoked, [run.urls.created[0].url], `${label}: revoked once`);
  }
});
