import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import SoilHealth from "../components/SoilHealth";
import { LanguageContext, Language } from "../i18n";

function setup(language: Language = "en") {
  const result = vi.fn();
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><LanguageContext.Provider value={language}><SoilHealth result={null} onResult={result} onExplain={vi.fn()} /></LanguageContext.Provider></QueryClientProvider>);
  return result;
}
describe("soil", () => {
  it("shows both paths before requesting data", () => {
    const fetch = vi.spyOn(globalThis, "fetch"); setup();
    expect(screen.getByText("Get Soil Data Using My Location")).toBeTruthy();
    expect(screen.getByText("Enter Soil Test Values Manually")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("submits decimal manual values and never fills unknown nutrients", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ profile: { source_type: "USER_ENTERED" } }), { status: 200 }));
    const result = setup();
    fireEvent.click(screen.getByText("Enter Soil Test Values Manually"));
    fireEvent.change(screen.getByLabelText("pH"), { target: { value: "7.1" } });
    fireEvent.click(screen.getByText("Use These Soil Values"));
    await waitFor(() => expect(result).toHaveBeenCalled());
    const body = JSON.parse(fetch.mock.calls[0][1]?.body as string);
    expect(body.parameters).toEqual({ ph: { value: 7.1, unit: "pH" } });
  });
  it("requires units and preserves drafts only with opt-in", async () => {
    setup(); fireEvent.click(screen.getByText("Enter Soil Test Values Manually"));
    fireEvent.change(screen.getByLabelText("Nitrogen (N)"), { target: { value: "123.4" } });
    expect(localStorage.getItem("soil-draft-v1")).toBeNull();
    fireEvent.click(screen.getByText("Use These Soil Values"));
    expect(screen.getByRole("alert").textContent).toContain("Choose the unit");
    fireEvent.click(screen.getByLabelText("Save this form on this device"));
    await waitFor(() => expect(localStorage.getItem("soil-draft-v1")).toContain("123.4"));
    fireEvent.click(screen.getByText("Clear saved draft"));
    expect(JSON.parse(localStorage.getItem("soil-draft-v1")!)).toBeNull();
  });
  it("keeps manual fallback available when government directory fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: { message: "Government unavailable" } }), { status: 503 }));
    setup(); fireEvent.click(screen.getByText("Get Soil Data Using My Location"));
    await screen.findByText("Government unavailable");
    fireEvent.click(screen.getByText("Enter Soil Test Values Manually"));
    expect(screen.getByLabelText("pH")).toBeTruthy();
  });
  it.each([["hi", "मेरी मिट्टी जाँचें"], ["ta", "என் மண்ணை அறிய"], ["te", "నా నేలను తనిఖీ చేయండి"]])("localizes primary actions in %s", (language, title) => {
    setup(language as Language); expect(screen.getByRole("heading", { name: title })).toBeTruthy();
  });
});
