from __future__ import annotations

from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pydantic import ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import AdvisorConversation, AdvisorMessage
from app.modules.advisor.service import AdvisorGenerationError, generate_advisor_answer
from app.modules.advisor.translation import GeminiTranslation, Language, TranslationError
from app.core.security import sign, verify
from app.modules.soil.models import SoilProfile
from app.modules.soil.recommendations import explain


router = APIRouter(prefix="/advisor")
MAX_HISTORY_MESSAGES = 8


class AdvisorChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: UUID | None = None
    conversation_token: str | None = Field(default=None, max_length=2000)
    language: Language = "en"
    soil_token: str | None = Field(default=None, max_length=15000)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Please enter a question.")
        return value.strip()


class AdvisorChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    generation_model: str
    disclaimer: str
    conversation_token: str
    canonical_answer: str
    original_transcript: str
    english_transcript: str
    language: Language
    translation_failed: bool = False


def _configured_api_key(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip()
    if not clean or clean.lower().startswith("replace-with"):
        return None
    return clean


@router.post("/chat", response_model=AdvisorChatResponse, status_code=status.HTTP_201_CREATED)
def chat_with_advisor(
    request: AdvisorChatRequest,
    db: Session = Depends(get_db, scope="function"),
) -> AdvisorChatResponse:
    settings = get_settings()
    api_key = _configured_api_key(settings.gemini_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The advisor is not configured. Add GEMINI_API_KEY to backend/.env and restart the backend.",
        )

    question = request.question.strip()
    original_question = question
    translator = GeminiTranslation(api_key, settings.gemini_generation_model)
    if request.conversation_id is not None:
        capability = verify(request.conversation_token or "", "conversation")
        if capability.get("id") != str(request.conversation_id):
            raise HTTPException(403, "This conversation belongs to another session.")
    profile = SoilProfile.model_validate(verify(request.soil_token, "soil")) if request.soil_token else None
    if request.language != "en":
        try:
            question = translator.translate(question, request.language, "en")
        except TranslationError as error:
            raise HTTPException(503, str(error)) from None
    if request.conversation_id is None:
        conversation = AdvisorConversation()
        db.add(conversation)
        db.flush()
    else:
        conversation = db.get(AdvisorConversation, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    statement = (
        select(AdvisorMessage)
        .where(AdvisorMessage.conversation_id == conversation.id)
        .order_by(AdvisorMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    history = list(reversed(db.scalars(statement).all()))

    started = perf_counter()
    try:
        answer = explain(profile) if profile else generate_advisor_answer(
            question,
            history,
            api_key=api_key,
            model=settings.gemini_generation_model,
        )
    except AdvisorGenerationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    generation_model = "soil-guidance-1" if profile else settings.gemini_generation_model
    message = AdvisorMessage(
        conversation_id=conversation.id,
        question=question,
        answer=answer,
        abstained=False,
        latency_ms=(perf_counter() - started) * 1000,
        generation_model=generation_model,
    )
    db.add(message)
    db.flush()

    displayed = answer
    translation_failed = False
    if request.language != "en":
        try:
            displayed = translator.translate(answer, "en", request.language)
        except TranslationError:
            translation_failed = True

    return AdvisorChatResponse(
        conversation_id=conversation.id,
        message_id=message.id,
        answer=displayed,
        generation_model=generation_model,
        disclaimer=("Guidance from your soil values; verify important decisions with a local agricultural expert." if profile else "AI-generated general guidance; verify important decisions with a local agricultural expert."),
        conversation_token=sign({"id": str(conversation.id)}, "conversation"),
        canonical_answer=answer,
        original_transcript=original_question,
        english_transcript=question,
        language="en" if translation_failed else request.language,
        translation_failed=translation_failed,
    )


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    source: Language = "en"
    target: Language


@router.post("/translate")
def translate(request: TranslateRequest):
    settings = get_settings()
    api_key = _configured_api_key(settings.gemini_api_key)
    if not api_key:
        raise HTTPException(503, "Translation is not connected. The original text is still available.")
    try:
        return {"text": GeminiTranslation(api_key, settings.gemini_generation_model).translate(request.text, request.source, request.target), "language": request.target}
    except TranslationError as error:
        raise HTTPException(503, str(error)) from None
