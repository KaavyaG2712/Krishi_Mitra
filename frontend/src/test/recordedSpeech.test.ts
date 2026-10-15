import { afterEach, expect, it, vi } from "vitest";
import { recordSpeech, encodeWav } from "../services/recordedSpeech";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
class Recorder {
  static last: Recorder; static isTypeSupported() { return true; }
  state = "inactive"; mimeType = "audio/webm";
  ondataavailable?: (e: { data: Blob }) => void; onstop?: () => void; onerror?: () => void;
  constructor() { Recorder.last = this; }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["recorded audio"]) }); this.onstop?.(); }
}
it("reports missing backend configuration without opening the microphone", async () => {
  const getUserMedia = vi.fn(); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ available: false })));
  const error = vi.fn(); const done = vi.fn();
  recordSpeech("hi", vi.fn(), vi.fn(), done, error);
  await vi.waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(error.mock.calls[0][0]).toContain("GEMINI_API_KEY"); expect(getUserMedia).not.toHaveBeenCalled();
});
it("releases a microphone granted after cancellation and never uploads it", async () => {
  let grant: (stream: unknown) => void = () => undefined;
  const stop = vi.fn(); const getUserMedia = vi.fn(() => new Promise(resolve => { grant = resolve; }));
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ available: true })));
  const done = vi.fn();
  const session = recordSpeech("en", vi.fn(), vi.fn(), done, vi.fn());
  await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
  session.cancel(); grant({ getTracks: () => [{ stop }] }); await settle();
  expect(stop).toHaveBeenCalledOnce(); expect(done).toHaveBeenCalledOnce(); expect(fetch).toHaveBeenCalledOnce();
});
it("records without SpeechRecognition, uploads WAV, returns original script and stops tracks", async () => {
  const stop = vi.fn(); const transcript = vi.fn(); const done = vi.fn(); const error = vi.fn();
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } });
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("AudioContext", class { decodeAudioData() { return Promise.resolve({ duration: 1 }); } close() { return Promise.resolve(); } });
  vi.stubGlobal("OfflineAudioContext", class {
    destination = {}; createBufferSource() { return { buffer: null, connect() {}, start() {} }; }
    startRendering() { return Promise.resolve({ getChannelData: () => new Float32Array(16000) }); }
  });
  // jsdom's Blob lacks arrayBuffer; the browser API is mocked here, not microphone content.
  Object.defineProperty(Blob.prototype, "arrayBuffer", { configurable: true, value: async () => new ArrayBuffer(8) });
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ available: true }))).mockResolvedValueOnce(new Response(JSON.stringify({ text: "மண் பரிசோதனை", language: "ta" })));
  const session = recordSpeech("ta", transcript, vi.fn(), done, error);
  await vi.waitFor(() => expect(Recorder.last?.state).toBe("recording")); session.stop();
  await vi.waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(error).not.toHaveBeenCalled(); expect(transcript).toHaveBeenCalledWith("மண் பரிசோதனை"); expect(stop).toHaveBeenCalled();
  expect(fetch.mock.calls[1][0]).toContain("language=ta"); expect((fetch.mock.calls[1][1]?.body as Blob).type).toBe("audio/wav");
});
it("uses bounded mono PCM WAV sizes", () => {
  const wav = encodeWav(new Float32Array(16000));
  expect(wav.type).toBe("audio/wav"); expect(wav.size).toBe(32044);
});
