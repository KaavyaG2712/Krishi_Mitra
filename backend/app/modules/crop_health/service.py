from __future__ import annotations

import json
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock

import torch
from PIL import Image, UnidentifiedImageError
from torchvision.models import mobilenet_v2
from torchvision.transforms import v2

LABELS = ["tomato_healthy", "tomato_early_blight", "tomato_late_blight", "potato_healthy", "potato_early_blight", "potato_late_blight", "maize_healthy", "maize_common_rust", "grape_healthy", "grape_black_rot"]
DISPLAY_LABELS = {label: label.replace("_", " ").title().replace("Maize", "Maize").replace("Grape", "Grape") for label in LABELS}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_AVERAGE_CHROMA = 4.0
_inference_lock = Lock()


class InvalidLeafImage(ValueError):
    pass


def is_grayscale(image: Image.Image) -> bool:
    """Reject monochrome inputs instead of silently treating them as colour photos.

    The version-1 model was trained only on the colour PlantVillage subset.  A
    grayscale photo is outside that training distribution; converting it to RGB
    creates three identical channels but does not restore the missing colour
    information the model learned from.
    """
    if image.mode in {"1", "L", "I", "I;16", "F"}:
        return True
    sample = image.convert("RGB")
    sample.thumbnail((64, 64))
    pixels = list(sample.getdata())
    if not pixels:
        return True
    average_chroma = sum(max(pixel) - min(pixel) for pixel in pixels) / len(pixels)
    return average_chroma < MIN_AVERAGE_CHROMA


def validate_image(contents: bytes) -> Image.Image:
    if not contents or len(contents) > MAX_IMAGE_BYTES:
        raise InvalidLeafImage("Upload a non-empty PNG, JPEG, or WebP image under 10 MB.")
    try:
        image = Image.open(BytesIO(contents))
        image.verify()
        decoded = Image.open(BytesIO(contents))
        if is_grayscale(decoded):
            raise InvalidLeafImage(
                "Upload a colour leaf photo. Grayscale images are outside this model's supported input range."
            )
        return decoded.convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidLeafImage("The uploaded file is not a valid readable image.") from error


@lru_cache
def load_model(artifact_dir: Path) -> tuple[torch.nn.Module, v2.Compose]:
    checkpoint = artifact_dir / "best_model.pt"
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Model artefact unavailable: {checkpoint}")
    model = mobilenet_v2(weights=None)
    model.classifier[1] = torch.nn.Linear(model.last_channel, len(LABELS))
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    model.eval()
    transform = v2.Compose([v2.Resize(256), v2.CenterCrop(224), v2.ToImage(), v2.ToDtype(torch.float32, scale=True), v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    return model, transform


def predict(contents: bytes, artifact_dir: Path) -> tuple[str, float]:
    image = validate_image(contents)
    model, transform = load_model(artifact_dir)
    with _inference_lock, torch.inference_mode():
        probabilities = torch.softmax(model(transform(image).unsqueeze(0)), dim=1)[0]
    index = int(probabilities.argmax().item())
    return LABELS[index], float(probabilities[index].item())
