from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.modules.advisor.translation import Language
from app.modules.advisor.transcription import MAX_AUDIO_BYTES, transcribe_audio, validate_audio

router = APIRouter(prefix="/speech")


def configured_key():
    key = (get_settings().gemini_api_key or "").strip()
    return key if key and not key.lower().startswith("replace-with") else None


@router.get("/status")
def status():
    return {"available": bool(configured_key()), "provider": "gemini", "max_seconds": 30}


@router.post("/transcribe")
async def transcribe(request: Request, language: Language = "en"):
    key = configured_key()
    if not key:
        raise HTTPException(503, "Server speech needs GEMINI_API_KEY in backend/.env. The app owner must configure it and restart the backend; farmers do not need their own key.")
    if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise HTTPException(415, "Use a WAV microphone recording.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Keep recordings under 30 seconds.")
        data.extend(chunk)
    try:
        validate_audio(bytes(data))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    settings = get_settings()
    try:
        text = await run_in_threadpool(transcribe_audio, bytes(data), language, key, settings.gemini_speech_model or settings.gemini_generation_model)
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from None
    if not text:
        raise HTTPException(422, "No clear speech was heard. Move closer to the microphone and try again.")
    return {"text": text, "language": language}
