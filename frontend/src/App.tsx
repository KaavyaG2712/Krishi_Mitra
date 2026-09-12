import { FormEvent, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

type View = "overview" | "health" | "advisor";

const supportedCrops = ["Tomato", "Potato", "Maize", "Grape"];

async function checkApi(): Promise<boolean> {
  const response = await fetch(`${apiBaseUrl}/health`);
  return response.ok;
}

function StatusPill({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${ready ? "bg-leaf-100 text-leaf-700" : "bg-amber-100 text-amber-800"}`}>
      <span className={`h-2 w-2 rounded-full ${ready ? "bg-leaf-500" : "bg-amber-500"}`} />
      {label}
    </span>
  );
}

function App() {
  const [view, setView] = useState<View>("overview");
  const { data: apiReady = false } = useQuery({
    queryKey: ["api-health"],
    queryFn: checkApi,
    retry: false,
    refetchInterval: 15_000,
  });

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#e4f2dd_0,_transparent_30%),linear-gradient(180deg,_#fbfdf9_0%,_#f4f8f1_100%)]">
      <div className="mx-auto max-w-6xl px-5 pb-12 pt-6 sm:px-8">
        <header className="flex flex-col gap-5 border-b border-leaf-100 pb-6 md:flex-row md:items-center md:justify-between">
          <button className="flex items-center gap-3 text-left" onClick={() => setView("overview")}>
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-leaf-700 text-xl text-white shadow-card">✦</span>
            <span>
              <span className="block text-xl font-bold tracking-tight text-leaf-900">KrishiMitra</span>
              <span className="block text-xs font-medium text-leaf-700">Evidence-aware crop support</span>
            </span>
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill ready={apiReady} label={apiReady ? "API connected" : "API starting"} />
            <StatusPill ready={false} label="Review 3 build" />
          </div>
        </header>

        <nav className="mt-5 flex flex-wrap gap-2" aria-label="Main navigation">
          {(["overview", "health", "advisor"] as View[]).map((item) => (
            <button
              key={item}
              className={`rounded-xl px-4 py-2 text-sm font-semibold capitalize transition ${view === item ? "bg-leaf-700 text-white shadow-sm" : "text-leaf-700 hover:bg-leaf-100"}`}
              onClick={() => setView(item)}
            >
              {item === "health" ? "Crop health" : item === "advisor" ? "Agronomy advisor" : "Overview"}
            </button>
          ))}
        </nav>

        {view === "overview" && <Overview onNavigate={setView} />}
        {view === "health" && <CropHealth />}
        {view === "advisor" && <Advisor />}
      </div>
    </main>
  );
}

function Overview({ onNavigate }: { onNavigate: (view: View) => void }) {
  return (
    <>
      <section className="grid gap-7 py-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
        <div>
          <p className="mb-3 inline-block rounded-full bg-soil-50 px-3 py-1 text-sm font-semibold text-soil-700">Local review demonstration</p>
          <h1 className="max-w-2xl text-4xl font-bold tracking-tight text-leaf-900 sm:text-5xl">Two practical AI tools, built with evidence and care.</h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-600">Upload a leaf for a confidence-aware health result, then ask crop questions that are answered only from cited agricultural sources.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button className="rounded-xl bg-leaf-700 px-5 py-3 font-semibold text-white shadow-card transition hover:bg-leaf-900" onClick={() => onNavigate("health")}>Try crop health</button>
            <button className="rounded-xl border border-leaf-200 bg-white px-5 py-3 font-semibold text-leaf-700 transition hover:bg-leaf-50" onClick={() => onNavigate("advisor")}>Ask the advisor</button>
          </div>
        </div>
        <aside className="rounded-3xl bg-leaf-900 p-7 text-white shadow-card">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-leaf-100">Review 3 scope</p>
          <dl className="mt-6 space-y-5">
            <div><dt className="text-2xl font-bold">10</dt><dd className="text-sm text-leaf-100">approved disease labels</dd></div>
            <div><dt className="text-2xl font-bold">2</dt><dd className="text-sm text-leaf-100">complete AI modules</dd></div>
            <div><dt className="text-2xl font-bold">0</dt><dd className="text-sm text-leaf-100">cloud services required for the demo</dd></div>
          </dl>
        </aside>
      </section>

      <section className="grid gap-5 md:grid-cols-2">
        <ModuleCard number="01" title="Crop Health Intelligence" detail="MobileNetV2 classifies the selected Tomato, Potato, Maize, and Grape leaf conditions. Low-confidence results direct the farmer to a KVK or agricultural officer." action="Open image upload" onClick={() => onNavigate("health")} />
        <ModuleCard number="02" title="Citation-Grounded Advisor" detail="PostgreSQL + pgvector retrieves relevant excerpts from approved official documents before Gemini prepares an answer with source pages." action="Open advisor" onClick={() => onNavigate("advisor")} />
      </section>
    </>
  );
}

function ModuleCard({ number, title, detail, action, onClick }: { number: string; title: string; detail: string; action: string; onClick: () => void }) {
  return <article className="rounded-3xl border border-leaf-100 bg-white p-6 shadow-card"><p className="text-sm font-bold text-leaf-500">MODULE {number}</p><h2 className="mt-3 text-2xl font-bold text-leaf-900">{title}</h2><p className="mt-3 min-h-24 leading-7 text-slate-600">{detail}</p><button className="mt-6 font-semibold text-leaf-700 hover:text-leaf-900" onClick={onClick}>{action} →</button></article>;
}

function CropHealth() {
  const [file, setFile] = useState<File | null>(null);
  const [crop, setCrop] = useState("Tomato");
  const [message, setMessage] = useState<string | null>(null);
  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) return setMessage("Choose one clear leaf image first.");
    setMessage("The upload interface is ready. Model training and the validated prediction endpoint are the next implementation step, so no result is being fabricated yet.");
  };

  return <section className="py-10"><SectionTitle eyebrow="Module 1" title="Crop Health Intelligence" detail="For Review 3, the model will support Tomato, Potato, Maize, and Grape only." /><div className="mt-7 grid gap-6 lg:grid-cols-[1fr_0.8fr]"><form className="rounded-3xl border border-leaf-100 bg-white p-6 shadow-card" onSubmit={submit}><label className="block text-sm font-bold text-leaf-900">Crop hint</label><select className="mt-2 w-full rounded-xl border border-leaf-200 bg-white px-3 py-3 text-slate-700 focus:border-leaf-500 focus:outline-none" value={crop} onChange={(event) => setCrop(event.target.value)}>{supportedCrops.map((item) => <option key={item}>{item}</option>)}</select><label className="mt-6 grid min-h-52 cursor-pointer place-items-center rounded-2xl border-2 border-dashed border-leaf-200 bg-leaf-50 p-6 text-center transition hover:border-leaf-500"><input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setMessage(null); }} /><span><span className="block text-3xl">⌁</span><span className="mt-2 block font-semibold text-leaf-900">Choose a leaf image</span><span className="mt-1 block text-sm text-slate-500">PNG, JPG, or WebP · clear single leaf preferred</span></span></label>{file && <p className="mt-3 text-sm text-leaf-700">Selected: {file.name}</p>}<button className="mt-6 w-full rounded-xl bg-leaf-700 px-5 py-3 font-semibold text-white hover:bg-leaf-900" type="submit">Analyse leaf</button>{message && <p className="mt-4 rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-900">{message}</p>}</form><aside className="rounded-3xl bg-soil-50 p-6"><p className="font-bold text-soil-700">Result preview</p>{previewUrl ? <img className="mt-5 aspect-square w-full rounded-2xl object-cover" src={previewUrl} alt="Selected leaf preview" /> : <div className="mt-5 grid aspect-square place-items-center rounded-2xl border border-dashed border-soil-200 bg-white p-8 text-center text-sm text-slate-500">Your selected leaf will appear here.</div>}<p className="mt-5 text-sm leading-6 text-slate-600">A completed result will show the predicted label, confidence, model version, advisory reference, and an uncertainty warning where appropriate.</p></aside></div></section>;
}

function Advisor() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<string | null>(null);
  const submit = (event: FormEvent) => { event.preventDefault(); setResponse(question.trim() ? "The advisor interface is ready. It will be enabled after official documents are catalogued, embedded, and evaluated; until then, KrishiMitra will not generate an uncited answer." : "Enter a crop-related question to continue."); };
  return <section className="py-10"><SectionTitle eyebrow="Module 3" title="Citation-Grounded Agronomy Advisor" detail="The advisor will answer only when relevant approved evidence can be retrieved." /><div className="mt-7 rounded-3xl border border-leaf-100 bg-white p-6 shadow-card"><div className="rounded-2xl bg-leaf-50 p-5 text-sm leading-7 text-leaf-900"><p className="font-bold">Safety-first advisory</p><p className="mt-1">Answers will cite their source title and page. No-evidence, off-topic, and safety-critical questions receive a clear referral instead of a made-up response.</p></div>{response && <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-7 text-amber-950">{response}</div>}<form className="mt-6 flex flex-col gap-3 sm:flex-row" onSubmit={submit}><input className="min-w-0 flex-1 rounded-xl border border-leaf-200 px-4 py-3 text-slate-800 placeholder:text-slate-400 focus:border-leaf-500 focus:outline-none" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Example: How can I reduce tomato blight risk?" /><button className="rounded-xl bg-leaf-700 px-5 py-3 font-semibold text-white hover:bg-leaf-900" type="submit">Ask advisor</button></form></div></section>;
}

function SectionTitle({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) { return <div><p className="text-sm font-bold uppercase tracking-[0.15em] text-leaf-500">{eyebrow}</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-leaf-900">{title}</h1><p className="mt-3 max-w-2xl leading-7 text-slate-600">{detail}</p></div>; }

export default App;
