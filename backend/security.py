from pathlib import Path
from typing import Iterable
import hashlib
import hmac
import os
from urllib.parse import quote

from fastapi import HTTPException, UploadFile


MAX_CV_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 250 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
ALLOWED_CV_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp3", ".wav", ".m4a", ".ogg"}
CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
}
EXTENSION_CONTENT_TYPES = {
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}
TEMP_FILE_SECRET = os.environ.get("TEMP_FILE_SECRET") or os.environ.get("ADMIN_KEY", "")


def bounded_text(value: str, field: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if value and len(value) > max_chars:
        raise HTTPException(413, f"{field} vượt quá giới hạn {max_chars} ký tự")
    return value


async def read_upload_limited(
    upload: UploadFile,
    *,
    allowed_extensions: Iterable[str],
    max_bytes: int,
    field_name: str,
) -> tuple[bytes, str]:
    filename = upload.filename or ""
    ext = Path(filename).suffix.lower()
    if not ext and upload.content_type:
        ext = CONTENT_TYPE_EXTENSIONS.get(upload.content_type.lower(), "")
    allowed = {e.lower() for e in allowed_extensions}
    if ext not in allowed:
        raise HTTPException(
            415,
            f"{field_name} chỉ hỗ trợ: {', '.join(sorted(allowed))}",
        )

    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"{field_name} vượt quá giới hạn {max_bytes // (1024 * 1024)}MB")
    return data, ext


def media_content_type_for_path(path: Path) -> str:
    return EXTENSION_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _temp_file_token(filename: str) -> str:
    if not TEMP_FILE_SECRET:
        raise HTTPException(500, "TEMP_FILE_SECRET hoặc ADMIN_KEY chưa được cấu hình")
    return hmac.new(TEMP_FILE_SECRET.encode(), filename.encode(), hashlib.sha256).hexdigest()


def signed_temp_file_url(filename: str) -> str:
    return f"/temp_pushbacks/{quote(filename)}?token={_temp_file_token(filename)}"


def verify_temp_file_token(filename: str, token: str | None) -> None:
    expected = _temp_file_token(filename)
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "Token file tạm không hợp lệ")
