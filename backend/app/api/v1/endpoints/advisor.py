from __future__ import annotations

from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import AdvisorConversation, AdvisorMessage
from app.modules.advisor.service import AdvisorGenerationError, generate_advisor_answer


router = APIRouter(prefix="/advisor")
MAX_HISTORY_MESSAGES = 8


class AdvisorChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: UUID | None = None


class AdvisorChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    generation_model: str
    disclaimer: str


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
    db: Session = Depends(get_db),
) -> AdvisorChatResponse:
    settings = get_settings()
    api_key = _configured_api_key(settings.gemini_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The advisor is not configured. Add GEMINI_API_KEY to backend/.env and restart the backend.",
        )

    question = request.question.strip()
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
        answer = generate_advisor_answer(
            question,
            history,
            api_key=api_key,
            model=settings.gemini_generation_model,
        )
    except AdvisorGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    message = AdvisorMessage(
        conversation_id=conversation.id,
        question=question,
        answer=answer,
        abstained=False,
        latency_ms=(perf_counter() - started) * 1000,
        generation_model=settings.gemini_generation_model,
    )
    db.add(message)
    db.flush()

    return AdvisorChatResponse(
        conversation_id=conversation.id,
        message_id=message.id,
        answer=answer,
        generation_model=settings.gemini_generation_model,
        disclaimer="AI-generated general guidance; verify important decisions with a local agricultural expert.",
    )
