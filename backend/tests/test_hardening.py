from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.db.database import get_db
from app.modules.crop_health.service import InvalidLeafImage, validate_image


def test_unsupported_decoder_is_not_selected_from_spoofed_mime():
    data = BytesIO()
    Image.new("RGB", (128, 128), (20, 180, 40)).save(data, format="BMP")
    with pytest.raises(InvalidLeafImage, match="not a valid"):
        validate_image(data.getvalue())


def test_rate_limit_protects_paid_posts():
    client = TestClient(app)
    for _ in range(30):
        assert client.post("/api/v1/soil/manual", json={"parameters": {}}).status_code == 422
    response = client.post("/api/v1/soil/manual", json={"parameters": {}})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_database_failure_does_not_expose_sql_or_credentials():
    def failing_db():
        raise SQLAlchemyError("postgresql://private-password SELECT private farmer data")
        yield
    app.dependency_overrides[get_db] = failing_db
    try:
        response = TestClient(app, raise_server_exceptions=False).post("/api/v1/advisor/chat", json={"question": "What is soil?"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert "private" not in response.text and "SELECT" not in response.text
