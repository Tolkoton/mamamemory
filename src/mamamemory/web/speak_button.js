// speak_button.js — поправка F5 (speak-control): стан кнопки 🔊/⏹. Чистий модуль, без DOM (як voice_state.js).
// Кнопка ніколи не вимкнена: під час озвучення натиск зупиняє його.

const IDLE = { state: "idle", label: "🔊", disabled: false };
const SPEAKING = { state: "speaking", label: "⏹", disabled: false };
const STOPPING = { state: "stopping", label: "⏹", disabled: false };

/** Спокій: «🔊». */
export function initialButton() {
  return { ...IDLE };
}

/** Подія `press` чи `finished` → новий стан кнопки й дія (`start`, `abort`, `none`). */
export function onButton(button, event) {
  if (event === "press" && button.state === "idle") return { button: { ...SPEAKING }, action: "start" };
  if (event === "press" && button.state === "speaking") return { button: { ...STOPPING }, action: "abort" };
  if (event === "finished" && button.state !== "idle") return { button: { ...IDLE }, action: "none" };
  return { button, action: "none" };
}
