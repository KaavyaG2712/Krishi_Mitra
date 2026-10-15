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
it("shows the canonical response when translation fails and retries translation only", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "c", conversation_token: "t", message_id: "m", answer: "Check soil moisture.", canonical_answer: "Check soil moisture.", original_transcript: "मिट्टी", english_transcript: "soil", language: "en", translation_failed: true }))).mockResolvedValueOnce(new Response(JSON.stringify({ text: "मिट्टी की नमी जाँचें।", language: "hi" })));
  render(<LanguageContext.Provider value="hi"><Advisor soil={null} onClearSoil={vi.fn()} /></LanguageContext.Provider>);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "मिट्टी" } });
  fireEvent.click(screen.getByRole("button", { name: "भेजें" }));
  await screen.findByText("Check soil moisture.");
  fireEvent.click(screen.getByRole("button", { name: "फिर कोशिश करें" }));
  await screen.findByText("मिट्टी की नमी जाँचें।");
  expect(fetch.mock.calls[1][0]).toContain("/advisor/translate");
});
