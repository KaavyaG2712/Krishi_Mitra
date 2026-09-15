from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import DiseaseScan
from app.modules.crop_health.service import DISPLAY_LABELS, InvalidLeafImage, predict

router = APIRouter(prefix="/health")
SUPPORTED_CROPS = {"tomato", "potato", "maize", "grape"}
SUPPORTED_CONDITIONS = {
    "tomato": ["Healthy", "Early Blight", "Late Blight"],
    "potato": ["Healthy", "Early Blight", "Late Blight"],
    "maize": ["Healthy", "Common Rust"],
    "grape": ["Healthy", "Black Rot"],
}
UNSUPPORTED_DISEASE_NOTES = {
    "maize": "It cannot identify Northern Leaf Blight or other maize diseases.",
}


class HealthPredictionResponse(BaseModel):
    scan_id: UUID
    predicted_label: str
    confidence: float = Field(ge=0, le=1)
    is_uncertain: bool
    selected_crop: str | None = None
    detected_crop: str
    crop_mismatch: bool
    supported_conditions: list[str]
    model_version: str = "mobilenetv2-10class-v1"
    advisory_reference: str


@router.post("/predict", response_model=HealthPredictionResponse, status_code=status.HTTP_201_CREATED)
async def predict_leaf(
    image: UploadFile = File(...),
    crop_hint: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> HealthPredictionResponse:
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WebP leaf image.")
    if crop_hint and crop_hint.lower() not in SUPPORTED_CROPS:
        raise HTTPException(status_code=422, detail="Crop hint must be Tomato, Potato, Maize, or Grape.")
    settings = get_settings()
    try:
        image_contents = await image.read()
        label, confidence = predict(image_contents, settings.model_artifact_dir)
    except InvalidLeafImage as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="The crop-health model is unavailable.") from error
    detected_crop = label.split("_", maxsplit=1)[0]
    selected_crop = crop_hint.lower() if crop_hint else None
    crop_mismatch = selected_crop is not None and selected_crop != detected_crop
    uncertain = confidence < settings.health_confidence_threshold or crop_mismatch
    if crop_mismatch:
        reference = (
            f"You selected {selected_crop.title()}, but the classifier's supported-crop result is "
            f"{detected_crop.title()}. Do not use this as a diagnosis. Check the crop selection and upload "
            "a clear colour image of the selected crop."
        )
    elif confidence < settings.health_confidence_threshold:
        reference = (
            "Low-confidence result: this is the classifier's closest supported label, not a confirmed "
            "diagnosis. Try a sharper close-up leaf photo and consult a local agricultural officer/KVK "
            "before making treatment decisions."
        )
    else:
        unsupported_note = UNSUPPORTED_DISEASE_NOTES.get(
            detected_crop, "It cannot diagnose other diseases outside this limited label set."
        )
        reference = (
            f"This is a classifier result among the supported {detected_crop.title()} conditions only "
            f"({', '.join(SUPPORTED_CONDITIONS[detected_crop])}). {unsupported_note} "
            "confirm treatment decisions with a local agricultural officer/KVK."
        )
    scan = DiseaseScan(
        image_reference=f"sha256:{sha256(image_contents).hexdigest()}",
        crop_hint=selected_crop,
        crop_mismatch=crop_mismatch,
        predicted_label=label,
        confidence=confidence,
        model_version="mobilenetv2-10class-v1",
    )
    db.add(scan)
    db.flush()
    return HealthPredictionResponse(
        scan_id=scan.id,
        predicted_label=DISPLAY_LABELS[label],
        confidence=confidence,
        is_uncertain=uncertain,
        selected_crop=selected_crop.title() if selected_crop else None,
        detected_crop=detected_crop.title(),
        crop_mismatch=crop_mismatch,
        supported_conditions=SUPPORTED_CONDITIONS[detected_crop],
        advisory_reference=reference,
    )
