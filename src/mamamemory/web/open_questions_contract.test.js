// Contract tests of web/open_questions.js (slice open-questions, Seam 3), written by the slice tester
// from the sealed contract `.engine/slices/open-questions.md`, without the code.
import { test } from "node:test";
import assert from "node:assert/strict";

import { restore } from "./open_questions.js";

const SIGN_IN_AGAIN = "Щоб показати план, увійди знову.";

function planReply(planId, fingerprint) {
  return {
    text: "Пропоную: понеділок, 9 листопада, 10:15–10:45 — подзвонити нотаріусу. Записати?",
    question: { kind: "plan", id: planId, fingerprint },
    plan: {
      plan_id: planId,
      title: "подзвонити нотаріусу",
      start: "2026-11-09T10:15:00+01:00",
      end: "2026-11-09T10:45:00+01:00",
      fingerprint,
    },
  };
}

test("after_reload_open_question_returns_with_its_reply_to", () => {
  const reply = planReply("plan-7", "fp-7");
  const body = { replies: [reply], login_needed: false };
  const restored = restore(body);
  assert.deepEqual(restored.shown, [reply]);
  assert.deepEqual(restored.replyTo, { kind: "plan", id: "plan-7", fingerprint: "fp-7" });
  assert.equal(restored.loginNeeded, false);
});

test("reply_to_is_the_question_of_the_last_reply", () => {
  const ask = { text: "Скільки часу це займе?", question: { kind: "duration", id: "plan-1", fingerprint: null }, plan: null };
  const plan = planReply("plan-2", "fp-2");
  const restored = restore({ replies: [ask, plan], login_needed: false });
  assert.deepEqual(restored.shown, [ask, plan]);
  assert.deepEqual(restored.replyTo, { kind: "plan", id: "plan-2", fingerprint: "fp-2" });
});

test("empty_list_gives_null_reply_to", () => {
  const restored = restore({ replies: [], login_needed: false });
  assert.deepEqual(restored.shown, []);
  assert.equal(restored.replyTo, null);
  assert.equal(restored.loginNeeded, false);
});

test("login_needed_passes_through", () => {
  const login = { text: SIGN_IN_AGAIN, question: null, plan: null };
  const restored = restore({ replies: [login], login_needed: true });
  assert.deepEqual(restored.shown, [login]);
  assert.equal(restored.loginNeeded, true);
  // The last reply carries no question.
  assert.equal(restored.replyTo, null);
});
