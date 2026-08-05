import logging
from io import BytesIO
from urllib.parse import urlparse
from backend.config import (
    MINIO_ENDPOINT,
    MINIO_BUCKET,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
)

logger = logging.getLogger("storage_service")

_minio_client = None

def get_minio_client():
    global _minio_client
    if _minio_client is not None:
        return _minio_client

    if not MINIO_ENDPOINT or not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        logger.warning("[MinIO] Cấu hình MinIO chưa đầy đủ")
        return None

    try:
        from minio import Minio
        parsed = urlparse(MINIO_ENDPOINT)
        endpoint_host = parsed.netloc or parsed.path
        is_secure = parsed.scheme == "https"

        client = Minio(
            endpoint_host,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=is_secure,
        )

        # Kiểm tra và tạo bucket nếu chưa có
        try:
            if not client.bucket_exists(MINIO_BUCKET):
                client.make_bucket(MINIO_BUCKET)
                logger.info(f"[MinIO] Đã tạo bucket '{MINIO_BUCKET}'")
        except Exception as bucket_err:
            logger.warning(f"[MinIO] Kiểm tra/Tạo bucket '{MINIO_BUCKET}' báo lỗi: {bucket_err}")

        _minio_client = client
        return _minio_client
    except Exception as e:
        logger.error(f"[MinIO] Khởi tạo MinIO client thất bại: {e}")
        return None


def upload_video_to_minio(video_bytes: bytes, object_name: str, content_type: str = "video/webm") -> str | None:
    """Tải video phỏng vấn lên MinIO storage.
    Trả về MinIO URL/Key nếu thành công, None nếu có lỗi."""
    client = get_minio_client()
    if not client:
        return None

    try:
        data_stream = BytesIO(video_bytes)
        size = len(video_bytes)

        client.put_object(
            bucket_name=MINIO_BUCKET,
            object_name=object_name,
            data=data_stream,
            length=size,
            content_type=content_type,
        )
        logger.info(f"[MinIO] Upload video thành công: bucket={MINIO_BUCKET}, key={object_name}")
        minio_url = f"{MINIO_ENDPOINT.rstrip('/')}/{MINIO_BUCKET}/{object_name}"
        return minio_url
    except Exception as e:
        logger.error(f"[MinIO] Lỗi upload video '{object_name}' lên MinIO: {e}")
        return None
