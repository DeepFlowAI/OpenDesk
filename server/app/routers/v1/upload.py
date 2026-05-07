"""
File upload router
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile, File
from app.db.deps import get_current_user
from app.libs.storage import create_storage_client

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

CHANNEL_LOGO_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/svg+xml",
}
MAX_CHANNEL_LOGO_SIZE = 2 * 1024 * 1024  # 2MB (matches admin UI hint)

CHANNEL_FAVICON_TYPES = {
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/png",
    "image/svg+xml",
    "image/webp",
}
MAX_CHANNEL_FAVICON_SIZE = 512 * 1024  # 512KB

# Platform ceiling per request; field-level limits are enforced in the client from type_config.
MAX_CUSTOM_FIELD_FILE_SIZE = 100 * 1024 * 1024  # 100MB (aligns with admin default for 单文件最大体积)
BLOCKED_CUSTOM_FIELD_EXTENSIONS = {
    "exe",
    "bat",
    "cmd",
    "com",
    "msi",
    "scr",
    "pif",
    "dll",
    "vbs",
    "jar",
    "app",
    "deb",
    "rpm",
}


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload an avatar image and return the public URL."""
    from app.core.exceptions import ValidationError

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {file.content_type}. Allowed: JPEG, PNG, GIF, WebP")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise ValidationError("File size exceeds 5MB limit")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "png"
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"avatars/{date_prefix}/{uuid.uuid4().hex}.{ext}"

    storage = create_storage_client()
    url = await storage.upload(key, data, content_type=file.content_type or "image/png")
    return {"url": url}


@router.post("/channel-logo")
async def upload_channel_logo(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a channel header logo and return the public URL."""
    from app.core.exceptions import ValidationError

    if file.content_type not in CHANNEL_LOGO_TYPES:
        raise ValidationError(
            f"Unsupported image type: {file.content_type}. Allowed: JPEG, PNG, WebP, SVG"
        )

    data = await file.read()
    if len(data) > MAX_CHANNEL_LOGO_SIZE:
        raise ValidationError("File size exceeds 2MB limit")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "png"
    if file.content_type == "image/svg+xml":
        ext = "svg"
    elif ext not in ("jpg", "jpeg", "png", "webp", "svg"):
        ext = "png"

    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"channel-logos/{date_prefix}/{uuid.uuid4().hex}.{ext}"

    storage = create_storage_client()
    url = await storage.upload(key, data, content_type=file.content_type or "image/png")
    return {"url": url}


@router.post("/channel-favicon")
async def upload_channel_favicon(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a channel favicon (ICO/PNG/SVG/WebP, ≤512KB)."""
    from app.core.exceptions import ValidationError

    if file.content_type not in CHANNEL_FAVICON_TYPES:
        raise ValidationError(
            f"Unsupported favicon type: {file.content_type}. Allowed: ICO, PNG, SVG, WebP"
        )

    data = await file.read()
    if len(data) > MAX_CHANNEL_FAVICON_SIZE:
        raise ValidationError("File size exceeds 512KB limit")

    ext_map = {
        "image/x-icon": "ico",
        "image/vnd.microsoft.icon": "ico",
        "image/png": "png",
        "image/svg+xml": "svg",
        "image/webp": "webp",
    }
    ext = ext_map.get(file.content_type or "", "png")

    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"channel-favicons/{date_prefix}/{uuid.uuid4().hex}.{ext}"

    storage = create_storage_client()
    url = await storage.upload(key, data, content_type=file.content_type or "image/png")
    return {"url": url}


@router.post("/custom-field-file")
async def upload_custom_field_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a file for custom FILE fields; returns metadata for JSON slot storage."""
    from app.core.exceptions import ValidationError

    raw_name = file.filename or "upload"
    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ext in BLOCKED_CUSTOM_FIELD_EXTENSIONS:
        raise ValidationError(f"File type .{ext} is not allowed for security reasons")

    data = await file.read()
    if len(data) > MAX_CUSTOM_FIELD_FILE_SIZE:
        raise ValidationError("File size exceeds 100MB limit")

    safe_ext = ext if ext and ext not in BLOCKED_CUSTOM_FIELD_EXTENSIONS else "bin"
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"custom-field-files/{date_prefix}/{uuid.uuid4().hex}.{safe_ext}"

    storage = create_storage_client()
    content_type = file.content_type or "application/octet-stream"
    url = await storage.upload(key, data, content_type=content_type)
    return {
        "url": url,
        "name": raw_name,
        "size": len(data),
        "content_type": file.content_type,
    }
