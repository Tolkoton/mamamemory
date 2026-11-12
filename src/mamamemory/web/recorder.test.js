// Builder's own tests of recorder.js (self-added B3-B5, .engine/slices/voice-to-text.behaviors.md).
// The microphone and MediaRecorder are fakes: each getUserMedia call waits until the test resolves it.
import { test } from "node:test";
import assert from "node:assert/strict";

import { createRecorder } from "./recorder.js";

function fakeStream() {
  const track = { stopped: false, stop() { this.stopped = true; } };
  return { track, getTracks: () => [track] };
}

function world() {
  const asks = [];
  const recorders = [];
  const events = [];
  class FakeMediaRecorder {
    constructor(stream, options) {
      this.stream = stream;
      this.mimeType = options.mimeType;
      this.state = "inactive";
      recorders.push(this);
    }
    start() { this.state = "recording"; }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: "chunk" });
      queueMicrotask(() => this.onstop?.());
    }
  }
  const recorder = createRecorder({
    getUserMedia: () => new Promise((resolve, reject) => asks.push({ resolve, reject })),
    MediaRecorder: FakeMediaRecorder,
    Blob: class { constructor(parts, options) { this.parts = parts; this.type = options.type; } },
    mimeType: "audio/webm;codecs=opus",
    onAudio: (blob) => events.push(["audio", blob.type]),
    onNoAudio: () => events.push(["no_audio"]),
    onFailed: () => events.push(["failed"]),
  });
  return { recorder, asks, recorders, events };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a recording gives its audio once stopped and closes the microphone", async () => {
  const w = world();
  w.recorder.start();
  const stream = fakeStream();
  w.asks[0].resolve(stream);
  await settle();
  w.recorder.stop();
  await settle();
  assert.deepEqual(w.events, [["audio", "audio/webm;codecs=opus"]]);
  assert.equal(stream.track.stopped, true);
});

test("mic, send, mic while the first permission is pending: one microphone stays open", async () => {
  const w = world();
  w.recorder.start();
  w.recorder.stop();
  w.recorder.start();
  const first = fakeStream();
  const second = fakeStream();
  w.asks[0].resolve(first);
  w.asks[1].resolve(second);
  await settle();
  assert.equal(first.track.stopped, true, "the stream nobody wants any more is closed");
  assert.equal(second.track.stopped, false);
  assert.equal(w.recorders.length, 1);
  assert.deepEqual(w.events, [["no_audio"]]);
});

test("after a finished recording, send before the permission resolves does not hang", async () => {
  const w = world();
  w.recorder.start();
  w.asks[0].resolve(fakeStream());
  await settle();
  w.recorder.stop();
  await settle();
  w.recorder.start();
  w.recorder.stop();
  await settle();
  assert.deepEqual(w.events, [["audio", "audio/webm;codecs=opus"], ["no_audio"]]);
  const late = fakeStream();
  w.asks[1].resolve(late);
  await settle();
  assert.equal(late.track.stopped, true);
});

test("a refused microphone reports failure", async () => {
  const w = world();
  w.recorder.start();
  w.asks[0].reject(new Error("NotAllowedError"));
  await settle();
  assert.deepEqual(w.events, [["failed"]]);
});
