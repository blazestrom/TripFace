"""
face_engine.py
──────────────
Wraps InsightFace buffalo_l model.
Responsibilities:
  - Load the model once at startup (expensive, ~2-3 seconds)
  - Extract a 512-dim face embedding from a selfie image
  - Detect ALL faces in a group photo and extract their embeddings
  - Compare embeddings using cosine similarity to find matches

Usage:
    engine = FaceEngine()
    selfie_emb  = engine.get_selfie_embedding("selfie.jpg")
    result      = engine.find_person_in_photo("group.jpg", selfie_emb)
"""

import os
import logging
from pathlib import Path
from typing import Optional

import io
from threading import Lock
import cv2
import numpy as np
from numpy.linalg import norm
from PIL import Image, ImageOps
import pillow_heif
from insightface.app import FaceAnalysis

# Register HEIC/HEIF support into Pillow (iPhone photos)
pillow_heif.register_heif_opener()

# All supported extensions — shown to users in error messages
SUPPORTED_FORMATS = {
    ".jpg", ".jpeg",          # standard JPEG
    ".png",                   # PNG
    ".webp",                  # WebP (Android, modern cameras)
    ".heic", ".heif",         # iPhone / iOS photos
    ".bmp",                   # Bitmap
    ".tiff", ".tif",          # TIFF (DSLRs, scanners)
    ".gif",                   # GIF (first frame only)
    ".avif",                  # AVIF (modern web format)
}

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

# Cosine similarity threshold.
# >= MATCH_THRESHOLD  →  same person
# ArcFace paper uses 0.40; you can raise to 0.45 if you get false positives.
DEFAULT_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.4"))

# InsightFace model name — buffalo_l is the most accurate CPU model
MODEL_NAME = os.getenv("INSIGHTFACE_MODEL", "buffalo_l")

# Detection image size — 640x640 is the recommended size for buffalo_l.
# Use (320, 320) if you need faster scans and can accept slightly lower accuracy.
DET_SIZE = (640, 640)
RETRY_DET_SIZE = tuple(
    int(v.strip())
    for v in os.getenv("RETRY_DET_SIZE", "960,960").split(",", 1)
)


# ── FaceEngine class ──────────────────────────────────────────────────────────

class FaceEngine:
    """
    Singleton-style wrapper around InsightFace FaceAnalysis.
    Instantiate once and reuse across requests.
    """

    def __init__(self):
        logger.info(f"Loading InsightFace model: {MODEL_NAME} ...")
        self._app = FaceAnalysis(
            name=MODEL_NAME,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            # InsightFace automatically falls back to CPU if CUDA is unavailable
        )
        self._app.prepare(ctx_id=0, det_size=DET_SIZE)
        self._det_size = DET_SIZE
        self._lock = Lock()
        logger.info(f"InsightFace providers: {self._app.models['recognition'].session.get_providers()}")
        logger.info("InsightFace model loaded successfully.")


    # ── Public API ────────────────────────────────────────────────────────────

    def get_selfie_embedding(self, image_source) -> np.ndarray:
        """
        Extract a face embedding from a selfie.

        Args:
            image_source: File path (str/Path) or raw image bytes.

        Returns:
            numpy array of shape (512,) — the face embedding.

        Raises:
            ValueError: If no face is detected or image cannot be read.
        """
        img = self._load_image(image_source)
        faces = self._get_faces(img)

        if not faces:
            raise ValueError(
                "No face detected in the selfie. "
                "Please use a clear, front-facing photo with good lighting."
            )

        if len(faces) > 1:
            logger.warning(
                f"Multiple faces ({len(faces)}) found in selfie. "
                "Using the largest/most prominent face."
            )

        # Pick the face with the largest bounding box (most prominent face)
        best_face = max(faces, key=lambda f: _bbox_area(f.bbox))
        embedding = best_face.embedding

        # Normalise to unit vector — required for cosine similarity
        return embedding / norm(embedding)


    def find_person_in_photo(
        self,
        image_source,
        selfie_embedding: np.ndarray,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> dict:
        """
        Check if the person from the selfie appears in a given photo.

        Args:
            image_source:     File path or raw image bytes of the photo to check.
            selfie_embedding: Normalised embedding from get_selfie_embedding().
            threshold:        Cosine similarity cutoff (default 0.4).

        Returns:
            dict with keys:
              - match (bool):        True if person was found
              - confidence (float):  Best cosine similarity score (0.0 – 1.0)
              - confidence_label (str): "high" / "medium" / "low"
              - faces_detected (int): Total faces found in the photo
              - best_face_index (int | None): Index of the matching face
        """
        img = self._load_image(image_source)
        faces = self._get_faces(img)

        if not faces:
            return _no_match_result(faces_detected=0, reason="no_faces")

        best_score = -1.0
        best_index = None

        for i, face in enumerate(faces):
            emb = face.embedding / norm(face.embedding)  # normalise
            score = float(np.dot(selfie_embedding, emb))  # cosine similarity
            if score > best_score:
                best_score = score
                best_index = i

        matched = best_score >= threshold

        return {
            "match": matched,
            "confidence": round(best_score, 4),
            "confidence_label": _confidence_label(best_score, threshold),
            "faces_detected": len(faces),
            "best_face_index": best_index if matched else None,
        }


    def get_all_embeddings(self, image_source, retry: bool = False) -> list[np.ndarray]:
        """
        Extract embeddings for ALL faces in a photo.
        Useful for pre-caching group photos.

        Returns:
            List of normalised (512,) numpy arrays — one per detected face.
            Empty list if no faces detected.
        """
        img = self._load_image(image_source)
        det_size = RETRY_DET_SIZE if retry else DET_SIZE
        faces = self._get_faces(img, det_size=det_size)
        if not faces:
            return []
        return [face.embedding / norm(face.embedding) for face in faces]


    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_image(self, source) -> np.ndarray:
        """
        Load an image into a cv2 BGR numpy array.

        Supports:
          - File path (str / Path) for any format below
          - Raw bytes (from Drive download, upload endpoint, etc.)
          - numpy array (already decoded)

        Supported formats:
          JPEG, PNG, WebP, HEIC/HEIF (iPhone), BMP, TIFF, GIF, AVIF

        Strategy:
          1. Try cv2 directly — handles JPEG, PNG, BMP, WebP, TIFF natively
          2. Fall back to Pillow — handles HEIC, AVIF, GIF, and anything
             cv2 missed (Pillow result is converted to BGR for InsightFace)
        """
        if isinstance(source, np.ndarray):
            return source

        # ── Get raw bytes ──────────────────────────────────────────────────
        if isinstance(source, (str, Path)):
            path = Path(source)
            ext = path.suffix.lower()
            if ext and ext not in SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported file format: '{ext}'. "
                    f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
                )
            raw_bytes = path.read_bytes()
        elif isinstance(source, bytes):
            raw_bytes = source
            ext = None
        else:
            raise TypeError(f"Unsupported image source type: {type(source)}")

        # Pillow respects EXIF orientation, which matters for phone photos.
        try:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            pil_img = ImageOps.exif_transpose(pil_img)
            if getattr(pil_img, "is_animated", False):
                pil_img.seek(0)
            pil_img = pil_img.convert("RGB")
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception:
            pass

        # ── Strategy 1: Try cv2 (fastest, handles most formats) ───────────
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            return img

        # ── Strategy 2: Pillow fallback (HEIC, AVIF, GIF, edge cases) ─────
        try:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            pil_img = ImageOps.exif_transpose(pil_img)

            # For animated GIFs — use only the first frame
            if getattr(pil_img, "is_animated", False):
                pil_img.seek(0)

            # Convert to RGB first (handles palette, RGBA, grayscale, etc.)
            pil_img = pil_img.convert("RGB")

            # Pillow gives RGB — cv2/InsightFace expects BGR
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return img

        except Exception as e:
            raise ValueError(
                f"Could not decode image. "
                f"Tried cv2 and Pillow — both failed.\n"
                f"Pillow error: {e}\n"
                f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )


    def _get_faces(self, img: np.ndarray, det_size: tuple[int, int] = DET_SIZE):
        """Run InsightFace detection with the requested detector size."""
        with self._lock:
            if det_size != self._det_size:
                self._app.prepare(ctx_id=0, det_size=det_size)
                self._det_size = det_size
            return self._app.get(img)


# ── Module-level helpers ──────────────────────────────────────────────────────
def _bbox_area(bbox) -> float:
    """Return area of a face bounding box [x1, y1, x2, y2]."""
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _confidence_label(score: float, threshold: float) -> str:
    """Convert a cosine similarity score to a human-readable label."""
    if score >= threshold + 0.15:
        return "high"
    elif score >= threshold:
        return "medium"
    else:
        return "low"


def _no_match_result(faces_detected: int, reason: str = "") -> dict:
    return {
        "match": False,
        "confidence": 0.0,
        "confidence_label": "low",
        "faces_detected": faces_detected,
        "best_face_index": None,
        "reason": reason,
    }
