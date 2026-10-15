import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, readStored, storeLocal } from "../services/api";
import { currentLocation } from "../services/speech";
import { useLanguage } from "../i18n";
import ReportImport from "./ReportImport";
import { REPORT_STORAGE_KEY, SavedSoilReport, validDraft } from "../services/soilReport";

export const parameterGroups = [
  { title: "Primary nutrients", items: [["nitrogen", "Nitrogen (N)", "kg/ha,mg/kg,ppm"], ["phosphorus", "Phosphorus (P)", "kg/ha,mg/kg,ppm"], ["potassium", "Potassium (K)", "kg/ha,mg/kg,ppm"]] },
  { title: "Soil condition", items: [["ph", "pH", "pH"], ["electricalConductivity", "Electrical conductivity (EC)", "dS/m,mS/cm,uS/cm"], ["organicCarbon", "Organic carbon (OC)", "%,g/kg"]] },
  { title: "Other nutrients", items: [["sulphur", "Sulphur (S)", "mg/kg,ppm,kg/ha"], ["zinc", "Zinc (Zn)", "mg/kg,ppm"], ["iron", "Iron (Fe)", "mg/kg,ppm"], ["copper", "Copper (Cu)", "mg/kg,ppm"], ["manganese", "Manganese (Mn)", "mg/kg,ppm"], ["boron", "Boron (B)", "mg/kg,ppm"]] },
];
export type SoilResult = {
  profile: { parameters: Record<string, { value: number; unit: string; method?: string }>;
    source: string; source_type: "GOVERNMENT_VERIFIED" | "USER_ENTERED" | "AI_ESTIMATED";
    location: { state: string; district: string; block: string; village: string };
    sample_date: string | null; retrieved_at: string; coverage: string; is_demo: boolean;
  };
  profile_token: string; cached: boolean;
  recommendation: { summary: string; steps: string[]; limitations: string[]; missing_parameters: string[] };
};
type DirectoryItem = { id: string; name: string };
type Draft = { values: Record<string, string>; units: Record<string, string>; sampleDate: string };
const emptyDraft: Draft = { values: {}, units: {}, sampleDate: "" };
function restoredDraft(): Draft {
  const draft = readStored<Draft>("soil-draft-v1", emptyDraft);
  if (!draft || typeof draft.sampleDate !== "string" || !draft.values || !draft.units || typeof draft.values !== "object" || typeof draft.units !== "object") return emptyDraft;
  return { sampleDate: draft.sampleDate, values: Object.fromEntries(Object.entries(draft.values).filter(([,v]) => typeof v === "string")), units: Object.fromEntries(Object.entries(draft.units).filter(([,v]) => typeof v === "string")) };
}

export default function SoilHealth({ result, onResult, onExplain }: { result: SoilResult | null; onResult: (r: SoilResult) => void; onExplain: () => void }) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<"import" | "location" | "manual" | null>(null);
  const [needsReview, setNeedsReview] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [saveReport, setSaveReport] = useState(false);
  const [reportName, setReportName] = useState("");
  const [reports, setReports] = useState<SavedSoilReport[]>(() => {
    const saved = readStored<unknown>(REPORT_STORAGE_KEY, []);
    return Array.isArray(saved) ? saved.filter(r => r && typeof r.id === "string" && typeof r.name === "string" && r.name.length <= 60 && typeof r.savedAt === "string" && validDraft(r.draft)).slice(0, 10) : [];
  });
  const [draft, setDraft] = useState<Draft>(restoredDraft);
  const [save, setSave] = useState(() => readStored<boolean>("soil-draft-consent", false) === true);
  const [storageError, setStorageError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState("");
  const resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (result) resultHeading.current?.focus(); }, [result]);
  const [selected, setSelected] = useState({ state: "", district: "", block: "", village: "" });
  const directory = (level: string, enabled: boolean, query = "") => ({ queryKey: ["soil-directory", level, query], queryFn: () => api<DirectoryItem[]>(`/soil/locations/${level}${query}`), enabled: mode === "location" && enabled, staleTime: 900000, retry: false });
  const states = useQuery(directory("states", true));
  const districts = useQuery(directory("districts", !!selected.state, `?state=${encodeURIComponent(selected.state)}`));
  const blocks = useQuery(directory("blocks", !!selected.district, `?state=${encodeURIComponent(selected.state)}&district=${encodeURIComponent(selected.district)}`));
  const villages = useQuery(directory("villages", !!selected.block, `?district=${encodeURIComponent(selected.district)}&block=${encodeURIComponent(selected.block)}`));
  const directoryError = [states, districts, blocks, villages].find(q => q.error);

  useEffect(() => {
    if (save) setStorageError(!storeLocal("soil-draft-v1", draft));
  }, [save, draft]);

  const receive = (response: SoilResult | { profile: null; message: string }) => {
    if (response.profile === null) setEmpty(response.message);
    else { onResult(response as SoilResult); setEmpty(""); }
  };
  const runLookup = async (coordinates?: { latitude: number; longitude: number }) => {
    setBusy(true); setError(""); setEmpty("");
    try {
      const location = { state_id: selected.state, district_id: selected.district, block_id: selected.block, village_id: selected.village,
        state: states.data?.find(i => i.id === selected.state)?.name || "", district: districts.data?.find(i => i.id === selected.district)?.name || "",
        block: blocks.data?.find(i => i.id === selected.block)?.name || "", village: villages.data?.find(i => i.id === selected.village)?.name || "" };
      receive(await api<SoilResult | { profile: null; message: string }>("/soil/lookup", coordinates || { location }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const gps = async () => {
    setBusy(true); setError("");
    try { const position = await currentLocation(); await runLookup({ latitude: position.coords.latitude, longitude: position.coords.longitude }); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const manual = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setEmpty("");
    if (needsReview && !reviewed) return setError("Compare the imported values and units with your report, then confirm the review below.");
    if (saveReport && !reportName.trim()) return setError("Name this report so you can find it next time.");
    const parameters: Record<string, { value: number; unit: string }> = {};
    for (const [key, label] of parameterGroups.flatMap(group => group.items)) {
      const raw = draft.values[key]?.trim();
      if (!raw) continue;
      if (!Number.isFinite(Number(raw)) || Number(raw) < 0) return setError(`Check ${label}: enter a positive number or zero.`);
      if (!draft.units[key] && key !== "ph") return setError(`Choose the unit printed on your report for ${label}.`);
      parameters[key] = { value: Number(raw), unit: key === "ph" ? "pH" : draft.units[key] };
    }
    if (!Object.keys(parameters).length) return setError("Enter at least one value from your soil-test report. Leave unknown values blank.");
    setBusy(true);
    try {
      receive(await api<SoilResult>("/soil/manual", { parameters, sample_date: draft.sampleDate || null }));
      if (saveReport) {
        const entry = { id: crypto.randomUUID(), name: reportName.trim().slice(0,60), savedAt: new Date().toISOString(), draft };
        const next = [entry, ...reports].slice(0, 10);
        if (storeLocal(REPORT_STORAGE_KEY, next)) { setReports(next); setSaveReport(false); }
        else setError("The soil result is ready, but this browser could not save the report. Keep a copy of the original.");
      }
    }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const clear = () => { setSave(false); setDraft(emptyDraft); setNeedsReview(false); setReviewed(false); storeLocal("soil-draft-consent", false); storeLocal("soil-draft-v1", null); setError(""); };

  return <section className="py-8" aria-labelledby="soil-title">
    <p className="eyebrow">SOIL HEALTH</p><h1 id="soil-title" className="text-3xl font-bold mt-2">{t("Check My Soil")}</h1>
    <p className="mt-3 text-slate-600">{t("Choose where your soil information comes from. A laboratory test gives the most reliable picture of your field.")}</p>
    {reports.length > 0 && <div className="panel mt-5"><h2 className="text-xl font-bold">{t("Saved soil reports")}</h2><p className="help">Stored on this device. Choose the right field and test date; an old report does not describe today's soil.</p>{reports.map(report => <div className="saved-report" key={report.id}><div><strong>{report.name}</strong><p className="help">Sample date: {report.draft.sampleDate || "Not supplied"} · {Object.keys(report.draft.values).length} values</p></div><div className="actions"><button className="secondary" aria-label={`Use ${report.name}`} onClick={() => { setDraft(report.draft); setReportName(report.name); setNeedsReview(true); setReviewed(false); setMode("manual"); setError(""); }}>{t("Use saved report")}</button><button className="secondary" aria-label={`Delete ${report.name}`} onClick={() => { const next = reports.filter(r => r.id !== report.id); if (storeLocal(REPORT_STORAGE_KEY, next)) setReports(next); else setError("This browser could not remove the saved report."); }}>{t("Delete")}</button></div></div>)}</div>}
    <div className="choice-grid">
      <button className={`choice ${mode === "import" ? "selected" : ""}`} aria-pressed={mode === "import"} onClick={() => { setMode("import"); setError(""); }}><span aria-hidden="true">▧</span><strong>{t("Scan or import your soil report")}</strong><small>{t("Read a photo or PDF, check the values, and save them for next time.")}</small></button>
      <button className={`choice ${mode === "manual" ? "selected" : ""}`} aria-pressed={mode === "manual"} onClick={() => { setMode("manual"); setError(""); }}><span aria-hidden="true">▤</span><strong>{t("Enter Soil Test Values Manually")}</strong><small>{t("Copy only the values you know from your report.")}</small></button>
    </div>
    <details className="soil-group"><summary>{t("Optional government connection")}</summary><p className="help">For deployments with approved Soil Health Card API access. Most farmers should import their own report above.</p><button className="secondary mt-3" aria-pressed={mode === "location"} onClick={() => { setMode("location"); setError(""); }}>{t("Get Soil Data Using My Location")}</button></details>
    {mode === "import" && <ReportImport onReview={next => { setDraft(next); setNeedsReview(true); setReviewed(false); setMode("manual"); setError(""); }} />}
    {mode === "location" && <div className="panel mt-5">
      <p className="notice">Automatic government lookup is an optional authorized integration, not a public API. Without issued access, import your own report instead.</p><button className="primary mt-3" onClick={() => setMode("import")}>{t("Scan or import your soil report")}</button>
      <h2 className="text-xl font-bold">{t("Select Location Manually")}</h2>
      <p className="help">Location is requested only when you tap the button. We do not track you or save GPS coordinates. The current government API requires a village selection; GPS lookup is not yet available.</p>
      <button className="secondary mt-3" disabled={busy} onClick={gps}>⌖ {t("Use My Current Location")}</button>
      <div className="field-grid mt-5">
        {([ ["state", "State", states], ["district", "District", districts], ["block", "Block / Taluka / Mandal", blocks], ["village", "Village", villages] ] as const).map(([key, label, query]) => <label key={key}>{t(label)}
          <select value={selected[key]} disabled={busy || !query.data?.length} onChange={e => setSelected(current => ({ ...current, [key]: e.target.value, ...(key === "state" ? { district: "", block: "", village: "" } : key === "district" ? { block: "", village: "" } : key === "block" ? { village: "" } : {}) }))}>
            <option value="">{query.isFetching ? t("Working…") : t("Choose")}</option>{query.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>)}
      </div>
      {directoryError && <div role="alert" className="notice">{(directoryError.error as Error).message} <button className="secondary" onClick={() => directoryError.refetch()}>{t("Retry")}</button></div>}
      <button className="primary mt-5" disabled={busy || !selected.village} onClick={() => runLookup()}>{busy ? t("Working…") : t("Find Soil Data")}</button>
    </div>}
    {mode === "manual" && <form className="panel mt-5" onSubmit={manual}>
      <p className="help">{t("Copy the number and unit exactly as printed. Leave unknown values blank. We do not convert units or assume a test method.")}</p>
      {parameterGroups.map((group, index) => <details className="soil-group" key={group.title} open={index < 2 || needsReview}>
        <summary>{t(group.title)}</summary><div className="field-grid">
          {group.items.map(([key, label, units]) => <div key={key} className="soil-field"><label htmlFor={`soil-${key}`}>{t(label)}</label>
            <div className="value-unit"><input id={`soil-${key}`} type="number" inputMode="decimal" min="0" max={key === "ph" ? 14 : undefined} step="any" value={draft.values[key] || ""} aria-describedby={`help-${key}`} onChange={e => setDraft(current => ({ ...current, values: { ...current.values, [key]: e.target.value } }))} />
              {key === "ph" ? <span className="unit">pH</span> : <select aria-label={`${label} unit`} value={draft.units[key] || ""} onChange={e => setDraft(current => ({ ...current, units: { ...current.units, [key]: e.target.value } }))}><option value="">{t("Unit")}</option>{units.split(",").map(unit => <option key={unit}>{unit}</option>)}</select>}
            </div><p className="help" id={`help-${key}`}>{key === "ph" ? t("How acidic or alkaline the soil is: 0–14.") : t("Use the unit on your report. Blank means unknown.")}</p>
          </div>)}
        </div></details>)}
      <label className="block max-w-xs">{t("Sample date (optional)")}<input type="date" max={new Date().toLocaleDateString("en-CA")} value={draft.sampleDate} onChange={e => setDraft(current => ({ ...current, sampleDate: e.target.value }))} /></label>
      {needsReview && <label className="consent"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />{t("I checked every value and unit against the original report")}</label>}
      <label className="consent"><input type="checkbox" checked={saveReport} onChange={e => setSaveReport(e.target.checked)} />{t("Save as a reusable report on this device")}</label>
      {saveReport && <><label className="block max-w-xs">{t("Report name")}<input value={reportName} maxLength={60} placeholder="e.g. North field — September" onChange={e => setReportName(e.target.value)} /></label><p className="help">Anyone using this device can see saved values. Only the latest 10 reports are kept. You can delete each report above. The original photo/PDF is not saved.</p></>}
      <label className="consent"><input type="checkbox" checked={save} onChange={e => { setSave(e.target.checked); storeLocal("soil-draft-consent", e.target.checked); if (!e.target.checked) storeLocal("soil-draft-v1", null); }} />{t("Save this form on this device")}</label>
      {save && <p className="help">Anyone using this device may see the saved draft. Use “Clear saved draft” on shared phones.</p>}
      {storageError && <p role="status" className="notice">This browser could not save the draft. Keep this page open until you submit.</p>}
      <div className="actions mt-5"><button type="submit" className="primary" disabled={busy}>{busy ? t("Working…") : t("Use These Soil Values")}</button><button type="button" className="secondary" onClick={clear}>{t("Clear saved draft")}</button></div>
    </form>}
    {(error || empty) && <div className="notice mt-5" role="alert"><p>{error || empty}</p>{mode === "location" && <div className="actions mt-3"><button className="secondary" onClick={() => setMode("manual")}>{t("Enter Soil Test Values Manually")}</button>{selected.village && <button className="secondary" disabled={busy} onClick={() => runLookup()}>{t("Retry")}</button>}</div>}</div>}
    {result && <article className="panel mt-6" aria-label="Soil result">
      {(error || empty) && <p className="notice">Your previous result is shown below. The latest request did not replace it.</p>}
      <span className={`source-badge ${result.profile.source_type === "AI_ESTIMATED" ? "estimated" : ""}`}>{result.profile.is_demo ? "DEMO — SYNTHETIC VALUES" : t({ GOVERNMENT_VERIFIED: "Government Soil Data", USER_ENTERED: "Entered by You", AI_ESTIMATED: "AI Estimate — Not a Soil Test" }[result.profile.source_type])}</span>
      <h2 ref={resultHeading} tabIndex={-1} className="text-2xl font-bold mt-4">{t("Your soil information")}</h2>
      <p className="help">Source: {result.profile.source} · Sample date: {result.profile.sample_date || "Not supplied"}</p>
      <p className="help">Location: {[result.profile.location.village, result.profile.location.block, result.profile.location.district, result.profile.location.state].filter(Boolean).join(", ") || "Not supplied"} · Retrieved: {new Date(result.profile.retrieved_at).toLocaleString()}{result.cached ? " · Cached result" : ""}</p>
      {result.profile.coverage === "area_sample" && <p className="notice">This is an area sample. It may be old and may not represent your field today.</p>}
      {result.profile.source_type === "AI_ESTIMATED" && <p className="notice">Estimated — laboratory soil testing is recommended for accurate fertilizer decisions.</p>}
      <div className="results-grid">{parameterGroups.flatMap(g => g.items).map(([key, label]) => { const measurement = result.profile.parameters[key]; return measurement && <div className="result-value" key={key}><p>{t(label)}</p><strong>{measurement.value} <small>{measurement.unit}</small></strong><p className="help">{measurement.method || "Test method not supplied"}</p></div>; })}</div>
      <p className="mt-4">{result.recommendation.summary}</p><ul className="guidance">{result.recommendation.steps.map(step => <li key={step}>{step}</li>)}</ul>
      <p className="help">{result.recommendation.limitations[0]}</p><button className="primary mt-4" onClick={onExplain}>{t("What can I do?")}</button>
    </article>}
    <details className="soil-group mt-6"><summary>How do I get a Soil Health Card or soil test?</summary><p className="mt-3">Contact your local agriculture office or KVK for sample collection and testing. Use the official portal’s laboratory directory and take your report to an agricultural officer for crop-specific recommendations.</p><a className="text-link" href="https://soilhealth.dac.gov.in/" target="_blank" rel="noreferrer">Open the official Soil Health Card portal ↗</a></details>
  </section>;
}
