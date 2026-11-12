// recorder.js — S2: життя одного запису звуку. Мікрофон, MediaRecorder і Blob передаються ззовні.
// Кожен `start`/`stop` має свій номер: потік, що прийшов для вже непотрібної спроби, закривається одразу,
// тож мікрофон відкритий щонайбільше один, а `stop` без запису ніколи не зависає.
// Не робить: надсилання звуку (застосунок), станів розмови (voice_state.js).

export function createRecorder({ getUserMedia, MediaRecorder, Blob, mimeType, onAudio, onNoAudio, onFailed }) {
  let attempt = 0;
  let active = null;

  async function start() {
    const mine = ++attempt;
    let stream;
    try {
      stream = await getUserMedia();
    } catch {
      if (mine === attempt) onFailed();
      return;
    }
    if (mine !== attempt) {
      closeStream(stream);
      return;
    }
    const media = new MediaRecorder(stream, { mimeType });
    const chunks = [];
    media.ondataavailable = (e) => chunks.push(e.data);
    media.start();
    active = { media, stream, chunks };
  }

  function stop() {
    attempt++;
    const current = active;
    active = null;
    if (current === null) {
      onNoAudio();
      return;
    }
    current.media.onstop = () => {
      closeStream(current.stream);
      onAudio(new Blob(current.chunks, { type: current.media.mimeType }));
    };
    current.media.stop();
  }

  return { start, stop };
}

function closeStream(stream) {
  stream.getTracks().forEach((track) => track.stop());
}
