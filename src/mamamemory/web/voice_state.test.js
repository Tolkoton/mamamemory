// Builder's own tests of voice_state.js (self-added behaviours, .engine/slices/voice-to-text.behaviors.md).
import { test } from "node:test";
import assert from "node:assert/strict";

import { initial, on } from "./voice_state.js";

const FAILED = "Не вдалося, спробуйте ще раз.";

test("a microphone that could not start returns to silence and shows the error", () => {
  let out = on(initial(null), { type: "mic" });
  out = on(out.state, { type: "recording_failed", error: FAILED });
  assert.deepEqual(out.actions, [{ do: "show_error", error: FAILED }]);
  out = on(out.state, { type: "mic" });
  assert.deepEqual(out.actions, [{ do: "start_recording" }]);
});

test("a transcribe without any response (status 0) returns to silence and shows the error", () => {
  let out = on(initial(null), { type: "mic" });
  out = on(out.state, { type: "send" });
  out = on(out.state, { type: "transcribed", status: 0, body: { error: FAILED } });
  assert.deepEqual(out.actions, [{ do: "show_error", error: FAILED }]);
  out = on(out.state, { type: "mic" });
  assert.deepEqual(out.actions, [{ do: "start_recording" }]);
});

test("the screen shows what is happening: listening, recognising, ready to send", async () => {
  const { statusOf } = await import("./voice_state.js");
  let state = initial(null);
  assert.deepEqual(statusOf(state), { label: "", recording: false, canSend: false });
  state = on(state, { type: "mic" }).state;
  assert.deepEqual(statusOf(state), { label: "Слухаю… Натисніть ➤, коли закінчите.", recording: true, canSend: true });
  state = on(state, { type: "send" }).state;
  assert.deepEqual(statusOf(state), { label: "Розпізнаю…", recording: false, canSend: false });
  state = on(state, { type: "transcribed", status: 200, body: { text: "Привіт" } }).state;
  assert.deepEqual(statusOf(state), { label: "Перевірте текст і натисніть ➤ ще раз.", recording: false, canSend: true });
});
