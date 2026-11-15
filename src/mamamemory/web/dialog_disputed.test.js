// Disputed tests of web/dialog.js (slice dialog): each takes one reading of a question to the contract
// `.engine/slices/dialog.md` (its id in the test name). Sealed after the slice planner answers.
import { test } from "node:test";
import assert from "node:assert/strict";

import { mineText } from "./dialog.js";

test("Q1_said_is_trimmed_of_tabs_and_newlines_too", () => {
  assert.equal(mineText("said", "\n купити хліб\t"), "купити хліб");
  assert.equal(mineText("said", "\r\nзавтра до лікаря \n"), "завтра до лікаря");
});

test("Q2_whitespace_only_of_any_form_gives_empty_for_every_kind", () => {
  for (const kind of ["said", "button", "file", "other"]) {
    for (const value of ["\t", "\n", "\r\n", " \n\t "]) {
      assert.equal(mineText(kind, value), "", `kind ${kind}, value ${JSON.stringify(value)}`);
    }
  }
});

test("Q3_missing_value_gives_empty_without_throwing", () => {
  for (const kind of ["said", "button", "file"]) {
    assert.equal(mineText(kind, undefined), "", `kind ${kind}, undefined`);
    assert.equal(mineText(kind, null), "", `kind ${kind}, null`);
  }
});

test("Q4_button_label_is_trimmed", () => {
  assert.equal(mineText("button", "  так "), "так");
});

test("Q5_file_name_is_trimmed_after_the_paperclip", () => {
  assert.equal(mineText("file", " звіт.pdf  "), "📎 звіт.pdf");
});
