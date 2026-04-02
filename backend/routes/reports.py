import logging
from fastapi import APIRouter, HTTPException, Request
from models import ReportCreate, ReportUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


def _get_store(request: Request):
    return request.app.state.store


@router.get("/{study_uid}")
async def get_report(study_uid: str, request: Request):
    """Get report for a study. Returns 404 if none exists."""
    store = _get_store(request)
    report = store.get_report(study_uid)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/{study_uid}", status_code=201)
async def create_report(study_uid: str, body: ReportCreate, request: Request):
    """Create a new report for a study."""
    store = _get_store(request)

    # Check study exists
    study = store.get_study(study_uid)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    # Check no existing report
    existing = store.get_report(study_uid)
    if existing:
        raise HTTPException(status_code=409, detail="Report already exists; use PUT to update")

    measurements = None
    if body.measurements:
        measurements = body.measurements.model_dump(exclude_none=False)

    report_dict = {
        "study_uid": study_uid,
        "patient_name": body.patient_name or study.get("patient_name", ""),
        "patient_age": body.patient_age or "",
        "referring_doctor": body.referring_doctor or "",
        "radiologist": body.radiologist or "",
        "measurements": measurements,
        "impression": body.impression or "",
        "advice": body.advice or "",
    }

    store.save_report(report_dict)
    return store.get_report(study_uid)


@router.put("/{study_uid}")
async def update_report(study_uid: str, body: ReportUpdate, request: Request):
    """Update an existing report. Creates one if it doesn't exist (upsert)."""
    store = _get_store(request)

    study = store.get_study(study_uid)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    existing = store.get_report(study_uid)

    measurements = None
    if body.measurements is not None:
        measurements = body.measurements.model_dump(exclude_none=False)
    elif existing and existing.get("measurements"):
        measurements = existing["measurements"]

    if existing:
        report_dict = {
            "patient_name": body.patient_name if body.patient_name is not None else existing.get("patient_name", ""),
            "patient_age": body.patient_age if body.patient_age is not None else existing.get("patient_age", ""),
            "referring_doctor": body.referring_doctor if body.referring_doctor is not None else existing.get("referring_doctor", ""),
            "radiologist": body.radiologist if body.radiologist is not None else existing.get("radiologist", ""),
            "measurements": measurements,
            "impression": body.impression if body.impression is not None else existing.get("impression", ""),
            "advice": body.advice if body.advice is not None else existing.get("advice", ""),
        }
        store.update_report(study_uid, report_dict)
    else:
        # Auto-create
        report_dict = {
            "study_uid": study_uid,
            "patient_name": body.patient_name or study.get("patient_name", ""),
            "patient_age": body.patient_age or "",
            "referring_doctor": body.referring_doctor or "",
            "radiologist": body.radiologist or "",
            "measurements": measurements,
            "impression": body.impression or "",
            "advice": body.advice or "",
        }
        store.save_report(report_dict)

    return store.get_report(study_uid)


@router.get("/{study_uid}/pdf-data")
async def get_pdf_data(study_uid: str, request: Request):
    """Return all data needed for PDF generation."""
    store = _get_store(request)

    study = store.get_study(study_uid)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    images = store.get_study_images(study_uid)
    report = store.get_report(study_uid)

    if not report:
        raise HTTPException(status_code=404, detail="No report found for this study; save a report first")

    return {
        "study": study,
        "images": images,
        "report": report,
    }
