"""
DICOM Test Simulator
====================
Generates synthetic obstetric ultrasound DICOM images and sends them
to the local DICOM receiver via C-STORE — no real machine needed.

Usage:
    python tools/dicom_simulator.py                     # send 1 study, 5 images
    python tools/dicom_simulator.py --images 10         # 10 images
    python tools/dicom_simulator.py --studies 3         # 3 separate studies
    python tools/dicom_simulator.py --host 192.168.1.x  # remote receiver
    python tools/dicom_simulator.py --port 11112        # custom port
    python tools/dicom_simulator.py --save-only         # save .dcm locally, don't send
    python tools/dicom_simulator.py --save-dir ./test_dcm

Dependencies: pydicom, pynetdicom, numpy, Pillow (all in backend/requirements.txt)
"""

import argparse
import os
import sys
import random
import time
import datetime
import struct

import numpy as np

try:
    import pydicom
    from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
    from pydicom.sequence import Sequence
    from pydicom.uid import (
        generate_uid,
        ExplicitVRLittleEndian,
        UID,
    )
except ImportError:
    sys.exit("pydicom not installed. Run: pip install pydicom")

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow not installed. Run: pip install Pillow")


# ── Synthetic patient data ────────────────────────────────────────────────

PATIENTS = [
    {"name": "LAKSHMI^PRIYA", "id": "PT001", "sex": "F", "dob": "19960315",
     "ga_weeks": 28, "ga_days": 3},
    {"name": "ANITHA^KUMARI", "id": "PT002", "sex": "F", "dob": "19920710",
     "ga_weeks": 34, "ga_days": 1},
    {"name": "SRIDEVI^M", "id": "PT003", "sex": "F", "dob": "19990820",
     "ga_weeks": 20, "ga_days": 5},
    {"name": "MEENA^DEVI", "id": "PT004", "sex": "F", "dob": "19880512",
     "ga_weeks": 38, "ga_days": 2},
    {"name": "RAJESHWARI^B", "id": "PT005", "sex": "F", "dob": "20010225",
     "ga_weeks": 16, "ga_days": 0},
]

# Image label names matching common USG views
VIEW_LABELS = [
    "BPD MEASUREMENT",
    "HC MEASUREMENT",
    "AC MEASUREMENT",
    "FL MEASUREMENT",
    "FETAL HEART",
    "PLACENTA",
    "AFI QUADRANT 1",
    "AFI QUADRANT 2",
    "CERVICAL LENGTH",
    "FETAL FACE",
    "FETAL SPINE",
    "FETAL KIDNEY",
    "UMBILICAL ARTERY DOPPLER",
    "FETAL PROFILE",
    "CORONAL SECTION",
]

# Ultrasound SOP Class
US_MULTIFRAME_SOP = "1.2.840.10008.5.1.4.1.1.3.1"   # US Multi-frame Image
US_IMAGE_SOP      = "1.2.840.10008.5.1.4.1.1.6.1"    # Ultrasound Image Storage


# ── Image generation ─────────────────────────────────────────────────────

def _draw_ultrasound_frame(width=640, height=480, label="", frame_num=0):
    """Generate a synthetic grayscale ultrasound-like image as numpy array."""
    rng = np.random.default_rng(seed=frame_num * 17 + hash(label) % 1000)

    # Base: dark background
    img = np.zeros((height, width), dtype=np.float32)

    # Fan-shaped scan region
    cx, cy = width // 2, int(height * 0.08)
    r_inner, r_outer = int(height * 0.05), int(height * 0.95)
    half_angle = 55  # degrees

    yy, xx = np.mgrid[0:height, 0:width]
    dx = xx - cx
    dy = yy - cy
    r = np.sqrt(dx ** 2 + dy ** 2)
    theta = np.degrees(np.arctan2(dx, dy))

    in_fan = (r >= r_inner) & (r <= r_outer) & (np.abs(theta) <= half_angle)

    # Speckle noise (tissue texture)
    speckle = rng.exponential(scale=0.4, size=(height, width)).astype(np.float32)
    img[in_fan] = speckle[in_fan]

    # Add some blob structures (fetal structures)
    n_blobs = rng.integers(3, 8)
    for _ in range(n_blobs):
        bx = int(cx + rng.uniform(-0.3, 0.3) * r_outer)
        by = int(cy + rng.uniform(0.2, 0.8) * r_outer)
        br = rng.integers(20, 80)
        brightness = rng.uniform(0.3, 1.0)
        blob_yy, blob_xx = np.mgrid[
            max(0, by - br): min(height, by + br),
            max(0, bx - br): min(width, bx + br)
        ]
        dist = np.sqrt((blob_xx - bx) ** 2 + (blob_yy - by) ** 2)
        mask = dist < br
        blob_region = img[max(0, by - br): min(height, by + br),
                          max(0, bx - br): min(width, bx + br)]
        blob_region[mask] = np.clip(
            blob_region[mask] + brightness * (1 - dist[mask] / br), 0, 2
        )

    # Add measurement calipers (dotted lines)
    if "MEASUREMENT" in label.upper():
        caliper_y = int(cy + r_outer * 0.5)
        caliper_x1 = cx - 60
        caliper_x2 = cx + 60
        for x in range(caliper_x1, caliper_x2, 4):
            if x < width:
                img[caliper_y, x] = 2.0
        for y in range(caliper_y - 4, caliper_y + 4):
            if 0 <= y < height:
                img[y, caliper_x1] = 2.0
                img[y, caliper_x2] = 2.0

    # Add Doppler waveform at bottom for Doppler views
    if "DOPPLER" in label.upper():
        wave_y_base = int(height * 0.8)
        for x in range(20, width - 20):
            wave_y = wave_y_base - int(np.sin(x * 0.15) * 30 * max(0, np.sin(x * 0.04)))
            if 0 <= wave_y < height:
                img[wave_y, x] = 1.5

    # Normalize to 0-255
    img = np.clip(img, 0, 2)
    img = (img / 2 * 255).astype(np.uint8)

    # Convert to PIL, add text overlay, convert back
    pil = PILImage.fromarray(img, mode='L')
    draw = ImageDraw.Draw(pil)

    # Patient/study info overlay (top-left)
    draw.text((8, 6), "SAMSUNG MEDISON V6", fill=200)
    draw.text((8, 20), f"OBSTETRIC  {datetime.date.today().strftime('%d/%m/%Y')}", fill=180)
    if label:
        draw.text((8, height - 20), label, fill=220)

    # Depth markers (right side)
    for depth_pct in [0.25, 0.5, 0.75]:
        marker_y = int(cy + r_outer * depth_pct)
        if 0 <= marker_y < height:
            draw.text((width - 40, marker_y - 6),
                      f"{int(depth_pct * 18)} cm", fill=160)

    return np.array(pil)


# ── DICOM dataset creation ────────────────────────────────────────────────

def create_dicom_dataset(patient: dict, study_uid: str, series_uid: str,
                         instance_num: int, label: str, width=640, height=480) -> FileDataset:
    """Create a synthetic DICOM US image dataset."""

    sop_instance_uid = generate_uid()
    now = datetime.datetime.now()
    study_date = now.strftime("%Y%m%d")
    study_time = now.strftime("%H%M%S")

    # File meta
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = UID(US_IMAGE_SOP)
    file_meta.MediaStorageSOPInstanceUID = UID(sop_instance_uid)
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.ImplementationVersionName = "UTERUS_SIM_1.0"

    ds = FileDataset(
        filename_or_obj="",
        dataset={},
        file_meta=file_meta,
        is_implicit_VR=False,
        is_little_endian=True,
    )
    ds.is_implicit_VR = False
    ds.is_little_endian = True

    # Patient module
    ds.PatientName = patient["name"]
    ds.PatientID = patient["id"]
    ds.PatientSex = patient["sex"]
    ds.PatientBirthDate = patient["dob"]

    # General study
    ds.StudyInstanceUID = UID(study_uid)
    ds.StudyDate = study_date
    ds.StudyTime = study_time
    ds.StudyDescription = f"OBS US - {patient['ga_weeks']}W{patient['ga_days']}D"
    ds.AccessionNumber = f"ACC{random.randint(10000, 99999)}"

    # General series
    ds.SeriesInstanceUID = UID(series_uid)
    ds.SeriesNumber = 1
    ds.SeriesDescription = "2D GRAYSCALE"
    ds.Modality = "US"

    # SOP common
    ds.SOPClassUID = UID(US_IMAGE_SOP)
    ds.SOPInstanceUID = UID(sop_instance_uid)
    ds.InstanceNumber = instance_num
    ds.ContentDate = study_date
    ds.ContentTime = study_time

    # Image plane / pixel
    ds.Rows = height
    ds.Columns = width
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PlanarConfiguration = 0

    # Windowing
    ds.WindowCenter = 128
    ds.WindowWidth = 256

    # US-specific
    ds.ImageType = ["ORIGINAL", "PRIMARY", "2D"]
    ds.FrameTime = 33.0
    ds.FrameDelay = 0.0

    # Generate pixel data
    pixel_array = _draw_ultrasound_frame(width=width, height=height,
                                         label=label, frame_num=instance_num)
    ds.PixelData = pixel_array.tobytes()

    return ds


# ── C-STORE sender ────────────────────────────────────────────────────────

def send_study(patient: dict, num_images: int, host: str, port: int,
               calling_ae: str = "SIMULATOR", called_ae: str = "UTERUS_GLB",
               save_dir: str = None, save_only: bool = False) -> bool:
    """Create and send one study."""
    from pynetdicom import AE
    from pynetdicom.sop_class import UltrasoundImageStorage

    study_uid = generate_uid()
    series_uid = generate_uid()

    datasets = []
    labels = random.sample(VIEW_LABELS, min(num_images, len(VIEW_LABELS)))
    if num_images > len(VIEW_LABELS):
        labels += random.choices(VIEW_LABELS, k=num_images - len(VIEW_LABELS))

    print(f"\n  Patient : {patient['name'].replace('^', ' ')}")
    print(f"  ID      : {patient['id']}")
    print(f"  GA      : {patient['ga_weeks']}W {patient['ga_days']}D")
    print(f"  Images  : {num_images}")
    print(f"  Study   : {study_uid[:20]}...")

    for i in range(num_images):
        ds = create_dicom_dataset(
            patient=patient,
            study_uid=study_uid,
            series_uid=series_uid,
            instance_num=i + 1,
            label=labels[i],
        )
        datasets.append(ds)

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"{ds.SOPInstanceUID}.dcm")
            ds.save_as(path, write_like_original=False)
            print(f"  Saved   : {path}")

    if save_only:
        print(f"  [save-only mode, not sending via DICOM]")
        return True

    # Send via C-STORE
    ae = AE(ae_title=calling_ae)
    ae.add_requested_context(UltrasoundImageStorage)

    print(f"\n  Connecting to {host}:{port} (AE: {called_ae})...")

    try:
        assoc = ae.associate(host, port, ae_title=called_ae)
        if not assoc.is_established:
            print(f"  ERROR: Could not connect to {host}:{port}. Is the backend running?")
            return False

        print(f"  Connected. Sending {len(datasets)} images...")
        ok = 0
        for i, ds in enumerate(datasets):
            status = assoc.send_c_store(ds)
            if status and status.Status == 0x0000:
                ok += 1
                print(f"  [{i+1}/{len(datasets)}] Sent: {labels[i]}")
            else:
                code = status.Status if status else "no response"
                print(f"  [{i+1}/{len(datasets)}] FAILED (status=0x{code:04X}): {labels[i]}")
            time.sleep(0.05)  # small delay between images

        assoc.release()
        print(f"\n  Done: {ok}/{len(datasets)} images sent successfully")
        return ok == len(datasets)

    except Exception as e:
        print(f"  ERROR sending study: {e}")
        return False


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DICOM USG test simulator — send synthetic studies to the receiver"
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="DICOM receiver host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=11112,
                        help="DICOM receiver port (default: 11112)")
    parser.add_argument("--called-ae", default="UTERUS_GLB",
                        help="Called AE title (default: UTERUS_GLB)")
    parser.add_argument("--calling-ae", default="SIMULATOR",
                        help="Calling AE title (default: SIMULATOR)")
    parser.add_argument("--studies", type=int, default=1,
                        help="Number of studies to send (default: 1)")
    parser.add_argument("--images", type=int, default=5,
                        help="Images per study (default: 5)")
    parser.add_argument("--patient", type=int, default=None,
                        help="Patient index 0-4 (default: random)")
    parser.add_argument("--save-dir", default=None,
                        help="Also save .dcm files to this directory")
    parser.add_argument("--save-only", action="store_true",
                        help="Save files locally only, do not send via DICOM")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between studies (default: 1.0)")
    args = parser.parse_args()

    print("=" * 60)
    print("  USG DICOM Test Simulator")
    print("=" * 60)
    if not args.save_only:
        print(f"  Target  : {args.host}:{args.port}  AE={args.called_ae}")
    print(f"  Studies : {args.studies}  |  Images/study: {args.images}")
    print("=" * 60)

    success = 0
    for i in range(args.studies):
        print(f"\nStudy {i+1}/{args.studies}")
        idx = args.patient if args.patient is not None else random.randint(0, len(PATIENTS) - 1)
        patient = dict(PATIENTS[idx % len(PATIENTS)])
        # Randomize patient ID slightly for multiple studies
        if args.studies > 1 and args.patient is None:
            patient = dict(random.choice(PATIENTS))
            patient["id"] = f"PT{random.randint(100, 999)}"

        ok = send_study(
            patient=patient,
            num_images=args.images,
            host=args.host,
            port=args.port,
            calling_ae=args.calling_ae,
            called_ae=args.called_ae,
            save_dir=args.save_dir,
            save_only=args.save_only,
        )
        if ok:
            success += 1

        if i < args.studies - 1:
            print(f"\n  Waiting {args.delay}s before next study...")
            time.sleep(args.delay)

    print("\n" + "=" * 60)
    print(f"  Finished: {success}/{args.studies} studies sent")
    print("=" * 60)


if __name__ == "__main__":
    main()
