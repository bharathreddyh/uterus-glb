import os
import logging
import numpy as np
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["images"])


def _get_store(request: Request):
    return request.app.state.store


@router.get("/{uid}/dicom")
async def serve_dicom(uid: str, request: Request):
    """Serve raw DICOM file."""
    store = _get_store(request)
    image = store.get_image(uid)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = image["file_path"]
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="DICOM file not found on disk")

    return FileResponse(
        file_path,
        media_type="application/dicom",
        filename=f"{uid}.dcm",
        headers={"Content-Disposition": f'attachment; filename="{uid}.dcm"'},
    )


@router.get("/{uid}/jpeg")
async def serve_jpeg(uid: str, request: Request):
    """Serve JPEG thumbnail."""
    store = _get_store(request)
    image = store.get_image(uid)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    thumb_path = image.get("thumbnail_path", "")
    if thumb_path and os.path.isfile(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg")

    # Try to generate on-the-fly from DICOM
    file_path = image.get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="No thumbnail available")

    try:
        import pydicom
        from PIL import Image as PILImage
        from dicom_receiver import _generate_thumbnail

        data_dir = store.data_dir
        thumb_dir = os.path.join(data_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        new_thumb_path = os.path.join(thumb_dir, f"{uid}.jpg")

        ds = pydicom.dcmread(file_path)
        _generate_thumbnail(ds, new_thumb_path)

        if os.path.isfile(new_thumb_path):
            store.save_image({
                **image,
                "thumbnail_path": new_thumb_path,
            })
            return FileResponse(new_thumb_path, media_type="image/jpeg")
    except Exception as e:
        logger.warning("Could not generate thumbnail on-the-fly: %s", e)

    raise HTTPException(status_code=404, detail="Thumbnail not available")


@router.get("/{uid}/frames")
async def serve_frame(uid: str, request: Request, frame: int = 0):
    """Return JPEG of a specific frame from a DICOM file for the viewer."""
    store = _get_store(request)
    image = store.get_image(uid)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = image.get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="DICOM file not found on disk")

    try:
        import pydicom
        from PIL import Image as PILImage

        ds = pydicom.dcmread(file_path)
        if not hasattr(ds, "PixelData"):
            raise HTTPException(status_code=422, detail="DICOM has no pixel data")

        pixel_array = ds.pixel_array

        # Select frame
        if pixel_array.ndim == 3 and getattr(ds, "SamplesPerPixel", 1) == 1:
            # Multi-frame grayscale: (frames, rows, cols)
            total_frames = pixel_array.shape[0]
            frame_idx = min(frame, total_frames - 1)
            pixel_array = pixel_array[frame_idx]
        elif pixel_array.ndim == 4:
            # Multi-frame color: (frames, rows, cols, channels)
            total_frames = pixel_array.shape[0]
            frame_idx = min(frame, total_frames - 1)
            pixel_array = pixel_array[frame_idx]
        # else: single frame 2D or 3D RGB

        # Convert to displayable image
        if pixel_array.ndim == 2:
            if hasattr(ds, "WindowCenter") and hasattr(ds, "WindowWidth"):
                wc = float(ds.WindowCenter) if not hasattr(ds.WindowCenter, "__iter__") else float(ds.WindowCenter[0])
                ww = float(ds.WindowWidth) if not hasattr(ds.WindowWidth, "__iter__") else float(ds.WindowWidth[0])
                lo = wc - ww / 2
                hi = wc + ww / 2
            else:
                lo = float(pixel_array.min())
                hi = float(pixel_array.max())

            slope = float(getattr(ds, "RescaleSlope", 1) or 1)
            intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
            pixel_float = pixel_array.astype(np.float64) * slope + intercept

            if hi == lo:
                hi = lo + 1
            pixel_float = np.clip((pixel_float - lo) / (hi - lo) * 255, 0, 255)
            img_array = pixel_float.astype(np.uint8)

            photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))
            if "MONOCHROME1" in photometric:
                img_array = 255 - img_array

            pil_img = PILImage.fromarray(img_array, mode="L").convert("RGB")
        else:
            if pixel_array.dtype != np.uint8:
                pmax = pixel_array.max()
                if pmax > 0:
                    pixel_array = (pixel_array / pmax * 255).astype(np.uint8)
                else:
                    pixel_array = pixel_array.astype(np.uint8)
            pil_img = PILImage.fromarray(pixel_array)

        buf = BytesIO()
        pil_img.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/jpeg")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to render frame %d for %s: %s", frame, uid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to render frame: {e}")
