from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: ApiError
