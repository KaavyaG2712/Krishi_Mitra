from __future__ import annotations

from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pydantic import ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import AdvisorCitation, AdvisorConversation, AdvisorMessage
from app.modules.advisor.service import (
    AdvisorGenerationError,
    generate_agronomy_answer,
    retrieve_passages,
)
from app.modules.advisor.translation import GeminiTranslation, Language, LANGUAGES, TranslationError
from app.core.security import sign, verify
from app.modules.soil.models import SoilProfile
from app.modules.soil.recommendations import explain


router = APIRouter(prefix="/advisor")
RETRIEVAL_METHOD = "postgres-fts-rules-v1"


class AdvisorChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: UUID | None = None
    conversation_token: str | None = Field(default=None, max_length=2000)
    soil_token: str | None = Field(default=None, max_length=15000)
    language: Language = "en"

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Please enter a question.")
        return value.strip()


class AdvisorSource(BaseModel):
    title: str
    publisher: str
    source_url: str
    page_number: int | None = None
    section: str | None = None
    relevance: float


class AdvisorChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    answer_method: str
    disclaimer: str
    conversation_token: str
    canonical_answer: str
    original_transcript: str
    english_transcript: str
    language: Language = "en"
    abstained: bool = False
    sources: list[AdvisorSource]
    knowledge_language: str = "en"


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
    question = request.question.strip()
    original_question = question
    if request.conversation_id is not None:
        capability = verify(request.conversation_token or "", "conversation")
        if capability.get("id") != str(request.conversation_id):
            raise HTTPException(403, "This conversation belongs to another session.")
    profile = SoilProfile.model_validate(verify(request.soil_token, "soil")) if request.soil_token else None
    if request.conversation_id is None:
        conversation = AdvisorConversation()
        db.add(conversation)
        db.flush()
    else:
        conversation = db.get(AdvisorConversation, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    started = perf_counter()
    settings = get_settings()
    api_key = _configured_api_key(settings.gemini_api_key)
    if (not profile or request.language != "en") and not api_key:
        raise HTTPException(503, "Gemini is not configured. Add GEMINI_API_KEY to backend/.env and restart the backend.")

    english_question = question
    if request.language != "en":
        try:
            english_question = GeminiTranslation(api_key, settings.gemini_generation_model).translate(question, request.language, "en")
        except TranslationError as error:
            raise HTTPException(503, str(error)) from None

    hits = [] if profile else retrieve_passages(db, english_question)
    if profile:
        answer = explain(profile)
        web_sources = []
        answer_method = "soil-rules-v1"
        if request.language != "en":
            try:
                answer = GeminiTranslation(api_key, settings.gemini_generation_model).translate(answer, "en", request.language)
            except TranslationError as error:
                raise HTTPException(503, str(error)) from None
    else:
        try:
            answer, web_sources = generate_agronomy_answer(question, hits, api_key=api_key, model=settings.gemini_generation_model, answer_language=request.language)
        except AdvisorGenerationError as error:
            raise HTTPException(error.status_code, str(error)) from None
        search_label = "+google-search" if web_sources else ""
        answer_method = f"gemini{search_label}+{RETRIEVAL_METHOD}"
    english_answer = answer
    answer_language = request.language
    abstained = False
    message = AdvisorMessage(
        conversation_id=conversation.id,
        question=original_question,
        answer=answer,
        abstained=abstained,
        latency_ms=(perf_counter() - started) * 1000,
        generation_model=(settings.gemini_generation_model if answer_method != "soil-rules-v1" else answer_method),
    )
    db.add(message)
    db.flush()
    for rank, hit in enumerate(hits, start=1):
        db.add(
            AdvisorCitation(
                message_id=message.id,
                chunk_id=hit.chunk_id,
                rank=rank,
                similarity_score=hit.score,
            )
        )

    sources = [
        {
            "title": hit.title,
            "publisher": hit.publisher,
            "source_url": hit.source_url,
            "page_number": hit.page_number,
            "section": hit.section,
            "relevance": round(hit.score, 3),
        }
        for hit in hits
    ]
    sources.extend(
        {
            "title": item["title"],
            "publisher": "Web search",
            "source_url": item["url"],
            "page_number": None,
            "section": None,
            "relevance": 0.0,
        }
        for item in web_sources
    )

    return AdvisorChatResponse(
        conversation_id=conversation.id,
        message_id=message.id,
        answer=answer,
        answer_method=answer_method,
        disclaimer=(
            "Locally generated soil explanation; verify important decisions with a local agricultural expert."
            if profile
            else "Gemini-generated agronomy guidance can be inaccurate. Retrieved sources are supporting references, not a substitute for local advice. Verify chemical use and important decisions with a local KVK/agricultural officer."
        ),
        conversation_token=sign({"id": str(conversation.id)}, "conversation"),
        canonical_answer=english_answer,
        original_transcript=original_question,
        english_transcript=english_question,
        language=answer_language,
        abstained=abstained,
        sources=sources,
        knowledge_language=answer_language,
    )


class UiTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texts: list[str] = Field(min_length=1, max_length=80)
    target: Language

    @field_validator("texts")
    @classmethod
    def bounded_texts(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values) or sum(map(len, values)) > 12000:
            raise ValueError("Page translation text is too long.")
        return values


@router.post("/translate-ui")
def translate_ui(request: UiTranslationRequest):
    settings = get_settings()
    api_key = _configured_api_key(settings.gemini_api_key)
    if not api_key:
        raise HTTPException(503, "Page translation is not configured.")
    try:
        translations = GeminiTranslation(api_key, settings.gemini_generation_model).translate_many(request.texts, request.target)
    except TranslationError as error:
        raise HTTPException(503, str(error)) from None
    return {"translations": translations}
