"""This file manages which Gemini AI models Aether can use for free, checks which models are accessible through your Google API key, ranks them, and temporarily marks failed models as unavailable.

free_tier_ids()	-> Reads Google's pricing page and finds models whose input and output are both free.
is_free_text_model()-> Checks whether a model is free, supports text generation, and isn't an excluded model type.
model_rank()->Sorts models by version and family, preferring newer versions and then Pro, Flash, and Lite.
mark_model_unavailable()->Puts a model on cooldown, for 60 seconds by default.
availability()->Checks cooldowns and adds available and retry_after_seconds to each model.
get_free_models()->ain function: fetches pricing and Google's model list, filters and sorts models, caches the results, and returns availability information.
"""

import asyncio
import re
from time import monotonic

import httpx
from bs4 import BeautifulSoup

from app.core.config import config

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"
_catalog: list[dict] = []
_expires = 0.0
_catalog_key = ""
_catalog_lock = asyncio.Lock()
_cooldowns: dict[str, float] = {}
_cooldown_key = ""


def reset_key_cooldowns():
    """Failures for one credential must not disable models for a replacement key."""
    global _cooldown_key
    if _cooldown_key != config.gemini_api_key:
        _cooldowns.clear()
        _cooldown_key = config.gemini_api_key


def free_tier_ids(html: str) -> set[str]:
    """Read Standard free input/output prices; never assume unknown prices are free."""
    soup = BeautifulSoup(html, "html.parser")
    eligible = set()
    for heading in soup.find_all("h2"):
        codes = []
        table = None
        # Google wraps headings in divs; traverse document order across wrappers.
        for element in heading.next_elements:
            if getattr(element, "name", None) == "h2":
                break
            if getattr(element, "name", None) == "code":
                codes.append(element.get_text(strip=True))
            if getattr(element, "name", None) == "table":
                table = element
                break
        if not table:
            continue
        rows = [
            [cell.get_text(" ", strip=True).lower() for cell in row.find_all(["th", "td"])]
            for row in table.find_all("tr")
        ]
        if not rows:
            continue
        free_column = next((i for i, cell in enumerate(rows[0]) if cell == "free tier"), None)
        if free_column is None:
            continue
        prices = {}
        for row in rows[1:]:
            if len(row) > free_column:
                if row[0].startswith("input price"):
                    prices["input"] = row[free_column]
                elif row[0].startswith("output price"):
                    prices["output"] = row[free_column]
        if not all(prices.get(kind) == "free of charge" for kind in ("input", "output")):
            continue
        for model_id in codes:
            if re.fullmatch(r"gemini-[a-z0-9.-]+", model_id):
                eligible.add(model_id)
    if not eligible:
        raise ValueError("Could not verify Gemini free-tier pricing. No unverified models will be used.")
    return eligible


def is_free_text_model(item: dict, eligible: set[str]) -> bool:
    model_id = item.get("name", "").removeprefix("models/")
    return (
        model_id in eligible
        and "generateContent" in item.get("supportedGenerationMethods", [])
        and not any(word in model_id for word in ("image", "tts", "audio", "live", "transcribe", "robotics"))
    )


def model_rank(item: dict):
    """Prefer newer families, Pro then Flash then Lite; this is a heuristic, not a benchmark."""
    model_id = item["id"]
    version = re.search(r"gemini-(\d+)(?:\.(\d+))?", model_id)
    major, minor = (int(version[1]), int(version[2] or 0)) if version else (0, 0)
    family = 0 if "pro" in model_id else 2 if "lite" in model_id else 1
    return (-major, -minor, family, "preview" in model_id or "exp" in model_id, model_id)


def supported_parameters(model_id: str) -> list[str]:
    # Reviewed Developer API families: unknown families require a compatibility review.
    # Pricing and authenticated Models.list still determine eligibility independently.
    if re.match(r"^gemini-(?:2\.5|3(?:\.[15678])?)-(?:pro|flash)", model_id):
        return ["structured_outputs", "streaming", "vision"]
    return []


def mark_model_unavailable(model: str, seconds: int = 60):
    reset_key_cooldowns()
    _cooldowns[model] = monotonic() + seconds


def mark_model_available(model: str):
    reset_key_cooldowns()
    _cooldowns.pop(model, None)


def model_availability(model: str) -> dict:
    reset_key_cooldowns()
    remaining = max(0, int(_cooldowns.get(model, 0) - monotonic() + 0.999))
    return {"available": remaining == 0, "retry_after_seconds": remaining}


def availability(models: list[dict]) -> list[dict]:
    return [{**item, **model_availability(item["id"])} for item in models]


def get_free_models_sync() -> list[dict]:
    """Bounded synchronous discovery for OCR workers, without crossing event loops."""
    global _catalog, _expires, _catalog_key
    if not config.gemini_api_key:
        raise ValueError("Gemini is not configured.")
    if _catalog and _catalog_key == config.gemini_api_key and monotonic() < _expires:
        return availability(_catalog)
    deadline, token, seen, items = monotonic() + 30, None, set(), []
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(PRICING_URL)
        response.raise_for_status()
        eligible = free_tier_ids(response.text)
        for _ in range(10):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Gemini catalog deadline reached.")
            response = client.get(f"{GEMINI_API_URL}/models", headers={"x-goog-api-key": config.gemini_api_key},
                                  params={"pageSize": 1000, **({"pageToken": token} if token else {})}, timeout=remaining)
            response.raise_for_status()
            data = response.json()
            items.extend(data.get("models", []))
            token = data.get("nextPageToken")
            if not token:
                break
            if token in seen:
                raise ValueError("Repeated Gemini model page token.")
            seen.add(token)
        else:
            raise ValueError("Gemini model catalog exceeded the page limit.")
    models = [catalog_entry(item) for item in items if is_free_text_model(item, eligible)]
    models = sorted({item["id"]: item for item in models}.values(), key=model_rank)
    if not models:
        raise ValueError("No verified free-tier Gemini models are accessible.")
    _catalog, _expires, _catalog_key = models, monotonic() + 300, config.gemini_api_key
    return availability(models)


def catalog_entry(item):
    model_id = item["name"].removeprefix("models/")
    return {"id": model_id, "name": item.get("displayName", item["name"]),
            "context_length": item.get("inputTokenLimit", 0), "output_token_limit": item.get("outputTokenLimit", 0),
            "supported_parameters": supported_parameters(model_id),
            "pricing": {"prompt": "0", "completion": "0"}, "free_tier_eligible": True}


async def get_free_models(*, refresh: bool = False) -> list[dict]:
    """Cache the pricing/model intersection for five minutes; paginate Models.list."""
    global _catalog, _expires, _catalog_key
    if not config.gemini_api_key:
        raise ValueError("Add GEMINI_API_KEY to backend/.env and restart the backend.")
    async with _catalog_lock:
        if not refresh and _catalog and _catalog_key == config.gemini_api_key and monotonic() < _expires:
            return availability(_catalog)
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            prices = await client.get(PRICING_URL)
            prices.raise_for_status()
            eligible = free_tier_ids(prices.text)
            items = []
            page_token = None
            seen_tokens = set()
            while True:
                params = {"pageSize": 1000}
                if page_token:
                    params["pageToken"] = page_token
                response = await client.get(
                    f"{GEMINI_API_URL}/models",
                    headers={"x-goog-api-key": config.gemini_api_key},
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                items.extend(data.get("models", []))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                if page_token in seen_tokens:
                    raise ValueError("Gemini returned a repeated model page token.")
                seen_tokens.add(page_token)
        models = [
            catalog_entry(item)
            for item in items
            if is_free_text_model(item, eligible)
        ]
        models = list({item["id"]: item for item in models}.values())
        models.sort(key=model_rank)
        if not models:
            raise ValueError("No free-tier Gemini text models are accessible to this API key.")
        _catalog, _expires, _catalog_key = models, monotonic() + 300, config.gemini_api_key
        return availability(models)
