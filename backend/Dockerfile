FROM python:3.11-slim

WORKDIR /app

# Install system deps for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATA_DIR=/app/data \
    DICOM_AE_TITLE=UTERUS_GLB \
    DICOM_PORT=11112 \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000
EXPOSE 11112

CMD ["python", "main.py"]
