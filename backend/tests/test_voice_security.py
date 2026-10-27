import json
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import advisor
from app.core.security import sign, verify
from app.main import app
from app.modules.advisor import translation
from app.modules.advisor.translation import GeminiTranslation, TranslationError
from test_advisor import FakeSession, make_hit
from fastapi.testclient import TestClient
from app.db.database import get_db


@pytest.fixture
def chat(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(advisor, "retrieve_passages", lambda db, question: [make_hit()])
    monkeypatch.setattr(advisor, "get_settings", lambda: pytest.fail("Chat must not require Gemini configuration"))
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("language", ["en", "hi", "ta", "te"])
def test_local_chat_needs_no_translation_or_gemini(chat, monkeypatch, language):
    monkeypatch.setattr(
        GeminiTranslation,
        "translate",
        lambda *args: pytest.fail("Local retrieval must not call a translation model"),
    )
    result = chat.post("/api/v1/advisor/chat", json={"question": "potato disease question", "language": language})
    assert result.status_code == 201
    payload = result.json()
    assert payload["original_transcript"] == "potato disease question"
    assert payload["language"] == "en"
    assert payload["knowledge_language"] == "en"
    assert payload["translation_failed"] is False
    assert payload["answer_method"] == "postgres-fts-rules-v1"


def test_signature_tampering_rejected():
    token = sign({"id": "a"}, "conversation")
    with pytest.raises(Exception):
        verify(token + "bad", "conversation")
    with pytest.raises(Exception):
        verify(token, "soil")


@pytest.mark.parametrize("change", [False, True])
def test_optional_translation_preserves_numbers_units_and_crop_names(monkeypatch, change):
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
