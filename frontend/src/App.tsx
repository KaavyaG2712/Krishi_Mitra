import { FormEvent, useEffect, useMemo, useState, lazy, Suspense } from "react";
import { Language, LanguageContext, languageNames } from "./i18n";
import { checkApi, readStored, storeLocal } from "./services/api";
import type { SoilResult } from "./components/SoilHealth";
const SoilHealth = lazy(() => import("./components/ModuleTwo"));
const Advisor = lazy(() => import("./components/Advisor"));
import { useQuery } from "@tanstack/react-query";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

type View = "overview" | "health" | "soil" | "advisor";

const supportedCrops = ["Tomato", "Potato", "Maize", "Grape"];

type HealthPrediction = {
  predicted_label: string;
  confidence: number;
  is_uncertain: boolean;
  model_version: string;
  advisory_reference: string;
  crop_mismatch?: boolean;
  selected_crop?: string | null;
  detected_crop?: string | null;
  supported_conditions?: string[];
};

type ApiErrorPayload = {
  detail?: unknown;
  message?: unknown;
  code?: unknown;
  selected_crop?: unknown;
  expected_crop?: unknown;
  detected_crop?: unknown;
};

function formatCrop(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function predictionErrorMessage(payload: unknown) {
  if (typeof payload === "string") return payload;
  if (!payload || typeof payload !== "object") return "Prediction could not be completed.";

  const response = payload as ApiErrorPayload;
  const detail = response.detail && typeof response.detail === "object" ? response.detail as ApiErrorPayload : null;
  const code = detail?.code ?? response.code;
  const selectedCrop = detail?.selected_crop ?? detail?.expected_crop ?? response.selected_crop ?? response.expected_crop;
  const detectedCrop = detail?.detected_crop ?? response.detected_crop;

  if (code === "crop_mismatch" || (typeof selectedCrop === "string" && typeof detectedCrop === "string")) {
    return `Crop mismatch: you selected ${formatCrop(String(selectedCrop))}, but the model detected ${formatCrop(String(detectedCrop))}. This result is not a diagnosis. Select the actual crop and try a clear leaf image.`;
  }

  const message = detail?.message ?? response.message ?? response.detail;
  return typeof message === "string" ? message : "Prediction could not be completed.";
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
  const [language, setLanguage] = useState<Language>(() => { const saved = readStored<string>("language", "en"); return Object.prototype.hasOwnProperty.call(languageNames, saved) ? saved as Language : "en"; });
  const [soil, setSoil] = useState<SoilResult | null>(null);
  const [explainSoil, setExplainSoil] = useState(false);
  useEffect(() => { document.documentElement.lang = language; storeLocal("language", language); }, [language]);
  const { data: apiReady = false, isPending: checkingApi } = useQuery({
    queryKey: ["api-health"],
    queryFn: checkApi,
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    refetchInterval: 30_000,
  });

  return (
    <LanguageContext.Provider value={language}><main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#e4f2dd_0,_transparent_30%),linear-gradient(180deg,_#fbfdf9_0%,_#f4f8f1_100%)]">
      <div className="mx-auto max-w-6xl px-5 pb-12 pt-6 sm:px-8">
        <header className="flex flex-col gap-5 border-b border-leaf-100 pb-6 md:flex-row md:items-center md:justify-between">
          <button className="flex items-center gap-3 text-left" onClick={() => setView("overview")}>
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-leaf-700 text-xl text-white shadow-card">✦</span>
            <span>
              <span className="block text-xl font-bold tracking-tight text-leaf-900">KrishiMitra</span>
              <span className="block text-xs font-medium text-leaf-700">AI-powered crop support</span>
            </span>
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill ready={apiReady} label={checkingApi ? "Checking connection…" : apiReady ? "Connected" : "Connection unavailable"} />
            <label className="language-select">Language / भाषा
              <select aria-label="Language" value={language} onChange={event => setLanguage(event.target.value as Language)}>{Object.entries(languageNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select>
            </label>
          </div>
        </header>

        <nav className="mt-5 flex flex-wrap gap-2" aria-label="Main navigation">
          {(["overview", "soil", "health", "advisor"] as View[]).map((item) => (
            <button
              key={item}
              className={`rounded-xl px-4 py-2 text-sm font-semibold capitalize transition ${view === item ? "bg-leaf-700 text-white shadow-sm" : "text-leaf-700 hover:bg-leaf-100"}`}
              aria-current={view === item ? "page" : undefined}
              onClick={() => setView(item)}
            >
              {({ en: { overview: "Home", soil: "Check My Soil", health: "Crop Health", advisor: "Ask KrishiMitra" }, hi: { overview: "होम", soil: "मेरी मिट्टी जाँचें", health: "फसल स्वास्थ्य", advisor: "कृषिमित्र से पूछें" }, ta: { overview: "முகப்பு", soil: "என் மண்ணை அறிய", health: "பயிர் நலம்", advisor: "கிருஷிமித்ராவிடம் கேளுங்கள்" }, te: { overview: "హోమ్", soil: "నా నేలను తనిఖీ చేయండి", health: "పంట ఆరోగ్యం", advisor: "కృషిమిత్రను అడగండి" } })[language][item]}
            </button>
          ))}
        </nav>

        {view === "overview" && <Overview onNavigate={setView} />}
        {view === "health" && <CropHealth />}
        <Suspense fallback={<p role="status" className="panel mt-6">Loading…</p>}>
          {view === "soil" && <SoilHealth result={soil} onResult={setSoil} onExplain={() => { setExplainSoil(true); setView("advisor"); }} />}
          {view === "advisor" && <Advisor soil={explainSoil ? soil : null} onClearSoil={() => setExplainSoil(false)} />}
        </Suspense>
      </div>
    </main></LanguageContext.Provider>
  );
}

function Overview({ onNavigate }: { onNavigate: (view: View) => void }) {
  return (
    <>
      <section className="grid gap-7 py-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
        <div>
          <p className="mb-3 inline-block rounded-full bg-soil-50 px-3 py-1 text-sm font-semibold text-soil-700">PRACTICAL HELP FOR YOUR FARM</p>
          <h1 className="max-w-2xl text-4xl font-bold tracking-tight text-leaf-900 sm:text-5xl">Know your soil. Care for your crop.</h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-600">Explore crop options using your location, area soil and weather. Check a leaf photo, or ask a farming question in English, Hindi, Tamil or Telugu.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button className="rounded-xl bg-leaf-700 px-5 py-3 font-semibold text-white shadow-card transition hover:bg-leaf-900" onClick={() => onNavigate("soil")}>Check My Soil</button>
            <button className="rounded-xl border border-leaf-200 bg-white px-5 py-3 font-semibold text-leaf-700 transition hover:bg-leaf-50" onClick={() => onNavigate("advisor")}>Ask the advisor</button>
          </div>
        </div>
        <aside className="rounded-3xl bg-leaf-900 p-7 text-white shadow-card">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-leaf-100">Small steps. Better information.</p>
          <dl className="mt-6 space-y-5">
            <div><dt className="text-2xl font-bold">Soil & crop planning</dt><dd className="text-sm text-leaf-100">Automatic area estimates, weather and crop comparisons</dd></div>
            <div><dt className="text-2xl font-bold">Crops</dt><dd className="text-sm text-leaf-100">Leaf checks for four supported crops</dd></div>
            <div><dt className="text-2xl font-bold">Your language</dt><dd className="text-sm text-leaf-100">Speak, read and listen at your own pace</dd></div>
          </dl>
        </aside>
      </section>

      <section className="grid gap-5 md:grid-cols-3">
        <ModuleCard number="02" title="Soil & Crop Planning" detail="Choose your location to get mapped soil estimates, live weather and up to three crop options with transparent income and cost benchmarks. No soil values to type." action="Find crop options" onClick={() => onNavigate("soil")} />
        <ModuleCard number="01" title="Crop Health Intelligence" detail="The input guard rejects obvious non-leaf images before MobileNetV2 compares supported Tomato, Potato, Maize, and Grape leaf conditions. Low-confidence outputs are marked review-only, and accepted results are validated against the crop you selected." action="Open image upload" onClick={() => onNavigate("health")} />
        <ModuleCard number="03" title="AI Agronomy Chatbot" detail="Ask about soil, crops and watering. Speak or type in your language, then listen to the answer when you choose." action="Open chatbot" onClick={() => onNavigate("advisor")} />
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
  const [result, setResult] = useState<HealthPrediction | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return setMessage("Choose one clear leaf image first.");
    if (file.size > 10 * 1024 * 1024) return setMessage("Choose an image under 10 MB.");
    setIsSubmitting(true);
    setMessage(null);
    setResult(null);
    const form = new FormData();
    form.append("image", file);
    form.append("crop_hint", crop);
    try {
      const response = await fetch(`${apiBaseUrl}/health/predict`, { method: "POST", body: form, signal: AbortSignal.timeout(60000) });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(predictionErrorMessage(payload));
      setResult(payload as HealthPrediction);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Prediction could not be completed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="py-10">
      <SectionTitle
        eyebrow="Module 1"
        title="Crop Health Intelligence"
        detail="This check supports Tomato, Potato, Maize, and Grape only. Select the crop shown in the image so the result can be validated."
      />
      <div className="mt-7 grid gap-6 lg:grid-cols-[1fr_0.8fr]">
        <form className="rounded-3xl border border-leaf-100 bg-white p-6 shadow-card" onSubmit={submit}>
          <label className="block text-sm font-bold text-leaf-900" htmlFor="crop-hint">Expected crop (Crop Hint)</label>
          <select id="crop-hint" aria-describedby="crop-hint-help" className="mt-2 w-full rounded-xl border border-leaf-200 bg-white px-3 py-3 text-slate-700 focus:border-leaf-500 focus:outline-none" value={crop} onChange={(event) => setCrop(event.target.value)}>
            {supportedCrops.map((item) => <option key={item}>{item}</option>)}
          </select>
          <p id="crop-hint-help" className="mt-3 rounded-xl bg-leaf-50 p-3 text-sm leading-6 text-leaf-900">
            <strong>What this does:</strong> select the crop the uploaded leaf belongs to. This does not force a diagnosis; it validates the crop predicted by the model. If they differ, KrishiMitra marks the result as a mismatch and it must not be used as a diagnosis.
          </p>
          <label className="mt-6 grid min-h-52 cursor-pointer place-items-center rounded-2xl border-2 border-dashed border-leaf-200 bg-leaf-50 p-6 text-center transition hover:border-leaf-500">
            <input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setMessage(null); setResult(null); }} />
            <span><span className="block text-3xl">⌁</span><span className="mt-2 block font-semibold text-leaf-900">Choose a leaf image</span><span className="mt-1 block text-sm text-slate-500">PNG, JPG, or WebP · clear single leaf preferred</span></span>
          </label>
          {file && <p className="mt-3 text-sm text-leaf-700">Selected: {file.name}</p>}
          <button disabled={isSubmitting} className="mt-6 w-full rounded-xl bg-leaf-700 px-5 py-3 font-semibold text-white hover:bg-leaf-900 disabled:cursor-wait disabled:opacity-70" type="submit">{isSubmitting ? "Analysing…" : "Analyse leaf"}</button>
          {message && <p role="alert" className="mt-4 rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-900">{message}</p>}
        </form>
        <aside className="rounded-3xl bg-soil-50 p-6">
          <p className="font-bold text-soil-700">Result preview</p>
          {previewUrl ? <img className="mt-5 aspect-square w-full rounded-2xl object-cover" src={previewUrl} alt="Selected leaf preview" /> : <div className="mt-5 grid aspect-square place-items-center rounded-2xl border border-dashed border-soil-200 bg-white p-8 text-center text-sm text-slate-500">Your selected leaf will appear here.</div>}
          {result ? (
            <div className="mt-5 rounded-2xl bg-white p-4 text-sm text-slate-700">
              {result.crop_mismatch ? (
                <div role="alert" className="rounded-xl bg-amber-50 p-3 text-amber-950">
                  <p className="font-bold">Crop mismatch — do not use this as a diagnosis</p>
                  <p className="mt-1 leading-6">You selected <strong>{result.selected_crop ? formatCrop(result.selected_crop) : crop}</strong>, but the model detected <strong>{result.detected_crop ? formatCrop(result.detected_crop) : "a different supported crop"}</strong>. Choose the actual crop and analyse a clear leaf image again.</p>
                </div>
              ) : result.is_uncertain ? (
                <div role="status" className="rounded-xl bg-amber-50 p-3 text-amber-950">
                  <p className="font-bold">Low-confidence result — review only</p>
                  <p className="mt-1 leading-6">The model returned its closest supported label, but this is not a confirmed diagnosis. Try a sharper close-up photograph.</p>
                </div>
              ) : result.selected_crop && result.detected_crop ? <p className="rounded-xl bg-leaf-50 p-3 font-medium text-leaf-900">Crop validation passed: selected {formatCrop(result.selected_crop)} and detected {formatCrop(result.detected_crop)}.</p> : null}
              <p className={`mt-3 text-lg font-bold ${result.crop_mismatch || result.is_uncertain ? "text-amber-950" : "text-leaf-900"}`}>{result.crop_mismatch ? "Unvalidated classifier output" : result.predicted_label}</p>
              {result.crop_mismatch && <p className="mt-1 leading-6 text-amber-900">Initial classifier label: {result.predicted_label}. It is displayed for transparency only, not as a disease diagnosis.</p>}
              <p className="mt-1">Classifier confidence (accepted leaf only): <strong>{(result.confidence * 100).toFixed(1)}%</strong></p>
              <p className="mt-1">Model: {result.model_version}</p>
              {result.detected_crop && result.supported_conditions && <p className="mt-3 rounded-lg bg-soil-50 p-3 leading-6 text-soil-700"><strong>Model scope:</strong> for {formatCrop(result.detected_crop)}, this version only compares {result.supported_conditions.join(", ")}. A high score does not confirm diseases outside that list.</p>}
              <p className={`mt-3 rounded-lg p-3 ${result.is_uncertain || result.crop_mismatch ? "bg-amber-50 text-amber-900" : "bg-leaf-50 text-leaf-900"}`}>{result.advisory_reference}</p>
            </div>
          ) : <p className="mt-5 text-sm leading-6 text-slate-600">Start the FastAPI backend, then upload a supported leaf image to receive its real prediction.</p>}
        </aside>
      </div>
    </section>
  );
}

function SectionTitle({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) { return <div><p className="text-sm font-bold uppercase tracking-[0.15em] text-leaf-500">{eyebrow}</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-leaf-900">{title}</h1><p className="mt-3 max-w-2xl leading-7 text-slate-600">{detail}</p></div>; }

export default App;
