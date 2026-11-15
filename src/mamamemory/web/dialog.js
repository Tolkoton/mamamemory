// dialog.js — мамине повідомлення в розмові перед відповіддю (dialog): сказане, натиснута кнопка, файл.

/** Текст маминого абзацу; порожнє значення чи невідомий вид — "". */
export function mineText(kind, value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (kind === "said" || kind === "button") return text;
  if (kind === "file") return `📎 ${text}`;
  return "";
}
