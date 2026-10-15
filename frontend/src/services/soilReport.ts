/** Conservative extraction: uncertain/multiple values remain empty for farmer review. */
export type SoilDraft = { values: Record<string, string>; units: Record<string, string>; sampleDate: string };
export type ExtractedReport = { draft: SoilDraft; warnings: string[]; evidence: Record<string, string> };
const labels: [string, RegExp][] = [
  ["nitrogen", /^(?:available\s+)?(?:nitrogen\s*(?:\(N\))?|N)\b/i],
  ["phosphorus", /^(?:available\s+)?(?:phosph(?:orus|orous)\s*(?:\(P\))?|P)\b/i],
  ["potassium", /^(?:available\s+)?(?:potassium\s*(?:\(K\))?|K)\b/i],
  ["sulphur", /^(?:available\s+)?(?:sulphur\s*(?:\(S\))?|sulfur\s*(?:\(S\))?|S)\b/i],
  ["zinc", /^(?:zinc\s*(?:\(Zn\))?|Zn)\b/i], ["iron", /^(?:iron\s*(?:\(Fe\))?|Fe)\b/i],
  ["copper", /^(?:copper\s*(?:\(Cu\))?|Cu)\b/i], ["manganese", /^(?:manganese\s*(?:\(Mn\))?|Mn)\b/i],
  ["boron", /^(?:boron\s*(?:\(B\))?|B)\b/i], ["ph", /^pH\b/i],
  ["electricalConductivity", /^(?:electrical\s+conductivity\s*(?:\(EC\))?|EC)\b/i],
  ["organicCarbon", /^(?:organic\s+carbon\s*(?:\(OC\))?|O\.?C\.?)\b/i],
];
const units = /kg\s*\/\s*ha|mg\s*\/\s*kg|g\s*\/\s*kg|dS\s*\/\s*m|mS\s*\/\s*cm|[uμµ]S\s*\/\s*cm|ppm|%/gi;
const canonical: Record<string, string> = { "kg/ha": "kg/ha", "mg/kg": "mg/kg", "g/kg": "g/kg", "ds/m": "dS/m", "ms/cm": "mS/cm", "us/cm": "uS/cm", ppm: "ppm", "%": "%" };

export function extractSoilText(text: string): ExtractedReport {
  const draft: SoilDraft = { values: {}, units: {}, sampleDate: "" };
  const warnings: string[] = []; const evidence: Record<string, string> = {}; const seen = new Set<string>();
  for (const raw of text.slice(0, 100000).split(/\r?\n/)) {
    const line = raw.trim().replace(/^\d{1,2}[.)]?\s+/, "");
    const match = labels.find(([, pattern]) => pattern.test(line));
    if (!match) continue;
    const [key, pattern] = match;
    // Different reports/samples and ambiguous duplicate rows must never silently overwrite.
    if (seen.has(key)) { delete draft.values[key]; delete draft.units[key]; delete evidence[key]; warnings.push(`Multiple ${key} rows found. Enter the value from the correct sample.`); continue; }
    seen.add(key);
    const remainder = line.replace(pattern, "");
    const unitMatches = remainder.match(units) || [];
    const clean = remainder.replace(units, "");
    const numbers = clean.match(/[-+]?\d+(?:[.,]\d+)?/g) || [];
    const residue = clean.replace(/[-+]?\d+(?:[.,]\d+)?/g, "").replace(/\b(?:N|P|K|S|Zn|Fe|Cu|Mn|B|OC|EC|low|medium|high|very|normal|acidic|alkaline|neutral|deficient|sufficient)\b/gi, "").replace(/[\s:;()|=]/g, "");
    if (residue || /P\s*2\s*O\s*5|K\s*2\s*O|[<>≤≥]|\d\s*[-–—]\s*\d/i.test(line) || numbers.length !== 1 || numbers[0].includes(",") || unitMatches.length > 1 || /\b(?:recommend|dose|fertilizer|ideal|range|reference)\b/i.test(line)) {
      warnings.push(`Check ${key}: the row is ambiguous or uses a different chemical basis.`); continue;
    }
    const value = Number(numbers[0]);
    if (!Number.isFinite(value) || value < 0 || (key === "ph" && value > 14)) { warnings.push(`Check ${key}: the value could not be read reliably.`); continue; }
    const unit = key === "ph" ? "pH" : unitMatches[0] ? canonical[unitMatches[0].replace(/\s/g, "").replace(/[μµ]/g, "u").toLowerCase()] : "";
    draft.values[key] = String(value); draft.units[key] = unit; evidence[key] = raw.trim();
    if (!unit) warnings.push(`Choose the printed unit for ${key}; no unit was assumed.`);
  }
  // Only unambiguous explicitly labelled ISO sample dates are copied automatically.
  const date = text.match(/(?:sample|sampling|test)\s+date\s*[:|]?\s*(\d{4}-\d{2}-\d{2})\b/i);
  if (date) draft.sampleDate = date[1];
  if (!Object.keys(draft.values).length) warnings.push("No unambiguous soil values were found. Use a clearer crop of the results table, paste its text, or enter the known values.");
  return { draft, warnings: [...new Set(warnings)], evidence };
}

export type SavedSoilReport = { id: string; name: string; savedAt: string; draft: SoilDraft };
export const REPORT_STORAGE_KEY = "soil-reports-v1";
export function validDraft(value: unknown): value is SoilDraft {
  if (!value || typeof value !== "object") return false;
  const d = value as SoilDraft;
  return typeof d.sampleDate === "string" && d.sampleDate.length <= 10 && Boolean(d.values && d.units)
    && [d.values, d.units].every(map => typeof map === "object" && !Array.isArray(map) && Object.entries(map).length <= 12 && Object.entries(map).every(([k,v]) => labels.some(([key]) => key === k) && typeof v === "string" && v.length <= 40));
}
