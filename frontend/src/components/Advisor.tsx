import { FormEvent, useState } from "react";
import { Language, useLanguage } from "../i18n";
import { api } from "../services/api";
import { SoilResult } from "./SoilHealth";
import { VoiceInput, VoiceOutput } from "./Voice";

type Message = { id: string; role: "user" | "assistant"; text: string; language: Language; target: Language; canonical?: string; translationFailed?: boolean; originalTranscript?: string; englishTranscript?: string };
type ChatResponse = { conversation_id: string; conversation_token: string; message_id: string; answer: string; canonical_answer: string; original_transcript: string; english_transcript: string; language: Language; translation_failed: boolean };
export default function Advisor({ soil, onClearSoil }: { soil: SoilResult | null; onClearSoil: () => void }) {
  const { language, t } = useLanguage();
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState<{ id: string; token: string } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || question.trim().length < 2) return;
    const original = question.trim();
    const selectedLanguage = language;
    setBusy(true); setError("");
    try {
      const response = await api<ChatResponse>("/advisor/chat", { question: original, language: selectedLanguage, conversation_id: conversation?.id || null, conversation_token: conversation?.token || null, soil_token: soil?.profile_token || null });
      setConversation({ id: response.conversation_id, token: response.conversation_token });
      setMessages(current => [...current, { id: crypto.randomUUID(), role: "user", text: original, language: selectedLanguage, target: selectedLanguage, originalTranscript: response.original_transcript, englishTranscript: response.english_transcript },
        { id: response.message_id, role: "assistant", text: response.answer, canonical: response.canonical_answer, language: response.language, target: selectedLanguage, translationFailed: response.translation_failed }]);
      setQuestion("");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const retryTranslation = async (message: Message) => {
    setRetrying(message.id); setError("");
    try {
      const response = await api<{ text: string; language: Language }>("/advisor/translate", { text: message.canonical, source: "en", target: message.target });
      setMessages(current => current.map(item => item.id === message.id ? { ...item, text: response.text, language: response.language, translationFailed: false } : item));
    } catch (e) { setError((e as Error).message); } finally { setRetrying(null); }
  };
  return <section className="py-8"><p className="eyebrow">YOUR FARMING ASSISTANT</p><h1 className="text-3xl font-bold mt-2">{t("Ask KrishiMitra")}</h1>
    <p className="mt-3 text-slate-600">{t("Speak or type in your language. Check the words, then send when you are ready.")}</p>
    <div className="panel mt-6">
      <p className="notice">General guidance can be wrong. Confirm important farm decisions with a local agricultural officer. Fertilizer quantities need a current soil test and validated local recommendations.</p>
      {soil && <div className="soil-context mt-4"><strong>Soil explanation mode</strong><p>This explains the values you submitted and the safe next steps. It does not generate a crop ranking or fertilizer dose.</p><button className="secondary mt-2" onClick={onClearSoil}>Ask a general farming question instead</button></div>}
      <div className="chat-log" aria-live="polite" aria-relevant="additions">
        {!messages.length && <p className="empty-state">{soil ? "Ask for an explanation of your soil report." : "Ask about your crop, soil, watering or plant health."}</p>}
        {messages.map(message => <article key={message.id} className={`chat-message ${message.role}`} lang={message.language}>
          <p className="whitespace-pre-wrap">{message.text}</p>
          {message.role === "assistant" && <>
            {message.translationFailed && <div role="status" className="notice">Translation failed. The English response is kept. <button className="secondary" disabled={retrying === message.id} onClick={() => retryTranslation(message)}>{t("Retry")}</button></div>}
            <VoiceOutput text={message.text} language={message.language} />
          </>}
        </article>)}
        {busy && <p role="status">{t("Working…")}</p>}
      </div>
      {error && <p className="notice" role="alert">{error} Your question is kept below. Retry by pressing Send.</p>}
      <form onSubmit={submit} className="mt-5">
        <VoiceInput value={question} onChange={setQuestion} disabled={busy} />
        <label htmlFor="chat-question" className="block mt-4">{t("Your question or corrected transcript")}</label>
        <textarea id="chat-question" lang={language} className="w-full min-h-28" maxLength={2000} disabled={busy} value={question} onChange={e => setQuestion(e.target.value)} />
        <div className="actions mt-3"><button type="submit" className="primary" disabled={busy || question.trim().length < 2}>{busy ? t("Working…") : t("Send")}</button><button type="button" className="secondary" disabled={busy} onClick={() => { setConversation(null); setMessages([]); setError(""); }}>Start a new conversation</button></div>
      </form>
    </div>
  </section>;
}
