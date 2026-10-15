import { Language } from "../i18n";
import { apiBaseUrl } from "./api";
import { RecognitionSession } from "./speech";

export type RecordingState = "preparing" | "recording" | "transcribing";
export function recordingSupported() {
  return Boolean(typeof navigator.mediaDevices?.getUserMedia === "function" && typeof MediaRecorder !== "undefined" && typeof AudioContext !== "undefined");
}

export function encodeWav(samples: Float32Array): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (at: number, text: string) => [...text].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  write(0, "RIFF"); view.setUint32(4, buffer.byteLength - 8, true); write(8, "WAVE"); write(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  write(36, "data"); view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => { const s = Math.max(-1, Math.min(1, sample)); view.setInt16(44 + i * 2, s < 0 ? s * 32768 : s * 32767, true); });
  return new Blob([buffer], { type: "audio/wav" });
}

async function wavRecording(blob: Blob): Promise<Blob> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    if (decoded.duration < 0.25 || decoded.duration > 31) throw new Error("Record between 1 and 30 seconds and try again.");
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
    const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start();
    return encodeWav((await offline.startRendering()).getChannelData(0));
  } finally { await context.close(); }
}

export function recordSpeech(language: Language, transcript: (text: string) => void, state: (s: RecordingState) => void, ended: () => void, error: (message: string) => void): RecognitionSession {
  let active = true;
  let recorder: MediaRecorder | undefined;
  let stream: MediaStream | undefined;
  let timer: ReturnType<typeof setTimeout>;
  const controller = new AbortController();
  const release = () => { clearTimeout(timer); stream?.getTracks().forEach(track => track.stop()); };
  const finish = () => { if (!active) return; active = false; release(); controller.abort(); ended(); };
  const fail = (e: unknown) => {
    if (!active) return;
    const err = e as Error;
    error(err.name === "NotAllowedError" ? "Microphone permission was denied. Allow the microphone for this site or type below." : err.name === "NotFoundError" ? "No microphone was found. Connect one or type below." : err.name === "AbortError" ? "The speech request timed out. Retry or type below." : err instanceof TypeError ? "Unable to reach the app's speech server. Check that the backend is running." : err.message || "Recording failed. Retry or type below.");
    finish(); if (recorder?.state === "recording") recorder.stop();
  };
  const decodeResponse = async (response: Response) => {
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : "Speech service unavailable. Please retry.");
    return payload;
  };
  state("preparing");
  void (async () => {
    try {
      timer = setTimeout(() => fail(new Error("Speech setup timed out. Check microphone permission and the backend connection.")), 20000);
      const status = await decodeResponse(await fetch(`${apiBaseUrl}/speech/status`, { signal: controller.signal }));
      if (!active) return;
      if (!status?.available) throw new Error("Server speech is not configured. The app owner must add GEMINI_API_KEY to backend/.env and restart the backend. You can also try Browser speech.");
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
      if (!active) { release(); return; }
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = []; let bytes = 0;
      recorder.ondataavailable = event => {
        if (!active || !event.data.size) return;
        bytes += event.data.size;
        if (bytes > 6 * 1024 * 1024) { fail(new Error("Recording is too large. Try a shorter question.")); return; }
        chunks.push(event.data);
      };
      recorder.onerror = () => fail(new Error("The microphone stopped unexpectedly. Retry or type below."));
      recorder.onstop = () => {
        release();
        if (!active) return;
        state("transcribing");
        timer = setTimeout(() => fail(new DOMException("Timeout", "AbortError")), 35000);
        void (async () => {
          try {
            const wav = await wavRecording(new Blob(chunks, { type: recorder?.mimeType }));
            if (!active) return;
            const response = await decodeResponse(await fetch(`${apiBaseUrl}/speech/transcribe?language=${language}`, { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav, signal: controller.signal }));
            if (!active) return;
            if (typeof response?.text !== "string" || !response.text.trim()) throw new Error("No clear speech was heard. Please try again.");
            transcript(response.text.slice(0, 2000)); finish();
          } catch (e) { fail(e); }
        })();
      };
      recorder.start(1000); clearTimeout(timer); state("recording");
      timer = setTimeout(() => { if (recorder?.state === "recording") recorder.stop(); }, 30000);
    } catch (e) { fail(e); }
  })();
  return {
    stop() { if (recorder?.state === "recording") { clearTimeout(timer); recorder.stop(); } },
    cancel() { finish(); if (recorder?.state === "recording") recorder.stop(); },
  };
}
