"""
drive_client.py
───────────────
Handles all Google Drive interactions:
  - OAuth authentication (reuses token.json, auto-refreshes)
  - List folders in Drive
  - List image files inside a folder
  - Download image bytes for face processing
  - Create folders
  - Copy files into folders (for saving matched photos)

Scope upgraded to drive (read+write) to support folder creation and file copy.
"""

import os
import io
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

# Upgraded to full drive scope so we can create folders and copy files
SCOPES           = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_PATH = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
TOKEN_PATH       = Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json"))

IMAGE_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "image/heic", "image/heif", "image/bmp",
    "image/tiff", "image/gif", "image/avif",
}

FOLDER_MIME = "application/vnd.google-apps.folder"


# ── DriveClient ────────────────────────────────────────────────────────────────

class DriveClient:

    def __init__(self):
        creds = self._load_credentials()
        self._service = build("drive", "v3", credentials=creds)
        logger.info("Google Drive client ready.")

    # ── Read ───────────────────────────────────────────────────────────────────

    def list_folders(self, max_results: int = 50) -> list[dict]:
        query = f"mimeType = '{FOLDER_MIME}' and trashed = false"
        results = (
            self._service.files()
            .list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, modifiedTime)",
                orderBy="name",
            )
            .execute()
        )
        folders = results.get("files", [])
        logger.info(f"Found {len(folders)} folders.")
        return folders

    def list_images(self, folder_id: str) -> list[dict]:
        mime_filter = " or ".join([f"mimeType = '{m}'" for m in IMAGE_MIME_TYPES])
        query = (
            f"('{folder_id}' in parents) "
            f"and ({mime_filter}) "
            f"and trashed = false"
        )
        images = []
        page_token = None
        while True:
            params = dict(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                orderBy="name",
            )
            if page_token:
                params["pageToken"] = page_token
            response = self._service.files().list(**params).execute()
            images.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        logger.info(f"Found {len(images)} images in folder {folder_id}.")
        return images

    def download_image(self, file_id: str) -> bytes:
        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def get_folder_name(self, folder_id: str) -> str:
        try:
            f = self._service.files().get(fileId=folder_id, fields="name").execute()
            return f.get("name", folder_id)
        except Exception:
            return folder_id

    # ── Write ──────────────────────────────────────────────────────────────────

    def find_folder_by_name(self, name: str, parent_id: str = None) -> Optional[str]:
        """
        Find a folder by name. Returns folder ID if found, None otherwise.
        If parent_id given, searches inside that folder only.
        """
        name_escaped = name.replace("'", "\\'")
        query = f"mimeType = '{FOLDER_MIME}' and name = '{name_escaped}' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = (
            self._service.files()
            .list(q=query, pageSize=1, fields="files(id, name)")
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def create_folder(self, name: str, parent_id: str = None) -> dict:
        """
        Create a new folder in Drive.
        Returns {id, name} of the created folder.
        """
        metadata = {
            "name": name,
            "mimeType": FOLDER_MIME,
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = (
            self._service.files()
            .create(body=metadata, fields="id, name")
            .execute()
        )
        logger.info(f"Created folder '{name}' with id: {folder['id']}")
        return folder

    def get_or_create_folder(self, name: str, parent_id: str = None) -> dict:
        """
        Returns existing folder if name already exists, else creates it.
        Returns {id, name, created: bool}
        """
        existing_id = self.find_folder_by_name(name, parent_id)
        if existing_id:
            logger.info(f"Folder '{name}' already exists: {existing_id}")
            return {"id": existing_id, "name": name, "created": False}
        folder = self.create_folder(name, parent_id)
        return {**folder, "created": True}

    def copy_file_to_folder(self, file_id: str, folder_id: str) -> dict:
        """
        Copy a Drive file into a folder (no re-upload — server-side copy).
        Returns the new file metadata {id, name}.
        """
        # Get original file name
        original = self._service.files().get(
            fileId=file_id, fields="name"
        ).execute()

        copied = self._service.files().copy(
            fileId=file_id,
            body={"parents": [folder_id], "name": original["name"]},
            fields="id, name",
        ).execute()

        logger.info(f"Copied '{original['name']}' → folder {folder_id}")
        return copied

    def bulk_copy_to_folder(self, file_ids: list[str], folder_id: str) -> dict:
        """
        Copy multiple files into a folder.
        Returns {copied: N, failed: N, files: [{id, name}]}
        """
        copied_files = []
        failed = 0
        for fid in file_ids:
            try:
                result = self.copy_file_to_folder(fid, folder_id)
                copied_files.append(result)
            except Exception as e:
                logger.warning(f"Failed to copy {fid}: {e}")
                failed += 1
        return {
            "copied": len(copied_files),
            "failed": failed,
            "files": copied_files,
        }

    # ── Auth ───────────────────────────────────────────────────────────────────

    def _load_credentials(self) -> Credentials:
        creds = None
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Google OAuth token...")
                creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_PATH}."
                    )
                logger.info("Starting Google OAuth login flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json())
            logger.info(f"Token saved to {TOKEN_PATH}")
        return creds
