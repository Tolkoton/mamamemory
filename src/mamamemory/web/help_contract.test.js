// Contract tests of web/help.js (slice calm-open, Seam 3), written by the slice tester from the sealed
// contract `.engine/slices/calm-open.md`, without the code. `fetch` is a fake that records its calls.
import { test } from "node:test";
import assert from "node:assert/strict";

import { loadGuide } from "./help.js";

const GUIDE = "Я допомагаю планувати й пам'ятати справи.\nНе зрозумію — перепитаю.";

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function fakeFetch(answer) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url: String(url), options });
    return answer();
  };
  return { fn, calls };
}

function isGuideGet(call) {
  const method = call.options && call.options.method ? call.options.method.toUpperCase() : "GET";
  return call.url.endsWith("/api/guide") && method === "GET";
}

test("ok_200_gives_exactly_the_text_without_question", async () => {
  const fetch = fakeFetch(() =>
    response(200, { reply: { text: GUIDE, question: { kind: "plan", id: "p-1", fingerprint: "f-1" }, plan: null } }),
  );
  const found = await loadGuide(fetch.fn);
  assert.deepEqual(found, { text: GUIDE });
  assert.equal(fetch.calls.length, 1);
  assert.ok(isGuideGet(fetch.calls[0]), JSON.stringify(fetch.calls[0]));
});

test("status_401_gives_login", async () => {
  const fetch = fakeFetch(() => response(401, { detail: "not signed in" }));
  assert.equal(await loadGuide(fetch.fn), "login");
  assert.ok(isGuideGet(fetch.calls[0]), JSON.stringify(fetch.calls[0]));
});

test("other_status_gives_null", async () => {
  for (const status of [500, 403, 404]) {
    const fetch = fakeFetch(() => response(status, { detail: "fake" }));
    assert.equal(await loadGuide(fetch.fn), null, String(status));
  }
});

test("network_exception_gives_null", async () => {
  const thrown = async () => {
    throw new TypeError("fake: network down");
  };
  assert.equal(await loadGuide(thrown), null);
  const fetch = fakeFetch(() => Promise.reject(new TypeError("fake: offline")));
  assert.equal(await loadGuide(fetch.fn), null);
});
