from __future__ import annotations

import json
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image, UnidentifiedImageError

LABELS = ["tomato_healthy", "tomato_early_blight", "tomato_late_blight", "potato_healthy", "potato_early_blight", "potato_late_blight", "maize_healthy", "maize_common_rust", "grape_healthy", "grape_black_rot"]
DISPLAY_LABELS = {label: label.replace("_", " ").title().replace("Maize", "Maize").replace("Grape", "Grape") for label in LABELS}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_SIDE = 128
MIN_AVERAGE_CHROMA = 4.0
MIN_VEGETATION_RATIO = 0.08
MAX_FLAT_NEIGHBOUR_RATIO = 0.58
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
    pixels = list(sample.get_flattened_data())
    if not pixels:
        return True
    average_chroma = sum(max(pixel) - min(pixel) for pixel in pixels) / len(pixels)
    return average_chroma < MIN_AVERAGE_CHROMA


def vegetation_ratio(image: Image.Image) -> float:
    """Estimate whether the frame contains a meaningful amount of plant tissue.

    This is a deliberately conservative input guard, not a disease model.  The
    supported PlantVillage classes all contain green/yellow-green leaf tissue;
    obvious unrelated objects should never reach the closed-set classifier.
    """
    sample = image.convert("RGB")
    sample.thumbnail((128, 128))
    hsv_pixels = list(sample.convert("HSV").get_flattened_data())
    if not hsv_pixels:
        return 0.0

    plant_pixels = sum(
        1
        for hue, saturation, value in hsv_pixels
        if 24 <= hue <= 105 and saturation >= 35 and value >= 24
    )
    return plant_pixels / len(hsv_pixels)


def flat_neighbour_ratio(image: Image.Image) -> float:
    """Return the share of nearly identical adjacent pixels in a small sample.

    Natural leaf photographs contain fine colour and lighting variation. Flat
    illustrations usually contain large runs of almost identical pixels, even
    after antialiasing. This quality check complements the vegetation-colour
    check so green cartoons are not treated as leaf photographs.
    """
    sample = image.convert("RGB").resize((128, 128), Image.Resampling.BILINEAR)
    pixels = list(sample.get_flattened_data())
    width, height = sample.size
    flat_neighbours = 0
    neighbour_count = 0

    for y in range(height):
        for x in range(width):
            index = y * width + x
            neighbours = []
            if x + 1 < width:
                neighbours.append(index + 1)
            if y + 1 < height:
                neighbours.append(index + width)
            for neighbour_index in neighbours:
                neighbour_count += 1
                difference = sum(
                    abs(pixels[index][channel] - pixels[neighbour_index][channel])
                    for channel in range(3)
                )
                if difference < 9:
                    flat_neighbours += 1

    return flat_neighbours / neighbour_count if neighbour_count else 1.0


def validate_image(contents: bytes) -> Image.Image:
    if not contents or len(contents) > MAX_IMAGE_BYTES:
        raise InvalidLeafImage("Upload a non-empty PNG, JPEG, or WebP image under 10 MB.")
    try:
        image = Image.open(BytesIO(contents), formats=("PNG", "JPEG", "WEBP"))
        image.verify()
        decoded = Image.open(BytesIO(contents), formats=("PNG", "JPEG", "WEBP"))
        if decoded.width * decoded.height > 25_000_000:
            raise InvalidLeafImage("Please resize the image to under 25 megapixels.")
        if is_grayscale(decoded):
            raise InvalidLeafImage(
                "Upload a colour leaf photo. Grayscale images are outside this model's supported input range."
            )
        image = decoded.convert("RGB")
        if min(image.size) < MIN_IMAGE_SIDE:
            raise InvalidLeafImage(
                f"Upload a clearer leaf photo at least {MIN_IMAGE_SIDE} pixels wide and high."
            )
        if vegetation_ratio(image) < MIN_VEGETATION_RATIO:
            raise InvalidLeafImage(
                "No supported leaf was detected in this image. Upload a clear colour photo containing "
                "one Tomato, Potato, Maize, or Grape leaf. Cars, people, drawings, screenshots, and "
                "other objects cannot be diagnosed."
            )
        if flat_neighbour_ratio(image) > MAX_FLAT_NEIGHBOUR_RATIO:
            raise InvalidLeafImage(
                "This image appears too flat, blurred, or illustration-like for leaf diagnosis. Upload "
                "a natural, in-focus colour photograph of one supported leaf."
            )
        return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvalidLeafImage("The uploaded file is not a valid readable image.") from error


@lru_cache
def load_model(artifact_dir: Path) -> tuple[torch.nn.Module, v2.Compose]:
    import torch
    from torchvision.models import mobilenet_v2
    from torchvision.transforms import v2
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
    import torch
    model, transform = load_model(artifact_dir)
    with _inference_lock, torch.inference_mode():
        probabilities = torch.softmax(model(transform(image).unsqueeze(0)), dim=1)[0]
    index = int(probabilities.argmax().item())
    return LABELS[index], float(probabilities[index].item())
