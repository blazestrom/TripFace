"""
cache.py
────────
SQLite-backed cache for face embeddings.

Why this matters:
  A 200-photo folder takes ~3 minutes to scan.
  Without cache, every scan takes 3 minutes.
  With cache, second scan of the same folder takes ~5 seconds —
  only new or changed photos are re-processed.

Cache key: Google Drive file ID + MD5 of the file (detects edits).
Cache value: JSON-serialised list of 512-dim face embeddings.

Schema:
  embeddings table:
    file_id     TEXT  — Google Drive file ID
    file_hash   TEXT  — MD5 hash of file bytes (detects if photo was edited)
    embeddings  TEXT  — JSON array of float arrays
    face_count  INT   — how many faces were found
    created_at  TEXT  — ISO timestamp
"""

import json
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "embeddings_cache.db"


# ── EmbeddingCache class ──────────────────────────────────────────────────────

class EmbeddingCache:
    """
    Persistent SQLite cache for face embeddings.
    Thread-safe for single-process use.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        logger.info(f"Embedding cache ready at: {self.db_path}")


    def get(
        self, file_id: str, file_bytes: bytes
    ) -> Optional[list[np.ndarray]]:
        """
        Retrieve cached embeddings for a file.

        Returns:
            List of numpy arrays if cache hit and file unchanged.
            None if not cached or file has changed (triggers re-processing).
        """
        file_hash = _md5(file_bytes)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT embeddings FROM embeddings WHERE file_id = ? AND file_hash = ?",
                (file_id, file_hash),
            ).fetchone()

        if row is None:
            return None

        # Deserialise JSON → list of numpy arrays
        raw = json.loads(row[0])
        return [np.array(emb, dtype=np.float32) for emb in raw]


    def get_by_signature(
        self, file_id: str, file_signature: str
    ) -> Optional[list[np.ndarray]]:
        """
        Retrieve cached embeddings using Drive metadata.

        This lets scans skip downloading unchanged files. The signature should
        come from stable Drive metadata, e.g. modifiedTime + size.
        """
        if not file_signature:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT embeddings FROM embeddings
                WHERE file_id = ? AND file_signature = ?
                """,
                (file_id, file_signature),
            ).fetchone()

        if row is None:
            return None

        raw = json.loads(row[0])
        return [np.array(emb, dtype=np.float32) for emb in raw]


    def set(
        self,
        file_id: str,
        file_bytes: bytes,
        embeddings: list[np.ndarray],
        file_signature: str | None = None,
    ) -> None:
        """
        Store face embeddings for a file.

        Args:
            file_id:    Google Drive file ID.
            file_bytes: Raw bytes of the image (used to compute hash).
            embeddings: List of 512-dim numpy arrays.
        """
        file_hash = _md5(file_bytes)
        serialised = json.dumps([emb.tolist() for emb in embeddings])
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (file_id, file_hash, file_signature, embeddings, face_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    file_hash  = excluded.file_hash,
                    file_signature = excluded.file_signature,
                    embeddings = excluded.embeddings,
                    face_count = excluded.face_count,
                    created_at = excluded.created_at
                """,
                (file_id, file_hash, file_signature, serialised, len(embeddings), now),
            )


    def delete(self, file_id: str) -> None:
        """Remove a single entry from the cache."""
        with self._connect() as conn:
            conn.execute("DELETE FROM embeddings WHERE file_id = ?", (file_id,))


    def clear(self) -> None:
        """Wipe the entire cache. Use when switching Drive folders."""
        with self._connect() as conn:
            conn.execute("DELETE FROM embeddings")
        logger.info("Embedding cache cleared.")


    def stats(self) -> dict:
        """Return cache statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            with_faces = conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE face_count > 0"
            ).fetchone()[0]
            no_faces = conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE face_count = 0"
            ).fetchone()[0]

        return {
            "total_cached": total,
            "with_faces": with_faces,
            "no_faces": no_faces,
            "db_path": str(self.db_path),
        }


    # ── Private ───────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the database and table if they don't exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    file_id    TEXT PRIMARY KEY,
                    file_hash  TEXT NOT NULL,
                    file_signature TEXT,
                    embeddings TEXT NOT NULL,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()
            }
            if "file_signature" not in columns:
                conn.execute("ALTER TABLE embeddings ADD COLUMN file_signature TEXT")


    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md5(data: bytes) -> str:
    """Return MD5 hex digest of bytes."""
    return hashlib.md5(data).hexdigest()
