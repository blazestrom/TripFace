from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class AuthUrlResponse(BaseModel):
    auth_url: str


class DriveFolder(BaseModel):
    id: str
    name: str


class DriveImage(BaseModel):
    id: str
    name: str
    mimeType: str
    modifiedTime: str


class ErrorResponse(BaseModel):
    message: str


class CacheClearResponse(BaseModel):
    deleted: int
