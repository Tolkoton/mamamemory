// voice_state.js — S2: стани голосового вводу «тиша → запис → розпізнаю → текст готовий → надіслано».
// Чистий модуль без DOM і мережі: `on(state, event)` повертає новий стан і дії, які виконує застосунок.
// Не робить: запису звуку (MediaRecorder — у застосунку), озвучення (F5), правки тексту.

const SILENCE = "silence";
const RECORDING = "recording";
const TRANSCRIBING = "transcribing";
const READY = "ready";

/** Початковий стан; `replyTo` — `reply_to` останньої відповіді асистента на екрані. */
export function initial(replyTo = null) {
  return { phase: SILENCE, draft: "", replyTo };
}

/**
 * Події: {type: "mic"} | {type: "send"} | {type: "transcribed", status, body} | {type: "assistant_reply", reply}
 *        | {type: "recording_failed", error} (мікрофон не дали чи він не запустився).
 * Дії: {do: "start_recording"} | {do: "stop_and_transcribe"} | {do: "send_message", text, reply_to}
 *      | {do: "show_error", error} | {do: "show_draft", text}.
 * Повертає {state, actions}. Запит 1 (`transcribed`) ніколи не змінює `replyTo`.
 */
export function on(state, event) {
  switch (event.type) {
    case "mic":
      return onMic(state);
    case "send":
      return onSend(state);
    case "transcribed":
      return onTranscribed(state, event);
    case "recording_failed":
      return onRecordingFailed(state, event);
    case "assistant_reply":
      return { state: { ...state, replyTo: event.reply?.question ?? null }, actions: [] };
    default:
      return { state, actions: [] };
  }
}

function onMic(state) {
  if (state.phase === SILENCE || state.phase === READY) {
    return { state: { ...state, phase: RECORDING, draft: "" }, actions: [{ do: "start_recording" }] };
  }
  return { state, actions: [] };
}

function onRecordingFailed(state, event) {
  if (state.phase !== RECORDING) return { state, actions: [] };
  const back = { ...state, phase: SILENCE, draft: "" };
  return { state: back, actions: [{ do: "show_error", error: event.error }] };
}

function onSend(state) {
  if (state.phase === RECORDING) {
    return { state: { ...state, phase: TRANSCRIBING }, actions: [{ do: "stop_and_transcribe" }] };
  }
  if (state.phase === READY) {
    const action = { do: "send_message", text: state.draft, reply_to: state.replyTo };
    return { state: { ...state, phase: SILENCE, draft: "" }, actions: [action] };
  }
  return { state, actions: [] };
}

function onTranscribed(state, event) {
  if (state.phase !== TRANSCRIBING) return { state, actions: [] };
  const ok = event.status >= 200 && event.status < 300;
  if (!ok) {
    const error = event.body?.error ?? "Не вдалося, спробуйте ще раз.";
    return { state: { ...state, phase: SILENCE, draft: "" }, actions: [{ do: "show_error", error }] };
  }
  const text = String(event.body?.text ?? "");
  if (!text.trim()) return { state: { ...state, phase: SILENCE, draft: "" }, actions: [] };
  return { state: { ...state, phase: READY, draft: text }, actions: [{ do: "show_draft", text }] };
}

/** Що показати на екрані для стану: підпис, чи мікрофон «червоний», чи кнопка ➤ щось зробить. */
export function statusOf(state) {
  switch (state.phase) {
    case RECORDING:
      return { label: "Слухаю… Натисніть ➤, коли закінчите.", recording: true, canSend: true };
    case TRANSCRIBING:
      return { label: "Розпізнаю…", recording: false, canSend: false };
    case READY:
      return { label: "Перевірте текст і натисніть ➤ ще раз.", recording: false, canSend: true };
    default:
      return { label: "", recording: false, canSend: false };
  }
}
