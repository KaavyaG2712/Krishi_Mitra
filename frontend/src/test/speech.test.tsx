import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { browserSpeech, currentLocation, speak } from "../services/speech";
import { Language, LanguageContext, locales } from "../i18n";
import { VoiceInput, VoiceOutput } from "../components/Voice";

class FakeRecognition {
  static last: FakeRecognition;
  lang = ""; continuous = false; interimResults = false;
  onerror?: (e: { error: string }) => void; onend?: () => void;
  onresult?: (e: { results: { transcript: string }[][] }) => void;
  constructor() { FakeRecognition.last = this; }
  start() {} stop() { this.onend?.(); } abort() {}
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
it("falls back to typing on unsupported browsers", () => {
  render(<VoiceInput value="" onChange={vi.fn()} disabled={false} />);
  expect(screen.getByRole("status").textContent).toContain("Type your question");
});
it.each(Object.keys(locales))("selects the %s locale and returns original script", language => {
  vi.stubGlobal("SpeechRecognition", FakeRecognition);
  const transcript = vi.fn(); const ended = vi.fn();
  const session = browserSpeech.recognize(language as Language, transcript, ended, vi.fn());
  expect(FakeRecognition.last.lang).toBe(locales[language as Language]);
  FakeRecognition.last.onresult?.({ results: [[{ transcript: "मिट्टी மண் నేల" }]] });
  expect(transcript).toHaveBeenCalledWith("मिट्टी மண் నేల");
  session.cancel(); expect(ended).toHaveBeenCalledOnce();
});
it("leaves listening after permission denial and timeout", () => {
  vi.useFakeTimers(); vi.stubGlobal("SpeechRecognition", FakeRecognition);
  const ended = vi.fn(); const error = vi.fn();
  browserSpeech.recognize("en", vi.fn(), ended, error);
  FakeRecognition.last.onerror?.({ error: "not-allowed" });
  expect(ended).toHaveBeenCalledOnce(); expect(error.mock.calls[0][0]).toContain("denied");
  browserSpeech.recognize("ta", vi.fn(), ended, error);
  vi.advanceTimersByTime(30001); expect(ended).toHaveBeenCalledTimes(2);
});
it("handles GPS denied without continuous tracking", async () => {
  const get = vi.fn((_success, fail) => fail({ code: 1 }));
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: get } });
  await expect(currentLocation()).rejects.toThrow("Select your location manually");
  expect(get).toHaveBeenCalledOnce();
});
it("reports when local playback cannot run in an unsupported test browser", async () => {
  render(<LanguageContext.Provider value="te"><VoiceOutput text="నేల" language="te" /></LanguageContext.Provider>);
  fireEvent.click(screen.getByRole("button"));
  expect((await screen.findByRole("alert")).textContent).toContain("Local audio playback is unavailable");
});
it("does not use a device voice for a different language and falls back locally", async () => {
  const deviceSpeech = { getVoices: () => [{ lang: "en-US" }], speak: vi.fn(), cancel: vi.fn() };
  const error = vi.fn();
  vi.stubGlobal("speechSynthesis", deviceSpeech);
  vi.stubGlobal("SpeechSynthesisUtterance", class {});
  const session = speak("மண்", "ta", vi.fn(), error);
  expect(session).toHaveProperty("pause");
  expect(deviceSpeech.speak).not.toHaveBeenCalled();
  await waitFor(() => expect(error).toHaveBeenCalledWith("Local audio playback is unavailable. Please read the answer."));
});
