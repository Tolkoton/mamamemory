// player.js — F5 S4 + speak-control: програвання однієї частини аудіо. Чистий модуль: `Audio` і `URL` — параметрами.
// Promise вирішує перша подія: `ended` → виконано; `error` чи відхилений `audio.play()` → відхилено;
// `abort` сигналу → `pause()`, виконано (зупинка — не помилка).

/** Програвач для `speak`: `play(blob, signal?) -> Promise`; URL звільняється рівно раз, коли частина вирішена. */
export function makePlay(AudioCtor, urls) {
  return (blob, signal) =>
    new Promise((resolve, reject) => {
      if (signal?.aborted) {
        resolve();
        return;
      }
      const url = urls.createObjectURL(blob);
      const audio = new AudioCtor(url);
      let settled = false;
      const settle = (finish) => (value) => {
        if (settled) return;
        settled = true;
        urls.revokeObjectURL(url);
        finish(value);
      };
      audio.addEventListener("ended", settle(resolve));
      audio.addEventListener("error", settle(() => reject(new Error("audio error"))));
      signal?.addEventListener("abort", () => {
        if (settled) return;
        audio.pause();
        settle(resolve)();
      });
      Promise.resolve(audio.play()).catch(settle(reject));
    });
}
