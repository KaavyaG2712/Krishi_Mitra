import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ErrorBoundary from "../components/ErrorBoundary";
import { checkApi, api } from "../services/api";

it("reports disconnects and recovery rather than retaining a stale success", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("{}"))
    .mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(new Response("{}"));
  expect(await checkApi()).toBe(true);
  expect(await checkApi()).toBe(false);
  expect(await checkApi()).toBe(true);
});

it("provides recovery UI for failed lazy chunks or render errors", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  function FailedScreen(): never { throw new Error("Chunk unavailable"); }
  render(<ErrorBoundary><FailedScreen /></ErrorBoundary>);
  expect(screen.getByRole("alert").textContent).toContain("could not load");
  expect(screen.getByRole("button", { name: "Reload app" })).toBeTruthy();
});

it("distinguishes explicit cancellation from request timeout", async () => {
  const controller = new AbortController();
  vi.spyOn(globalThis, "fetch").mockImplementation((_url, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }));
  const request = api("/planning/locations?q=Warangal", undefined, { signal: controller.signal });
  controller.abort();
  await expect(request).rejects.toThrow("Request cancelled");
});
