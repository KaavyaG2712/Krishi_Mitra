import { useEffect, useRef, useState } from "react";
import { useLanguage } from "../i18n";
import { extractSoilText, ExtractedReport, SoilDraft } from "../services/soilReport";

export default function ReportImport({ onReview }: { onReview: (draft: SoilDraft) => void }) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false); const [progress, setProgress] = useState("");
  const [error, setError] = useState(""); const [text, setText] = useState("");
  const [extracted, setExtracted] = useState<ExtractedReport | null>(null);
  const [preview, setPreview] = useState<{ url: string; image: boolean } | null>(null);
  const job = useRef<AbortController>();
  useEffect(() => () => job.current?.abort(), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);
  const cancel = () => { job.current?.abort(); setBusy(false); setProgress(""); };
  const read = async (file?: File) => {
    if (!file) return;
    job.current?.abort(); const controller = new AbortController(); job.current = controller;
    setBusy(true); setError(""); setExtracted(null); setProgress("Reading report…");
    setPreview({ url: URL.createObjectURL(file), image: file.type.startsWith("image/") });
    const timeout = setTimeout(() => { controller.abort(); if (job.current === controller) { setBusy(false); setError("Reading took too long. Try a cropped, clearer photo or paste the results text."); } }, 90000);
    try {
      const { readSoilReport } = await import("../services/reportReader");
      const content = await readSoilReport(file, message => { if (!controller.signal.aborted) setProgress(message); }, controller.signal);
      if (!controller.signal.aborted) { setText(content.slice(0, 100000)); setExtracted(extractSoilText(content)); }
    } catch (e) { if (!controller.signal.aborted) setError((e as Error).message || "Could not read this report. Try another photo or paste the text."); }
    finally { clearTimeout(timeout); if (job.current === controller && !controller.signal.aborted) setBusy(false); }
  };
  return <div className="panel mt-5">
    <h2 className="text-xl font-bold">{t("Scan or import your soil report")}</h2>
    <p className="help">{t("Choose a photo or PDF of one soil sample. Reading happens on this device; no government API key is needed.")}</p>
    <p className="help">Use a clear, upright photo of the results table. Printed English labels or chemical symbols work best. The reader downloads once from this app; your report is not sent to an OCR service.</p>
    <label className="block mt-4">{t("Soil report photo or PDF")}<input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" disabled={busy} onChange={e => { void read(e.target.files?.[0]); e.target.value = ""; }} /></label>
    <p className="help">JPG, PNG, WebP or PDF · up to 10 MB · up to 3 pages · one sample at a time</p>
    {busy && <div className="actions"><p role="status">{progress}</p><button className="secondary" onClick={cancel}>{t("Cancel")}</button></div>}
    {error && <p role="alert" className="notice">{error}</p>}
    <details className="soil-group"><summary>{t("Paste report text instead")}</summary><label>{t("Report text")}<textarea rows={5} maxLength={100000} value={text} disabled={busy} onChange={e => setText(e.target.value)} /></label><button className="secondary mt-3" disabled={busy || !text.trim()} onClick={() => { setError(""); setExtracted(extractSoilText(text)); }}>{t("Read pasted values")}</button></details>
    {extracted && <div className="mt-4">
      <h3 className="font-bold">{Object.keys(extracted.draft.values).length} {t("values found — review before use")}</h3>
      <p className="notice">{t("Reading can make mistakes. Compare each value and unit with your report. Imported data is not government-verified.")}</p>
      {preview?.image && <img src={preview.url} alt="Your soil report for comparison" className="report-preview" />}
      {preview && !preview.image && <a className="text-link" href={preview.url} target="_blank" rel="noreferrer">Open your original PDF ↗</a>}
      <ul className="guidance">{Object.entries(extracted.evidence).map(([key, line]) => <li key={key}>{line}</li>)}</ul>
      {extracted.warnings.map(warning => <p className="help" key={warning}>{warning}</p>)}
      {Object.keys(extracted.draft.values).length > 0 && <button className="primary mt-4" onClick={() => onReview(extracted.draft)}>{t("Review these values")}</button>}
    </div>}
    <p className="help mt-4">Already have a Soil Health Card? Download your own card through the official portal, then import it here. You can also photograph a paper report from your soil-testing lab.</p>
    <a className="text-link" href="https://soilhealth.dac.gov.in/soilhealthcard" target="_blank" rel="noreferrer">Open Soil Health Card portal ↗</a>
  </div>;
}
