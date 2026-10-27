import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import Advisor from "../components/Advisor";
import { LanguageContext } from "../i18n";

it("preserves a failed question so it can be corrected and retried", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
  render(<Advisor soil={null} onClearSoil={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Your question or corrected transcript"), { target: { value: "Help my crop" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Your question is kept"));
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Help my crop");
});
it("shows local source citations and does not call a translation service", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "c", conversation_token: "t", message_id: "m", answer: "Check soil moisture.", answer_method: "postgres-fts-rules-v1", original_transcript: "मिट्टी", language: "en", knowledge_language: "en", translation_failed: false, abstained: false, sources: [{ title: "Soil guide", publisher: "ICAR", source_url: "https://icar.gov.in/soil.pdf", page_number: 4, section: "Soil health", relevance: 0.81 }] })));
  render(<LanguageContext.Provider value="hi"><Advisor soil={null} onClearSoil={vi.fn()} /></LanguageContext.Provider>);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "मिट्टी" } });
  fireEvent.click(screen.getByRole("button", { name: "भेजें" }));
  await screen.findByText("Check soil moisture.");
  expect(screen.getByText("स्थानीय ज्ञान संग्रह से अभी अंग्रेज़ी स्रोत सामग्री मिलती है।")).toBeTruthy();
  expect(screen.getByRole("link", { name: "ICAR: Soil guide" }).getAttribute("href")).toBe("https://icar.gov.in/soil.pdf");
  expect(fetch).toHaveBeenCalledTimes(1);
});
