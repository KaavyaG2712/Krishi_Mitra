from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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
