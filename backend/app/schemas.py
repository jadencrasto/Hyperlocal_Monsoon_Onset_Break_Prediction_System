from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HistoryRefreshRequest(BaseModel):
    provider: str = "open_meteo"
    start: date
    end: date

    @model_validator(mode="after")
    def _check(self):
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        if (self.end - self.start).days > 366 * 45:
            raise ValueError("date range too large (max 45 years per request)")
        if self.end > date.today():
            raise ValueError("end date is in the future; history cannot be fetched for future dates")
        return self


class ForecastRefreshRequest(BaseModel):
    provider: str = "open_meteo"


class ModeRequest(BaseModel):
    preference: Literal["auto", "online", "offline"] = Field(description="auto detects connectivity")
