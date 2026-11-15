// Contract tests of the slice one-message, Seams 1, 1b and I1: one guard over all the buttons of one message.
// Written by the slice tester from the sealed contract `.engine/slices/one-message.md`, without the code.
import { test } from "node:test";
import assert from "node:assert/strict";

import { bindButtons } from "./buttons.js";

const OK = { text: "Записала.", question: null, plan: null };
const FAIL = { text: "Не вдалося, спробуйте ще раз.", question: null, plan: null, failed: true };
const THROWN = { text: "Не вдалося, спробуйте ще раз.", question: null, plan: null, failed: true };

function element() {
  return {
    disabled: false,
    removed: 0,
    remove() {
      this.removed += 1;
    },
  };
}

// A postFn that answers each call with the next item of `answers`: a reply, or "throw".
function scripted(answers, elements) {
  const calls = [];
  const fn = (url, body) => {
    calls.push({ url, body, disabled: elements.map((e) => e.disabled) });
    const next = answers.shift();
    if (next === "throw") return Promise.reject(new Error("network"));
    return Promise.resolve(next);
  };
  return { fn, calls };
}

// A postFn whose calls stay pending until the test resolves them.
function pending(elements) {
  const calls = [];
  const fn = (url, body) =>
    new Promise((resolve) => {
      calls.push({ url, body, disabled: elements.map((e) => e.disabled), resolve });
    });
  return { fn, calls };
}

test("yes_twice_is_one_call_and_second_press_is_null", async () => {
  const yes = element();
  const els = [yes];
  const post = scripted([OK, OK], els);
  const press = bindButtons(els, post.fn);
  assert.deepEqual(await press("/api/plan/confirm", { plan: "p1" }), OK);
  assert.equal(await press("/api/plan/confirm", { plan: "p1" }), null);
  assert.equal(post.calls.length, 1);
  assert.deepEqual(post.calls[0].url, "/api/plan/confirm");
  assert.deepEqual(post.calls[0].body, { plan: "p1" });
});

test("two_clarify_buttons_one_after_another_are_one_call", async () => {
  const a = element();
  const b = element();
  const els = [a, b];
  const post = scripted([OK, OK], els);
  const press = bindButtons(els, post.fn);
  assert.deepEqual(await press("/api/message", { text: "так, це задача" }), OK);
  assert.equal(await press("/api/message", { text: "ні, це нотатка" }), null);
  assert.equal(post.calls.length, 1);
  assert.deepEqual(post.calls[0].body, { text: "так, це задача" });
});

test("second_press_while_first_request_runs_is_null_without_call", async () => {
  const yes = element();
  const c1 = element();
  const els = [yes, c1];
  const post = pending(els);
  const press = bindButtons(els, post.fn);
  const first = press("/api/plan/confirm", { plan: "p1" });
  const second = await press("/api/message", { text: "інше" });
  assert.equal(second, null);
  assert.equal(post.calls.length, 1);
  post.calls[0].resolve(OK);
  assert.deepEqual(await first, OK);
  assert.equal(post.calls.length, 1);
});

test("while_request_runs_all_elements_are_disabled", async () => {
  const els = [element(), element(), element()];
  const post = pending(els);
  const press = bindButtons(els, post.fn);
  const first = press("/api/plan/confirm", { plan: "p1" });
  await Promise.resolve();
  assert.equal(post.calls.length, 1);
  assert.deepEqual(post.calls[0].disabled, [true, true, true], "not all disabled when postFn was called");
  assert.deepEqual(
    els.map((e) => e.disabled),
    [true, true, true],
    "not all disabled while the request runs",
  );
  post.calls[0].resolve(OK);
  await first;
});

test("failed_reply_enables_all_removes_none_and_next_press_calls_again", async () => {
  const els = [element(), element()];
  const post = scripted([FAIL, OK], els);
  const press = bindButtons(els, post.fn);
  assert.deepEqual(await press("/api/plan/confirm", { plan: "p1" }), FAIL);
  assert.deepEqual(
    els.map((e) => e.disabled),
    [false, false],
  );
  assert.deepEqual(
    els.map((e) => e.removed),
    [0, 0],
  );
  assert.deepEqual(await press("/api/plan/confirm", { plan: "p1" }), OK);
  assert.equal(post.calls.length, 2);
});

test("throwing_post_is_like_failed_and_returns_the_failed_reply", async () => {
  const els = [element(), element()];
  const post = scripted(["throw", OK], els);
  const press = bindButtons(els, post.fn);
  assert.deepEqual(await press("/api/plan/confirm", { plan: "p1" }), THROWN);
  assert.deepEqual(
    els.map((e) => e.disabled),
    [false, false],
  );
  assert.deepEqual(
    els.map((e) => e.removed),
    [0, 0],
  );
  assert.deepEqual(await press("/api/plan/confirm", { plan: "p1" }), OK);
  assert.equal(post.calls.length, 2);
});

test("success_removes_every_element_and_then_only_null", async () => {
  const els = [element(), element(), element()];
  const post = scripted([OK, OK, OK], els);
  const press = bindButtons(els, post.fn);
  assert.deepEqual(await press("/api/message", { text: "так" }), OK);
  for (const e of els) assert.ok(e.removed >= 1, "an element was not removed after success");
  assert.equal(await press("/api/message", { text: "так" }), null);
  assert.equal(await press("/api/plan/confirm", { plan: "p2" }), null);
  assert.equal(post.calls.length, 1);
});

test("test_I1_post_called_at_most_once_after_each_failure_and_never_after_success", async () => {
  // Several presses of different buttons, during requests, failed replies, a throwing postFn, then success.
  const els = [element(), element(), element()];
  const post = pending(els);
  const press = bindButtons(els, post.fn);

  // Before any failure: one call; presses during the request make none.
  const p1 = press("/api/plan/confirm", { plan: "p1" });
  assert.equal(await press("/api/plan/confirm", { plan: "p1" }), null);
  assert.equal(await press("/api/message", { text: "ні" }), null);
  assert.equal(post.calls.length, 1);
  post.calls[0].resolve(FAIL);
  assert.deepEqual(await p1, FAIL);

  // After the first failure: one call (another button), the repeated presses during it make none.
  const p2 = press("/api/message", { text: "ні" });
  assert.equal(await press("/api/message", { text: "так" }), null);
  assert.equal(post.calls.length, 2);
  post.calls[1].resolve(FAIL);
  assert.deepEqual(await p2, FAIL);

  // After the second failure: one call, answered with success.
  const p3 = press("/api/message", { text: "так" });
  assert.equal(await press("/api/plan/confirm", { plan: "p1" }), null);
  assert.equal(post.calls.length, 3);
  post.calls[2].resolve(OK);
  assert.deepEqual(await p3, OK);

  // After success: no call at all, whatever is pressed.
  assert.equal(await press("/api/plan/confirm", { plan: "p1" }), null);
  assert.equal(await press("/api/message", { text: "ні" }), null);
  assert.equal(await press("/api/message", { text: "так" }), null);
  assert.equal(post.calls.length, 3);
  assert.deepEqual(
    post.calls.map((c) => c.url),
    ["/api/plan/confirm", "/api/message", "/api/message"],
  );

  // A second guard: a throwing postFn counts as a failure, then success closes it.
  const els2 = [element()];
  const post2 = scripted(["throw", "throw", OK, OK], els2);
  const press2 = bindButtons(els2, post2.fn);
  assert.deepEqual(await press2("/api/plan/confirm", { plan: "p9" }), THROWN);
  assert.equal(post2.calls.length, 1);
  assert.deepEqual(await press2("/api/plan/confirm", { plan: "p9" }), THROWN);
  assert.equal(post2.calls.length, 2);
  assert.deepEqual(await press2("/api/plan/confirm", { plan: "p9" }), OK);
  assert.equal(post2.calls.length, 3);
  assert.equal(await press2("/api/plan/confirm", { plan: "p9" }), null);
  assert.equal(post2.calls.length, 3);
});
