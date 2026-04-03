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
        Raises RuntimeError on failure.
        """
        path = self._user_path(user_id, filename)
        try:
            self.db.storage.from_(BUCKET).upload(
                path=path,
                file=file_bytes,
                file_options={"upsert": "true"},
            )
        except Exception as exc:
            logger.error(f"StorageService.upload_resume failed for {path}: {exc}")
            raise RuntimeError("Error al subir el archivo al almacenamiento.") from exc
        return path

    async def download_resume(self, file_path: str) -> bytes:
        """Download resume bytes from Supabase Storage.

        Raises RuntimeError on failure.
        """
        try:
            return self.db.storage.from_(BUCKET).download(file_path)
        except Exception as exc:
            logger.error(f"StorageService.download_resume failed for {file_path}: {exc}")
            raise RuntimeError("Error al descargar el archivo del almacenamiento.") from exc

    async def get_signed_url(
        self, file_path: str, expires_in: int = 3600
    ) -> str:
        """Generate a signed download URL for a resume file.

        Raises RuntimeError on failure or missing URL in response.
        """
        try:
            result = self.db.storage.from_(BUCKET).create_signed_url(
                file_path, expires_in
            )
        except Exception as exc:
            logger.error(f"StorageService.get_signed_url failed for {file_path}: {exc}")
            raise RuntimeError("Error al generar el enlace de descarga.") from exc

        url = result.get("signedURL")
        if not url:
            raise RuntimeError(f"Signed URL missing in storage response for {file_path}")
        return url
