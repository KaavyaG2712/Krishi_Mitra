import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import { currentLocation } from "../services/speech";
import { useLanguage } from "../i18n";

type Place = { name: string; latitude: number; longitude: number };
type Money = { yield_kg_ha: number; yield_scope: string; price_inr_quintal: number; cost_inr_quintal: number;
  marketing_season: string; cost_inr_ha: number; revenue_inr_ha: number; surplus_inr_ha: number;
  surplus_for_area: number; downside_inr_ha: number; source_url: string };
type Candidate = { rank: number; id: string; name: string; reasons: string[]; cautions: string[]; economics: Money; requirements_source: string };
type Plan = {
  status: "provisional" | "no_match" | "insufficient_data";
  request: Place & { location_name: string; sowing_date: string; irrigation: string; area_ha: number };
  soil: { status: string; message?: string; source?: string; source_url?: string; note?: string; reference_period?: string;
    retrieved_at?: string; measurements?: Record<string, { value: number; unit: string; source_url: string }> };
  forecast: { status: string; message?: string; temperature_c?: number; observed_at?: string; source_url?: string;
    days?: { date: string; high_c: number; low_c: number; rain_mm: number }[] };
  climate: { status: string; message?: string; period?: string; annual_rain_mm?: number; source_url?: string };
  top_crops: Candidate[]; excluded: { crop: string; reasons: string[] }[]; warnings: string[];
  generated_at: string; catalog_version: string; ranking_basis: string; yield_source: string; yield_period: string;
};
const rupees = (v: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(v);
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;

export default function CropPlanner() {
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  const [sowingDate, setSowingDate] = useState(localDate(new Date()));
  const [irrigation, setIrrigation] = useState("unknown");
  const [area, setArea] = useState("1");
  const [unit, setUnit] = useState("hectare");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const generation = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { generation.current++; activeRequest.current?.abort(); }, []);
  useEffect(() => { if (plan) heading.current?.focus(); }, [plan]);
  const reset = () => { setPlan(null); setError(""); };

  const search = async (e: FormEvent) => {
    e.preventDefault(); if (query.trim().length < 2) return;
    const id = ++generation.current;
    activeRequest.current = new AbortController();
    reset(); setPlace(null); setPlaces([]); setBusy("Finding your place…");
    try {
      const found = await api<Place[]>(`/planning/locations?q=${encodeURIComponent(query.trim())}`, undefined, { signal: activeRequest.current.signal });
      if (id !== generation.current) return;
      setPlaces(found);
      if (!found.length) setError("No matching place was found. Try a nearby town or use your current location.");
    } catch (e) { if (id === generation.current) setError((e as Error).message); }
    finally { if (id === generation.current) setBusy(""); }
  };
  const gps = async () => {
    const id = ++generation.current;
    reset(); setBusy("Waiting for location permission…"); setPlace(null); setPlaces([]);
    try {
      const p = await currentLocation();
      if (id !== generation.current) return;
      setPlace({ name: "My current location", latitude: p.coords.latitude, longitude: p.coords.longitude });
      setQuery("");
    } catch (e) { if (id === generation.current) setError((e as Error).message); }
    finally { if (id === generation.current) setBusy(""); }
  };
  const recommend = async (e: FormEvent) => {
    e.preventDefault();
    if (!place) return setError("Choose a search result or use your current location first.");
    const hectares = Number(area) * (unit === "acre" ? 0.40468564224 : 1);
    if (!Number.isFinite(hectares) || hectares <= 0 || hectares > 10000) return setError("Enter a field area greater than zero and at most 10,000 hectares.");
    const id = ++generation.current;
    activeRequest.current = new AbortController();
    reset(); setBusy("Reading area soil, live weather and historical climate… The first request can take up to two minutes.");
    try {
      const response = await api<Plan>("/planning/recommend", { latitude: place.latitude, longitude: place.longitude,
        location_name: place.name, sowing_date: sowingDate, irrigation, area_ha: hectares }, { signal: activeRequest.current.signal, timeoutMs: 120000 });
      if (id === generation.current) setPlan(response);
    } catch (e) { if (id === generation.current) setError((e as Error).message); }
    finally { if (id === generation.current) setBusy(""); }
  };
  const yearAhead = new Date(); yearAhead.setDate(yearAhead.getDate()+365);
  return <section className="crop-planner py-8" aria-labelledby="planner-title">
    <p className="eyebrow">MODULE 02 · {t("SOIL & CROP PLANNING")}</p>
    <h1 id="planner-title" className="text-3xl font-bold mt-2">{t("Find crops for my area")}</h1>
    <p className="mt-3 text-slate-600">{t("Start with your location. We read the soil map and weather for you—no soil values to type.")}</p>
    <div className="planner-inputs panel mt-6">
      <h2 className="text-xl font-bold">1. {t("Choose your location")}</h2>
      <p className="help">Mainland India · Choose the nearest town if your village is missing. GPS is requested once when you tap below. Coordinates are sent to the weather service; the backend reads the matching public soil map cell.</p>
      <button className="primary mt-3" disabled={!!busy} onClick={gps}>⌖ {t("Use My Current Location")}</button>
      <form className="place-search mt-4" onSubmit={search}>
        <label>{t("Village or town")}<input value={query} maxLength={100} minLength={2} required disabled={!!busy} placeholder="e.g. Warangal" onChange={e => { setQuery(e.target.value); setPlace(null); setPlaces([]); reset(); }} /></label>
        <button type="submit" className="secondary" disabled={!!busy || query.trim().length < 2}>{t("Search location")}</button>
      </form>
      {places.length > 0 && <div className="place-results" aria-label="Matching places">{places.map((p, i) => <button key={i} type="button" className="secondary" disabled={!!busy} aria-pressed={place === p} onClick={() => { setPlace(p); reset(); }}><strong>{p.name}</strong><span>{p.latitude.toFixed(4)}, {p.longitude.toFixed(4)}</span></button>)}</div>}
      {place && <p className="selected-place" role="status">✓ {place.name} · {place.latitude.toFixed(4)}, {place.longitude.toFixed(4)}</p>}
      <form onSubmit={recommend} className="mt-6">
        <h2 className="text-xl font-bold">2. {t("Plan your season")}</h2>
        <div className="field-grid mt-3">
          <label>{t("Planned sowing date")}<input type="date" required disabled={!!busy} value={sowingDate} min={localDate(new Date())} max={localDate(yearAhead)} onChange={e => { setSowingDate(e.target.value); reset(); }} /></label>
          <label>{t("Water availability")}<select value={irrigation} disabled={!!busy} onChange={e => { setIrrigation(e.target.value); reset(); }}><option value="unknown">{t("Not sure yet")}</option><option value="rainfed">{t("Rainfall only")}</option><option value="available">{t("Irrigation available")}</option></select></label>
          <label>{t("Field area")}<input type="number" required min="0.001" step="any" disabled={!!busy} value={area} onChange={e => { setArea(e.target.value); reset(); }} /></label>
          <label>{t("Area unit")}<select value={unit} disabled={!!busy} onChange={e => { setUnit(e.target.value); reset(); }}><option value="hectare">{t("Hectares")}</option><option value="acre">{t("Acres")}</option></select></label>
        </div>
        <button type="submit" className="primary mt-5" disabled={!!busy || !place}>{t("Find my top crop options")}</button>
        <p className="help mt-3">Compare up to three supported crops by estimated surplus using published national yield, price and cost benchmarks. Confirm local prices and costs before planting.</p>
      </form>
    </div>
    {busy && <div className="notice mt-5"><p role="status" aria-live="polite">{busy}</p><button type="button" className="secondary mt-3" onClick={() => { generation.current++; activeRequest.current?.abort(); setBusy(""); }}>Cancel lookup</button></div>}
    {error && <p className="notice mt-5" role="alert">{error}</p>}
    {plan && <div className="mt-7">
      <h2 ref={heading} tabIndex={-1} className="text-2xl font-bold">{t("Your area and crop options")}</h2>
      <p className="help">{plan.request.location_name} · Sowing {plan.request.sowing_date} · {plan.request.area_ha.toFixed(2)} ha · Checked {new Date(plan.generated_at).toLocaleString()}</p>
      <div className="planner-evidence mt-4">
        <article className="panel"><span className="source-badge estimated">{t("Area soil estimate")}</span><h3 className="text-lg font-bold mt-3">{t("Soil near your location")}</h3>
          {plan.soil.measurements ? <><dl className="soil-snapshot">{Object.entries(plan.soil.measurements).map(([key, m]) => <div key={key}><dt>{{ ph: "pH", organic_carbon: "Organic carbon", sand: "Sand content" }[key] || key}</dt><dd>{m.value} {m.unit}</dd></div>)}</dl><p className="help">250 m map · 10 cm depth · {plan.soil.reference_period}</p><p className="help">{plan.soil.note}</p><a className="text-link" href={plan.soil.source_url} target="_blank" rel="noreferrer">{plan.soil.source} ↗</a></> : <p className="notice">{plan.soil.message}</p>}
        </article>
        <article className="panel"><span className="source-badge">{t("Weather & climate")}</span><h3 className="text-lg font-bold mt-3">{plan.forecast.temperature_c !== undefined ? `${plan.forecast.temperature_c} °C now` : "Live weather unavailable"}</h3>
          {plan.forecast.days ? <><p className="help">Model weather time: {plan.forecast.observed_at} IST</p><div className="weather-days">{plan.forecast.days.map(d => <div key={d.date}><strong>{new Date(`${d.date}T12:00:00`).toLocaleDateString("en-IN", { weekday: "short" })}</strong><span>{d.high_c}° / {d.low_c}°</span><small>{d.rain_mm} mm</small></div>)}</div><a className="text-link" href={plan.forecast.source_url} target="_blank" rel="noreferrer">Open-Meteo forecast ↗</a></> : <p className="notice">{plan.forecast.message}</p>}
          {plan.climate.status === "available" ? <p className="help mt-3">Annual rainfall baseline: {plan.climate.annual_rain_mm} mm ({plan.climate.period}). <a className="text-link" href={plan.climate.source_url} target="_blank" rel="noreferrer">Historical climate ↗</a></p> : <p className="notice">{plan.climate.message}</p>}
        </article>
      </div>
      {plan.status === "insufficient_data" && <p className="notice mt-5" role="alert">We need mapped pH and historical climate to rank crops. A source is unavailable or incomplete. Retry using the button above; no crop ranking or soil values have been invented.</p>}
      {plan.status === "no_match" && <p className="notice mt-5" role="status">No supported crops passed all checks for this date and water choice. Review the reasons below or try another sowing date. We do not fill the list with unsuitable crops.</p>}
      {plan.top_crops.length > 0 && <><div className="mt-7"><h3 className="text-2xl font-bold">{plan.top_crops.length} {t("crop options to compare")}</h3><p className="help">Provisional shortlist · {plan.ranking_basis}. Figures are a benchmark scenario, not guaranteed net profit.</p></div>
        <div className="crop-shortlist mt-4">{plan.top_crops.map(c => <article className="panel crop-option" key={c.id}>
          <span className="rank-number">{c.rank}</span><h4 className="text-2xl font-bold mt-3">{c.name}</h4>
          <p className="help mt-3">Benchmark surplus / hectare</p><p className="crop-income">{rupees(c.economics.surplus_inr_ha)}</p>
          <p className="help">{rupees(c.economics.surplus_for_area)} for your {plan.request.area_ha.toFixed(2)} ha · before full land/capital opportunity costs</p>
          <p className="downside">Downside scenario: <strong>{rupees(c.economics.downside_inr_ha)}/ha</strong></p>
          <ul className="guidance">{c.reasons.map(r => <li key={r}>{r}</li>)}</ul>
          {c.cautions.length > 0 && <p className="notice mt-3">{c.cautions[0]}</p>}
          {c.cautions.length > 0 && <details className="soil-group"><summary>Conditions to check ({c.cautions.length})</summary><ul className="guidance">{c.cautions.map(r => <li key={r}>{r}</li>)}</ul></details>}
          <details className="soil-group"><summary>Price, yield and cost assumptions</summary><dl className="economics-list">
            <dt>Yield benchmark</dt><dd>{c.economics.yield_kg_ha} kg/ha · {c.economics.yield_scope} ({plan.yield_period})</dd>
            <dt>MSP scenario</dt><dd>{rupees(c.economics.price_inr_quintal)}/quintal · marketing year {c.economics.marketing_season}</dd>
            <dt>Revenue</dt><dd>{rupees(c.economics.revenue_inr_ha)}/ha</dd><dt>A2+FL cost benchmark</dt><dd>{rupees(c.economics.cost_inr_ha)}/ha</dd>
          </dl><p className="help">Surplus = yield ÷ 100 × MSP − benchmark cultivation cost. Downside = 75% yield × 80% price − 120% cost. MSP access and local selling price are unconfirmed.</p><a className="text-link" href={c.economics.source_url} target="_blank" rel="noreferrer">Government price/cost table ↗</a><br/><a className="text-link" href={c.requirements_source} target="_blank" rel="noreferrer">FAO crop requirements ↗</a></details>
        </article>)}</div></>}
      <details className="panel mt-5"><summary className="font-bold">How this comparison works and what is missing</summary><ul className="guidance">{plan.warnings.map(w => <li key={w}>{w}</li>)}</ul><a href={plan.yield_source} className="text-link" target="_blank" rel="noreferrer">Government yield dataset, table 2.1 ↗</a><p className="help">Catalogue reviewed {plan.catalog_version}. No crop-profit model has been trained or field-validated.</p></details>
      {plan.excluded.length > 0 && <details className="panel mt-4"><summary className="font-bold">Why other crops were excluded</summary>{plan.excluded.map(c => <p className="help mt-3" key={c.crop}><strong>{c.crop}:</strong> {c.reasons.join(". ")}</p>)}</details>}
    </div>}
  </section>;
}
