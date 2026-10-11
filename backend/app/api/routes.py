import asyncio
import json
import shutil
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select

from app.core.config import config
from app.core.auth import authorize_request, require_workspace_owner
from app.models.database import (
    AppSettings,
    Conversation,
    Document,
    Message,
    WorkflowRun,
    Workspace,
    as_dict,
    new_id,
)
from app.services.ai import safe_service_error
from app.services.free_models import get_free_models
from app.services.documents import extract_text, index_document, upload_document

router = APIRouter(prefix="/api", dependencies=[Depends(authorize_request)])


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        if not value.strip():
            raise ValueError("Name must contain text.")
        return value.strip()


class ChatInput(BaseModel):
    workspace_id: str
    conversation_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)
    regenerate: bool = False
    model: str = Field(default="auto", min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_./:~\-]+$")
    relevance_threshold: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False,
        description="Minimum per-document-chunk relevance score. Omit to use the internal default.",
    )

    @field_validator("question")
    @classmethod
    def trim_question(cls, value):
        if not value.strip():
            raise ValueError("Question must contain text.")
        return value.strip()


def require_record(db, table, record_id):
    record = db.get(table, record_id)
    if record is None:
        raise HTTPException(404, "Record not found.")
    return record


def document_summary(document):
    result = as_dict(document)
    result.pop("text")
    result.pop("content_hash")
    return result


def ensure_workspace_idle(request, workspace_id):
    if workspace_id in request.app.state.active_workspaces.values():
        raise HTTPException(409, "Wait for this workspace's active answer before changing its documents.")


@router.get("/health")
def health(request: Request):
    with request.app.state.db() as db:
        db.execute(select(1))
    return {
        "status": "ok",
        "gemini_configured": bool(config.gemini_api_key),
        "tavily_configured": bool(config.tavily_api_key),
        "embedding_model": config.embedding_model,
        "embeddings_loaded": request.app.state.vectors.model is not None,
        "max_upload_mb": config.max_upload_mb,
        "single_user": False,
        "authentication": "clerk",
        "clerk_configured": bool(config.clerk_secret_key or config.clerk_jwt_key),
    }


@router.get("/workspaces")
def list_workspaces(request: Request):
    with request.app.state.db() as db:
        rows = db.scalars(
            select(Workspace)
            .where(Workspace.owner_id == request.state.user_id)
            .order_by(Workspace.created_at)
        )
        result = []
        for row in rows:
            counts = db.execute(
                select(func.count(Document.id), func.coalesce(func.sum(Document.chunk_count), 0)).where(
                    Document.workspace_id == row.id
                )
            ).one()
            chats = db.scalar(select(func.count(Conversation.id)).where(Conversation.workspace_id == row.id))
            result.append(
                {
                    **as_dict(row),
                    "document_count": counts[0],
                    "chunk_count": counts[1],
                    "conversation_count": chats,
                }
            )
        return result


@router.post("/workspaces", status_code=201)
def create_workspace(data: WorkspaceInput, request: Request):
    with request.app.state.db() as db:
        workspace = Workspace(name=data.name, owner_id=request.state.user_id)
        db.add(workspace)
        db.commit()
        return as_dict(workspace)


@router.patch("/workspaces/{workspace_id}")
def rename_workspace(workspace_id: str, data: WorkspaceInput, request: Request):
    with request.app.state.db() as db:
        workspace = require_record(db, Workspace, workspace_id)
        workspace.name = data.name
        db.commit()
        return as_dict(workspace)


@router.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str, request: Request):
    with request.app.state.mutation_lock, request.app.state.vectors.lock, request.app.state.db() as db:
        ensure_workspace_idle(request, workspace_id)
        workspace = require_record(db, Workspace, workspace_id)
        request.app.state.vectors.delete_workspace(workspace_id)
        folder = config.data_dir / "uploads" / workspace_id
        if folder.exists():
            shutil.rmtree(folder)
        db.delete(workspace)
        db.commit()


@router.get("/workspaces/{workspace_id}/documents")
def list_documents(workspace_id: str, request: Request, search: str = ""):
    with request.app.state.db() as db:
        require_record(db, Workspace, workspace_id)
        rows = db.scalars(
            select(Document).where(Document.workspace_id == workspace_id).order_by(Document.created_at.desc())
        )
        return [document_summary(row) for row in rows if search.lower() in row.name.lower()]


@router.post("/workspaces/{workspace_id}/documents", status_code=201)
def upload_documents(workspace_id: str, request: Request, files: list[UploadFile]):
    if not 1 <= len(files) <= 10:
        raise HTTPException(422, "Upload between 1 and 10 files per request.")
    results = []
    with request.app.state.mutation_lock, request.app.state.vectors.lock, request.app.state.db() as db:
        ensure_workspace_idle(request, workspace_id)
        require_record(db, Workspace, workspace_id)
        for file in files:
            try:
                content = file.file.read(config.max_upload_mb * 1024 * 1024 + 1)
                if not content:
                    raise ValueError("Empty files cannot be indexed.")
                if len(content) > config.max_upload_mb * 1024 * 1024:
                    raise ValueError(f"File exceeds {config.max_upload_mb} MB.")
                document, duplicate = upload_document(
                    db,
                    request.app.state.vectors,
                    config.data_dir,
                    workspace_id,
                    file.filename or "file",
                    content,
                )
                results.append({"document": document_summary(document), "duplicate": duplicate})
            except ValueError as error:
                results.append({"name": file.filename, "error": str(error)})
            finally:
                file.file.close()
    return results


@router.get("/workspaces/{workspace_id}/documents/{document_id}")
def preview_document(workspace_id: str, document_id: str, request: Request):
    with request.app.state.db() as db:
        document = owned_document(db, workspace_id, document_id)
        return {
            **document_summary(document),
            "text": document.text[:100_000],
            "preview_truncated": len(document.text) > 100_000,
        }


def owned_document(db, workspace_id, document_id):
    document = require_record(db, Document, document_id)
    if document.workspace_id != workspace_id:
        raise HTTPException(404, "Document not found in this workspace.")
    return document


@router.get("/workspaces/{workspace_id}/documents/{document_id}/file")
def original_document(workspace_id: str, document_id: str, request: Request):
    with request.app.state.db() as db:
        document = owned_document(db, workspace_id, document_id)
        path = config.data_dir / "uploads" / workspace_id / document.id
        if not path.is_file():
            raise HTTPException(404, "Original file is unavailable.")
        return FileResponse(path, filename=document.name, media_type="application/octet-stream")


@router.post("/workspaces/{workspace_id}/documents/{document_id}/reindex")
def reindex_document(workspace_id: str, document_id: str, request: Request):
    with request.app.state.mutation_lock, request.app.state.vectors.lock, request.app.state.db() as db:
        ensure_workspace_idle(request, workspace_id)
        document = owned_document(db, workspace_id, document_id)
        path = config.data_dir / "uploads" / workspace_id / document.id
        if not path.is_file():
            raise HTTPException(404, "Original file is unavailable; upload it again.")
        try:
            segments = extract_text(path.read_bytes(), Path(document.name).suffix.lower())
            index_document(db, request.app.state.vectors, document, segments)
        except Exception as error:
            document.error = (
                "Reindexing failed. Any previous index is preserved. Check local model and disk access."
            )
            db.commit()
            raise HTTPException(503, document.error) from error
        return document_summary(document)


@router.delete("/workspaces/{workspace_id}/documents/{document_id}", status_code=204)
def delete_document(workspace_id: str, document_id: str, request: Request):
    with request.app.state.mutation_lock, request.app.state.vectors.lock, request.app.state.db() as db:
        ensure_workspace_idle(request, workspace_id)
        document = owned_document(db, workspace_id, document_id)
        request.app.state.vectors.delete_document(workspace_id, document_id)
        (config.data_dir / "uploads" / workspace_id / document.id).unlink(missing_ok=True)
        db.delete(document)
        db.commit()


@router.get("/models")
async def list_models(refresh: bool = False):
    try:
        return await get_free_models(refresh=True) if refresh else await get_free_models()
    except Exception as error:
        raise HTTPException(
            503,
            "Could not load free-tier Gemini models. Check GEMINI_API_KEY, network access, and AI Studio model access.",
        ) from error


@router.get("/workspaces/{workspace_id}/conversations")
def list_conversations(workspace_id: str, request: Request):
    with request.app.state.db() as db:
        require_record(db, Workspace, workspace_id)
        return [
            as_dict(row)
            for row in db.scalars(
                select(Conversation)
                .where(Conversation.workspace_id == workspace_id)
                .order_by(Conversation.created_at.desc())
            )
        ]


@router.get("/workspaces/{workspace_id}/conversations/{conversation_id}")
def get_conversation(workspace_id: str, conversation_id: str, request: Request):
    with request.app.state.db() as db:
        conversation = require_record(db, Conversation, conversation_id)
        if conversation.workspace_id != workspace_id:
            raise HTTPException(404, "Conversation not found in this workspace.")
        messages = db.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        )
        return {**as_dict(conversation), "messages": [as_dict(message) for message in messages]}


@router.delete("/workspaces/{workspace_id}/conversations/{conversation_id}", status_code=204)
def delete_conversation(workspace_id: str, conversation_id: str, request: Request):
    with request.app.state.mutation_lock, request.app.state.db() as db:
        if conversation_id in request.app.state.active_workspaces:
            raise HTTPException(409, "This conversation has an active answer.")
        conversation = require_record(db, Conversation, conversation_id)
        if conversation.workspace_id != workspace_id:
            raise HTTPException(404, "Conversation not found in this workspace.")
        db.delete(conversation)
        db.commit()


@router.get("/workspaces/{workspace_id}/workflows")
def list_runs(workspace_id: str, request: Request):
    with request.app.state.db() as db:
        require_record(db, Workspace, workspace_id)
        rows = db.scalars(
            select(WorkflowRun)
            .join(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(50)
        )
        return [as_dict(row) for row in rows]


@router.get("/workspaces/{workspace_id}/workflows/{run_id}")
def get_run(workspace_id: str, run_id: str, request: Request):
    with request.app.state.db() as db:
        row = require_record(db, WorkflowRun, run_id)
        conversation = require_record(db, Conversation, row.conversation_id)
        if conversation.workspace_id != workspace_id:
            raise HTTPException(404, "Workflow not found in this workspace.")
        return as_dict(row)


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def resolve_chat_models(data: ChatInput, request: Request):
    with request.app.state.db() as db:
        require_workspace_owner(db, data.workspace_id, request.state.user_id)
    if not config.gemini_api_key:
        raise HTTPException(503, "Add GEMINI_API_KEY to backend/.env and restart the backend.")
    try:
        catalog = await get_free_models()
    except Exception as error:
        raise HTTPException(503, "Could not verify free models. Please try again shortly.") from error
    by_id = {item["id"] for item in catalog}
    available = [item for item in catalog if item.get("available", True)]
    if not available:
        raise HTTPException(
            503,
            "All eligible Gemini models are temporarily unavailable or out of quota. Wait and refresh the model list.",
        )
    notice = None
    if data.model not in by_id:
        if data.model != "auto" and not data.model.startswith("gemini-"):
            raise HTTPException(
                422,
                "Only Gemini models verified as free-tier eligible and accessible to this key can be selected. Refresh the model list.",
            )
        if data.model != "auto":
            notice = f"{data.model} is no longer in the verified free-tier Gemini catalog. Using {available[0]['id']}."
    available_ids = {item["id"] for item in available}
    if data.model in by_id and data.model not in available_ids:
        notice = f"{data.model} is in cooldown after a quota or service failure. Using {available[0]['id']}."
    models = ([data.model] if data.model in available_ids else []) + [
        item["id"] for item in available if item["id"] != data.model
    ]
    return {"models": models, "notice": notice}


@router.post("/chat/stream")
def chat_stream(data: ChatInput, request: Request, selection: dict = Depends(resolve_chat_models)):
    # This reservation prevents overlapping requests from corrupting a conversation.
    with request.app.state.mutation_lock, request.app.state.db() as db:
        require_record(db, Workspace, data.workspace_id)
        if data.conversation_id:
            conversation = require_record(db, Conversation, data.conversation_id)
            if conversation.workspace_id != data.workspace_id:
                raise HTTPException(404, "Conversation not found in this workspace.")
        else:
            if data.regenerate:
                raise HTTPException(422, "Regeneration requires an existing conversation.")
            conversation = Conversation(id=new_id(), workspace_id=data.workspace_id, title=data.question[:80])
            db.add(conversation)
            db.flush()
        if conversation.id in request.app.state.active_workspaces:
            raise HTTPException(409, "An answer is already running in this conversation.")
        rows = list(
            db.scalars(
                select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)
            )
        )
        replaced_ids = []
        if data.regenerate:
            last_user = next((message for message in reversed(rows) if message.role == "user"), None)
            if not last_user or last_user.content != data.question:
                raise HTTPException(422, "Only the most recent question can be regenerated.")
            history_rows = rows[: rows.index(last_user)]
            replaced_ids = [message.id for message in rows[rows.index(last_user) + 1 :]]
        else:
            history_rows = rows
            db.add(Message(conversation_id=conversation.id, role="user", content=data.question))
        # Bound history by both count and characters to avoid oversized prompts.
        history = []
        remaining = 12_000
        for row in reversed(history_rows[-10:]):
            if len(row.content) > remaining:
                break
            history.insert(0, {"role": row.role, "content": row.content})
            remaining -= len(row.content)
        settings = as_dict(db.get(AppSettings, 1))
        settings["model"] = selection["models"][0]
        if data.relevance_threshold is not None:
            settings["relevance_threshold"] = data.relevance_threshold
        settings["validate_answer"] = True
        run = WorkflowRun(id=new_id(), conversation_id=conversation.id)
        db.add(run)
        db.commit()
        conversation_id, run_id = conversation.id, run.id
        request.app.state.active_workspaces[conversation_id] = data.workspace_id

    async def events():
        started = perf_counter()
        trace = []
        status, error_text = "cancelled", None
        iterator = request.app.state.graph.astream(
            {
                "question": data.question,
                "workspace_id": data.workspace_id,
                "history": history,
                "settings": settings,
                "sources": [],
                "warnings": [],
                "attempts": 0,
                "model_plan": {
                    "models": selection["models"],
                    "unavailable": [],
                    "notice": selection["notice"],
                },
            },
            stream_mode="custom",
            config={"recursion_limit": 30},
            version="v2",
        ).__aiter__()
        pending = None
        try:
            yield sse({"type": "start", "conversation_id": conversation_id, "run_id": run_id})
            while True:
                if pending is None:
                    pending = asyncio.create_task(anext(iterator))
                completed, _ = await asyncio.wait({pending}, timeout=15)
                if not completed:
                    yield ": heartbeat\n\n"
                    continue
                try:
                    part = pending.result()
                except StopAsyncIteration:
                    break
                pending = None
                payload = part["data"]
                payload["elapsed_ms"] = round((perf_counter() - started) * 1000)
                if payload["type"] != "token":
                    trace.append(payload)
                    with request.app.state.db() as db:
                        record = db.get(WorkflowRun, run_id)
                        record.events = list(trace)
                        db.commit()
                if payload["type"] == "final":
                    with request.app.state.db() as db:
                        if replaced_ids:
                            db.execute(delete(Message).where(Message.id.in_(replaced_ids)))
                        message = Message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=payload["answer"],
                            sources=payload["sources"],
                            run_id=run_id,
                        )
                        db.add(message)
                        db.commit()
                        payload["message"] = as_dict(message)
                    status = "completed" if payload["valid"] else "validation_failed"
                yield sse(payload)
            if status == "cancelled":
                raise RuntimeError("Workflow ended without a final answer.")
            yield sse(
                {
                    "type": "done",
                    "run_id": run_id,
                    "status": status,
                    "duration_ms": round((perf_counter() - started) * 1000),
                }
            )
        except asyncio.CancelledError:
            error_text = "Request disconnected or stopped. The incomplete answer was not saved."
            raise
        except Exception as error:
            status = "failed"
            error_text = safe_service_error(error)
            trace.append({"type": "error", "message": error_text})
            yield sse({"type": "error", "message": error_text, "run_id": run_id})
        finally:
            if pending and not pending.done():
                pending.cancel()
                try:
                    await pending
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
            await iterator.aclose()
            with request.app.state.mutation_lock, request.app.state.db() as db:
                record = db.get(WorkflowRun, run_id)
                if record:
                    record.status = status
                    record.error = error_text
                    record.events = list(trace)
                    record.duration_ms = round((perf_counter() - started) * 1000)
                    db.commit()
                request.app.state.active_workspaces.pop(conversation_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
