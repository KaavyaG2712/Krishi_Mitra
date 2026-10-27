from datetime import date
from typing import Literal

from pydantic import Field, model_validator
from app.modules.soil.models import StrictModel
from app.modules.planning.dates import today_in_india


class PlanRequest(StrictModel):
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    location_name: str = Field(default="Selected location", max_length=180)
    # Optional administrative labels accompany a selected geocoding result and
    # let the separate historical-yield experiment match the location to DLD.
    state: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    sowing_date: date = Field(default_factory=today_in_india)
    irrigation: Literal["unknown", "rainfed", "available"] = "unknown"
    area_ha: float = Field(default=1, gt=0, le=10000, strict=True)

    @model_validator(mode="after")
    def future_date(self):
        if not 0 <= (self.sowing_date - today_in_india()).days <= 365:
            raise ValueError("Choose a sowing date between today and one year from today.")
        return self
