from contextlib import asynccontextmanager
import logging
from threading import RLock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.agents.graph import build_graph
from app.api.routes import router
from app.core.config import config
from app.models.database import AppSettings, WorkflowRun, create_database
from app.services.vector import VectorStore


@asynccontextmanager
async def lifespan(app):
    engine, db_factory = create_database(config.data_dir)
    app.state.db = db_factory
    app.state.vectors = VectorStore(config.data_dir, config.embedding_model)
    app.state.graph = build_graph(app.state.vectors)
    app.state.mutation_lock = RLock()
    app.state.active_workspaces = {}
    with db_factory() as db:
        if db.get(AppSettings, 1) is None:
            db.add(AppSettings(id=1, model=config.gemini_model))
        # A process restart cannot resume a provider stream; mark interrupted runs honestly.
        for run in db.scalars(select(WorkflowRun).where(WorkflowRun.status == "running")):
            run.status = "interrupted"
            run.error = "Backend restarted before this answer completed. Regenerate the question."
        db.commit()
    yield
    engine.dispose()


app = FastAPI(title="Aether Research", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list({config.frontend_origin, config.frontend_origin.replace("localhost", "127.0.0.1")}),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(router)


@app.middleware("http")
async def protect_local_writes(request: Request, call_next):
    """Reject writes from unrelated browser origins; this is not user authentication."""
    origin = request.headers.get("origin")
    allowed = {config.frontend_origin, config.frontend_origin.replace("localhost", "127.0.0.1")}
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin not in allowed:
        return JSONResponse(
            status_code=403, content={"detail": "This browser origin is not allowed to change local data."}
        )
    return await call_next(request)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    # Return a safe message; no keys, provider bodies, or server paths are exposed.
    logging.getLogger("aether").error(
        "Unhandled %s during %s %s", type(error).__name__, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Check the backend terminal."},
    )
