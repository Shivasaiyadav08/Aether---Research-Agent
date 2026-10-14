import asyncio

import httpx
import pytest
from google.genai.errors import ClientError

from app.core.config import config
from app.services import free_models
from app.services.ai import (
    IncompleteAnswer,
    call_with_free_fallback,
    is_model_unavailable,
    safe_service_error,
    service_status,
)


def pricing_section(model, input_price="Free of charge", output_price="Free of charge"):
    return f"""<div class="heading-group"><h2>{model}</h2><em><code>{model}</code></em></div>
    <div><table><thead><tr><th></th><th>Free Tier</th><th>Paid Tier</th></tr></thead>
    <tbody><tr><td>Input price</td><td>{input_price}</td><td>$1</td></tr>
    <tr><td>Output price (including thinking tokens)</td><td>{output_price}</td><td>$2</td></tr>
    </tbody></table></div>"""


@pytest.fixture(autouse=True)
def reset_catalog(monkeypatch):
    monkeypatch.setattr(free_models, "_catalog", [])
    monkeypatch.setattr(free_models, "_expires", 0)
    monkeypatch.setattr(free_models, "_catalog_key", "")
    monkeypatch.setattr(free_models, "_cooldowns", {})
    monkeypatch.setattr(free_models, "_catalog_lock", asyncio.Lock())


@pytest.mark.parametrize(
    "input_price,output_price",
    [
        ("Not available", "Free of charge"),
        ("Free of charge", "$0.1"),
        ("", "Free of charge"),
        ("Unknown", "Unknown"),
    ],
)
def test_pricing_never_guesses_unknown_or_paid_models_are_free(input_price, output_price):
    html = pricing_section("gemini-3.7-flash") + pricing_section("gemini-paid", input_price, output_price)
    assert free_models.free_tier_ids(html) == {"gemini-3.7-flash"}


def test_missing_pricing_fails_closed_and_sections_do_not_borrow_prices():
    with pytest.raises(ValueError):
        free_models.free_tier_ids("<h2>gemini-missing</h2><code>gemini-missing</code>")
    html = "<h2>Missing</h2><code>gemini-missing</code>" + pricing_section("gemini-3.7-flash")
    assert free_models.free_tier_ids(html) == {"gemini-3.7-flash"}


def test_eligibility_excludes_image_audio_and_non_generation_models():
    for name, methods in [
        ("gemini-image", ["generateContent"]),
        ("gemini-live", ["generateContent"]),
        ("gemini-flash", ["embedContent"]),
        ("gemini-unpriced", ["generateContent"]),
    ]:
        assert not free_models.is_free_text_model(
            {"name": f"models/{name}", "supportedGenerationMethods": methods},
            {"gemini-image", "gemini-live", "gemini-flash"},
        )


async def test_real_api_contract_pagination_intersection_cache_and_refresh(monkeypatch):
    monkeypatch.setattr(config, "gemini_api_key", "test-only-never-in-url")
    calls = []
    html = pricing_section("gemini-3.8-flash") + pricing_section("gemini-2.5-pro")

    def respond(request):
        calls.append(request)
        if str(request.url) == free_models.PRICING_URL:
            return httpx.Response(200, text=html)
        assert request.headers["x-goog-api-key"] == "test-only-never-in-url"
        assert "test-only" not in str(request.url)
        model = "gemini-2.5-pro" if request.url.params.get("pageToken") else "gemini-3.8-flash"
        data = {
            "models": [
                {
                    "name": f"models/{model}",
                    "supportedGenerationMethods": ["generateContent"],
                    "inputTokenLimit": 1000000,
                },
                {"name": "models/gemini-paid-pro", "supportedGenerationMethods": ["generateContent"]},
            ]
        }
        if not request.url.params.get("pageToken"):
            data["nextPageToken"] = "second-page"
        return httpx.Response(200, json=data)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        free_models.httpx, "AsyncClient", lambda **_: original_client(transport=httpx.MockTransport(respond))
    )
    models = await free_models.get_free_models()
    assert [item["id"] for item in models] == ["gemini-3.8-flash", "gemini-2.5-pro"]
    assert all(item["available"] and item["free_tier_eligible"] for item in models)
    assert len(calls) == 3
    free_models.mark_model_unavailable("gemini-3.8-flash")
    assert not (await free_models.get_free_models())[0]["available"]
    assert len(calls) == 3
    await free_models.get_free_models(refresh=True)
    assert len(calls) == 6


async def test_invalid_model_listing_key_is_not_replaced_with_a_guessed_catalog(monkeypatch):
    monkeypatch.setattr(config, "gemini_api_key", "test-only")
    original_client = httpx.AsyncClient

    def respond(request):
        return (
            httpx.Response(200, text=pricing_section("gemini-3.8-flash"))
            if str(request.url) == free_models.PRICING_URL
            else httpx.Response(403)
        )

    monkeypatch.setattr(
        free_models.httpx, "AsyncClient", lambda **_: original_client(transport=httpx.MockTransport(respond))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await free_models.get_free_models()
    assert free_models._catalog == []


def wrapped_error(code):
    try:
        raise ClientError(
            code,
            {"error": {"code": code, "message": "Private provider details", "status": "RESOURCE_EXHAUSTED"}},
        )
    except ClientError as original:
        error = RuntimeError("SDK wrapper")
        error.__cause__ = original
        return error


@pytest.mark.parametrize("code", [404, 429, 503])
async def test_unavailable_or_quota_exhausted_models_fall_back_and_notify(code):
    calls, notices = [], []

    async def operation(model):
        calls.append(model)
        if model == "gemini-first":
            raise wrapped_error(code)
        return "grounded result"

    plan = {"models": ["gemini-first", "gemini-second"], "unavailable": []}
    assert (
        await call_with_free_fallback(plan, operation, lambda *notice: notices.append(notice))
        == "grounded result"
    )
    assert calls == ["gemini-first", "gemini-second"]
    assert notices[0][:2] == ("gemini-first", "gemini-second")
    assert plan["active"] == "gemini-second"
    assert ("gemini-first" in free_models._cooldowns) is (code != 503)


@pytest.mark.parametrize("code", [400, 401, 403])
async def test_invalid_key_or_request_is_not_hidden_by_fallback(code):
    calls = []

    async def operation(model):
        calls.append(model)
        raise wrapped_error(code)

    with pytest.raises(RuntimeError, match="SDK wrapper"):
        await call_with_free_fallback(
            {"models": ["gemini-one", "gemini-two"], "unavailable": []}, operation, lambda *_: None
        )
    assert calls == ["gemini-one"]


async def test_exhausted_fallback_is_bounded_and_skips_previous_failures():
    calls, notices = [], []

    async def operation(model):
        calls.append(model)
        raise wrapped_error(429)

    plan = {"models": ["gemini-old", "gemini-one", "gemini-two"], "unavailable": ["gemini-old"]}
    with pytest.raises(RuntimeError, match="quota"):
        await call_with_free_fallback(plan, operation, lambda *notice: notices.append(notice))
    assert calls == ["gemini-one", "gemini-two"]
    assert notices[-1][1] is None


def test_wrapped_google_status_is_recognized():
    error = wrapped_error(429)
    assert service_status(error) == 429
    assert is_model_unavailable(error)


def test_httpx_authentication_error_is_reported_without_credentials():
    response = httpx.Response(401, request=httpx.Request("GET", "https://example.org"))
    error = httpx.HTTPStatusError("secret-key-and-provider-body", request=response.request, response=response)
    assert service_status(error) == 401
    assert not is_model_unavailable(error)
    assert "HTTP 401" in safe_service_error(error)
    assert "secret" not in safe_service_error(error)


def test_wrapped_timeout_preserves_the_actual_failure():
    original = httpx.ReadTimeout("private provider details")
    error = RuntimeError("wrapper")
    error.__cause__ = original
    assert is_model_unavailable(error)
    assert "timed out" in safe_service_error(error)


async def test_transient_failure_retries_then_can_serve_the_next_workflow_step():
    calls, notices = [], []
    plan = {"models": ["gemini-only"], "unavailable": []}

    async def failing(model):
        calls.append(model)
        raise TimeoutError("private network details")

    with pytest.raises(RuntimeError, match="timed out") as caught:
        await call_with_free_fallback(plan, failing, lambda *notice: notices.append(notice))
    assert calls == ["gemini-only", "gemini-only"]
    assert plan["unavailable"] == []
    assert free_models.model_availability("gemini-only")["available"]
    assert "timed out" in safe_service_error(caught.value)
    assert "private" not in safe_service_error(caught.value)

    async def succeeding(model):
        return "next request works"

    assert await call_with_free_fallback(plan, succeeding, lambda *_: None) == "next request works"


async def test_incomplete_answer_does_not_disable_a_model_for_other_requests():
    plan = {"models": ["gemini-only"], "unavailable": []}

    async def incomplete(model):
        raise IncompleteAnswer("empty answer")

    with pytest.raises(RuntimeError, match="incomplete answer"):
        await call_with_free_fallback(plan, incomplete, lambda *_: None)
    assert plan["unavailable"] == []
    assert free_models.model_availability("gemini-only")["available"]


async def test_concurrent_success_is_not_poisoned_by_another_request_failure():
    started, failed = asyncio.Event(), asyncio.Event()
    plan = {"models": ["gemini-only"], "unavailable": []}

    async def succeeds(model):
        started.set()
        await failed.wait()
        return "graded correctly"

    async def fails(model):
        await started.wait()
        raise IncompleteAnswer("empty")

    success = asyncio.create_task(call_with_free_fallback(plan, succeeds, lambda *_: None))
    with pytest.raises(RuntimeError):
        await call_with_free_fallback(plan, fails, lambda *_: None)
    failed.set()
    assert await success == "graded correctly"
    assert plan["active"] == "gemini-only"
    assert plan["unavailable"] == []


async def test_quota_failure_remains_actionable_in_later_workflow_steps():
    plan = {"models": ["gemini-only"], "unavailable": []}
    calls = []

    async def failing(model):
        calls.append(model)
        raise wrapped_error(429)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="HTTP 429"):
            await call_with_free_fallback(plan, failing, lambda *_: None)
    assert calls == ["gemini-only"]


def test_cooldowns_expire_and_do_not_follow_a_replacement_key(monkeypatch):
    monkeypatch.setattr(config, "gemini_api_key", "old-test-key")
    free_models.mark_model_unavailable("gemini-only", 60)
    assert not free_models.model_availability("gemini-only")["available"]
    monkeypatch.setattr(config, "gemini_api_key", "new-test-key")
    assert free_models.model_availability("gemini-only")["available"]
    free_models.mark_model_unavailable("gemini-only", -1)
    assert free_models.model_availability("gemini-only")["available"]


async def test_slow_model_switches_to_an_alternative_without_repeating_the_timeout():
    calls = []

    async def operation(model):
        calls.append(model)
        if model == "gemini-slow":
            raise TimeoutError("private")
        return "answer"

    plan = {"models": ["gemini-slow", "gemini-fast"], "unavailable": []}
    assert await call_with_free_fallback(plan, operation, lambda *_: None) == "answer"
    assert calls == ["gemini-slow", "gemini-fast"]


async def test_distinct_pass_is_exhaustive_but_retry_budget_is_bounded(monkeypatch):
    monkeypatch.setattr(config, "gemini_max_model_attempts", 3)
    calls, notices = [], []

    async def operation(model):
        calls.append(model)
        raise wrapped_error(503)

    plan = {"models": [f"gemini-{i}" for i in range(8)], "unavailable": []}
    with pytest.raises(RuntimeError, match="HTTP 503"):
        await call_with_free_fallback(plan, operation, lambda *notice: notices.append(notice))
    assert calls == [f"gemini-{i}" for i in range(8)] + ["gemini-0", "gemini-1", "gemini-2"]
    assert notices[-1][1] is None


async def test_operation_deadline_cancels_a_stalled_call_and_retains_timeout(monkeypatch):
    monkeypatch.setattr(config, "gemini_operation_timeout_seconds", 0.02)
    calls, cancelled = [], asyncio.Event()

    async def stalled(model):
        calls.append(model)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    plan = {"models": ["gemini-stalled", "gemini-next"], "unavailable": []}
    with pytest.raises(RuntimeError, match="timed out"):
        await call_with_free_fallback(plan, stalled, lambda *_: None)
    # Windows timer granularity may consume the whole 20ms budget on the first call.
    assert calls[0] == "gemini-stalled"
    assert len(calls) == len(set(calls)) <= 2
    assert cancelled.is_set()
