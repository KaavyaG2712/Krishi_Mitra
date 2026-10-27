"""Small single-process limits. Production proxy must enforce global quotas."""
import json
import logging
from collections import OrderedDict
from time import monotonic

from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app):
        self.app = app
        self.windows = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] == "POST" or scope["path"].startswith(("/api/v1/soil/locations/", "/api/v1/planning/locations")):
            now = monotonic()
            while self.windows and next(iter(self.windows.values()))[0] < now - 60:
                self.windows.popitem(last=False)
            key = (scope.get("client") or ("unknown",))[0]
            start, count = self.windows.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= 30:
                return await JSONResponse({"detail": {"code": "rate_limited", "message": "Please wait a minute before trying again."}}, 429, headers={"Retry-After": "60"})(scope, receive, send)
            if len(self.windows) >= 10000 and key not in self.windows:
                return await JSONResponse({"detail": "The service is busy. Please retry shortly."}, 503)(scope, receive, send)
            self.windows[key] = (start, count + 1)
        limit = 11 * 1024 * 1024 if scope["path"].endswith("/health/predict") else 64 * 1024
        if scope["path"] == "/api/v1/speech/transcribe":
            limit = 1_100_000
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                from starlette.exceptions import HTTPException
                raise HTTPException(413, "The upload is too large.")
            return message

        await self.app(scope, limited_receive, send)


class EventFormatter(logging.Formatter):
    def format(self, record):
        # Fixed event names only. Never serialize exception bodies/requests.
        event = {"level": record.levelname, "event": record.getMessage()}
        for key in ("error_code", "duration_ms", "source_language", "target_language",
                    "source", "error_type", "status_code", "attempt", "layer"):
            if hasattr(record, key):
                event[key] = getattr(record, key)
        return json.dumps(event)
