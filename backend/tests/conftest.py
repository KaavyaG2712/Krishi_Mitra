import pytest
from app.main import app


@pytest.fixture(autouse=True)
def isolate_rate_limit_window():
    middleware = app.middleware_stack
    while middleware:
        if hasattr(middleware, "windows"):
            middleware.windows.clear()
        middleware = getattr(middleware, "app", None)
