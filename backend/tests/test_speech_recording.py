import io
import json
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.endpoints import speech
from app.modules.advisor import transcription


def wav(seconds=1, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(rate)
        audio.writeframes(b"\0\0" * int(rate * seconds))
    return output.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(speech, "get_settings", lambda: SimpleNamespace(gemini_api_key="test", gemini_generation_model="test", gemini_speech_model=None))
    return TestClient(app)


@pytest.mark.parametrize("language", ["en", "hi", "ta", "te"])
def test_recording_reaches_transcriber_without_database(client, monkeypatch, language):
    calls = []
    def transcribe(data, lang, key, model):
        calls.append((lang, key, model)); return "मिट्टी மண் నేల soil"
    monkeypatch.setattr(speech, "transcribe_audio", transcribe)
    response = client.post(f"/api/v1/speech/transcribe?language={language}", content=wav(), headers={"content-type": "audio/wav"})
    assert response.status_code == 200 and response.json()["language"] == language
    assert calls == [(language, "test", "test")]


def test_unconfigured_server_is_not_reported_as_network_failure(client, monkeypatch):
    monkeypatch.setattr(speech, "configured_key", lambda: None)
    assert client.get("/api/v1/speech/status").json()["available"] is False
    response = client.post("/api/v1/speech/transcribe", content=wav(), headers={"content-type": "audio/wav"})
    assert response.status_code == 503 and "GEMINI_API_KEY" in response.json()["detail"]


@pytest.mark.parametrize("data", [b"not audio", wav(0.1), wav(32), wav(rate=8000), wav()[:-20]], ids=["not-audio", "too-short", "too-long", "wrong-rate", "truncated"])
def test_bad_or_overlong_audio_never_reaches_provider(client, monkeypatch, data):
    monkeypatch.setattr(speech, "transcribe_audio", lambda *a: pytest.fail("Invalid upload reached the provider"))
    assert client.post("/api/v1/speech/transcribe", content=data, headers={"content-type": "audio/wav"}).status_code == 422


def test_upload_limit_and_type(client):
    assert client.post("/api/v1/speech/transcribe", content=b"x" * 1_100_001, headers={"content-type": "audio/wav"}).status_code == 413
    assert client.post("/api/v1/speech/transcribe", content=wav(), headers={"content-type": "text/plain"}).status_code == 415


def test_silence_and_provider_error_are_actionable(client, monkeypatch):
    monkeypatch.setattr(speech, "transcribe_audio", lambda *a: "")
    assert "No clear speech" in client.post("/api/v1/speech/transcribe", content=wav(), headers={"content-type": "audio/wav"}).json()["detail"]
    def fail(*a): raise RuntimeError("Transcription unavailable")
    monkeypatch.setattr(speech, "transcribe_audio", fail)
    assert client.post("/api/v1/speech/transcribe", content=wav(), headers={"content-type": "audio/wav"}).status_code == 503


def test_gemini_audio_payload_is_transcription_only(monkeypatch):
    class Client:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            assert kwargs["contents"][0].inline_data.mime_type == "audio/wav"
            assert "Do not answer" in kwargs["config"].system_instruction
            return SimpleNamespace(text=json.dumps({"text": "मिट्टी की जाँच"}))
    monkeypatch.setattr(transcription.genai, "Client", Client)
    assert transcription.transcribe_audio(wav(), "hi", "test", "test") == "मिट्टी की जाँच"
