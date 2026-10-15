import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CropPlanner from "../components/CropPlanner";

const location = { name: "Warangal, Telangana", latitude: 17.97, longitude: 79.59 };
const reply = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
async function choosePlace() {
  fireEvent.change(screen.getByLabelText("Village or town"), { target: { value: "Warangal" } });
  fireEvent.click(screen.getByRole("button", { name: "Search location" }));
  fireEvent.click(await screen.findByRole("button", { name: /Warangal, Telangana/ }));
}

describe("location crop planning", () => {
  it("cancels a pending lookup and ignores its late response", async () => {
    let finish: (value: Response) => void = () => {};
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; }));
    render(<CropPlanner />);
    fireEvent.change(screen.getByLabelText("Village or town"), { target: { value: "Warangal" } });
    fireEvent.click(screen.getByRole("button", { name: "Search location" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel lookup" }));
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    finish(reply([location]));
    await waitFor(() => expect((screen.getByRole("button", { name: "Search location" }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByRole("button", { name: /Warangal, Telangana/ })).toBeNull();
  });
  it("does not collect GPS or fetch on mount", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const gps = vi.fn(); Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition: gps } });
    render(<CropPlanner />);
    expect(fetch).not.toHaveBeenCalled(); expect(gps).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Find my top crop options" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("uses confirmed coordinates and converts acres without asking for soil values", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(reply([location])).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Provider temporarily unavailable" }), { status: 503 }));
    render(<CropPlanner />); await choosePlace();
    fireEvent.change(screen.getByLabelText("Field area"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Area unit"), { target: { value: "acre" } });
    fireEvent.click(screen.getByRole("button", { name: "Find my top crop options" }));
    await screen.findByText("Provider temporarily unavailable");
    const body = JSON.parse(fetch.mock.calls[1][1]?.body as string);
    expect(body.latitude).toBe(17.97); expect(body.longitude).toBe(79.59);
    expect(body.area_ha).toBeCloseTo(.80937128448); expect(body.irrigation).toBe("unknown");
    expect(body.parameters).toBeUndefined();
    expect((screen.getByLabelText("Field area") as HTMLInputElement).value).toBe("2");
  });
  it("clears a previously selected place when search text changes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(reply([location]));
    render(<CropPlanner />); await choosePlace();
    fireEvent.change(screen.getByLabelText("Village or town"), { target: { value: "Ludhiana" } });
    expect((screen.getByRole("button", { name: "Find my top crop options" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("shows absent sources and withholds crop cards", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(reply([location])).mockResolvedValueOnce(reply({
      status: "insufficient_data", request: { location_name: location.name, area_ha: 1, sowing_date: "2026-10-08" },
      soil: { status: "unavailable", message: "No mapped soil here" }, forecast: { status: "unavailable", message: "Weather offline" },
      climate: { status: "unavailable", message: "Climate offline" }, top_crops: [], excluded: [], warnings: [], generated_at: new Date().toISOString(),
    }));
    render(<CropPlanner />); await choosePlace();
    fireEvent.click(screen.getByRole("button", { name: "Find my top crop options" }));
    await screen.findByText("No mapped soil here");
    expect(screen.getByRole("alert").textContent).toContain("We need mapped pH");
    expect(screen.queryByText("Benchmark surplus / hectare")).toBeNull();
    fireEvent.change(screen.getByLabelText("Water availability"), { target: { value: "rainfed" } });
    await waitFor(() => expect(screen.queryByText("No mapped soil here")).toBeNull());
  });
});
