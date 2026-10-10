# Voice

**Output (implemented):** `apps/desktop/src/renderer/src/voice/voice-controller.ts`
plays `VoiceInstruction`s from the engine through the OS's local voices (Web Speech
API: SAPI on Windows, AVSpeech on macOS) behind a `SpeechEngine` adapter.
Rules: P0 interrupts anything, P1 interrupts P2/P3, others queue by priority; the
same dedupe key is not spoken twice within 8 s; instructions that cannot start
within their TTL are dropped; latency from source frame to speech start is
measured. Language follows the coaching setting (en-US / ko-KR voices).

**What decides what to say:** `services/coaching/tari_coaching/voice.py` (priority caps
by voice-frequency setting) and the bilingual phrasing in `phrasing.py`.

**Not implemented:** speech recognition, voice activity detection, conversation,
and callout coaching. The microphone is never opened in this build. This folder
is reserved for a local STT service (e.g. a Whisper-class model via ONNX Runtime)
behind the same adapter style.
