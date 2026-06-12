from __future__ import annotations

from functools import lru_cache

import numpy as np
from insightface.app import FaceAnalysis


@lru_cache(maxsize=1)
def _face_app() -> FaceAnalysis:
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def _normalize(embedding: np.ndarray) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def _face_area(face) -> float:
    x1, y1, x2, y2 = face.bbox
    return float(max(0, x2 - x1) * max(0, y2 - y1))


def get_face_embedding(image: np.ndarray) -> np.ndarray | None:
    faces = _face_app().get(image)
    if not faces:
        return None

    largest_face = max(faces, key=_face_area)
    return _normalize(largest_face.embedding)


def get_all_face_embeddings(image: np.ndarray) -> list[np.ndarray]:
    faces = _face_app().get(image)
    return [_normalize(face.embedding) for face in faces]


def match_faces(
    selfie_embedding: np.ndarray,
    photo_embedding: np.ndarray,
    threshold: float = 0.4,
) -> tuple[bool, float]:
    selfie = _normalize(selfie_embedding)
    photo = _normalize(photo_embedding)
    similarity = float(np.dot(selfie, photo))
    return similarity >= threshold, similarity
