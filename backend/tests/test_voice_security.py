import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import advisor
from app.core.security import sign, verify
from app.db.database import get_db
from app.main import app
from app.modules.advisor import translation
from app.modules.advisor.translation import GeminiTranslation, TranslationError
from test_advisor import FakeSession


@pytest.fixture
def chat(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(advisor, "get_settings", lambda: SimpleNamespace(gemini_api_key="test", gemini_generation_model="test"))
    monkeypatch.setattr(advisor, "generate_advisor_answer", lambda *a, **kw: "Check soil moisture.")
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_whitespace_and_unsupported_language(chat):
    assert chat.post("/api/v1/advisor/chat", json={"question": "  "}).status_code == 422
    assert chat.post("/api/v1/advisor/chat", json={"question": "soil", "language": "xx"}).status_code == 422


def test_conversation_requires_matching_capability(chat):
    result = chat.post("/api/v1/advisor/chat", json={"question": "Tell me about soil", "conversation_id": str(uuid4())})
    assert result.status_code == 403


@pytest.mark.parametrize("language", ["en", "hi", "ta", "te"])
def test_four_languages_and_transcripts(chat, monkeypatch, language):
    monkeypatch.setattr(GeminiTranslation, "translate", lambda self, text, source, target: f"{target}:{text}")
    result = chat.post("/api/v1/advisor/chat", json={"question": "soil question", "language": language})
    assert result.status_code == 201
    payload = result.json()
    assert payload["original_transcript"] == "soil question"
    assert payload["english_transcript"] == ("soil question" if language == "en" else "en:soil question")
    assert payload["language"] == language


def test_output_translation_failure_retains_english(chat, monkeypatch):
    def translate(self, text, source, target):
        if target != "en":
            raise TranslationError("unavailable")
        return "Tell me about soil"
    monkeypatch.setattr(GeminiTranslation, "translate", translate)
    result = chat.post("/api/v1/advisor/chat", json={"question": "मिट्टी", "language": "hi"}).json()
    assert result["translation_failed"] and result["language"] == "en"
    assert result["answer"] == result["canonical_answer"] == "Check soil moisture."


def test_input_translation_failure_does_not_generate(chat, monkeypatch):
    def fail(*args):
        raise TranslationError("retry")
    monkeypatch.setattr(GeminiTranslation, "translate", fail)
    monkeypatch.setattr(advisor, "generate_advisor_answer", lambda *a, **kw: pytest.fail("Should not generate"))
    assert chat.post("/api/v1/advisor/chat", json={"question": "மண்", "language": "ta"}).status_code == 503


def test_soil_explanation_uses_signed_measurements_without_llm(chat, monkeypatch):
    profile = chat.post("/api/v1/soil/manual", json={"parameters": {"ph": {"value": 7.1, "unit": "pH"}}}).json()
    monkeypatch.setattr(advisor, "generate_advisor_answer", lambda *a, **kw: pytest.fail("Soil measurements must not be invented"))
    result = chat.post("/api/v1/advisor/chat", json={"question": "Explain my soil", "soil_token": profile["profile_token"]})
    assert result.status_code == 201
    assert "7.1 pH" in result.json()["answer"] and "USER_ENTERED" in result.json()["answer"]
    assert result.json()["generation_model"] == "soil-guidance-1"
    assert "AI-generated" not in result.json()["disclaimer"]


def test_signature_tampering_rejected():
    token = sign({"id": "a"}, "conversation")
    with pytest.raises(Exception):
        verify(token + "bad", "conversation")
    with pytest.raises(Exception):
        verify(token, "soil")


@pytest.mark.parametrize("change", [False, True])
def test_translation_protects_numbers_units_and_crop_names(monkeypatch, change):
    class FakeClient:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            text = json.loads(kwargs["contents"])["text"]
            assert "7.1" not in text and "Tomato" not in text
            return SimpleNamespace(text=json.dumps({"text": text.replace("__VALUE_0__", "8") if change else text}))
    monkeypatch.setattr(translation.genai, "Client", FakeClient)
    provider = GeminiTranslation("test", "test")
    if change:
        with pytest.raises(TranslationError): provider.translate("Tomato pH 7.1; N 12 kg/ha", "en", "hi")
    else:
        assert provider.translate("Tomato pH 7.1; N 12 kg/ha", "en", "hi") == "Tomato pH 7.1; N 12 kg/ha"
