from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import advisor
from app.core.security import sign
from app.db.database import get_db
from app.db.models import AdvisorCitation, AdvisorMessage
from app.main import app
from app.modules.advisor.service import KnowledgeHit, NO_MATCH_ANSWER


class FakeSession:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, item: object) -> None:
        self.items.append(item)

    def flush(self) -> None:
        for item in self.items:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def get(self, _model: type, _item_id: object) -> object | None:
        return None


def make_hit(text: str = "Inspect potato leaves regularly and ask the local KVK to confirm rapidly spreading symptoms.") -> KnowledgeHit:
    return KnowledgeHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        title="Potato late blight and its management",
        publisher="ICAR",
        source_url="https://icar.gov.in/example.pdf",
        page_number=31,
        section="Symptoms and field observation",
        text=text,
        score=0.81,
    )


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch):
    session = FakeSession()
    monkeypatch.setattr(advisor, "retrieve_passages", lambda db, question: [make_hit()])
    monkeypatch.setattr(advisor, "get_settings", lambda: pytest.fail("Local chat must not need Gemini settings"))
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app), session
    app.dependency_overrides.clear()


def test_local_chat_returns_citations_without_gemini(chat) -> None:
    client, session = chat
    response = client.post("/api/v1/advisor/chat", json={"question": "potato leaf spots", "language": "en"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["answer_method"] == "postgres-fts-rules-v1"
    assert payload["answer"].startswith("Inspect potato leaves")
    assert payload["sources"][0]["page_number"] == 31
    assert payload["sources"][0]["source_url"].startswith("https://")
    assert payload["abstained"] is False
    assert any(isinstance(item, AdvisorCitation) for item in session.items)
    assert any(isinstance(item, AdvisorMessage) and item.abstained is False for item in session.items)


def test_localized_question_is_matched_without_online_translation(chat, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = chat
    received: list[str] = []
    monkeypatch.setattr(advisor, "retrieve_passages", lambda db, question: (received.append(question) or [make_hit()]))
    response = client.post("/api/v1/advisor/chat", json={"question": "आलू पत्ते धब्बे", "language": "hi"})

    assert response.status_code == 201
    assert received == ["आलू पत्ते धब्बे"]
    assert response.json()["language"] == "en"
    assert response.json()["knowledge_language"] == "en"
    assert response.json()["translation_failed"] is False


def test_no_match_is_persisted_as_abstention(chat, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session = chat
    monkeypatch.setattr(advisor, "retrieve_passages", lambda db, question: [])
    response = client.post("/api/v1/advisor/chat", json={"question": "How do I repair a laptop screen?"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["answer"] == NO_MATCH_ANSWER
    assert payload["abstained"] is True
    assert payload["sources"] == []
    assert any(isinstance(item, AdvisorMessage) and item.abstained for item in session.items)


def test_application_quantities_are_refused_without_search(chat, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = chat
    monkeypatch.setattr(advisor, "retrieve_passages", lambda *args: pytest.fail("Unsafe dosage query must abstain"))
    response = client.post("/api/v1/advisor/chat", json={"question": "What pesticide dose should I spray on potato?"})

    assert response.status_code == 201
    assert "cannot provide" in response.json()["answer"]
    assert response.json()["abstained"] is True
    assert response.json()["sources"] == []


def test_conversation_requires_matching_capability(chat) -> None:
    client, _ = chat
    result = client.post("/api/v1/advisor/chat", json={"question": "Tell me about soil", "conversation_id": str(uuid4())})
    assert result.status_code == 403


def test_whitespace_and_unsupported_language(chat) -> None:
    client, _ = chat
    assert client.post("/api/v1/advisor/chat", json={"question": "  "}).status_code == 422
    assert client.post("/api/v1/advisor/chat", json={"question": "soil", "language": "xx"}).status_code == 422


def test_soil_explanation_remains_rule_based(chat, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = chat
    profile_token = sign(
        {
            "parameters": {"ph": {"value": 7.1, "unit": "pH"}},
            "source": "manual report",
            "source_type": "USER_ENTERED",
        },
        "soil",
    )
    response = client.post("/api/v1/advisor/chat", json={"question": "Explain this", "soil_token": profile_token})
    assert response.status_code == 201
    assert "7.1 pH" in response.json()["answer"]
    assert response.json()["answer_method"] == "soil-rules-v1"
    assert "AI-generated" not in response.json()["disclaimer"]
