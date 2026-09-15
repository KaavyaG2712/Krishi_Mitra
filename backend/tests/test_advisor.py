from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import advisor
from app.db.database import get_db
from app.main import app


class FakeScalarResult:
    def all(self) -> list[object]:
        return []


class FakeSession:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, item: object) -> None:
        self.items.append(item)

    def flush(self) -> None:
        for item in self.items:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def scalars(self, _statement: object) -> FakeScalarResult:
        return FakeScalarResult()


def test_advisor_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=None, gemini_generation_model="gemini-3.6-flash"),
    )

    response = TestClient(app).post("/api/v1/advisor/chat", json={"question": "How should I water tomatoes?"})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_advisor_creates_conversation_and_message(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(
        advisor,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key="test-key", gemini_generation_model="gemini-3.6-flash"),
    )
    monkeypatch.setattr(
        advisor,
        "generate_advisor_answer",
        lambda question, history, **kwargs: f"Water near the soil in the morning. Asked: {question}",
    )
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).post(
            "/api/v1/advisor/chat",
            json={"question": "How should I water tomatoes?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["message_id"]
    assert "morning" in payload["answer"]
    assert payload["generation_model"] == "gemini-3.6-flash"
    assert len(session.items) == 2
