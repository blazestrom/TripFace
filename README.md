# TripFace 🔍

> Find yourself in every group photo — automatically.

TripFace scans a Google Drive folder and identifies every photo you appear in using local AI face recognition. No cloud AI, no data sharing — everything runs on your machine.

---

## Demo

**Upload a selfie → Pick a Drive folder → Get every photo you're in**

```
732 photos scanned · 15 matched · 4 photos/sec
```

---

## Features

- 🎯 **Face recognition** — InsightFace buffalo_l (ArcFace + RetinaFace) with 512-dim embeddings
- ⚡ **Parallel scanning** — processes 4 photos simultaneously (~4x faster than sequential)
- 👥 **Multi-person** — scan for up to 2 people at once, detect photos where both appear
- 📁 **Google Drive** — reads folders, streams results live, saves matched photos back to Drive
- 🧠 **Smart cache** — SQLite embedding cache, rescans take seconds not minutes
- 📡 **Live progress** — results stream to browser in real time via Server-Sent Events
- 📷 **3 capture modes** — webcam live capture, mobile front camera, or gallery upload
- 💾 **Save to Drive** — copy matched photos into a new or existing Drive folder instantly
- 🔒 **100% local** — photos and face data never leave your machine

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Face AI | InsightFace 0.7.3 (buffalo_l), ONNX Runtime |
| Image processing | OpenCV, Pillow, pillow-heif |
| Drive integration | Google Drive API v3, OAuth2 |
| Cache | SQLite (via Python sqlite3) |
| Streaming | Server-Sent Events (SSE) |
| Frontend | React 18, Vite, Axios |

---

## Project Structure

```
trip-photo-finder/
├── backend/
│   ├── main.py              # FastAPI server + all endpoints
│   ├── face_engine.py       # InsightFace wrapper (detect + match)
│   ├── drive_client.py      # Google Drive API integration
│   ├── cache.py             # SQLite embedding cache
│   ├── requirements.txt
│   ├── credentials.json     # ← your Google OAuth file (not committed)
│   └── .env
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── SelfieUpload.jsx   # Webcam / camera / gallery capture
            ├── FolderPicker.jsx   # Drive folder selection
            ├── ScanProgress.jsx   # Live scan with SSE
            └── ResultsGrid.jsx    # Results + Save to Drive
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- A Google account with photos in Google Drive

---

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/trip-photo-finder.git
cd trip-photo-finder
```

---

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate — Windows
venv\Scripts\activate

# Activate — Mac/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### 3. Google Drive API setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project
3. Enable the **Google Drive API**
4. Go to **APIs & Services → OAuth consent screen** → External → fill in app name
5. Add scope: `https://www.googleapis.com/auth/drive`
6. Add your Gmail as a test user
7. Go to **Credentials → Create OAuth client ID → Desktop app**
8. Download the JSON → rename to `credentials.json` → place in `backend/`

Then run the one-time login:

```bash
cd backend
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = ['https://www.googleapis.com/auth/drive']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)
open('token.json', 'w').write(creds.to_json())
print('Done.')
"
```

---

### 4. Environment configuration

Create a `.env` file in `backend/`:

```env
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
INSIGHTFACE_MODEL=buffalo_l
MATCH_THRESHOLD=0.4
SCAN_WORKERS=4
HOST=127.0.0.1
PORT=8000
```

> **MATCH_THRESHOLD** — cosine similarity cutoff for face match (0.1–0.9). Lower = more lenient, higher = stricter. Default 0.4 works well for most photos.
>
> **SCAN_WORKERS** — number of photos processed in parallel. Default 4. Increase if you have a fast CPU and internet connection.

---

### 5. Start the backend

```bash
cd backend
uvicorn main:app --reload
```

First run downloads the InsightFace `buffalo_l` model (~500 MB). This only happens once.

---

### 6. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## How It Works

### Face matching pipeline

```
Selfie upload
    ↓
InsightFace extracts 512-dim ArcFace embedding
    ↓
For each photo in Drive folder:
    Download image bytes
    Check SQLite cache (skip if already processed)
    InsightFace detects all faces → extract embeddings
    Cosine similarity vs selfie embedding
    If similarity ≥ threshold → MATCH
    Store embeddings in cache
    ↓
Stream result to browser via SSE
```

### Why cosine similarity?

ArcFace embeddings are unit-normalised vectors. Cosine similarity between two face embeddings measures how "alike" two faces are on a scale of -1 to 1. A threshold of 0.4 means the faces must be at least 40% similar to count as a match — this eliminates most false positives while catching genuine matches even with glasses, different lighting, or slight angle changes.

### Why local and not a cloud API?

Trip photos are personal. Using a cloud face recognition API means sending every photo to a third-party server. InsightFace runs entirely on your machine — photos never leave your local network.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/selfie` | Upload selfie with person name |
| `GET` | `/selfies` | List loaded persons |
| `DELETE` | `/selfies` | Clear all persons |
| `GET` | `/drive/folders` | List Drive folders |
| `GET` | `/drive/folders/{id}/images` | List images in folder |
| `GET` | `/scan/{folder_id}` | Start scan (SSE stream) |
| `GET` | `/drive/thumbnail/{file_id}` | Get photo thumbnail |
| `POST` | `/drive/save` | Save matched photos to Drive folder |
| `GET` | `/settings` | Get current settings |
| `POST` | `/settings` | Update threshold / workers |
| `GET` | `/cache/stats` | Embedding cache statistics |
| `DELETE` | `/cache` | Clear embedding cache |

---

## Performance

| Folder size | First scan | Rescan (cached) |
|---|---|---|
| 100 photos | ~1.5 min | ~5 sec |
| 500 photos | ~7 min | ~20 sec |
| 1000 photos | ~14 min | ~40 sec |

*Tested on Intel Core i7, 16GB RAM, 50 Mbps internet, SCAN_WORKERS=4*

> Speed improves significantly with a GPU — change `onnxruntime` to `onnxruntime-gpu` in requirements.txt and set `ctx_id=0` in face_engine.py.

---

## Supported Image Formats

`.jpg` `.jpeg` `.png` `.webp` `.heic` `.heif` `.bmp` `.tiff` `.tif` `.gif` `.avif`

HEIC/HEIF (iPhone photos) are supported via `pillow-heif`.

---

## Known Limitations

- Detection accuracy drops on very small faces (far from camera) or heavily obscured faces
- Works best with a clear, front-facing selfie with good lighting
- Google OAuth app stays in "Testing" mode unless submitted for verification — only added test users can log in
- Parallel scanning uses more RAM — reduce `SCAN_WORKERS` if you run out of memory

---

## Roadmap

- [ ] GPU acceleration support
- [ ] Adjustable threshold slider in UI
- [ ] Download all matched photos as ZIP
- [ ] Mobile-optimised layout
- [ ] Support for shared Drive folders

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Built with InsightFace, FastAPI, and React.
