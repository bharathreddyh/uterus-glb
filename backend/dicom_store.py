import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DicomStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, "uterus.db")
        os.makedirs(data_dir, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        # check_same_thread=False allows use from DICOM receiver thread
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS studies (
                    study_instance_uid TEXT PRIMARY KEY,
                    patient_name TEXT DEFAULT '',
                    patient_id TEXT DEFAULT '',
                    patient_dob TEXT DEFAULT '',
                    patient_sex TEXT DEFAULT '',
                    study_date TEXT DEFAULT '',
                    study_time TEXT DEFAULT '',
                    modality TEXT DEFAULT '',
                    num_images INTEGER DEFAULT 0,
                    received_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS images (
                    image_uid TEXT PRIMARY KEY,
                    study_uid TEXT NOT NULL,
                    series_uid TEXT NOT NULL,
                    instance_number INTEGER DEFAULT 0,
                    file_path TEXT NOT NULL,
                    thumbnail_path TEXT DEFAULT '',
                    FOREIGN KEY (study_uid) REFERENCES studies(study_instance_uid) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_uid TEXT UNIQUE NOT NULL,
                    patient_name TEXT DEFAULT '',
                    patient_age TEXT DEFAULT '',
                    referring_doctor TEXT DEFAULT '',
                    radiologist TEXT DEFAULT '',
                    measurements TEXT DEFAULT '{}',
                    impression TEXT DEFAULT '',
                    advice TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (study_uid) REFERENCES studies(study_instance_uid) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_images_study ON images(study_uid);
                CREATE INDEX IF NOT EXISTS idx_reports_study ON reports(study_uid);
                CREATE INDEX IF NOT EXISTS idx_studies_received ON studies(received_at DESC);
            """)
            conn.commit()
            logger.info("Database initialized at %s", self.db_path)
        finally:
            conn.close()

    def save_study(self, study_dict: dict):
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT study_instance_uid, num_images FROM studies WHERE study_instance_uid = ?",
                (study_dict["study_instance_uid"],)
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE studies SET
                        patient_name = ?,
                        patient_id = ?,
                        patient_dob = ?,
                        patient_sex = ?,
                        study_date = ?,
                        study_time = ?,
                        modality = ?,
                        num_images = num_images + 1
                    WHERE study_instance_uid = ?
                """, (
                    study_dict.get("patient_name", ""),
                    study_dict.get("patient_id", ""),
                    study_dict.get("patient_dob", ""),
                    study_dict.get("patient_sex", ""),
                    study_dict.get("study_date", ""),
                    study_dict.get("study_time", ""),
                    study_dict.get("modality", ""),
                    study_dict["study_instance_uid"],
                ))
            else:
                conn.execute("""
                    INSERT INTO studies
                        (study_instance_uid, patient_name, patient_id, patient_dob, patient_sex,
                         study_date, study_time, modality, num_images, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    study_dict["study_instance_uid"],
                    study_dict.get("patient_name", ""),
                    study_dict.get("patient_id", ""),
                    study_dict.get("patient_dob", ""),
                    study_dict.get("patient_sex", ""),
                    study_dict.get("study_date", ""),
                    study_dict.get("study_time", ""),
                    study_dict.get("modality", ""),
                    study_dict.get("received_at", datetime.utcnow().isoformat()),
                ))
            conn.commit()
        finally:
            conn.close()

    def save_image(self, image_dict: dict):
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO images
                    (image_uid, study_uid, series_uid, instance_number, file_path, thumbnail_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                image_dict["image_uid"],
                image_dict["study_uid"],
                image_dict["series_uid"],
                image_dict.get("instance_number", 0),
                image_dict["file_path"],
                image_dict.get("thumbnail_path", ""),
            ))
            conn.commit()
        finally:
            conn.close()

    def get_all_studies(self) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM studies ORDER BY received_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_study(self, uid: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM studies WHERE study_instance_uid = ?", (uid,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_study_images(self, study_uid: str) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM images WHERE study_uid = ? ORDER BY instance_number ASC",
                (study_uid,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_image(self, image_uid: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM images WHERE image_uid = ?", (image_uid,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def save_report(self, report_dict: dict):
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            measurements = report_dict.get("measurements")
            if measurements and not isinstance(measurements, str):
                measurements = json.dumps(measurements)
            elif measurements is None:
                measurements = "{}"

            conn.execute("""
                INSERT INTO reports
                    (study_uid, patient_name, patient_age, referring_doctor, radiologist,
                     measurements, impression, advice, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_dict["study_uid"],
                report_dict.get("patient_name", ""),
                report_dict.get("patient_age", ""),
                report_dict.get("referring_doctor", ""),
                report_dict.get("radiologist", ""),
                measurements,
                report_dict.get("impression", ""),
                report_dict.get("advice", ""),
                now,
                now,
            ))
            conn.commit()
        finally:
            conn.close()

    def get_report(self, study_uid: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM reports WHERE study_uid = ?", (study_uid,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("measurements"):
                try:
                    d["measurements"] = json.loads(d["measurements"])
                except (json.JSONDecodeError, TypeError):
                    d["measurements"] = {}
            return d
        finally:
            conn.close()

    def update_report(self, study_uid: str, report_dict: dict):
        conn = self._get_conn()
        try:
            now = datetime.utcnow().isoformat()
            measurements = report_dict.get("measurements")
            if measurements and not isinstance(measurements, str):
                measurements = json.dumps(measurements)
            elif measurements is None:
                measurements = "{}"

            conn.execute("""
                UPDATE reports SET
                    patient_name = ?,
                    patient_age = ?,
                    referring_doctor = ?,
                    radiologist = ?,
                    measurements = ?,
                    impression = ?,
                    advice = ?,
                    updated_at = ?
                WHERE study_uid = ?
            """, (
                report_dict.get("patient_name", ""),
                report_dict.get("patient_age", ""),
                report_dict.get("referring_doctor", ""),
                report_dict.get("radiologist", ""),
                measurements,
                report_dict.get("impression", ""),
                report_dict.get("advice", ""),
                now,
                study_uid,
            ))
            conn.commit()
        finally:
            conn.close()

    def delete_study(self, uid: str):
        conn = self._get_conn()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM studies WHERE study_instance_uid = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
