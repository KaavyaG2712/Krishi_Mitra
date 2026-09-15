from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.api.v1.endpoints import crop_health
from app.db.database import get_db
from app.main import app
from app.modules.crop_health.service import InvalidLeafImage, validate_image


def image_bytes(mode: str, colour: tuple[int, int, int] | int) -> bytes:
    image = Image.new(mode, (32, 32), colour)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_grayscale_image_is_rejected_before_inference() -> None:
    grayscale = image_bytes("L", 120)
    with pytest.raises(InvalidLeafImage, match="colour leaf photo"):
        validate_image(grayscale)

    response = TestClient(app).post(
        "/api/v1/health/predict",
        files={"image": ("gray-leaf.png", grayscale, "image/png")},
        data={"crop_hint": "Potato"},
    )
    assert response.status_code == 422
    assert "colour leaf photo" in response.json()["detail"]


def test_obvious_non_leaf_image_is_rejected_before_inference() -> None:
    image = Image.new("RGB", (256, 256), (210, 15, 20))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    red_object = buffer.getvalue()

    with pytest.raises(InvalidLeafImage, match="No supported leaf"):
        validate_image(red_object)

    response = TestClient(app).post(
        "/api/v1/health/predict",
        files={"image": ("red-car-like-object.png", red_object, "image/png")},
        data={"crop_hint": "Maize"},
    )
    assert response.status_code == 422
    assert "No supported leaf" in response.json()["detail"]


def test_flat_green_illustration_is_rejected_before_inference() -> None:
    image = Image.new("RGB", (256, 256), (235, 235, 235))
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((35, 60, 220, 195), fill=(55, 180, 45), outline=(5, 25, 5), width=10)
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    with pytest.raises(InvalidLeafImage, match="illustration-like"):
        validate_image(buffer.getvalue())


def test_low_confidence_leaf_returns_tentative_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        scan = None

        def add(self, scan: object) -> None:
            self.scan = scan

        def flush(self) -> None:
            self.scan.id = uuid4()

    session = FakeSession()
    monkeypatch.setattr(crop_health, "predict", lambda *_: ("tomato_late_blight", 0.708))
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).post(
            "/api/v1/health/predict",
            files={"image": ("random-green-image.png", image_bytes("RGB", (30, 140, 40)), "image/png")},
            data={"crop_hint": "Tomato"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["predicted_label"] == "Tomato Late Blight"
    assert payload["is_uncertain"] is True
    assert "Low-confidence result" in payload["advisory_reference"]
    assert session.scan.predicted_label == "tomato_late_blight"


def test_crop_hint_mismatch_is_marked_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        scan = None

        def add(self, scan: object) -> None:
            self.scan = scan

        def flush(self) -> None:
            self.scan.id = uuid4()

    session = FakeSession()
    monkeypatch.setattr(crop_health, "predict", lambda *_: ("potato_healthy", 0.96))
    app.dependency_overrides[get_db] = lambda: session
    try:
        response = TestClient(app).post(
            "/api/v1/health/predict",
            files={"image": ("leaf.png", image_bytes("RGB", (30, 140, 40)), "image/png")},
            data={"crop_hint": "Tomato"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["predicted_label"] == "Potato Healthy"
    assert payload["detected_crop"] == "Potato"
    assert payload["crop_mismatch"] is True
    assert payload["is_uncertain"] is True
    assert session.scan.crop_hint == "tomato"
    assert session.scan.crop_mismatch is True
