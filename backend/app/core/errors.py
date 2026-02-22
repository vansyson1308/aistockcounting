from fastapi import HTTPException, status


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


BAD_REQUEST_IMAGE = api_error(
    status.HTTP_400_BAD_REQUEST,
    "INVALID_IMAGE",
    "Invalid image payload. Only JPEG/PNG images are accepted.",
)
