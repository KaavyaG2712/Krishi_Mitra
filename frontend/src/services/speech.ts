import { Language, locales } from "../i18n";
import espeakWasmUrl from "espeak-ng/dist/espeak-ng.wasm?url";

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null; onnomatch: (() => void) | null;
  start(): void; stop(): void; abort(): void;
};
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
export interface RecognitionSession { stop(): void; cancel(): void; }
export interface PlaybackSession { pause(): void; resume(): void; stop(): void; }
export interface SpeechProvider {
  supported(): boolean;
  recognize(language: Language, transcript: (text: string) => void, ended: () => void, error: (message: string) => void): RecognitionSession;
}
const errors: Record<string, string> = {
  "not-allowed": "Microphone permission was denied. You can type below.",
  "service-not-allowed": "Speech is unavailable in this browser. You can type below.",
  "no-speech": "No speech was detected. Try a quieter place or type below.",
  "audio-capture": "No microphone was found. You can type below.",
  "network": "The browser's speech service could not connect. Switch to Server recording, or open the app in a supported browser. Your internet connection may still be working.",
  "language-not-supported": "This speech language is unavailable. You can type in your language below.",
};
export const browserSpeech: SpeechProvider = {
  supported() { const w = window as SpeechWindow; return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition); },
  recognize(language, transcript, ended, error) {
    const w = window as SpeechWindow;
    const Constructor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Constructor) throw new Error("Speech is unsupported in this browser. You can type below.");
    const recognition = new Constructor();
    let active = true;
    let received = false;
    let failed = false;
    let timer: ReturnType<typeof setTimeout>;
    const finish = () => { if (!active) return; active = false; clearTimeout(timer); ended(); };
    recognition.lang = locales[language]; recognition.continuous = false; recognition.interimResults = true;
    recognition.onresult = event => {
      if (!active) return;
      const text = Array.from(event.results).map(result => result[0].transcript).join(" ");
      received = Boolean(text.trim()); transcript(text.slice(0, 2000));
    };
    recognition.onerror = event => { if (!active) return; failed = true; console.warn("speech_recognition_failed", { code: event.error }); if (event.error !== "aborted") error(errors[event.error] || "Speech could not be recognized. Retry or type below."); finish(); recognition.abort(); };
    recognition.onnomatch = () => { if (active) { failed = true; error(errors["no-speech"]); finish(); recognition.abort(); } };
    recognition.onend = () => { if (active && !received && !failed) error(errors["no-speech"]); finish(); };
    timer = setTimeout(() => { if (!active) return; error("Listening timed out. Check the text and retry if needed."); finish(); recognition.abort(); }, 30000);
    try { recognition.start(); } catch { finish(); throw new Error("The microphone could not start. Retry or type below."); }
    return {
      stop() { if (!active) return; recognition.stop(); clearTimeout(timer); timer = setTimeout(() => { finish(); recognition.abort(); }, 1500); },
      cancel() { finish(); recognition.abort(); },
    };
  },
};

export function currentLocation(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Location is unsupported. Select your location manually."));
    navigator.geolocation.getCurrentPosition(resolve, error => reject(new Error(error.code === 1 ? "Location permission was denied. Select your location manually." : "Your location could not be found. Select it manually.")), { timeout: 10000, maximumAge: 0, enableHighAccuracy: false });
  });
}

const localVoices: Record<Language, string> = { en: "en", hi: "hi", ta: "ta", te: "te", bn: "bn", mr: "mr", kn: "kn" };

async function speakWithLocalEngine(text: string, language: Language, done: () => void, error: (message: string) => void): Promise<PlaybackSession> {
  if (!("AudioContext" in window)) throw new Error("Local audio playback is unavailable. Please read the answer.");
  // Create/resume audio directly in the click handler to preserve the user's
  // playback gesture while the local WebAssembly voice engine loads.
  const context = new AudioContext();
  const resume = context.resume();
  let active = true;
  let paused = false;
  let offset = 0;
  let startedAt = 0;
  let buffer: AudioBuffer | undefined;
  let source: AudioBufferSourceNode | undefined;
  const close = () => { if (context.state !== "closed") void context.close(); };
  const stopSource = () => {
    if (!source) return;
    source.onended = null;
    try { source.stop(); } catch { /* The source may already have stopped. */ }
    source.disconnect();
    source = undefined;
  };
  const play = () => {
    if (!active || paused || !buffer) return;
    if (offset >= buffer.duration) { active = false; close(); done(); return; }
    source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    startedAt = context.currentTime;
    source.onended = () => {
      if (!active || paused) return;
      active = false;
      close();
      done();
    };
    source.start(0, offset);
  };
  void (async () => {
    try {
      const { default: ESpeakNG } = await import("espeak-ng");
      if (!active) return;
      const engine = await ESpeakNG({
        // Vite serves this imported asset with the correct WASM MIME type in
        // development and emits a hashed asset URL for production builds.
        locateFile: () => espeakWasmUrl,
        arguments: ["-v", localVoices[language], "-s", "158", "-w", "/answer.wav", text],
      });
      if (!active) return;
      const wav = engine.FS.readFile("/answer.wav");
      const copy = wav.buffer.slice(wav.byteOffset, wav.byteOffset + wav.byteLength) as ArrayBuffer;
      buffer = await context.decodeAudioData(copy);
      await resume;
      play();
    } catch {
      if (!active) return;
      active = false;
      close();
      error("The local voice could not create audio. The answer text is still available.");
      done();
    }
  })();
  return {
    pause() {
      if (!active || paused || !source || !buffer) return;
      offset = Math.min(buffer.duration, offset + context.currentTime - startedAt);
      paused = true;
      stopSource();
    },
    resume() {
      if (!active || !paused) return;
      paused = false;
      void context.resume().then(play);
    },
    stop() { if (!active) return; active = false; stopSource(); close(); done(); },
  };
}

export function speak(text: string, language: Language, done: () => void, error: (message: string) => void): PlaybackSession {
  const synth = "speechSynthesis" in window ? window.speechSynthesis : undefined;
  const locale = locales[language].toLowerCase();
  const voice = synth?.getVoices().find(v => v.lang.toLowerCase() === locale)
    || synth?.getVoices().find(v => v.lang.toLowerCase().startsWith(`${language}-`));
  if (!synth || !("SpeechSynthesisUtterance" in window) || !voice) {
    let stopped = false;
    let paused = false;
    let local: PlaybackSession | undefined;
    void speakWithLocalEngine(text, language, done, error).then(session => {
      local = session;
      if (stopped) session.stop();
      else if (paused) session.pause();
    }).catch(cause => { error((cause as Error).message); done(); });
    return {
      pause() { paused = true; local?.pause(); },
      resume() { paused = false; local?.resume(); },
      stop() { stopped = true; local?.stop(); },
    };
  }
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = locales[language]; utterance.voice = voice; utterance.rate = 0.9;
  utterance.onend = done;
  utterance.onerror = event => { if (!["canceled", "interrupted"].includes(event.error)) { console.warn("speech_playback_failed", { code: event.error }); error("Audio playback failed. The answer text is still available."); } done(); };
  synth.speak(utterance);
  return {
    pause() { synth.pause(); },
    resume() { synth.resume(); },
    stop() { utterance.onend = null; utterance.onerror = null; synth.cancel(); done(); },
  };
}
