"""Dataset endpoints behind screen 1 (Start): upload a CSV, load the sample, read the active one.

Each load replaces the active dataset ("Change dataset" is simply another load), so only
one dataset is active at a time (POLICY D-6). The response is the stored profile (TMP-04):
table and column names, inferred types and row counts, the dataset fingerprint, and up to
five example values per text column for local display on the Data overview (screen 2).
It is read from disk; these endpoints never open the dataset after it is loaded.
"""

from fastapi import APIRouter, HTTPException, UploadFile

from app.pipeline.loader import DatasetError, active_dataset, load_csv_upload, load_sample

router = APIRouter(prefix="/datasets", tags=["datasets"])

# HTTP status for each rejection reason; the message itself comes from the loader.
_STATUS = {"too_large": 413, "not_csv": 415, "busy": 409}


def _reject(error: DatasetError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(error.reason, 422),
        detail={"reason": error.reason, "message": str(error)},
    )


@router.post("/upload")
def upload_csv(file: UploadFile) -> dict:
    try:
        summary = load_csv_upload(file.file, file.filename or "")
    except DatasetError as error:
        raise _reject(error) from None
    return {"dataset": summary.to_dict()}


@router.post("/sample")
def use_sample() -> dict:
    try:
        summary = load_sample()
    except DatasetError as error:
        raise _reject(error) from None
    return {"dataset": summary.to_dict()}


@router.get("/active")
def get_active() -> dict:
    summary = active_dataset()
    return {"dataset": summary.to_dict() if summary else None}
