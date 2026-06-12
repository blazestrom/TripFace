from __future__ import annotations

import json
import os
from datetime import datetime

import numpy as np
from sqlalchemy import DateTime, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./embeddings_cache.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    drive_file_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    drive_modified_time: Mapped[str] = mapped_column(String, nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def _serialize_embeddings(embeddings: list[np.ndarray]) -> str:
    return json.dumps([np.asarray(item, dtype=np.float32).tolist() for item in embeddings])


def _deserialize_embeddings(payload: str) -> list[np.ndarray]:
    return [np.asarray(item, dtype=np.float32) for item in json.loads(payload)]


def save_embeddings(
    drive_file_id: str,
    file_name: str,
    modified_time: str,
    embeddings: list[np.ndarray],
) -> None:
    with SessionLocal() as session:
        existing = session.scalar(
            select(FaceEmbedding).where(FaceEmbedding.drive_file_id == drive_file_id)
        )
        if existing:
            existing.file_name = file_name
            existing.drive_modified_time = modified_time
            existing.embedding_json = _serialize_embeddings(embeddings)
            existing.created_at = datetime.utcnow()
        else:
            session.add(
                FaceEmbedding(
                    drive_file_id=drive_file_id,
                    file_name=file_name,
                    drive_modified_time=modified_time,
                    embedding_json=_serialize_embeddings(embeddings),
                )
            )
        session.commit()


def get_cached_embeddings(drive_file_id: str, modified_time: str) -> list[np.ndarray] | None:
    with SessionLocal() as session:
        cached = session.scalar(
            select(FaceEmbedding).where(FaceEmbedding.drive_file_id == drive_file_id)
        )
        if not cached or cached.drive_modified_time != modified_time:
            return None
        return _deserialize_embeddings(cached.embedding_json)


def clear_cache() -> int:
    with SessionLocal() as session:
        result = session.execute(delete(FaceEmbedding))
        session.commit()
        return int(result.rowcount or 0)
