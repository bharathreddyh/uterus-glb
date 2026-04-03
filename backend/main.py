import os
import asyncio
import logging
import queue
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", "./data")
DICOM_AE_TITLE = os.environ.get("DICOM_AE_TITLE", "IHA_CARE")
DICOM_PORT = int(os.environ.get("DICOM_PORT", "11112"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "thumbnails"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "dicom"), exist_ok=True)

from dicom_store import DicomStore
from dicom_receiver import DICOMReceiver
from routes import studies, images, reports

# Global instances
store = DicomStore(DATA_DIR)
dicom_event_queue: queue.Queue = queue.Queue(maxsize=100)
receiver = DICOMReceiver(
    store=store,
    data_dir=DATA_DIR,
    ae_title=DICOM_AE_TITLE,
    port=DICOM_PORT,
    event_queue=dicom_event_queue,
)

# Asyncio queues for SSE clients
sse_clients: list[asyncio.Queue] = []


async def _poll_dicom_events():
    """Poll the thread-safe queue and forward to SSE clients."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Non-blocking check
            event = dicom_event_queue.get_nowait()
            for q in list(sse_clients):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        except queue.Empty:
            pass
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    store.init_db()
    receiver.start()
    task = asyncio.create_task(_poll_dicom_events())
    logger.info("Application started. DICOM port: %d", DICOM_PORT)
    yield
    # Shutdown
    task.cancel()
    receiver.stop()
    logger.info("Application stopped")


app = FastAPI(
    title="IHA Care — USG Typist",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Expose store and receiver to routes via app state
app.state.store = store
app.state.receiver = receiver

# Static files for thumbnails
thumbs_dir = os.path.join(DATA_DIR, "thumbnails")
app.mount("/thumbnails", StaticFiles(directory=thumbs_dir), name="thumbnails")

# Include routers
app.include_router(studies.router)
app.include_router(images.router)
app.include_router(reports.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "dicom_port": DICOM_PORT,
        "dicom_ae_title": DICOM_AE_TITLE,
        "dicom_receiver_running": receiver.is_running,
    }


@app.get("/events")
async def sse_events():
    """Server-Sent Events endpoint for real-time notifications."""
    client_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    sse_clients.append(client_queue)

    async def event_generator():
        try:
            # Send initial connected event
            yield "data: " + json.dumps({"type": "connected"}) + "\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                    yield "data: " + json.dumps(event) + "\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                sse_clients.remove(client_queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
