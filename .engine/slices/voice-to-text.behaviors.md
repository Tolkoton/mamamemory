# voice-to-text — behaviours added by the builder

The contract tests are the independent tester's (sealed). Below are the behaviours the builder added on top of
them, each with its own test in `src/mamamemory/web/voice_state.test.js`.

- B1 (self-added) — a microphone that could not start (permission refused, no device) returns to «тиша» and
  shows the error. Seen in overseer PASS 2026-11-06 (test gap): a refused `getUserMedia` left the app in
  «запис» until a reload. The contract's Errors line covers only non-2xx answers, so this was not visible at
  Step 3.
- B2 (self-added) — a transcribe without any response (fetch rejected, network down) is fed as status 0 and
  takes the non-2xx path: «тиша», the error shown, no draft. Same source.
- B3 (self-added) — at most one microphone is open: a stream granted for an attempt that is no longer wanted
  (mama pressed «надіслати» or «мікрофон» again while the permission was pending) is closed at once
  (`web/recorder.js`, numbered attempts). Seen in two overseer PASSes 2026-11-06 (test gaps on app.js wiring).
- B4 (self-added) — «надіслати» with no recorder running (permission still pending, or after a finished
  recording) reports «no audio», which takes the non-2xx path: «тиша» and the error, never «розпізнаю» forever.
- B5 (self-added) — a stopped recording gives its audio once and closes the microphone.
