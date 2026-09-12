from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.crop_health.service import DISPLAY_LABELS, InvalidLeafImage, predict

router = APIRouter(prefix="/health")
SUPPORTED_CROPS = {"tomato", "potato", "maize", "grape"}


class HealthPredictionResponse(BaseModel):
    scan_id: UUID
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    is_uncertain: bool
    model_version: str = "mobilenetv2-10class-v1"
    advisory_reference: str


@router.post("/predict", response_model=HealthPredictionResponse, status_code=status.HTTP_201_CREATED)
async def predict_leaf(image: UploadFile = File(...), crop_hint: str | None = Form(default=None)) -> HealthPredictionResponse:
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WebP leaf image.")
    if crop_hint and crop_hint.lower() not in SUPPORTED_CROPS:
        raise HTTPException(status_code=422, detail="Crop hint must be Tomato, Potato, Maize, or Grape.")
    settings = get_settings()
    try:
        label, confidence = predict(await image.read(), settings.model_artifact_dir)
    except InvalidLeafImage as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="The crop-health model is unavailable.") from error
    uncertain = confidence < settings.health_confidence_threshold
    reference = "Result uncertain. Please consult a local agricultural officer/KVK." if uncertain else "Use the cited Agronomy Advisor for evidence-grounded next steps; confirm treatment decisions with a local agricultural officer/KVK."
    return HealthPredictionResponse(scan_id=uuid4(), predicted_label=DISPLAY_LABELS[label], confidence=confidence, is_uncertain=uncertain, advisory_reference=reference)
