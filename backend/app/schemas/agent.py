from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AgentRunResponse(BaseModel):
    success: bool = True
    data: dict[str, Any]


class TraceResponse(BaseModel):
    success: bool = True
    data: dict[str, Any]


class ApproveRequest(BaseModel):
    approver_id: str = Field(min_length=1, max_length=80)
    decision: Literal["approve", "correct", "reject"]
    corrected_count: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    unit_value: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _corrected_count_required(self) -> "ApproveRequest":
        if self.decision == "correct" and self.corrected_count is None:
            raise ValueError("corrected_count is required when decision is 'correct'")
        return self


class ApproveResponse(BaseModel):
    success: bool = True
    data: dict[str, Any]
