// Contract tests of the slice agenda-card, Seam 4: `buildCard(card, make)` builds the card through `make` only.
// Written by the slice tester from the sealed contract `.engine/slices/agenda-card.md`, without the code.
// A fake `make(tag, className, text)` records every element; a write of textContent / innerHTML / innerText
// after `make` is recorded too. Classes are checked where the contract names one (div.card, h4.card-heading,
// span.card-time / card-text / card-note); the classes of h3, ul and li are not named and not checked.
import { test } from "node:test";
import assert from "node:assert/strict";

import { buildCard } from "./card.js";

function fakeMake() {
  const made = [];
  const writes = [];
  const make = (tag, className, text) => {
    const el = { tag, className, text, children: [] };
    el.append = (child) => {
      el.children.push(child);
    };
    for (const prop of ["textContent", "innerHTML", "innerText"]) {
      Object.defineProperty(el, prop, {
        get: () => undefined,
        set: (value) => {
          writes.push({ tag, prop, value });
        },
      });
    }
    made.push(el);
    return el;
  };
  return { make, made, writes };
}

const NAMED = { div: "card", h4: "card-heading" };

function classes(el) {
  return String(el.className ?? "").split(/\s+/).filter(Boolean);
}

// The tree as [tag, class the contract names (or null), text for h3 / h4 / span (or null), children].
function shape(el) {
  const tag = String(el.tag).toLowerCase();
  let cls = null;
  if (tag in NAMED) {
    assert.ok(classes(el).includes(NAMED[tag]), `${tag} has class ${el.className}, not ${NAMED[tag]}`);
    cls = NAMED[tag];
  } else if (tag === "span") {
    cls = classes(el).find((c) => ["card-time", "card-text", "card-note"].includes(c)) ?? String(el.className);
  }
  const text = ["h3", "h4", "span"].includes(tag) ? el.text : null;
  return [tag, cls, text, el.children.map(shape)];
}

const span = (cls, text) => ["span", cls, text, []];
const li = (...spans) => ["li", null, null, spans];
const ul = (...items) => ["ul", null, null, items];
const h3 = (text) => ["h3", null, text, []];
const h4 = (text) => ["h4", "card-heading", text, []];
const root = (...children) => ["div", "card", null, children];

test("tree_is_div_card_h3_then_heading_and_ul_per_section_in_card_order", () => {
  const card = {
    title: "На цей тиждень",
    sections: [
      {
        heading: "Вівторок, 10 листопада",
        items: [
          { time: "11:00", text: "Ярмарок", note: null },
          { time: "весь день", text: "Бабусин день", note: null },
        ],
      },
      { heading: "Четвер, 12 листопада", items: [{ time: "12:30", text: "Банк", note: null }] },
      { heading: "Задачі без часу", items: [{ time: null, text: "забрати посилку", note: null }] },
    ],
  };
  const fake = fakeMake();
  const result = buildCard(card, fake.make);
  assert.ok(fake.made.includes(result), "buildCard does not return an element made by make");
  assert.deepEqual(
    shape(result),
    root(
      h3("На цей тиждень"),
      h4("Вівторок, 10 листопада"),
      ul(
        li(span("card-time", "11:00"), span("card-text", "Ярмарок")),
        li(span("card-time", "весь день"), span("card-text", "Бабусин день")),
      ),
      h4("Четвер, 12 листопада"),
      ul(li(span("card-time", "12:30"), span("card-text", "Банк"))),
      h4("Задачі без часу"),
      ul(li(span("card-text", "забрати посилку"))),
    ),
  );
});

test("no_heading_no_time_no_note_make_no_such_elements", () => {
  const card = {
    title: "Задачі в списку",
    sections: [
      {
        heading: null,
        items: [
          { time: null, text: "оплатити світло", note: null },
          { time: null, text: "подзвонити нотаріусу", note: "до 13 листопада" },
        ],
      },
      { heading: "", items: [{ time: "14:00", text: "Лікар", note: null }] },
    ],
  };
  const fake = fakeMake();
  assert.deepEqual(
    shape(buildCard(card, fake.make)),
    root(
      h3("Задачі в списку"),
      ul(
        li(span("card-text", "оплатити світло")),
        li(span("card-text", "подзвонити нотаріусу"), span("card-note", "до 13 листопада")),
      ),
      ul(li(span("card-time", "14:00"), span("card-text", "Лікар"))),
    ),
  );
});

test("text_is_given_only_as_the_third_argument_of_make", () => {
  const card = {
    title: "На сьогодні",
    sections: [
      { heading: null, items: [{ time: null, text: "В календарі нічого немає.", note: null }] },
      { heading: "Задачі без часу", items: [{ time: null, text: "<b>аптека</b>", note: "до 9 листопада" }] },
    ],
  };
  const fake = fakeMake();
  buildCard(card, fake.make);
  assert.deepEqual(fake.writes, []);
  const texts = fake.made.map((el) => el.text).filter((t) => typeof t === "string" && t !== "");
  assert.deepEqual(
    texts.sort(),
    ["На сьогодні", "В календарі нічого немає.", "Задачі без часу", "<b>аптека</b>", "до 9 листопада"].sort(),
  );
});
