import { FormEvent, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Language, useLanguage } from "../i18n";
import { api } from "../services/api";
import { SoilResult } from "./SoilHealth";
import { VoiceInput, VoiceOutput } from "./Voice";

type Source = { title: string; publisher: string; source_url: string; page_number: number | null; section: string | null; relevance: number };
type Message = { id: string; role: "user" | "assistant"; text: string; sources: Source[]; language: Language; abstained?: boolean };
type ChatResponse = { conversation_id: string; conversation_token: string; message_id: string; answer: string; answer_method: string; original_transcript: string; language: Language; abstained: boolean; sources: Source[] };
export default function Advisor({ soil, onClearSoil }: { soil: SoilResult | null; onClearSoil: () => void }) {
  const { t, language } = useLanguage();
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState<{ id: string; token: string } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || question.trim().length < 2) return;
    const original = question.trim();
    setBusy(true); setError("");
    try {
      const response = await api<ChatResponse>("/advisor/chat", { question: original, language, conversation_id: conversation?.id || null, conversation_token: conversation?.token || null, soil_token: soil?.profile_token || null });
      setConversation({ id: response.conversation_id, token: response.conversation_token });
      setMessages(current => [...current, { id: crypto.randomUUID(), role: "user", text: original, sources: [], language },
        { id: response.message_id, role: "assistant", text: response.answer, sources: response.sources, language: response.language, abstained: response.abstained }]);
      setQuestion("");
    } catch { setError("Could not get an answer. Please try again."); } finally { setBusy(false); }
  };
  return <section className="py-8"><p className="eyebrow">YOUR FARMING ASSISTANT</p><h1 className="text-3xl font-bold mt-2">{t("Ask KrishiMitra")}</h1>
    <p className="mt-3 text-slate-600">Ask your farming question in your selected language. Type it or use voice input.</p>
    <div className="panel mt-6">
      {soil && <div className="soil-context mt-4"><strong>Soil explanation mode</strong><p>This explains the values you submitted and the safe next steps. It does not generate a crop ranking or fertilizer dose.</p><button className="secondary mt-2" onClick={onClearSoil}>Ask a general farming question instead</button></div>}
      <div className="chat-log" aria-live="polite" aria-relevant="additions">
        {!messages.length && <p className="empty-state">{soil ? "Ask for an explanation of your soil report." : "Ask about your crop, soil, watering or plant health."}</p>}
        {messages.map(message => <article key={message.id} className={`chat-message ${message.role}`} lang={message.language}>
          {message.role === "assistant" ? <div className="chat-markdown"><ReactMarkdown components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a> }}>{message.text}</ReactMarkdown></div> : <p className="whitespace-pre-wrap">{message.text}</p>}
          {message.role === "assistant" && <>
            {message.sources.length > 0 && <div className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 p-3"><strong>{t("Sources")}</strong><ol className="mt-1 list-decimal pl-5">{message.sources.map((source, index) => <li key={`${source.source_url}-${source.page_number}-${index}`}><a className="underline" href={source.source_url} target="_blank" rel="noreferrer">{source.publisher}: {source.title}</a>{source.page_number !== null ? ` — p. ${source.page_number}` : source.section ? ` — ${source.section}` : ""}</li>)}</ol></div>}
            <VoiceOutput text={message.text} language={message.language} />
          </>}
        </article>)}
        {busy && <p role="status">{t("Working…")}</p>}
      </div>
      {error && <p className="notice" role="alert">{error}</p>}
      <form onSubmit={submit} className="mt-5">
        <VoiceInput value={question} onChange={setQuestion} disabled={busy} />
        <label htmlFor="chat-question" className="block mt-4">{t("Your question or corrected transcript")}</label>
        <textarea id="chat-question" lang={language} className="w-full min-h-28" maxLength={2000} disabled={busy} value={question} onChange={e => setQuestion(e.target.value)} />
        <div className="actions mt-3"><button type="submit" className="primary" disabled={busy || question.trim().length < 2}>{busy ? t("Working…") : t("Send")}</button><button type="button" className="secondary" disabled={busy} onClick={() => { setConversation(null); setMessages([]); setError(""); }}>Start a new conversation</button></div>
      </form>
    </div>
  </section>;
}
