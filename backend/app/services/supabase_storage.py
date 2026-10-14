"""Private Supabase Storage over REST; credentials never reach the browser."""
from pathlib import Path
from time import monotonic
from urllib.parse import quote

import httpx

from app.core.config import config


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
        if method == "GET" and (response.status_code == 404 or
                (response.status_code == 400 and details.get("error") == "not_found")):
            raise FileNotFoundError("The original document is unavailable in Supabase Storage.")
        raise RuntimeError(f"Supabase Storage returned HTTP {response.status_code}. Check bucket, backend secret key and storage quota.")
    return response


def bucket():
    return quote(config.supabase_storage_bucket, safe="")


def object_path(workspace_id, document_id):
    if any(not value or "/" in value or "\\" in value or value in {".", ".."}
           for value in (workspace_id, document_id)):
        raise ValueError("Invalid document storage identifier.")
    return f"uploads/{workspace_id}/{document_id}"


def check_bucket():
    try:
        details = request("GET", f"bucket/{bucket()}", timeout=10).json()
    except FileNotFoundError:
        raise RuntimeError("Supabase private bucket is missing. Run backend/supabase/setup.sql and check SUPABASE_STORAGE_BUCKET.") from None
    if details.get("public") is not False:
        raise RuntimeError("SUPABASE_STORAGE_BUCKET must be private to protect user documents.")
    limit = details.get("file_size_limit")
    if limit is not None and int(limit) < config.max_upload_mb * 1024 * 1024:
        raise RuntimeError("Supabase bucket file-size limit is below MAX_UPLOAD_MB. Update the bucket limit or MAX_UPLOAD_MB.")


def upload_file(workspace_id, document_id, content_or_path):
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
