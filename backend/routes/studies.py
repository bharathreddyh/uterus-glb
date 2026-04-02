import os
import shutil
import logging
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studies", tags=["studies"])


def _get_store(request: Request):
    return request.app.state.store


@router.get("")
async def list_studies(request: Request):
    """List all studies sorted by received_at desc."""
    store = _get_store(request)
    studies = store.get_all_studies()
    return studies


@router.get("/{uid}")
async def get_study(uid: str, request: Request):
    """Get study detail including image list."""
    store = _get_store(request)
    study = store.get_study(uid)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    images = store.get_study_images(uid)
    report = store.get_report(uid)
    return {
        "study": study,
        "images": images,
        "report": report,
    }


@router.delete("/{uid}")
async def delete_study(uid: str, request: Request):
    """Delete study, its images, report, and files."""
    store = _get_store(request)
    study = store.get_study(uid)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    # Get images to delete files
    images = store.get_study_images(uid)

    # Delete from DB (cascades to images and reports)
    store.delete_study(uid)

    # Delete DICOM files
    data_dir = request.app.state.store.data_dir
    study_dicom_dir = os.path.join(data_dir, "dicom", uid)
    if os.path.isdir(study_dicom_dir):
        shutil.rmtree(study_dicom_dir, ignore_errors=True)

    # Delete thumbnail files
    for image in images:
        thumb = image.get("thumbnail_path", "")
        if thumb and os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass

    return {"deleted": uid}
