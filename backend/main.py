"""
main.py
────────
FastAPI server for Trip Photo Finder.

Endpoints:
  POST /selfie                        Upload selfie(s) with person name
  GET  /selfies                       List currently loaded persons
  DELETE /selfies                     Clear all loaded persons
  GET  /drive/folders                 List Google Drive folders
  GET  /drive/folders/{id}/images     List images in a folder
  GET  /scan/{folder_id}              Scan folder — SSE streaming
  POST /drive/save                    Save matched photos to a Drive folder
  GET  /cache/stats                   Cache stats
  DELETE /cache                       Clear cache
"""

import os
import json
import asyncio
import logging
import numpy as np
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from face_engine import FaceEngine, SUPPORTED_FORMATS
from drive_client import DriveClient
from cache import EmbeddingCache

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Trip Photo Finder", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    app.state.face_engine = FaceEngine()
    app.state.drive_client = DriveClient()
    app.state.cache = EmbeddingCache()
    # Dict of {person_name: np.ndarray(512,)}
    app.state.persons = {}
    logger.info("All services ready.")

# ── Helpers ────────────────────────────────────────────────────────────────────

def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def get_engine()  -> FaceEngine:      return app.state.face_engine
def get_drive()   -> DriveClient:     return app.state.drive_client
def get_cache()   -> EmbeddingCache:  return app.state.cache
def get_persons() -> dict:            return app.state.persons

THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.4"))

def confidence_label(score: float) -> str:
    if score >= THRESHOLD + 0.15: return "high"
    if score >= THRESHOLD:        return "medium"
    return "low"

def drive_file_signature(image: dict) -> str:
    """Stable cache key from Drive metadata, before downloading bytes."""
    return f"{image.get('modifiedTime', '')}:{image.get('size', '')}"

def match_persons(embeddings: list[np.ndarray], persons: dict) -> list[dict]:
    persons_matched = []

    for person_name, selfie_emb in persons.items():
        best_score = -1.0
        for emb in embeddings:
            score = float(np.dot(selfie_emb, emb))
            if score > best_score:
                best_score = score

        if best_score >= THRESHOLD:
            persons_matched.append({
                "name":              person_name,
                "confidence":        round(best_score, 4),
                "confidence_label":  confidence_label(best_score),
            })

    return persons_matched

# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "Trip Photo Finder", "version": "2.0.0"}

# ── Selfie endpoints ───────────────────────────────────────────────────────────

@app.post("/selfie")
async def upload_selfie(
    file: UploadFile = File(...),
    name: str = Form(default="Person 1"),
):
    """
    Upload a selfie for one person.
    Call twice (with different names) to scan for two people.

    Form fields:
      file  — image file
      name  — person's name (e.g. "Rahul", "Priya")
    """
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext and ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    image_bytes = await file.read()

    try:
        embedding = get_engine().get_selfie_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Store under person's name — overwrites if same name uploaded again
    app.state.persons[name] = embedding
    logger.info(f"Selfie stored for: '{name}'. Total persons: {len(app.state.persons)}")

    return {
        "ok": True,
        "name": name,
        "message": f"Selfie processed for {name}.",
        "total_persons": len(app.state.persons),
        "persons": list(app.state.persons.keys()),
    }


@app.get("/selfies")
def list_selfies():
    """List all currently loaded persons."""
    return {
        "persons": list(get_persons().keys()),
        "count": len(get_persons()),
    }


@app.delete("/selfies")
def clear_selfies():
    """Clear all loaded persons."""
    app.state.persons = {}
    return {"ok": True, "message": "All persons cleared."}


@app.delete("/selfie/{name}")
def remove_selfie(name: str):
    """Remove a specific person by name."""
    if name not in app.state.persons:
        raise HTTPException(status_code=404, detail=f"Person '{name}' not found.")
    del app.state.persons[name]
    return {
        "ok": True,
        "message": f"Removed '{name}'.",
        "persons": list(app.state.persons.keys()),
    }

# ── Drive read endpoints ───────────────────────────────────────────────────────

@app.get("/drive/folders")
def list_folders():
    try:
        folders = get_drive().list_folders()
        return {"folders": folders}
    except Exception as e:
        logger.error(f"Drive folder list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drive/folders/{folder_id}/images")
def list_images(folder_id: str):
    try:
        images      = get_drive().list_images(folder_id)
        folder_name = get_drive().get_folder_name(folder_id)
        return {
            "folder_id":   folder_id,
            "folder_name": folder_name,
            "images":      images,
            "count":       len(images),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Scan endpoint (SSE) ────────────────────────────────────────────────────────

@app.get("/scan/{folder_id}")
async def scan_folder(folder_id: str):
    """
    Scan all images in a Drive folder for ALL uploaded persons.

    SSE event types:
      start    — {type, total, folder_name, persons: [name, ...]}
      progress — {type, index, total, file_id, name, persons_matched: [{name, confidence, confidence_label}], faces_detected, cached}
      done     — {type, total, matched_by_person: {name: count}, skipped}
      error    — {type, message}
    """
    persons = get_persons()
    if not persons:
        raise HTTPException(
            status_code=400,
            detail="No selfies uploaded yet. POST to /selfie first."
        )

    engine = get_engine()
    drive  = get_drive()
    cache  = get_cache()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            images      = drive.list_images(folder_id)
            folder_name = drive.get_folder_name(folder_id)
            total       = len(images)

            yield sse_event({
                "type":        "start",
                "total":       total,
                "folder_name": folder_name,
                "persons":     list(persons.keys()),
            })

            if total == 0:
                yield sse_event({
                    "type": "done", "total": 0,
                    "matched_by_person": {n: 0 for n in persons},
                    "skipped": 0,
                })
                return

            # Track match counts per person
            matched_by_person = {name: 0 for name in persons}
            skipped = 0

            for index, image in enumerate(images):
                file_id   = image["id"]
                file_name = image["name"]
                file_signature = drive_file_signature(image)

                try:
                    cached_embeddings = cache.get_by_signature(file_id, file_signature)
                    metadata_cached = cached_embeddings is not None
                    was_cached = metadata_cached
                    retried = False
                    image_bytes = None

                    if cached_embeddings is None:
                        image_bytes = await asyncio.to_thread(drive.download_image, file_id)
                        cached_embeddings = cache.get(file_id, image_bytes)
                        was_cached = cached_embeddings is not None

                    if cached_embeddings is None:
                        cached_embeddings = await asyncio.to_thread(
                            engine.get_all_embeddings, image_bytes
                        )
                        persons_matched = match_persons(cached_embeddings, persons)

                        if not persons_matched:
                            retry_embeddings = await asyncio.to_thread(
                                engine.get_all_embeddings, image_bytes, True
                            )
                            retry_matches = match_persons(retry_embeddings, persons)
                            if retry_matches or len(retry_embeddings) > len(cached_embeddings):
                                cached_embeddings = retry_embeddings
                                persons_matched = retry_matches
                                retried = True

                        cache.set(
                            file_id,
                            image_bytes,
                            cached_embeddings,
                            file_signature=file_signature,
                        )
                    else:
                        persons_matched = match_persons(cached_embeddings, persons)
                        if not metadata_cached and not persons_matched:
                            retry_embeddings = await asyncio.to_thread(
                                engine.get_all_embeddings, image_bytes, True
                            )
                            retry_matches = match_persons(retry_embeddings, persons)
                            if retry_matches or len(retry_embeddings) > len(cached_embeddings):
                                cached_embeddings = retry_embeddings
                                persons_matched = retry_matches
                                retried = True
                            cache.set(
                                file_id,
                                image_bytes,
                                cached_embeddings,
                                file_signature=file_signature,
                            )

                    for person in persons_matched:
                        matched_by_person[person["name"]] += 1

                    yield sse_event({
                        "type":             "progress",
                        "index":            index + 1,
                        "total":            total,
                        "file_id":          file_id,
                        "name":             file_name,
                        "persons_matched":  persons_matched,
                        "any_match":        len(persons_matched) > 0,
                        "both_match":       len(persons_matched) == len(persons) and len(persons) > 1,
                        "faces_detected":   len(cached_embeddings),
                        "cached":           was_cached,
                        "retried":          retried,
                    })

                except Exception as e:
                    skipped += 1
                    logger.warning(f"Skipped {file_name}: {e}")
                    yield sse_event({
                        "type":            "progress",
                        "index":           index + 1,
                        "total":           total,
                        "file_id":         file_id,
                        "name":            file_name,
                        "persons_matched": [],
                        "any_match":       False,
                        "both_match":      False,
                        "skipped":         True,
                        "error":           str(e),
                    })

                await asyncio.sleep(0)

            yield sse_event({
                "type":              "done",
                "total":             total,
                "matched_by_person": matched_by_person,
                "skipped":           skipped,
            })

        except Exception as e:
            logger.error(f"Scan error: {e}")
            yield sse_event({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

# ── Save to Drive ──────────────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    file_ids:    list[str]
    folder_name: str
    parent_id:   str | None = None   # optional parent folder


@app.post("/drive/save")
async def save_to_drive(req: SaveRequest):
    """
    Copy matched photos into a Drive folder (new or existing).

    Body:
      file_ids    — list of Drive file IDs to copy
      folder_name — name of destination folder
      parent_id   — optional parent folder ID (defaults to Drive root)

    Returns:
      {ok, folder_id, folder_name, created, copied, failed}
    """
    if not req.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided.")
    if not req.folder_name.strip():
        raise HTTPException(status_code=400, detail="folder_name cannot be empty.")

    drive = get_drive()

    try:
        # Get or create the destination folder
        folder = await asyncio.to_thread(
            drive.get_or_create_folder,
            req.folder_name.strip(),
            req.parent_id,
        )

        # Copy all matched files into it
        result = await asyncio.to_thread(
            drive.bulk_copy_to_folder,
            req.file_ids,
            folder["id"],
        )

        return {
            "ok":          True,
            "folder_id":   folder["id"],
            "folder_name": folder["name"],
            "created":     folder["created"],
            "copied":      result["copied"],
            "failed":      result["failed"],
        }

    except Exception as e:
        logger.error(f"Save to Drive failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Cache ──────────────────────────────────────────────────────────────────────

@app.get("/cache/stats")
def cache_stats():
    return get_cache().stats()

@app.delete("/cache")
def clear_cache():
    get_cache().clear()
    return {"ok": True, "message": "Cache cleared."}

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
