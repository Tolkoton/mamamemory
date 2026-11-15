// Contract tests of the slice add-simply, Seam 4: the button «Що я вмію» toggles one guide block. Written by the
// slice tester from the sealed contract `.engine/slices/add-simply.md`, without the code.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { nextGuide } from "./help.js";

test("next_guide_hidden_opens", () => {
  assert.equal(nextGuide(false), "open");
});

test("next_guide_shown_closes", () => {
  assert.equal(nextGuide(true), "close");
});

test("index_has_guide_block_outside_conversation", () => {
  const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
  const guide = html.search(/id=["']guide["']/);
  assert.ok(guide >= 0, "no element with id=guide in index.html");
  const open = html.search(/<section[^>]*id=["']conversation["']/);
  assert.ok(open >= 0, "no #conversation in index.html");
  const close = html.indexOf("</section>", open);
  assert.ok(close > open, "#conversation is not closed");
  assert.ok(guide < open || guide > close, "#guide stands inside #conversation");
});
