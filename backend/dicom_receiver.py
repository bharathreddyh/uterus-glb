import os
import logging
import threading
import queue
import numpy as np
from datetime import datetime
from pathlib import Path

import pydicom
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian, ExplicitVRBigEndian
from PIL import Image as PILImage
from pynetdicom import AE, evt, AllStoragePresentationContexts, VerificationPresentationContexts
from pynetdicom.sop_class import Verification

logger = logging.getLogger(__name__)


def _safe_str(val) -> str:
    """Safely convert a DICOM value to string."""
    if val is None:
        return ""
    try:
        s = str(val)
        # Remove null bytes and strip
        return s.replace("\x00", "").strip()
    except Exception:
        return ""


def _generate_thumbnail(ds, thumbnail_path: str) -> bool:
    """Generate a JPEG thumbnail from a DICOM dataset."""
    try:
        if not hasattr(ds, "PixelData"):
            return False

        pixel_array = ds.pixel_array

        # Handle multi-frame: take first frame
        if pixel_array.ndim == 3 and pixel_array.shape[0] > 1:
            # Check if it's (frames, rows, cols) or (rows, cols, channels)
            if ds.SamplesPerPixel == 1:
                pixel_array = pixel_array[0]
            # else it's RGB, keep as is
        elif pixel_array.ndim == 4:
            pixel_array = pixel_array[0]

        # Apply windowing for grayscale
        if pixel_array.ndim == 2:
            # Use DICOM window settings if available
            if hasattr(ds, "WindowCenter") and hasattr(ds, "WindowWidth"):
                wc = float(ds.WindowCenter) if not hasattr(ds.WindowCenter, "__iter__") else float(ds.WindowCenter[0])
                ww = float(ds.WindowWidth) if not hasattr(ds.WindowWidth, "__iter__") else float(ds.WindowWidth[0])
                lo = wc - ww / 2
                hi = wc + ww / 2
            else:
                lo = float(pixel_array.min())
                hi = float(pixel_array.max())

            # Rescale slope/intercept
            slope = float(getattr(ds, "RescaleSlope", 1) or 1)
            intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
            pixel_float = pixel_array.astype(np.float64) * slope + intercept

            if hi == lo:
                hi = lo + 1
            pixel_float = np.clip((pixel_float - lo) / (hi - lo) * 255, 0, 255)
            img_array = pixel_float.astype(np.uint8)

            # Handle PhotometricInterpretation MONOCHROME1 (inverted)
            photometric = _safe_str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))
            if "MONOCHROME1" in photometric:
                img_array = 255 - img_array

            pil_img = PILImage.fromarray(img_array, mode="L").convert("RGB")
        else:
            # RGB/YBR
            if pixel_array.dtype != np.uint8:
                pixel_array = (pixel_array / pixel_array.max() * 255).astype(np.uint8)
            pil_img = PILImage.fromarray(pixel_array)

        # Resize to thumbnail
        pil_img.thumbnail((256, 256), PILImage.LANCZOS)
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        pil_img.save(thumbnail_path, "JPEG", quality=85)
        return True

    except Exception as e:
        logger.warning("Failed to generate thumbnail: %s", e)
        return False


class DICOMReceiver:
    def __init__(self, store, data_dir: str, ae_title: str = "IHA_CARE",
                 port: int = 11112, event_queue: queue.Queue = None):
        self.store = store
        self.data_dir = data_dir
        self.ae_title = ae_title
        self.port = port
        self.event_queue = event_queue or queue.Queue()
        self._ae: AE = None
        self._thread: threading.Thread = None
        self._running = False
        self._lock = threading.Lock()

    def _handle_store(self, event):
        """Handle C-STORE request."""
        ds = event.dataset
        ds.file_meta = event.file_meta

        try:
            study_uid = _safe_str(getattr(ds, "StudyInstanceUID", "")) or "unknown"
            series_uid = _safe_str(getattr(ds, "SeriesInstanceUID", "")) or "unknown"
            instance_uid = _safe_str(getattr(ds, "SOPInstanceUID", "")) or "unknown"

            # Build file path
            dcm_dir = os.path.join(self.data_dir, "dicom", study_uid, series_uid)
            os.makedirs(dcm_dir, exist_ok=True)
            dcm_path = os.path.join(dcm_dir, f"{instance_uid}.dcm")

            # Save DICOM file
            ds.save_as(dcm_path, write_like_original=False)
            logger.info("Saved DICOM: %s", dcm_path)

            # Generate thumbnail
            thumb_dir = os.path.join(self.data_dir, "thumbnails")
            thumb_path = os.path.join(thumb_dir, f"{instance_uid}.jpg")
            _generate_thumbnail(ds, thumb_path)

            # Extract metadata
            study_dict = {
                "study_instance_uid": study_uid,
                "patient_name": _safe_str(getattr(ds, "PatientName", "")),
                "patient_id": _safe_str(getattr(ds, "PatientID", "")),
                "patient_dob": _safe_str(getattr(ds, "PatientBirthDate", "")),
                "patient_sex": _safe_str(getattr(ds, "PatientSex", "")),
                "study_date": _safe_str(getattr(ds, "StudyDate", "")),
                "study_time": _safe_str(getattr(ds, "StudyTime", "")),
                "modality": _safe_str(getattr(ds, "Modality", "")),
                "received_at": datetime.utcnow().isoformat(),
            }

            instance_num = 0
            try:
                instance_num = int(getattr(ds, "InstanceNumber", 0) or 0)
            except (ValueError, TypeError):
                pass

            image_dict = {
                "image_uid": instance_uid,
                "study_uid": study_uid,
                "series_uid": series_uid,
                "instance_number": instance_num,
                "file_path": dcm_path,
                "thumbnail_path": thumb_path if os.path.exists(thumb_path) else "",
            }

            self.store.save_study(study_dict)
            self.store.save_image(image_dict)

            # Notify SSE listeners
            try:
                self.event_queue.put_nowait({
                    "type": "new_study",
                    "study_uid": study_uid,
                    "patient_name": study_dict["patient_name"],
                })
            except queue.Full:
                pass

            return 0x0000  # Success

        except Exception as e:
            logger.error("Error handling C-STORE: %s", e, exc_info=True)
            return 0xA700  # Out of resources

    def _handle_echo(self, event):
        """Handle C-ECHO (ping) request."""
        logger.debug("C-ECHO received from %s", event.assoc.requestor.address)
        return 0x0000

    def start(self):
        with self._lock:
            if self._running:
                return

            self._ae = AE(ae_title=self.ae_title)

            # Accept all storage SOP classes
            for context in AllStoragePresentationContexts:
                self._ae.add_supported_context(
                    context.abstract_syntax,
                    [ExplicitVRLittleEndian, ImplicitVRLittleEndian, ExplicitVRBigEndian]
                )

            # Accept verification (C-ECHO)
            self._ae.add_supported_context(Verification)

            handlers = [
                (evt.EVT_C_STORE, self._handle_store),
                (evt.EVT_C_ECHO, self._handle_echo),
            ]

            self._running = True
            self._thread = threading.Thread(
                target=self._run,
                args=(handlers,),
                daemon=True,
                name="DICOMReceiver"
            )
            self._thread.start()
            logger.info("DICOM receiver started on port %d (AE: %s)", self.port, self.ae_title)

    def _run(self, handlers):
        try:
            self._ae.start_server(
                ("0.0.0.0", self.port),
                block=True,
                evt_handlers=handlers,
            )
        except Exception as e:
            if self._running:
                logger.error("DICOM server error: %s", e, exc_info=True)
        finally:
            self._running = False

    def stop(self):
        with self._lock:
            self._running = False
            if self._ae:
                try:
                    self._ae.shutdown()
                except Exception:
                    pass
                self._ae = None
        logger.info("DICOM receiver stopped")

    @property
    def is_running(self) -> bool:
        return self._running
