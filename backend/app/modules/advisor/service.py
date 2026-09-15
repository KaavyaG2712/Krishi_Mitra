from __future__ import annotations

from collections.abc import Sequence

from google import genai
from google.genai import types

from app.db.models import AdvisorMessage


SYSTEM_INSTRUCTION = """
You are KrishiMitra, a concise agricultural information assistant for farmers.
Answer only questions about crops, soil, irrigation, plant health, weather-related
farm planning, and general agricultural practices. If a question is outside
agriculture, politely say that you can only help with agriculture.

Use plain language and practical numbered steps where helpful. Never claim that
you have inspected a farm or confirmed a diagnosis. Do not invent pesticide
dosages, legal restrictions, market prices, weather, or citations. For pesticide
choice or dosage, severe crop loss, poisoning, or uncertain disease symptoms,
recommend checking the product label and consulting a local KVK, agricultural
officer, or qualified professional. State important uncertainty clearly.
""".strip()


class AdvisorGenerationError(RuntimeError):
    """Raised when Gemini does not return a usable advisor response."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _provider_error(error: Exception, model: str) -> AdvisorGenerationError:
    code = getattr(error, "code", None)
    if code == 404:
        return AdvisorGenerationError(
            f"The configured Gemini model '{model}' is unavailable. Update GEMINI_GENERATION_MODEL in backend/.env.",
            status_code=503,
        )
    if code in {401, 403}:
        return AdvisorGenerationError(
            "Gemini rejected the API credentials. Check GEMINI_API_KEY and its project restrictions.",
            status_code=503,
        )
    if code == 429:
        return AdvisorGenerationError(
            "The Gemini API rate limit or quota was reached. Wait briefly or check the API project's usage limits.",
            status_code=429,
        )
    if code == 503:
        return AdvisorGenerationError(
            f"Gemini model '{model}' is temporarily busy. Please try again shortly.",
            status_code=503,
        )
    return AdvisorGenerationError("The AI service could not generate a response.")


def _conversation_prompt(question: str, history: Sequence[AdvisorMessage]) -> str:
    turns: list[str] = []
    for message in history:
        turns.append(f"Farmer: {message.question}\nKrishiMitra: {message.answer}")
    turns.append(f"Farmer: {question}\nKrishiMitra:")
    return "\n\n".join(turns)


def generate_advisor_answer(
    question: str,
    history: Sequence[AdvisorMessage],
    *,
    api_key: str,
    model: str,
) -> str:
    """Generate one safety-guided answer using recent conversation context."""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=_conversation_prompt(question, history),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=700,
            ),
        )
        answer = (response.text or "").strip()
    except Exception as error:
        raise _provider_error(error, model) from error

    if not answer:
        raise AdvisorGenerationError("The AI service returned an empty response.")
    return answer
