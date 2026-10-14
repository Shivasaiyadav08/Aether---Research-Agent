"""Private Supabase Storage over REST; credentials never reach the browser."""
from pathlib import Path
import logging
from time import monotonic
from urllib.parse import quote

import httpx

from app.core.config import config

logger = logging.getLogger("aether.storage")
_bucket_limit_bytes = None


def request(method, path, *, timeout=60, **kwargs):
    key = config.supabase_secret_key
    headers = {"apikey": key, **kwargs.pop("headers", {})}
    # New secret keys are not JWTs. Legacy service_role JWTs need Bearer too.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(method, config.supabase_url.rstrip("/") + "/storage/v1/" + path,
                                      headers=headers, **kwargs)
    except httpx.RequestError:
        raise RuntimeError("Supabase Storage is unreachable. Check SUPABASE_URL and provider status.") from None
    if not response.is_success:
        try:
            details = response.json()
        except ValueError:
            details = {}
        if not isinstance(details, dict):
            details = {}
        code = details.get("code") or details.get("error")
        missing = code in {"NoSuchBucket", "NoSuchKey", "not_found", "Bucket not found", "Object not found"}
        if method == "GET" and (response.status_code == 404 or
                (response.status_code == 400 and missing)):
            raise FileNotFoundError("The original document is unavailable in Supabase Storage.")
        # Only fixed diagnostics are emitted: never reflect provider messages,
        # invalid credential values, URLs, or arbitrary error codes into logs.
        hints = {
            "InvalidJWT": "The backend credential is invalid or expired. Copy the Supabase backend secret key from the same project as SUPABASE_URL.",
            "Invalid API key": "The API key is invalid. Copy the backend secret key from the same Supabase project as SUPABASE_URL.",
            "Unauthorized": "Storage rejected the backend credential. Use a secret or legacy service_role key, not anon or the database password.",
            "unauthorized": "Storage rejected the backend credential. Use a secret or legacy service_role key, not anon or the database password.",
            "AccessDenied": "The backend key cannot access Storage. Verify it is a secret or legacy service_role key from this project.",
            "InvalidBucketName": "SUPABASE_STORAGE_BUCKET must be the exact bucket name without quotes, spaces or a URL.",
            "TenantNotFound": "Supabase Storage is not provisioned for this project. Check the project URL and Storage status.",
            "EntityTooLarge": "The upload exceeds the Supabase bucket file-size limit.",
        }
        hint = hints.get(code, "Check SUPABASE_URL, the backend secret key and the private bucket in the same project.")
        raise RuntimeError(f"Supabase Storage returned HTTP {response.status_code}. {hint}")
    return response


def bucket():
    return quote(config.supabase_storage_bucket, safe="")


def object_path(workspace_id, document_id):
    if any(not value or "/" in value or "\\" in value or value in {".", ".."}
           for value in (workspace_id, document_id)):
        raise ValueError("Invalid document storage identifier.")
    return f"uploads/{workspace_id}/{document_id}"


def check_bucket():
    global _bucket_limit_bytes
    _bucket_limit_bytes = None
    try:
        details = request("GET", f"bucket/{bucket()}", timeout=10).json()
    except FileNotFoundError:
        raise RuntimeError("Supabase private bucket is missing. Run backend/supabase/setup.sql and check SUPABASE_STORAGE_BUCKET.") from None
    if details.get("public") is not False:
        raise RuntimeError("SUPABASE_STORAGE_BUCKET must be private to protect user documents.")
    limit = details.get("file_size_limit")
    if limit is not None:
        try:
            _bucket_limit_bytes = int(limit)
        except (TypeError, ValueError):
            raise RuntimeError("Supabase returned an invalid bucket file-size limit.") from None
        if _bucket_limit_bytes < 0:
            raise RuntimeError("Supabase returned an invalid bucket file-size limit.")
        configured = config.max_upload_mb * 1024 * 1024
        if _bucket_limit_bytes < configured:
            logger.warning("Supabase upload limit is %d bytes; reducing the configured %d-byte limit. Backend startup continues.",
                           _bucket_limit_bytes, configured)


def upload_limit_bytes():
    configured = config.max_upload_mb * 1024 * 1024
    return configured if _bucket_limit_bytes is None else min(configured, _bucket_limit_bytes)


def upload_file(workspace_id, document_id, content_or_path):
    size = Path(content_or_path).stat().st_size if isinstance(content_or_path, (str, Path)) else len(content_or_path)
    if size > upload_limit_bytes():
        raise ValueError("The document exceeds the effective Supabase upload limit.")
    data = Path(content_or_path).read_bytes() if isinstance(content_or_path, (str, Path)) else content_or_path
    path = quote(object_path(workspace_id, document_id), safe="/")
    request("POST", f"object/{bucket()}/{path}", content=data,
            headers={"Content-Type": "application/octet-stream", "x-upsert": "false"})


def download_file(workspace_id, document_id):
    path = quote(object_path(workspace_id, document_id), safe="/")
    return request("GET", f"object/{bucket()}/{path}").content


def delete_file(workspace_id, document_id):
    request("DELETE", f"object/{bucket()}", json={"prefixes": [object_path(workspace_id, document_id)]})


def delete_workspace_files(workspace_id):
    prefix = object_path(workspace_id, "placeholder").rsplit("/", 1)[0]
    # Remove one page at a time; never advance an offset after deleting a page.
    deadline = monotonic() + 60
    previous = None
    while monotonic() < deadline:
        entries = request("POST", f"object/list/{bucket()}", json={
            "prefix": prefix, "limit": 100, "offset": 0,
            "sortBy": {"column": "name", "order": "asc"},
        }, timeout=max(1, deadline - monotonic())).json()
        if not entries:
            return
        paths = [object_path(workspace_id, item["name"]) for item in entries]
        if paths == previous:
            raise RuntimeError("Supabase did not remove the requested files. Workspace metadata was retained; retry deletion.")
        previous = paths
        request("DELETE", f"object/{bucket()}", json={"prefixes": paths}, timeout=max(1, deadline - monotonic()))
    raise RuntimeError("Supabase workspace deletion timed out. Workspace metadata was retained; retry deletion.")
