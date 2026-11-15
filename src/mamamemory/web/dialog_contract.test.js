// Contract tests of web/dialog.js (slice dialog, Seam 1), written by the slice tester from the sealed
// contract `.engine/slices/dialog.md`, without the code. Expected values are written by hand.
import { test } from "node:test";
import assert from "node:assert/strict";

import { mineText } from "./dialog.js";

test("said_is_the_value_trimmed_of_spaces", () => {
  assert.equal(mineText("said", "  купити хліб  "), "купити хліб");
  assert.equal(mineText("said", "купити хліб"), "купити хліб");
  assert.equal(mineText("said", "   завтра до лікаря"), "завтра до лікаря");
});

test("button_is_the_label_of_the_button", () => {
  assert.equal(mineText("button", "так"), "так");
  assert.equal(mineText("button", "Завтра зранку"), "Завтра зранку");
});

test("file_is_paperclip_space_and_the_file_name", () => {
  assert.equal(mineText("file", "фото.jpg"), "📎 фото.jpg");
  assert.equal(mineText("file", "аналізи березень.pdf"), "📎 аналізи березень.pdf");
});

test("empty_value_after_trimming_gives_empty_for_every_kind", () => {
  for (const kind of ["said", "button", "file", "other"]) {
    assert.equal(mineText(kind, ""), "", `kind ${kind}, value ""`);
    assert.equal(mineText(kind, "   "), "", `kind ${kind}, value "   "`);
  }
});

test("unknown_kind_gives_empty_even_with_a_value", () => {
  assert.equal(mineText("voice", "купити хліб"), "");
  assert.equal(mineText("", "так"), "");
  assert.equal(mineText("photo", "фото.jpg"), "");
});
