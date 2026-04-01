"""Supabase Storage service for resume file upload/download."""

import logging

logger = logging.getLogger(__name__)

BUCKET = "resumes"


class StorageService:
    def __init__(self, supabase_client):
        self.db = supabase_client

    def _user_path(self, user_id: str, filename: str) -> str:
        """Files are scoped per user: resumes/{user_id}/{filename}."""
        return f"{user_id}/{filename}"

    async def upload_resume(
        self, user_id: str, file_bytes: bytes, filename: str
    ) -> str:
        """Upload resume bytes to Supabase Storage.

        Returns the storage path (resumes/{user_id}/{filename}).
        """
        path = self._user_path(user_id, filename)
        self.db.storage.from_(BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"upsert": "true"},
        )
        return path

    async def download_resume(self, file_path: str) -> bytes:
        """Download resume bytes from Supabase Storage."""
        return self.db.storage.from_(BUCKET).download(file_path)

    async def get_signed_url(
        self, file_path: str, expires_in: int = 3600
    ) -> str:
        """Generate a signed download URL for a resume file."""
        result = self.db.storage.from_(BUCKET).create_signed_url(
            file_path, expires_in
        )
        return result["signedURL"]
