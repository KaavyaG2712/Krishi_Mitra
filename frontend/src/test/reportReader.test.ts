import { afterEach, expect, it, vi } from "vitest";
import { readSoilReport } from "../services/reportReader";
const worker = vi.hoisted(() => ({ terminate: vi.fn().mockResolvedValue(undefined), setParameters: vi.fn().mockResolvedValue(undefined), recognize: vi.fn() }));
vi.mock("tesseract.js", () => ({ createWorker: vi.fn().mockResolvedValue(worker) }));
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it("rejects invalid reports before creating a reader", async () => {
  await expect(readSoilReport(new File(["x"], "x.svg", {type:"image/svg+xml"}), vi.fn(), new AbortController().signal)).rejects.toThrow("Choose a PDF");
  await expect(readSoilReport(new File([], "empty.pdf", {type:"application/pdf"}), vi.fn(), new AbortController().signal)).rejects.toThrow("under 10 MB");
});
it("cancels a pending OCR job and releases the bitmap", async () => {
  const close = vi.fn();
  vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 100, height: 100, close }));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ fillRect: vi.fn(), drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  worker.recognize.mockImplementation(() => new Promise(() => undefined));
  const controller = new AbortController();
  const reading = readSoilReport(new File(["test"], "test.png", {type:"image/png"}), vi.fn(), controller.signal);
  const failure = expect(reading).rejects.toMatchObject({ name: "AbortError" });
  await vi.waitFor(() => expect(worker.recognize).toHaveBeenCalled()); controller.abort();
  await failure;
  expect(worker.terminate).toHaveBeenCalled(); expect(close).toHaveBeenCalledOnce();
});
