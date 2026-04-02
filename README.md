# Uterus GLB — USG Typist

A complete DICOM receiver and obstetric ultrasound reporting web application.

## Features

- Built-in DICOM SCP (Service Class Provider) — receives images directly from ultrasound machines via DICOM protocol
- DICOM image viewer with windowing, navigation, and metadata overlay
- Obstetric measurement form with auto-calculated EFW (Hadlock formula) and GA estimation
- PDF report generation with professional layout
- Real-time notifications via Server-Sent Events when new studies arrive
- SQLite storage — no external database required

---

## 1. Samsung V6 DICOM Configuration

On the Samsung V6 ultrasound machine, configure the DICOM Store destination:

| Setting | Value |
|---------|-------|
| AE Title (Remote) | `UTERUS_GLB` |
| Remote IP | `<PC_IP_ADDRESS>` (see §2) |
| Remote Port | `11112` |
| Transfer Syntax | Explicit VR Little Endian |

Steps on the Samsung V6:
1. Go to **Setup → DICOM → Storage SCU**
2. Add a new DICOM destination
3. Enter the IP address of the PC running this application
4. Set Port to `11112` and AE Title to `UTERUS_GLB`
5. Run a **C-ECHO (Ping)** test to verify connectivity before sending images

---

## 2. PC Network Setup

For reliable DICOM connectivity, assign a **static IP** to the PC:

### Windows
1. Open **Network & Internet Settings → Ethernet → Edit**
2. Set Manual / Static
3. Example: IP `192.168.1.100`, Subnet `255.255.255.0`, Gateway `192.168.1.1`

### Linux (netplan example)
```yaml
network:
  ethernets:
    eth0:
      addresses: [192.168.1.100/24]
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8]
  version: 2
```

**Firewall**: Open TCP port `11112` and TCP port `8000` (or `5173` if using Vite dev server).

```bash
# Ubuntu/Debian
sudo ufw allow 11112/tcp
sudo ufw allow 8000/tcp

# Windows — run as Administrator
netsh advfirewall firewall add rule name="DICOM" dir=in action=allow protocol=TCP localport=11112
```

---

## 3. Running with Docker Compose (Recommended)

```bash
# Clone / navigate to project
cd /path/to/uterus-glb

# Build and start all services
docker compose up -d --build

# Check logs
docker compose logs -f backend

# Stop
docker compose down
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- DICOM SCP: port 11112

DICOM files and the SQLite database are stored in `./data/` (bind-mounted).

---

## 4. Running Manually

### Backend (Python 3.11+)

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure (copy and edit)
cp .env.example .env
# Edit DATA_DIR, DICOM_PORT etc. as needed

# Run
python main.py
```

The backend starts on http://0.0.0.0:8000 and the DICOM SCP on port 11112.

### Frontend (Node 18+)

```bash
cd frontend

# Install dependencies
npm install

# Start Vite dev server (proxies API to localhost:8000)
npm run dev
```

Open http://localhost:5173

---

## 5. Usage Workflow

1. **Configure the ultrasound machine** (see §1) with the PC's static IP and port 11112
2. **Start the application** (Docker or manual)
3. **Perform a scan** on the Samsung V6 — at end of study, send images via DICOM
4. Images appear in the sidebar with a **NEW** badge within seconds
5. **Click a study** to open the DICOM viewer
6. Switch to the **Report / Measurements** tab
7. Enter fetal biometry measurements — EFW and GA auto-calculate
8. Fill in placenta location, presentation, AFI, FHR, impression, and advice
9. Click **Save Report**
10. Click **Download PDF** to generate and download the formatted report

---

## 6. Troubleshooting

### No images appearing after sending from machine

- Verify the PC's IP and port 11112 are correct on the machine
- Check the firewall allows TCP 11112 inbound
- Look at backend logs: `docker compose logs backend`
- Run C-ECHO ping from the machine — if it fails, it's a network issue

### "DICOM SCP offline" shown in sidebar

- The backend may have failed to bind port 11112 (port in use by another service)
- Check: `netstat -tlnp | grep 11112` (Linux) or `netstat -an | findstr 11112` (Windows)
- Change `DICOM_PORT` in `.env` if needed

### Thumbnails not generating

- Ensure the backend has write access to `./data/thumbnails/`
- Some compressed DICOM transfer syntaxes require additional decompression libraries
- Check backend logs for "Failed to generate thumbnail" messages

### PDF download not working

- The report must be **saved** before PDF generation
- Check browser console for JavaScript errors
- Ensure `jspdf` and `jspdf-autotable` are installed: `npm install` in `frontend/`

### Port conflicts

Change ports in `docker-compose.yml` or `.env`:
```yaml
# docker-compose.yml
ports:
  - "8001:8000"   # Change host port from 8000 to 8001
  - "11113:11112" # Change DICOM port
```

### Database corruption

```bash
# Backup and reset
cp ./data/uterus.db ./data/uterus.db.bak
rm ./data/uterus.db
# Restart app — it will recreate the DB (DICOM files are preserved)
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + DICOM status |
| GET | `/studies` | List all studies |
| GET | `/studies/{uid}` | Study detail + images |
| DELETE | `/studies/{uid}` | Delete study + files |
| GET | `/images/{uid}/dicom` | Raw DICOM file download |
| GET | `/images/{uid}/jpeg` | JPEG thumbnail |
| GET | `/images/{uid}/frames?frame=0` | Rendered frame as JPEG |
| GET | `/reports/{study_uid}` | Get report |
| POST | `/reports/{study_uid}` | Create report |
| PUT | `/reports/{study_uid}` | Update report |
| GET | `/reports/{study_uid}/pdf-data` | Data for PDF generation |
| GET | `/events` | SSE stream for new-study notifications |

---

## Directory Structure

```
uterus-glb/
├── backend/
│   ├── main.py              # FastAPI app, startup/shutdown, SSE
│   ├── dicom_receiver.py    # pynetdicom SCP, thumbnail generation
│   ├── dicom_store.py       # SQLite data access layer
│   ├── models.py            # Pydantic models
│   ├── routes/
│   │   ├── studies.py
│   │   ├── images.py
│   │   └── reports.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main layout + SSE client
│   │   ├── api.js           # API helper functions
│   │   ├── components/
│   │   │   ├── StudyList.jsx
│   │   │   ├── DicomViewer.jsx
│   │   │   ├── MeasurementForm.jsx
│   │   │   └── ReportPDF.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
├── data/                    # Runtime data (gitignored)
│   ├── uterus.db
│   ├── dicom/
│   └── thumbnails/
└── docker-compose.yml
```
