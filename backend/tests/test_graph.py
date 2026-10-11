import json
import asyncio
import pytest

from langchain_core.messages import AIMessageChunk

from app.agents.graph import build_graph, evidence_route, validation_route
from app.agents.nodes import citation_errors
from app.agents.state import AnswerValidation, EvidenceAssessment, RelevanceGrade, RewrittenQuery

SETTINGS = {
    "model": "test/model",
    "relevance_threshold": 0.5,
    "validate_answer": True,
    "max_retries": 1,
    "retrieval_count": 6,
}


def mock_ai(monkeypatch, *, score=0.9, sufficient=True, valid=True, answer=None):
    async def structured(model, schema, instruction, data):
        if schema is RelevanceGrade:
            return schema(score=score, reason="Contains supporting facts")
        if schema is EvidenceAssessment:
            return schema(
                sufficient=sufficient,
                reason="Evidence coverage checked",
                missing_information="" if sufficient else "Recent data",
            )
        if schema is RewrittenQuery:
            return schema(query="astronomy stars current research")
        if schema is AnswerValidation:
            return schema(grounded=valid, reason="Checked support")
        raise AssertionError("Unexpected schema")

    class FakeModel:
        async def astream(self, messages):
            data = json.loads(messages[-1].content)
            text = answer or f"Stars are studied in astronomy [{data['evidence'][0]['id']}]."
            for part in [text[:12], text[12:]]:
                yield AIMessageChunk(content=part)

    monkeypatch.setattr("app.agents.nodes.structured_call", structured)
    monkeypatch.setattr("app.agents.nodes.create_llm", lambda model: FakeModel())


async def run_graph(vectors, settings=None, model_plan=None):
    return [
        part["data"]
        async for part in build_graph(vectors).astream(
            {
                "question": "What is astronomy?",
                "workspace_id": "test_workspace",
                "settings": settings or SETTINGS,
                "history": [],
                "sources": [],
                "warnings": [],
                "attempts": 0,
                "model_plan": model_plan,
            },
            stream_mode="custom",
            version="v2",
        )
    ]


def seed(vectors):
    vectors.index(
        "test_workspace", "doc", "space.txt", [{"text": "Astronomy studies stars", "page": 1}], "v1"
    )


async def test_grading_runs_concurrently_with_a_limit_of_three(vectors, monkeypatch):
    import app.agents.nodes as nodes

    vectors.index(
        "test_workspace",
        "many",
        "evidence.txt",
        [{"text": f"Astronomy evidence number {i}", "page": 0} for i in range(6)],
        "v1",
    )
    mock_ai(monkeypatch)
    original = nodes.structured_call
    active, peak = 0, 0
    gate = asyncio.Event()

    async def tracked(model, schema, instruction, data):
        nonlocal active, peak
        if schema is not RelevanceGrade:
            return await original(model, schema, instruction, data)
        active += 1
        peak = max(peak, active)
        if active == 3:
            gate.set()
        await asyncio.wait_for(gate.wait(), timeout=2)
        await asyncio.sleep(0)
        try:
            return await original(model, schema, instruction, data)
        finally:
            active -= 1

    monkeypatch.setattr(nodes, "structured_call", tracked)
    events = await run_graph(vectors)
    assert peak == 3
    grades = [event["source"] for event in events if event["type"] == "grade"]
    assert len(grades) == 6
    assert {source["id"] for source in grades} == {f"D{i}" for i in range(1, 7)}
    assert events[-1]["valid"]


async def test_sufficient_document_route_and_real_tokens(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch)
    events = await run_graph(vectors)
    names = [event["node"] for event in events if event["type"] == "node_start"]
    assert names == ["retrieve", "grade", "assess", "generate", "validate", "finalize"]
    assert len([event for event in events if event["type"] == "token"]) == 2
    assert events[-1]["sources"][0]["id"] == "D1"
    assert events[-1]["valid"] is True


async def test_gemini_fallback_replaces_partial_stream_and_accepts_text_blocks(vectors, monkeypatch):
    from google.genai.errors import ClientError

    seed(vectors)
    mock_ai(monkeypatch)

    class GeminiStream:
        def __init__(self, model):
            self.model = model

        async def astream(self, messages):
            if self.model == "gemini-first":
                yield AIMessageChunk(content="Partial draft to discard")
                raise ClientError(
                    429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota"}}
                )
            yield AIMessageChunk(
                content=[
                    {
                        "type": "text",
                        "text": "Astronomy studies stars [D1].",
                        "extras": {"signature": "not-visible"},
                    }
                ]
            )

    monkeypatch.setattr("app.agents.nodes.create_llm", GeminiStream)
    events = await run_graph(
        vectors, model_plan={"models": ["gemini-first", "gemini-second"], "unavailable": []}
    )
    assert events[-1]["answer"] == "Astronomy studies stars [D1]."
    fallback = next(event for event in events if event["type"] == "model_fallback")
    assert fallback["model"] == "gemini-second"
    assert "quota" in fallback["message"]
    resets = [event for event in events if event["type"] == "answer_reset" and "model" in event]
    assert [event["model"] for event in resets] == ["gemini-first", "gemini-second"]


@pytest.mark.parametrize("failure", ["MAX_TOKENS", "empty"])
async def test_incomplete_gemini_answer_uses_next_model(vectors, monkeypatch, failure):
    seed(vectors)
    mock_ai(monkeypatch)

    class GeminiStream:
        def __init__(self, model):
            self.model = model

        async def astream(self, messages):
            if self.model == "gemini-first":
                if failure == "MAX_TOKENS":
                    yield AIMessageChunk(
                        content="Truncated draft", response_metadata={"finish_reason": "MAX_TOKENS"}
                    )
                return
            yield AIMessageChunk(content="Astronomy studies stars [D1].")

    monkeypatch.setattr("app.agents.nodes.create_llm", GeminiStream)
    events = await run_graph(
        vectors, model_plan={"models": ["gemini-first", "gemini-second"], "unavailable": []}
    )
    assert events[-1]["answer"] == "Astronomy studies stars [D1]."
    assert next(event for event in events if event["type"] == "model_fallback")["model"] == "gemini-second"


async def test_relevant_but_insufficient_routes_to_web(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, sufficient=False)

    async def search(query):
        assert query == "astronomy stars current research"
        return [
            {
                "id": "W1",
                "kind": "web",
                "name": "Research",
                "url": "https://example.org",
                "text": "More evidence",
            }
        ]

    monkeypatch.setattr("app.agents.nodes.search_web", search)
    events = await run_graph(vectors)
    assert any(event.get("node") == "web_search" for event in events)
    assert next(event for event in events if event["type"] == "decision")["route"] == "web"
    assert events[-1]["valid"]


async def test_low_grades_excluded_from_generation(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, score=0.2)

    async def search(query):
        return [
            {
                "id": "W1",
                "kind": "web",
                "name": "Research",
                "url": "https://example.org",
                "text": "Astronomy studies stars",
            }
        ]

    monkeypatch.setattr("app.agents.nodes.search_web", search)
    events = await run_graph(vectors)
    assert events[-1]["sources"][0]["id"] == "W1"
    assert not next(event for event in events if event["type"] == "grade")["source"]["accepted"]


async def test_web_failure_abstains_without_fabricating(vectors, monkeypatch):
    mock_ai(monkeypatch)

    async def fail(query):
        raise RuntimeError("private provider details")

    monkeypatch.setattr("app.agents.nodes.search_web", fail)
    events = await run_graph(vectors)
    assert "could not find usable evidence" in events[-1]["answer"]
    assert any("Web search failed" in warning for warning in events[-1]["warnings"])
    assert "private provider details" not in str(events)


async def test_invalid_citation_bounded_retry(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, answer="An invented claim [D99].")
    events = await run_graph(vectors)
    assert (
        len([event for event in events if event.get("node") == "generate" and event["type"] == "node_start"])
        == 2
    )
    assert not events[-1]["valid"]
    assert "D99" not in events[-1]["answer"]
    assert events[-1]["sources"] == []


async def test_semantic_validation_failure_is_not_approved(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, valid=False)
    events = await run_graph(vectors, {**SETTINGS, "max_retries": 0})
    assert not events[-1]["valid"]


async def test_optional_validation_still_enforces_citations(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, answer="Uncited assertion")
    events = await run_graph(vectors, {**SETTINGS, "validate_answer": False, "max_retries": 0})
    assert not events[-1]["valid"]


def test_routing_and_citation_membership():
    assert evidence_route({"assessment": {"sufficient": True}}) == "generate"
    assert evidence_route({"assessment": {"sufficient": False}}) == "rewrite"
    assert validation_route({"valid": False, "attempts": 1, "settings": {"max_retries": 1}}) == "generate"
    assert validation_route({"valid": False, "attempts": 2, "settings": {"max_retries": 1}}) == "finalize"
    assert citation_errors("Facts [D1] and [W1]", [{"id": "D1"}, {"id": "W1"}]) == []
    assert citation_errors("Facts [D2]", [{"id": "D1"}])


async def test_relevance_threshold_boundary(vectors, monkeypatch):
    seed(vectors)
    mock_ai(monkeypatch, score=0.5)
    events = await run_graph(vectors)
    assert next(event for event in events if event["type"] == "grade")["source"]["accepted"]
