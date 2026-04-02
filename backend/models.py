from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Study(BaseModel):
    study_instance_uid: str
    patient_name: Optional[str] = ""
    patient_id: Optional[str] = ""
    patient_dob: Optional[str] = ""
    patient_sex: Optional[str] = ""
    study_date: Optional[str] = ""
    study_time: Optional[str] = ""
    modality: Optional[str] = ""
    num_images: int = 0
    received_at: Optional[str] = None


class Image(BaseModel):
    image_uid: str
    study_uid: str
    series_uid: str
    instance_number: Optional[int] = 0
    file_path: str
    thumbnail_path: Optional[str] = ""


class OBMeasurements(BaseModel):
    bpd: Optional[float] = None          # mm
    hc: Optional[float] = None           # mm
    ac: Optional[float] = None           # mm
    fl: Optional[float] = None           # mm
    efw: Optional[float] = None          # grams
    afi: Optional[float] = None          # cm
    placenta_location: Optional[str] = None  # anterior/posterior/fundal/lateral/low-lying
    amniotic_fluid: Optional[str] = None    # normal/polyhydramnios/oligohydramnios
    presentation: Optional[str] = None      # cephalic/breech/transverse/oblique
    fetal_heart_rate: Optional[int] = None  # bpm
    edd_by_lmp: Optional[str] = None
    edd_by_scan: Optional[str] = None
    ga_weeks: Optional[int] = None
    ga_days: Optional[int] = None


class Report(BaseModel):
    id: Optional[int] = None
    study_uid: str
    patient_name: Optional[str] = ""
    patient_age: Optional[str] = ""
    referring_doctor: Optional[str] = ""
    radiologist: Optional[str] = ""
    measurements: Optional[OBMeasurements] = None
    impression: Optional[str] = ""
    advice: Optional[str] = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReportCreate(BaseModel):
    patient_name: Optional[str] = ""
    patient_age: Optional[str] = ""
    referring_doctor: Optional[str] = ""
    radiologist: Optional[str] = ""
    measurements: Optional[OBMeasurements] = None
    impression: Optional[str] = ""
    advice: Optional[str] = ""


class ReportUpdate(BaseModel):
    patient_name: Optional[str] = None
    patient_age: Optional[str] = None
    referring_doctor: Optional[str] = None
    radiologist: Optional[str] = None
    measurements: Optional[OBMeasurements] = None
    impression: Optional[str] = None
    advice: Optional[str] = None


class StudyDetail(BaseModel):
    study: Study
    images: list[Image]
    report: Optional[Report] = None


class ReportPdfData(BaseModel):
    study: Study
    images: list[Image]
    report: Report
