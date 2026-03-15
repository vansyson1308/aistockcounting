import asyncio

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.audit import audit_log
from app.schemas.count import CountResponse
from app.services.inference import InferenceService
from app.services.storage import StorageService
from app.utils.image_validation import (
    validate_decodable_image,
    validate_file_size,
    validate_file_type,
)

router = APIRouter(prefix="", tags=["Counting"])


@router.post(
    "/count-items",
    response_model=CountResponse,
    summary="Upload tray image and run AI counting",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "example": {
                        "image": "<binary>",
                        "tray_id": "TRAY-A1",
                        "staff_id": "EMP-001",
                    }
                }
            }
        }
    },
)
async def count_items(
    image: UploadFile = File(...),
    tray_id: str | None = Form(default=None),
    staff_id: str | None = Form(default=None),
    storage: StorageService = Depends(StorageService),
    inference: InferenceService = Depends(InferenceService),
) -> CountResponse:
    validate_file_type(image)
    payload = await image.read()
    validate_file_size(payload)
    validate_decodable_image(payload)

    storage_task = asyncio.to_thread(
        storage.save_image_and_thumbnail, payload, image.filename or "upload.jpg"
    )
    inference_task = inference.predict(payload)
    (image_path, image_thumbnail), detection = await asyncio.gather(
        storage_task, inference_task
    )

    audit_log(
        "COUNT",
        staff_id,
        {"tray_id": tray_id, "detected_count": detection["detected_count"]},
    )

    return CountResponse(
        data={
            "image_path": image_path,
            "image_thumbnail": image_thumbnail,
            "tray_id": tray_id,
            "staff_id": staff_id,
            **detection,
        }
    )
