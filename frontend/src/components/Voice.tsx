import { useEffect, useRef, useState } from "react";
import { Language, useLanguage } from "../i18n";
import { browserSpeech, PlaybackSession, RecognitionSession, speak } from "../services/speech";
import { recordSpeech, recordingSupported, RecordingState } from "../services/recordedSpeech";

export function VoiceInput({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled: boolean }) {
  const { t, language } = useLanguage();
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const [provider, setProvider] = useState<"server" | "browser">(() => recordingSupported() ? "server" : "browser");
  const [phase, setPhase] = useState<RecordingState>("preparing");
  const session = useRef<RecognitionSession>();
  const previous = useRef("");
  useEffect(() => () => session.current?.cancel(), []);
  useEffect(() => { if (disabled) session.current?.cancel(); }, [disabled]);
  useEffect(() => { session.current?.cancel(); setListening(false); }, [language]);
  const start = () => {
    setError(""); previous.current = value; setListening(true);
    try {
      session.current = provider === "server"
        ? recordSpeech(language, onChange, setPhase, () => setListening(false), setError)
        : browserSpeech.recognize(language, onChange, () => setListening(false), setError);
    }
    catch (e) { setListening(false); setError((e as Error).message); }
  };
  return <div className="voice-controls">
    {recordingSupported() && <label className="block max-w-xs">{t("Speech service")}<select aria-label="Speech service" value={provider} disabled={listening || disabled} onChange={e => { setProvider(e.target.value as "server" | "browser"); setError(""); }}><option value="server">{t("Server recording (recommended)")}</option>{browserSpeech.supported() && <option value="browser">{t("Browser speech")}</option>}</select></label>}
    <p className="help">{provider === "server" ? t("Record up to 30 seconds, then tap Stop. Audio is sent to this app's server and Google Gemini for transcription; the app does not save recordings. Check the text before sending.") : t("Your browser may send audio to its speech provider. Start only when you are ready. Check and edit the text before sending.")}</p>
    {provider === "browser" && !browserSpeech.supported() ? <p role="status">{t("Speech is unsupported in this browser. Type your question below.")}</p> : <div className="actions">
      {!listening ? <button type="button" className="secondary" disabled={disabled} onClick={start}>🎙 {t("Tap to Speak")}</button> : <>
        <span role="status">● {t(provider === "browser" || phase === "recording" ? "Listening…" : phase === "preparing" ? "Starting microphone…" : "Transcribing…")}</span>
        {(provider === "browser" || phase === "recording") && <button type="button" className="secondary" onClick={() => session.current?.stop()}>{t("Stop")}</button>}
        <button type="button" className="secondary" onClick={() => { session.current?.cancel(); onChange(previous.current); }}>{t("Cancel")}</button>
      </>}
    </div>}
    {error && <p role="alert" className="notice">{error}</p>}
  </div>;
}

export function VoiceOutput({ text, language }: { text: string; language: Language }) {
  const { t } = useLanguage();
  const [state, setState] = useState<"idle" | "playing" | "paused">("idle");
  const [error, setError] = useState("");
  const playback = useRef<PlaybackSession>();
  useEffect(() => () => playback.current?.stop(), [text, language]);
  const start = () => {
    setError("");
    try { playback.current = speak(text, language, () => setState("idle"), setError); setState("playing"); }
    catch (e) { setState("idle"); setError((e as Error).message); }
  };
  return <div className="mt-3"><div className="actions">
    <button type="button" className="secondary" onClick={start}>🔊 {t("Listen")}</button>
    {state === "playing" && <button type="button" className="secondary" onClick={() => { playback.current?.pause(); setState("paused"); }}>⏸ {t("Pause")}</button>}
    {state === "paused" && <button type="button" className="secondary" onClick={() => { playback.current?.resume(); setState("playing"); }}>▶ {t("Resume")}</button>}
    {state !== "idle" && <button type="button" className="secondary" onClick={() => playback.current?.stop()}>⏹ {t("Stop")}</button>}
  </div>{error && <p role="alert" className="notice">{error}</p>}</div>;
}
