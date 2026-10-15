import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { extractSoilText, REPORT_STORAGE_KEY, validDraft } from "../services/soilReport";
import SoilHealth from "../components/SoilHealth";

const sample = "SYNTHETIC TEST REPORT\nNitrogen (N) 210 kg/ha\nPhosphorus (P) 14.2 kg/ha\nPotassium (K) 180 kg/ha\npH 7.1\nOrganic Carbon (OC) 0.65 %\nEC 0.3 dS/m\nZn 1.2 ppm\nTest date: 2026-01-20";
it("extracts explicit values, units and dates without filling missing elements", () => {
  const { draft } = extractSoilText(sample);
  expect(draft.values).toEqual({ nitrogen: "210", phosphorus: "14.2", potassium: "180", ph: "7.1", organicCarbon: "0.65", electricalConductivity: "0.3", zinc: "1.2" });
  expect(draft.units.organicCarbon).toBe("%"); expect(draft.sampleDate).toBe("2026-01-20");
});
it("leaves reference ranges, different chemical bases, duplicates and ambiguous decimals for review", () => {
  const { draft, warnings } = extractSoilText("pH 6.5 - 7.5\nPhosphorus (P2O5) 20 kg/ha\nK2O 34 kg/ha\nZn 0,8 ppm\nIron 5 ppm\nIron 6 ppm\nN 200 kg/ha 280 low\nBoron <0.5 ppm");
  expect(draft.values).toEqual({}); expect(warnings.length).toBeGreaterThan(3);
});
it("requires a missing unit instead of assuming one", () => {
  const { draft, warnings } = extractSoilText("Nitrogen 123\npH 7.0");
  expect(draft.units.nitrogen).toBe(""); expect(warnings.join()).toContain("no unit was assumed");
  expect(validDraft({ values: { notAParameter: "7" }, units: {}, sampleDate: "" })).toBe(false);
});
it("does not accept an OCR fragment that hides a damaged digit", () => {
  expect(extractSoilText("pH «1\nNitrogen (N) 210 kg/ha Low").draft.values).toEqual({ nitrogen: "210" });
  expect(extractSoilText("pH 7 .1").draft.values).toEqual({});
});
it("imports into an editable form, requires review, saves and reuses a named report", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ profile: { source_type: "USER_ENTERED" } })));
  const receive = vi.fn();
  render(<QueryClientProvider client={new QueryClient()}><SoilHealth result={null} onResult={receive} onExplain={vi.fn()} /></QueryClientProvider>);
  fireEvent.click(screen.getByText("Scan or import your soil report"));
  fireEvent.change(screen.getByLabelText("Report text"), { target: { value: sample } });
  fireEvent.click(screen.getByText("Read pasted values"));
  fireEvent.click(screen.getByText("Review these values"));
  expect((screen.getByLabelText("Nitrogen (N)") as HTMLInputElement).value).toBe("210");
  fireEvent.click(screen.getByText("Use These Soil Values"));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("I checked every value and unit against the original report"));
  fireEvent.click(screen.getByLabelText("Save as a reusable report on this device"));
  fireEvent.change(screen.getByLabelText("Report name"), { target: { value: "North field" } });
  fireEvent.click(screen.getByText("Use These Soil Values"));
  await waitFor(() => expect(receive).toHaveBeenCalledOnce());
  const saved = JSON.parse(localStorage.getItem(REPORT_STORAGE_KEY)!);
  expect(saved[0].draft.values.ph).toBe("7.1");
  expect(JSON.stringify(saved)).not.toContain("profile_token");
  fireEvent.click(screen.getByText("Clear saved draft"));
  fireEvent.click(screen.getByLabelText("Use North field"));
  expect((screen.getByLabelText("pH") as HTMLInputElement).value).toBe("7.1");
  fireEvent.click(screen.getByLabelText("Delete North field"));
  expect(JSON.parse(localStorage.getItem(REPORT_STORAGE_KEY)!)).toEqual([]);
});
