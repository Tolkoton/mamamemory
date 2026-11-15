// card.js — відповідь розкладу чи задач карткою (agenda-card): заголовок, розділи, рядки з часом.
// `make(tag, className, text)` створює елемент (текст — лише через `textContent`) з методом `append`.

/** Корінь `div.card` з картки сервера: h3, на розділ — h4 (якщо є заголовок) і ul, на рядок — li зі span-ами. */
export function buildCard(card, make) {
  const root = make("div", "card", null);
  root.append(make("h3", "card-title", card.title));
  for (const section of card.sections) {
    if (section.heading) root.append(make("h4", "card-heading", section.heading));
    const list = make("ul", "card-list", null);
    for (const item of section.items) {
      const row = make("li", "card-row", null);
      if (item.time) row.append(make("span", "card-time", item.time));
      row.append(make("span", "card-text", item.text));
      if (item.note) row.append(make("span", "card-note", item.note));
      list.append(row);
    }
    root.append(list);
  }
  return root;
}
