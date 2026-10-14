"""Cloudflare R2 / S3-compatible storage adapter.

When R2 credentials are configured the adapter uploads, downloads, and deletes
files from your R2 bucket. When the credentials are absent it falls back to the
local `data/uploads/` directory transparently.

No extra dependencies beyond `httpx` (already in requirements) and the Python
standard library. SigV4 signing is implemented inline so we do NOT need boto3
(which would add ~50 MB to the container).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import config

logger = logging.getLogger("aether.storage")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_str: str, region: str, service: str) -> bytes:
    return _sign(
        _sign(
            _sign(
                _sign(("AWS4" + secret).encode("utf-8"), date_str),
                region,
            ),
            service,
        ),
        "aws4_request",
    )


def _sigv4_headers(
    method: str,
    bucket: str,
    key: str,
    region: str,
    access_key: str,
    secret_key: str,
    payload_hash: str,
    host: str,
    content_type: str = "application/octet-stream",
) -> dict:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join(
        [
            method,
            f"/{bucket}/{key}",
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{date_str}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _signing_key(secret_key, date_str, region, "s3")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Content-Type": content_type,
    }


def _r2_configured() -> bool:
    return bool(
        config.storage_provider in {"auto", "r2"}
        and config.r2_account_id
        and config.r2_access_key_id
        and config.r2_secret_access_key
        and config.r2_bucket_name
    )


def provider() -> str:
    if config.storage_provider == "supabase":
        return "supabase"
    return "r2" if _r2_configured() else "local"


def max_upload_bytes() -> int:
    if provider() == "supabase":
        from app.services.supabase_storage import upload_limit_bytes
        return upload_limit_bytes()
    return config.max_upload_mb * 1024 * 1024


def max_upload_mb() -> float:
    # Round down for the frontend so it never promises more than Storage allows.
    return (max_upload_bytes() * 100 // (1024 * 1024)) / 100


def _r2_endpoint() -> str:
    return f"https://{config.r2_account_id}.r2.cloudflarestorage.com"


def _object_key(workspace_id: str, document_id: str) -> str:
    return f"uploads/{workspace_id}/{document_id}"


def _local_path(workspace_id: str, document_id: str) -> Path:
    return config.data_dir / "uploads" / workspace_id / document_id


def upload_file(workspace_id: str, document_id: str, content_or_path) -> None:
    """Upload a document file to R2 (or save locally as fallback)."""
    if provider() == "supabase":
        from app.services import supabase_storage
        return supabase_storage.upload_file(workspace_id, document_id, content_or_path)
    if not _r2_configured():
        dest = _local_path(workspace_id, document_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content_or_path, (str, Path)):
            shutil.copyfile(str(content_or_path), str(dest))
        else:
            dest.write_bytes(content_or_path)
        logger.debug("storage: saved %s/%s locally", workspace_id, document_id)
        return

    if isinstance(content_or_path, (str, Path)):
        data = Path(content_or_path).read_bytes()
    else:
        data = content_or_path

    bucket = config.r2_bucket_name
    region = "auto"
    host = f"{config.r2_account_id}.r2.cloudflarestorage.com"
    key = _object_key(workspace_id, document_id)
    payload_hash = hashlib.sha256(data).hexdigest()

    headers = _sigv4_headers(
        method="PUT",
        bucket=bucket,
        key=key,
        region=region,
        access_key=config.r2_access_key_id,
        secret_key=config.r2_secret_access_key,
        payload_hash=payload_hash,
        host=host,
    )

    url = f"{_r2_endpoint()}/{bucket}/{key}"
    with httpx.Client(timeout=60) as client:
        response = client.put(url, headers=headers, content=data)
        response.raise_for_status()

    logger.info("storage: uploaded %s/%s to R2 (%d bytes)", workspace_id, document_id, len(data))


def download_file(workspace_id: str, document_id: str) -> bytes:
    """Download a document file from R2 (or from local disk as fallback)."""
    if provider() == "supabase":
        from app.services import supabase_storage
        return supabase_storage.download_file(workspace_id, document_id)
    if not _r2_configured():
        path = _local_path(workspace_id, document_id)
        if not path.is_file():
            raise FileNotFoundError(f"Local file not found: {path}")
        return path.read_bytes()

    bucket = config.r2_bucket_name
    region = "auto"
    host = f"{config.r2_account_id}.r2.cloudflarestorage.com"
    key = _object_key(workspace_id, document_id)
    empty_hash = hashlib.sha256(b"").hexdigest()

    headers = _sigv4_headers(
        method="GET",
        bucket=bucket,
        key=key,
        region=region,
        access_key=config.r2_access_key_id,
        secret_key=config.r2_secret_access_key,
        payload_hash=empty_hash,
        host=host,
    )

    url = f"{_r2_endpoint()}/{bucket}/{key}"
    with httpx.Client(timeout=60) as client:
        response = client.get(url, headers=headers)
        if response.status_code == 404:
            raise FileNotFoundError(f"R2 object not found: {key}")
        response.raise_for_status()
        return response.content


def delete_file(workspace_id: str, document_id: str) -> None:
    """Delete a document file from R2 or local disk."""
    if provider() == "supabase":
        from app.services import supabase_storage
        return supabase_storage.delete_file(workspace_id, document_id)
    if not _r2_configured():
        _local_path(workspace_id, document_id).unlink(missing_ok=True)
        return

    bucket = config.r2_bucket_name
    region = "auto"
    host = f"{config.r2_account_id}.r2.cloudflarestorage.com"
    key = _object_key(workspace_id, document_id)
    empty_hash = hashlib.sha256(b"").hexdigest()

    headers = _sigv4_headers(
        method="DELETE",
        bucket=bucket,
        key=key,
        region=region,
        access_key=config.r2_access_key_id,
        secret_key=config.r2_secret_access_key,
        payload_hash=empty_hash,
        host=host,
    )

    url = f"{_r2_endpoint()}/{bucket}/{key}"
    try:
        with httpx.Client(timeout=30) as client:
            response = client.delete(url, headers=headers)
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()
    except Exception as exc:
        logger.warning("storage: failed to delete R2 object %s: %s", key, exc)


def delete_workspace_files(workspace_id: str) -> None:
    """Delete all files belonging to a workspace from R2 or local disk."""
    if provider() == "supabase":
        from app.services import supabase_storage
        return supabase_storage.delete_workspace_files(workspace_id)
    if not _r2_configured():
        folder = config.data_dir / "uploads" / workspace_id
        if folder.exists():
            shutil.rmtree(folder)
        return

    import re

    bucket = config.r2_bucket_name
    region = "auto"
    host = f"{config.r2_account_id}.r2.cloudflarestorage.com"
    prefix = f"uploads/{workspace_id}/"
    empty_hash = hashlib.sha256(b"").hexdigest()

    list_headers = _sigv4_headers(
        method="GET",
        bucket=bucket,
        key="",
        region=region,
        access_key=config.r2_access_key_id,
        secret_key=config.r2_secret_access_key,
        payload_hash=empty_hash,
        host=host,
        content_type="application/x-www-form-urlencoded",
    )

    list_url = f"{_r2_endpoint()}/{bucket}?list-type=2&prefix={prefix}"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(list_url, headers=list_headers)
            resp.raise_for_status()
            keys = re.findall(r"<Key>([^<]+)</Key>", resp.text)
        for key in keys:
            doc_id = key.split("/")[-1]
            delete_file(workspace_id, doc_id)
        logger.info("storage: deleted %d R2 objects for workspace %s", len(keys), workspace_id)
    except Exception as exc:
        logger.warning("storage: failed to list/delete R2 workspace %s: %s", workspace_id, exc)


def file_exists_locally(workspace_id: str, document_id: str) -> bool:
    """Check if a file exists on local disk."""
    return provider() == "local" and _local_path(workspace_id, document_id).is_file()


def local_path(workspace_id: str, document_id: str) -> Path:
    """Return the local disk path for a document."""
    return _local_path(workspace_id, document_id)
