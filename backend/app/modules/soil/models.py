from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PARAMETERS = {
    "nitrogen": ("Nitrogen (N)", ["kg/ha", "mg/kg", "ppm"]),
    "phosphorus": ("Phosphorus (P)", ["kg/ha", "mg/kg", "ppm"]),
    "potassium": ("Potassium (K)", ["kg/ha", "mg/kg", "ppm"]),
    "sulphur": ("Sulphur (S)", ["mg/kg", "ppm", "kg/ha"]),
    "zinc": ("Zinc (Zn)", ["mg/kg", "ppm"]),
    "iron": ("Iron (Fe)", ["mg/kg", "ppm"]),
    "copper": ("Copper (Cu)", ["mg/kg", "ppm"]),
    "manganese": ("Manganese (Mn)", ["mg/kg", "ppm"]),
    "boron": ("Boron (B)", ["mg/kg", "ppm"]),
    "ph": ("pH", ["pH"]),
    "electricalConductivity": ("Electrical conductivity (EC)", ["dS/m", "mS/cm", "uS/cm"]),
    "organicCarbon": ("Organic carbon (OC)", ["%", "g/kg"]),
}


class SourceType(StrEnum):
    GOVERNMENT_VERIFIED = "GOVERNMENT_VERIFIED"
    USER_ENTERED = "USER_ENTERED"
    AI_ESTIMATED = "AI_ESTIMATED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Measurement(StrictModel):
    value: float = Field(ge=0, strict=True)
    unit: str = Field(min_length=1, max_length=40)
    method: str | None = Field(default=None, max_length=120)


class Location(StrictModel):
    state: str = Field(default="", max_length=120)
    district: str = Field(default="", max_length=120)
    block: str = Field(default="", max_length=120)
    village: str = Field(default="", max_length=120)
    state_id: str = Field(default="", max_length=80)
    district_id: str = Field(default="", max_length=80)
    block_id: str = Field(default="", max_length=80)
    village_id: str = Field(default="", max_length=80)


class SoilInput(StrictModel):
    parameters: dict[str, Measurement] = Field(min_length=1, max_length=12)
    location: Location = Field(default_factory=Location)
    sample_date: date | None = None

    @model_validator(mode="after")
    def valid_measurements(self):
        if self.sample_date and self.sample_date > date.today():
            raise ValueError("The soil test date cannot be in the future.")
        for key, measurement in self.parameters.items():
            if key not in PARAMETERS:
                raise ValueError("Choose a supported soil parameter.")
            authoritative = isinstance(self, SoilProfile) and self.source_type == SourceType.GOVERNMENT_VERIFIED
            if measurement.unit not in PARAMETERS[key][1] and not authoritative:
                raise ValueError(f"Check the unit for {PARAMETERS[key][0]} against your report.")
            if key == "ph" and measurement.value > 14:
                raise ValueError("Soil pH must be between 0 and 14.")
            if measurement.unit in {"%", "g/kg", "mg/kg", "ppm"}:
                maximum = {"%": 100, "g/kg": 1000, "mg/kg": 1_000_000, "ppm": 1_000_000}[measurement.unit]
                if measurement.value > maximum:
                    raise ValueError(f"{PARAMETERS[key][0]} exceeds the physical limit for {measurement.unit}.")
        return self


class SoilProfile(SoilInput):
    source: str
    source_type: SourceType
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float | None = Field(default=None, ge=0, le=1)
    coverage: Literal["entered_sample", "area_sample", "estimate"] = "entered_sample"
    is_demo: bool = False


class SoilLookup(StrictModel):
    location: Location = Field(default_factory=Location)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def location_required(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Both latitude and longitude are required.")
        if self.latitude is None and not all([self.location.state_id, self.location.district_id, self.location.block_id, self.location.village_id]):
            raise ValueError("Select state, district, block and village, or use current location.")
        return self
